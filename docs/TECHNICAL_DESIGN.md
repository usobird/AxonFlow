# AutoFlow 技术实现方案

> 版本: v1.0  
> 日期: 2026-03-31  
> 状态: 草案  

---

## 1. 技术选型总览

| 维度 | 选型 | 理由 |
|------|------|------|
| 编程语言 | Python 3.11+ | AI/LLM 生态成熟，asyncio 异步支持好 |
| 异步框架 | asyncio + aiohttp | 原生协程支持，适合 I/O 密集型 Agent 场景 |
| 消息队列 | Redis Streams | 轻量级、持久化、消费者组支持，部署简单 |
| LLM 集成 | LiteLLM | 统一接口适配 100+ LLM Provider |
| 配置管理 | Pydantic + PyYAML | 类型安全的配置解析与校验 |
| CLI 框架 | Click / Typer | 声明式 CLI 构建，自动生成帮助文档 |
| 日志系统 | structlog | 结构化日志，便于机器解析和检索 |
| 进程管理 | systemd / supervisord | 守护进程管理与自动重启 |
| 测试框架 | pytest + pytest-asyncio | 异步测试支持好 |
| 包管理 | uv / poetry | 现代 Python 依赖管理 |

---

## 2. 系统架构

### 2.1 整体架构图

```
┌─────────────────────────────────────────────────────────────┐
│                        AutoFlow Engine                       │
│                                                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐    │
│  │ Agent A  │  │ Agent B  │  │ Agent C  │  │ Agent N  │    │
│  │ (Coder)  │  │ (Tester) │  │(Publisher)│  │  (...)   │    │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘    │
│       │              │              │              │          │
│  ┌────▼──────────────▼──────────────▼──────────────▼─────┐   │
│  │              Message Bus (Redis Streams)               │   │
│  └────┬──────────────┬──────────────┬──────────────┬─────┘   │
│       │              │              │              │          │
│  ┌────▼─────┐  ┌─────▼────┐  ┌─────▼────┐  ┌─────▼────┐   │
│  │Workflow  │  │  Tool    │  │   LLM    │  │  State   │   │
│  │Orchestr. │  │ Registry │  │ Gateway  │  │  Store   │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              Observability Layer                       │   │
│  │  (Structured Logs / Metrics / Trace / Dashboard)      │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              CLI Interface (Typer)                     │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 核心分层

```
┌─────────────────┐
│   Interface      │  CLI / API / Dashboard
├─────────────────┤
│   Orchestration  │  Workflow Engine / Scheduler / Cron
├─────────────────┤
│   Agent          │  Agent Runtime / LLM Integration / Tool Execution
├─────────────────┤
│   Messaging      │  Message Bus / Protocol / Serialization
├─────────────────┤
│   Infrastructure │  Redis / Storage / Config / Logging
└─────────────────┘
```

---

## 3. 核心模块设计

### 3.1 Agent 运行时 (Agent Runtime)

每个 Agent 是一个独立的异步任务（asyncio.Task），持续监听自己的消息队列。

```python
# 核心 Agent 基类设计
class BaseAgent(ABC):
    """智能体基类"""

    def __init__(self, config: AgentConfig):
        self.id: str = config.id
        self.name: str = config.name
        self.role: str = config.role
        self.model: ModelConfig = config.model
        self.tools: list[Tool] = []
        self.message_bus: MessageBus = None
        self.state: AgentState = AgentState.IDLE

    async def start(self):
        """启动 Agent，开始监听消息队列"""
        self.state = AgentState.RUNNING
        while self.state == AgentState.RUNNING:
            message = await self.message_bus.receive(self.id)
            if message:
                self.state = AgentState.WORKING
                try:
                    result = await self.handle_message(message)
                    await self._send_response(message, result)
                except Exception as e:
                    await self._handle_error(message, e)
                finally:
                    self.state = AgentState.RUNNING

    async def handle_message(self, message: Message) -> AgentResult:
        """处理消息的核心逻辑"""
        # 1. 构建 Prompt（系统提示 + 上下文 + 用户消息）
        prompt = self._build_prompt(message)
        # 2. 调用 LLM
        llm_response = await self.llm_client.chat(prompt)
        # 3. 解析 LLM 输出，判断是否需要调用工具
        actions = self._parse_actions(llm_response)
        # 4. 执行工具调用
        results = await self._execute_actions(actions)
        # 5. 汇总结果
        return AgentResult(output=results, status="success")

    async def send_request(self, target_agent_id: str, payload: dict):
        """向其他智能体发起请求"""
        message = Message(
            sender=self.id,
            receiver=target_agent_id,
            type=MessageType.TASK_REQUEST,
            payload=payload,
        )
        await self.message_bus.send(message)

    @abstractmethod
    async def _build_prompt(self, message: Message) -> list[dict]:
        """由子类实现具体的 Prompt 构建逻辑"""
        ...
```

**Agent 状态机：**

```
          ┌──────────────┐
          │    IDLE       │ (刚创建，未启动)
          └──────┬───────┘
                 │ start()
          ┌──────▼───────┐
     ┌───→│   RUNNING     │←──────┐
     │    │ (监听消息中)   │       │
     │    └──────┬───────┘       │
     │           │ 收到消息       │ 处理完成
     │    ┌──────▼───────┐       │
     │    │   WORKING     │───────┘
     │    │ (处理任务中)   │
     │    └──────┬───────┘
     │           │ 异常
     │    ┌──────▼───────┐
     │    │    ERROR      │
     │    └──────┬───────┘
     │           │ 恢复
     └───────────┘
```

### 3.2 消息系统 (Message Bus)

#### 3.2.1 消息协议

```python
@dataclass
class Message:
    """统一消息格式"""
    id: str                      # 消息唯一 ID (UUID)
    workflow_id: str             # 所属工作流 ID
    step_id: str                # 当前步骤 ID
    sender: str                  # 发送方 Agent ID
    receiver: str                # 接收方 Agent ID
    type: MessageType            # 消息类型
    priority: int                # 优先级 (1-10, 10 最高)
    payload: dict                # 负载数据
    context: dict                # 共享上下文引用
    created_at: datetime         # 创建时间
    ttl: int | None              # 过期时间（秒）
    parent_message_id: str | None  # 父消息 ID（用于追踪链路）

class MessageType(Enum):
    TASK_REQUEST = "task_request"     # 任务请求
    TASK_RESPONSE = "task_response"   # 任务响应
    FEEDBACK = "feedback"             # 反馈（如测试失败的详情）
    ERROR = "error"                   # 异常通知
    HEARTBEAT = "heartbeat"          # 心跳
    CONTROL = "control"              # 控制指令（暂停/恢复/终止）
```

#### 3.2.2 Redis Streams 实现

```python
class RedisMessageBus(MessageBus):
    """基于 Redis Streams 的消息总线"""

    def __init__(self, redis_url: str):
        self.redis = aioredis.from_url(redis_url)

    async def send(self, message: Message):
        """发送消息到目标 Agent 的 Stream"""
        stream_key = f"autoflow:agent:{message.receiver}:inbox"
        await self.redis.xadd(
            stream_key,
            {"data": message.to_json()},
        )

    async def receive(self, agent_id: str, block_ms: int = 5000) -> Message | None:
        """从自己的 inbox Stream 中读取消息"""
        stream_key = f"autoflow:agent:{agent_id}:inbox"
        group_name = f"agent-{agent_id}-group"
        consumer_name = f"agent-{agent_id}-consumer"

        # 使用消费者组确保消息不被重复消费
        results = await self.redis.xreadgroup(
            groupname=group_name,
            consumername=consumer_name,
            streams={stream_key: ">"},
            count=1,
            block=block_ms,
        )
        if results:
            stream, messages = results[0]
            msg_id, data = messages[0]
            message = Message.from_json(data[b"data"])
            # ACK 消息
            await self.redis.xack(stream_key, group_name, msg_id)
            return message
        return None

    async def get_queue_depth(self, agent_id: str) -> int:
        """获取指定 Agent 的消息队列深度"""
        stream_key = f"autoflow:agent:{agent_id}:inbox"
        return await self.redis.xlen(stream_key)
```

#### 3.2.3 进程内降级方案

当 Redis 不可用时，自动降级到进程内 asyncio.Queue：

```python
class InMemoryMessageBus(MessageBus):
    """进程内消息总线（开发/测试用或降级方案）"""

    def __init__(self):
        self._queues: dict[str, asyncio.Queue] = {}

    async def send(self, message: Message):
        queue = self._get_queue(message.receiver)
        await queue.put(message)

    async def receive(self, agent_id: str, block_ms: int = 5000) -> Message | None:
        queue = self._get_queue(agent_id)
        try:
            return await asyncio.wait_for(
                queue.get(), timeout=block_ms / 1000
            )
        except asyncio.TimeoutError:
            return None

    def _get_queue(self, agent_id: str) -> asyncio.Queue:
        if agent_id not in self._queues:
            self._queues[agent_id] = asyncio.Queue()
        return self._queues[agent_id]
```

### 3.3 工作流引擎 (Workflow Orchestrator)

```python
class WorkflowOrchestrator:
    """工作流编排引擎"""

    def __init__(self, config: WorkflowConfig, agent_registry: AgentRegistry):
        self.config = config
        self.agents = agent_registry
        self.state_store = StateStore()
        self.iteration_count = 0

    async def execute(self, initial_input: str) -> WorkflowResult:
        """执行工作流"""
        # 1. 初始化工作流上下文
        ctx = WorkflowContext(
            workflow_id=str(uuid4()),
            input=initial_input,
            shared_state={},
        )
        self.state_store.save(ctx)

        # 2. 向入口 Agent 发送初始任务
        entry_agent = self.config.flow.entry
        await self._dispatch(
            ctx=ctx,
            target=entry_agent,
            payload={"task": initial_input},
        )

        # 3. 事件循环：监听结果，驱动流转
        while self.iteration_count < self.config.flow.max_iterations:
            event = await self._wait_for_event(ctx)

            if self._is_terminal(event):
                return WorkflowResult(
                    status="completed",
                    output=event.payload,
                    iterations=self.iteration_count,
                )

            # 根据事件类型和工作流定义，决定下一步
            next_actions = self._resolve_next(event)
            for action in next_actions:
                await self._dispatch(ctx, action.target, action.payload)

            self.iteration_count += 1

        return WorkflowResult(
            status="max_iterations_reached",
            iterations=self.iteration_count,
        )

    def _resolve_next(self, event: WorkflowEvent) -> list[Action]:
        """根据当前事件解析下一步动作"""
        sender = event.sender
        status = event.payload.get("status")

        # 查找工作流配置中的路由规则
        routes = self.config.flow.routes.get(sender, [])
        matched = []
        for route in routes:
            if route.condition is None or route.condition.evaluate(status):
                matched.append(Action(target=route.target, payload=event.payload))
        return matched
```

**工作流上下文：**

```python
@dataclass
class WorkflowContext:
    """工作流执行上下文"""
    workflow_id: str
    input: str
    shared_state: dict            # 各 Agent 可读写的共享状态
    history: list[Message] = field(default_factory=list)  # 消息历史
    created_at: datetime = field(default_factory=datetime.now)
    iteration: int = 0

    def update_state(self, key: str, value: any):
        self.shared_state[key] = value

    def get_state(self, key: str, default=None):
        return self.shared_state.get(key, default)
```

### 3.4 LLM 网关 (LLM Gateway)

```python
class LLMGateway:
    """统一 LLM 调用网关"""

    def __init__(self, config: LLMConfig):
        self.config = config
        self.token_tracker = TokenTracker()
        self.fallback_chain = config.fallback_models or []

    async def chat(
        self,
        messages: list[dict],
        model: str | None = None,
        **kwargs
    ) -> LLMResponse:
        """统一 LLM 调用入口"""
        model = model or self.config.default_model

        # 检查 Token 预算
        if self.token_tracker.is_budget_exceeded():
            raise BudgetExceededError(
                f"Token budget exceeded: {self.token_tracker.total_tokens}"
            )

        try:
            # 使用 LiteLLM 统一调用
            response = await litellm.acompletion(
                model=model,
                messages=messages,
                **kwargs,
            )
            # 记录 Token 用量
            self.token_tracker.record(
                model=model,
                input_tokens=response.usage.prompt_tokens,
                output_tokens=response.usage.completion_tokens,
            )
            return LLMResponse(
                content=response.choices[0].message.content,
                model=model,
                usage=response.usage,
            )
        except Exception as e:
            # 尝试降级到备用模型
            return await self._fallback(messages, e, **kwargs)

    async def _fallback(self, messages, error, **kwargs) -> LLMResponse:
        """模型降级"""
        for fallback_model in self.fallback_chain:
            try:
                logger.warning(
                    "llm_fallback",
                    original_error=str(error),
                    fallback_model=fallback_model,
                )
                return await self.chat(
                    messages, model=fallback_model, **kwargs
                )
            except Exception:
                continue
        raise LLMUnavailableError("All LLM models unavailable")
```

### 3.5 工具系统 (Tool System)

```python
class ToolRegistry:
    """工具注册中心"""

    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool):
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def get_schemas(self, tool_names: list[str]) -> list[dict]:
        """获取工具的 JSON Schema（用于 LLM Function Calling）"""
        return [
            self._tools[name].to_schema()
            for name in tool_names
            if name in self._tools
        ]


class Tool(ABC):
    """工具基类"""

    name: str
    description: str
    parameters: dict  # JSON Schema

    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        """执行工具"""
        ...

    def to_schema(self) -> dict:
        """转换为 LLM Function Calling 格式"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


# 内置工具示例
class ShellExecTool(Tool):
    name = "shell_exec"
    description = "执行 Shell 命令并返回输出"
    parameters = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "要执行的 Shell 命令",
            },
            "timeout": {
                "type": "integer",
                "description": "超时时间（秒），默认 30",
                "default": 30,
            },
        },
        "required": ["command"],
    }

    async def execute(self, command: str, timeout: int = 30) -> ToolResult:
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
            return ToolResult(
                success=proc.returncode == 0,
                output=stdout.decode(),
                error=stderr.decode() if proc.returncode != 0 else None,
            )
        except asyncio.TimeoutError:
            proc.kill()
            return ToolResult(success=False, error=f"Command timed out after {timeout}s")


class FileWriteTool(Tool):
    name = "file_write"
    description = "将内容写入指定文件"
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "文件路径"},
            "content": {"type": "string", "description": "文件内容"},
        },
        "required": ["path", "content"],
    }

    async def execute(self, path: str, content: str) -> ToolResult:
        try:
            file_path = Path(path)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding="utf-8")
            return ToolResult(success=True, output=f"File written: {path}")
        except Exception as e:
            return ToolResult(success=False, error=str(e))
```

### 3.6 调度系统 (Scheduler)

```python
class Scheduler:
    """定时任务调度器"""

    def __init__(self):
        self._jobs: list[ScheduledJob] = []
        self._running = False

    def add_cron_job(
        self,
        workflow_id: str,
        cron_expr: str,
        input_data: str,
    ):
        """添加 Cron 定时任务"""
        job = ScheduledJob(
            workflow_id=workflow_id,
            cron=CronExpression(cron_expr),
            input=input_data,
        )
        self._jobs.append(job)

    async def start(self):
        """启动调度循环"""
        self._running = True
        while self._running:
            now = datetime.now()
            for job in self._jobs:
                if job.cron.should_run(now) and not job.is_running:
                    asyncio.create_task(self._execute_job(job))
            await asyncio.sleep(1)  # 每秒检查一次

    async def _execute_job(self, job: ScheduledJob):
        """执行调度任务"""
        job.is_running = True
        try:
            orchestrator = WorkflowOrchestrator(
                config=self._load_workflow(job.workflow_id),
                agent_registry=self.agent_registry,
            )
            result = await orchestrator.execute(job.input)
            logger.info("scheduled_job_completed", job=job, result=result)
        except Exception as e:
            logger.error("scheduled_job_failed", job=job, error=str(e))
        finally:
            job.is_running = False
            job.last_run = datetime.now()
```

---

## 4. 数据模型

### 4.1 配置模型

```python
# ===== 智能体配置 =====
class ModelConfig(BaseModel):
    provider: str = "openai"         # openai / anthropic / ollama
    name: str = "gpt-4o"            # 模型名称
    temperature: float = 0.7
    max_tokens: int = 4096
    api_base: str | None = None      # 自定义 API 地址
    api_key_env: str | None = None   # API Key 环境变量名

class AgentConfig(BaseModel):
    id: str                          # 唯一标识
    name: str                        # 显示名称
    role: str                        # 角色 Prompt
    model: ModelConfig               # LLM 配置
    tools: list[str] = []            # 可用工具列表
    can_request: list[str] = []      # 可以向哪些 Agent 发请求
    max_concurrent: int = 1          # 最大并发处理数

# ===== 工作流配置 =====
class TriggerConfig(BaseModel):
    type: str                        # manual / cron / event
    cron: str | None = None          # Cron 表达式
    event: str | None = None         # 事件名称

class RouteCondition(BaseModel):
    field: str                       # 判断字段
    operator: str                    # eq / neq / contains / gt / lt
    value: Any                       # 期望值

class Route(BaseModel):
    target: str                      # 目标 Agent ID
    condition: RouteCondition | None = None  # 路由条件（空=默认路由）

class FlowConfig(BaseModel):
    entry: str                       # 入口 Agent ID
    max_iterations: int = 10         # 最大迭代次数
    timeout: int = 3600              # 工作流超时（秒）
    routes: dict[str, list[Route]] = {}  # Agent ID → 路由规则列表
    terminate_on: list[dict] = []    # 终止条件

class WorkflowConfig(BaseModel):
    id: str
    name: str
    trigger: TriggerConfig
    agents: list[str]                # 参与的 Agent ID 列表
    flow: FlowConfig
    context: dict = {}               # 初始共享上下文
```

### 4.2 运行时数据模型

```python
class AgentState(Enum):
    IDLE = "idle"
    RUNNING = "running"
    WORKING = "working"
    ERROR = "error"
    STOPPED = "stopped"

class WorkflowStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    MAX_ITERATIONS = "max_iterations"

@dataclass
class ToolResult:
    success: bool
    output: str | None = None
    error: str | None = None

@dataclass
class AgentResult:
    output: Any
    status: str
    tool_calls: list[dict] = field(default_factory=list)
    tokens_used: int = 0

@dataclass
class WorkflowResult:
    status: str
    output: Any = None
    iterations: int = 0
    duration_seconds: float = 0
    total_tokens: int = 0
```

---

## 5. 关键流程

### 5.1 消息处理流程

```
Agent 收到消息
      │
      ▼
  构建 Prompt
  ┌──────────────────────────────┐
  │ System: {role prompt}        │
  │ Context: {workflow context}  │
  │ History: {recent messages}   │
  │ Task: {message payload}      │
  │ Tools: {available tools}     │
  └──────────────────────────────┘
      │
      ▼
  调用 LLM (通过 LLM Gateway)
      │
      ▼
  解析 LLM 输出
      │
      ├── 需要调用工具？
      │       │
      │       ▼ Yes
      │   执行工具 → 获取结果 → 再次调用 LLM（附带工具结果）
      │       │
      │       ▼
      │   (循环直到 LLM 给出最终回答)
      │
      ├── 需要请求其他 Agent？
      │       │
      │       ▼ Yes
      │   构建 Message → 通过 MessageBus 发送
      │
      └── 最终回答
              │
              ▼
         发送结果消息给 Orchestrator
```

### 5.2 工作流生命周期

```
用户提交任务
      │
      ▼
  创建 WorkflowContext
      │
      ▼
  发送初始消息给 Entry Agent
      │
      ▼
  ┌──────────────────────────┐
  │   工作流事件循环           │
  │                           │
  │   等待事件 ←───────────┐  │
  │      │                 │  │
  │      ▼                 │  │
  │   是否终止条件？        │  │
  │      │                 │  │
  │   No ▼                 │  │
  │   解析路由规则          │  │
  │      │                 │  │
  │      ▼                 │  │
  │   分发消息给下游 Agent  │  │
  │      │                 │  │
  │      └─────────────────┘  │
  │                           │
  │   Yes ▼                   │
  │   返回 WorkflowResult     │
  └──────────────────────────┘
```

### 5.3 异常恢复流程

```
Agent 执行异常
      │
      ▼
  记录错误日志 + 错误消息入库
      │
      ▼
  当前步骤重试（最多 3 次）
      │
      ├── 重试成功 → 继续正常流程
      │
      └── 重试失败
              │
              ▼
         通知 Orchestrator
              │
              ▼
         标记该 Agent 为 ERROR 状态
              │
              ▼
         触发告警（Webhook）
              │
              ▼
         工作流降级处理
         ├── 跳过该步骤（如果配置了 skip_on_error）
         └── 终止工作流（默认行为）
```

---

## 6. 安全设计

### 6.1 工具执行沙箱

```python
class SandboxExecutor:
    """沙箱化工具执行器"""

    def __init__(self, config: SandboxConfig):
        self.enabled = config.enabled
        self.allowed_commands = config.command_whitelist
        self.blocked_paths = config.blocked_paths

    async def execute(self, tool: Tool, **kwargs) -> ToolResult:
        if self.enabled:
            # 命令白名单检查
            if isinstance(tool, ShellExecTool):
                cmd = kwargs.get("command", "")
                if not self._is_allowed(cmd):
                    return ToolResult(
                        success=False,
                        error=f"Command blocked by sandbox policy: {cmd}"
                    )

            # 文件路径检查
            if hasattr(kwargs, "path"):
                if self._is_blocked_path(kwargs["path"]):
                    return ToolResult(
                        success=False,
                        error=f"Path blocked by sandbox policy: {kwargs['path']}"
                    )

        return await tool.execute(**kwargs)
```

### 6.2 密钥管理

```python
class SecretManager:
    """密钥管理器"""

    @staticmethod
    def get_api_key(env_var: str) -> str:
        """从环境变量获取 API Key"""
        key = os.environ.get(env_var)
        if not key:
            raise ConfigError(f"Environment variable {env_var} not set")
        return key

    @staticmethod
    def mask_key(key: str) -> str:
        """脱敏显示"""
        if len(key) <= 8:
            return "****"
        return key[:4] + "****" + key[-4:]
```

---

## 7. 可观测性设计

### 7.1 结构化日志

```python
import structlog

logger = structlog.get_logger()

# 日志示例
logger.info(
    "agent_message_received",
    agent_id="agent-coder",
    workflow_id="wf-001",
    message_type="task_request",
    queue_depth=3,
)

logger.info(
    "llm_call_completed",
    agent_id="agent-coder",
    model="gpt-4o",
    input_tokens=1200,
    output_tokens=800,
    latency_ms=2340,
)

logger.info(
    "tool_executed",
    agent_id="agent-coder",
    tool="file_write",
    success=True,
    duration_ms=15,
)
```

### 7.2 指标采集

```python
@dataclass
class SystemMetrics:
    """系统运行指标"""
    active_workflows: int
    agent_states: dict[str, str]       # agent_id → state
    queue_depths: dict[str, int]       # agent_id → queue_depth
    total_tokens_used: int
    total_tool_calls: int
    uptime_seconds: float
    error_count: int
    llm_calls: int
    avg_llm_latency_ms: float
```

### 7.3 Webhook 通知

```python
class WebhookNotifier:
    """Webhook 事件通知"""

    async def notify(self, event_type: str, data: dict):
        """发送 Webhook 通知"""
        for hook in self.config.webhooks:
            if event_type in hook.events:
                payload = {
                    "event": event_type,
                    "timestamp": datetime.now().isoformat(),
                    "data": data,
                }
                async with aiohttp.ClientSession() as session:
                    await session.post(
                        hook.url,
                        json=payload,
                        headers={"Content-Type": "application/json"},
                    )
```

---

## 8. 部署方案

### 8.1 单机部署（推荐起步方案）

```
┌─────────────────────────────────┐
│          主机 / VM               │
│                                  │
│  ┌───────────┐  ┌────────────┐  │
│  │ AutoFlow  │  │   Redis    │  │
│  │  Engine   │──│  (Streams) │  │
│  │           │  │            │  │
│  └───────────┘  └────────────┘  │
│                                  │
│  systemd / supervisord 管理进程  │
└─────────────────────────────────┘
```

### 8.2 Docker Compose 部署

```yaml
# docker-compose.yml
version: "3.8"
services:
  autoflow:
    build: .
    environment:
      - REDIS_URL=redis://redis:6379
      - OPENAI_API_KEY=${OPENAI_API_KEY}
    volumes:
      - ./config:/app/config
      - ./workspace:/app/workspace
      - ./logs:/app/logs
    depends_on:
      - redis
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    volumes:
      - redis-data:/data
    restart: unless-stopped

volumes:
  redis-data:
```

### 8.3 后续扩展：分布式部署

```
┌──────────┐  ┌──────────┐  ┌──────────┐
│ Worker 1 │  │ Worker 2 │  │ Worker 3 │
│ Agent A  │  │ Agent B  │  │ Agent C  │
└────┬─────┘  └────┬─────┘  └────┬─────┘
     │              │              │
     └──────────────┼──────────────┘
                    │
            ┌───────▼───────┐
            │ Redis Cluster │
            └───────────────┘
```

---

## 9. 技术债务与演进方向

| 阶段 | 技术债务 | 演进方向 |
|------|---------|---------|
| V1.0 | 进程内所有 Agent 共享事件循环 | V2.0 支持多进程/分布式 Worker |
| V1.0 | 工作流路由规则为静态配置 | V2.0 支持 LLM 动态路由决策 |
| V1.0 | 仅 CLI 交互 | V2.0 提供 Web Dashboard |
| V1.0 | 无持久化存储（除 Redis） | V2.0 接入 SQLite/PostgreSQL 存储执行历史 |
| V1.0 | 无权限模型 | V2.0 引入 RBAC 权限控制 |
