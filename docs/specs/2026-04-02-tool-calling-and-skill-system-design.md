# Phase 1 设计规格：Tool Calling 闭环 + Skill 系统 + 执行日志

> 日期: 2026-04-02
> 状态: 待实现
> 分支: feat/orchestrator-persona-extensibility (在现有 Round 2 基础上)

## 1. 背景与目标

AutoFlow 当前存在一个关键基础设施缺失：Agent 的 tool calling 循环未接通。
LLM 收到了工具 schemas，可能返回 `tool_calls`，但 `LLMGateway` 丢弃了这些调用，
`handle_message` 的循环体中没有工具执行和结果回填逻辑。

**目标：**

1. **Tool Calling 闭环** — 让 Agent 能真正调用工具（读写文件、执行命令、git 操作等）
2. **Skill 系统** — 支持高阶策略/能力的声明式配置，由 prompt 模板 + 预置脚本组成
3. **执行日志** — 统一记录 tool 调用、错误、异常，便于复盘纠错

这三个子系统共同构成 Agent "能动手、有套路、可追溯"的基础能力层，
是后续 Phase 2（自举工作流）的前置条件。

---

## 2. 子系统 A：Tool Calling 闭环

### 2.1 LLMResponse 扩展

文件：`src/autoflow/llm/gateway.py`

```python
@dataclass
class LLMResponse:
    content: str
    model: str
    tool_calls: list[dict] | None = None  # 新增
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
```

### 2.2 LLMGateway.chat() 解析 tool_calls

文件：`src/autoflow/llm/gateway.py`

在现有的 `chat()` 方法中，解析 LLM 响应的 `tool_calls` 字段：

```python
msg = response.choices[0].message
content = msg.content or ""

# 解析 tool_calls
tool_calls = None
if hasattr(msg, "tool_calls") and msg.tool_calls:
    tool_calls = [
        {
            "id": tc.id,
            "function": {
                "name": tc.function.name,
                "arguments": tc.function.arguments,  # JSON string
            },
            "type": tc.type,
        }
        for tc in msg.tool_calls
    ]

return LLMResponse(
    content=content,
    model=model_str,
    tool_calls=tool_calls,
    ...
)
```

### 2.3 ToolRegistry.execute() 调度方法

文件：`src/autoflow/tools/base.py`

```python
async def execute(self, tool_name: str, arguments: dict) -> ToolResult:
    """根据工具名称调度执行"""
    tool = self.get(tool_name)
    if not tool:
        return ToolResult(success=False, error=f"Unknown tool: {tool_name}")
    try:
        return await tool.execute(**arguments)
    except Exception as e:
        return ToolResult(success=False, error=f"Tool execution failed: {e}")
```

### 2.4 BaseAgent.handle_message() 多轮工具调用循环

文件：`src/autoflow/core/agent.py`

替换现有的循环骨架：

```
loop (max 10 rounds):
  1. 调用 LLM(messages, tool_schemas) → response
  2. 如果 response.tool_calls 非空:
     a. 将 LLM 的 assistant message (含 tool_calls) 追加到 messages
     b. 遍历每个 tool_call:
        - 解析 function.name 和 function.arguments (JSON parse)
        - 调用 ToolRegistry.execute(name, parsed_args)
        - 记录到 ExecutionLogger
        - 将结果构造为 role="tool", tool_call_id=xxx 的 message，追加到 messages
     c. continue (让 LLM 看到工具结果后决定下一步)
  3. 如果 response.content 非空:
     - 记录到 memory，返回 success
  4. 如果既无 content 也无 tool_calls:
     - 记录 warning，继续循环（给 LLM 一次重试机会）
```

### 2.5 错误处理

| 场景 | 处理方式 |
|------|----------|
| LLM 返回了不存在的 tool 名 | ToolRegistry.execute() 返回 error ToolResult，回填给 LLM 自行修正 |
| tool 执行超时 | 各 tool 已有 timeout，超时返回 error，回填给 LLM |
| tool 执行抛异常 | 捕获异常包装为 ToolResult error，回填给 LLM |
| arguments JSON 解析失败 | 捕获 JSONDecodeError，构造 error message 回填给 LLM |
| 10 轮用尽未产出 content | 返回 error 状态，编排器按失败路由处理 |

所有错误均记录到 ExecutionLogger（见子系统 C）。

---

## 3. 子系统 B：Skill 系统

### 3.1 概念定义

| 概念 | 定义 | 类比 |
|------|------|------|
| Tool | 原子操作，单次函数调用，无状态 | "手" |
| Skill | 高阶策略，由 prompt 指引 + 预置脚本组成 | "套路" |
| Persona | 身份与价值观 (soul/user/workflow.md) | "人格" |

Skill 与 Persona 同层但用途不同：Persona 定义"你是谁"，Skill 定义"你会什么套路"。

### 3.2 目录结构

```
config/skills/
  code-review/          # 目录形式（有脚本）
    SKILL.md            # 指引文档（必需）
    scripts/
      lint.sh           # 预置脚本（可选）
      check-coverage.sh
  tdd/
    SKILL.md
    scripts/
      run-tests.sh
  gap-analysis.md       # 单文件形式（纯 prompt，向后兼容）
```

支持两种格式：
- **目录格式：** `config/skills/{name}/SKILL.md` + 可选 `scripts/` 子目录
- **单文件格式：** `config/skills/{name}.md`

### 3.3 @script 标记

SKILL.md 中使用 `@script:filename` 标记引用同目录下的脚本。

加载时，loader 将标记替换为 shell_exec 调用指引：

```
原文：运行检查：执行 @script:lint.sh {file_path}
替换后：运行检查：使用 shell_exec 工具执行 /absolute/path/to/config/skills/code-review/scripts/lint.sh {file_path}
```

如果引用的脚本不存在，保留原始文本不替换，日志 warning。

### 3.4 AgentConfig 扩展

文件：`src/autoflow/config/models.py`

```python
class AgentConfig(BaseModel):
    # ... 现有字段 ...
    skills: list[str] = Field(default_factory=list)  # 如 ["code-review", "tdd"]
```

### 3.5 加载逻辑

文件：`src/autoflow/config/loader.py`

新增函数：

```python
def load_skill_content(skills_dir: Path, skill_names: list[str]) -> str:
    """加载指定 skill 的内容，拼接返回"""
    sections = []
    for name in skill_names:
        # 优先查找目录格式
        skill_dir = skills_dir / name
        if skill_dir.is_dir():
            skill_md = skill_dir / "SKILL.md"
            if skill_md.exists():
                content = skill_md.read_text(encoding="utf-8")
                content = _resolve_script_refs(content, skill_dir / "scripts")
                sections.append(content)
            else:
                logger.warning("skill.missing_skill_md", skill=name)
            continue
        # 回退到单文件格式
        skill_file = skills_dir / f"{name}.md"
        if skill_file.exists():
            sections.append(skill_file.read_text(encoding="utf-8"))
        else:
            logger.warning("skill.not_found", skill=name)
    return "\n\n---\n\n".join(sections)

def _resolve_script_refs(content: str, scripts_dir: Path) -> str:
    """将 @script:xxx 替换为绝对路径的 shell_exec 指引"""
    import re
    def replacer(m):
        script_name = m.group(1)
        script_path = scripts_dir / script_name
        if script_path.exists():
            return f"使用 shell_exec 工具执行 {script_path.resolve()}"
        logger.warning("skill.script_not_found", script=script_name)
        return m.group(0)  # 保留原始文本
    return re.sub(r"@script:(\S+)", replacer, content)
```

### 3.6 PromptBuilder 注入

文件：`src/autoflow/llm/prompt_builder.py`

System prompt 组装顺序：
```
1. Persona (soul.md / user.md / workflow.md)
2. Role (agent config 中的 role 字段)
3. Skills (SKILL.md 内容)       ← 新增
4. Tool schemas 描述
5. Memory 上下文
```

### 3.7 边界处理

| 场景 | 处理方式 |
|------|----------|
| agent 引用不存在的 skill | 日志 warning，跳过，不阻塞启动 |
| skill 目录下没有 SKILL.md | 日志 warning，跳过 |
| @script 引用的脚本不存在 | 保留原始文本不替换，日志 warning |
| skills_dir 不存在 | 返回空字符串，日志 info |

---

## 4. 子系统 C：执行日志

### 4.1 数据模型

文件：`src/autoflow/observability/execution_log.py`（新建）

```python
@dataclass
class ExecutionLogEntry:
    timestamp: str          # ISO 8601
    workflow_id: str
    agent_id: str
    action: str             # tool_call | tool_error | llm_error | skill_error
    tool_name: str | None   # 涉及的工具名
    arguments: dict | None  # 工具参数（脱敏后）
    result: str | None      # 执行结果（截断到 2000 字符）
    error: str | None       # 错误信息
    round: int              # 第几轮 tool call
```

### 4.2 记录时机

| 事件 | action |
|------|--------|
| tool 调用成功 | `tool_call` |
| tool 名称不存在 | `tool_error` |
| tool 执行超时/异常 | `tool_error` |
| tool arguments JSON 解析失败 | `tool_error` |
| LLM 调用失败（含降级） | `llm_error` |
| skill 加载失败 / @script 引用缺失 | `skill_error` |
| 10 轮用尽未产出结果 | `tool_error` |

### 4.3 存储方式

**双写策略：**

1. **内存** — `list[ExecutionLogEntry]`，按时间顺序，引擎运行期间可查
2. **磁盘** — JSON Lines 格式追加写入 `{workspace_dir}/logs/execution-{workflow_id}.jsonl`

```python
class ExecutionLogger:
    def __init__(self, workspace_dir: str = "./workspace"):
        self._entries: list[ExecutionLogEntry] = []
        self._workspace_dir = Path(workspace_dir)

    def log(self, entry: ExecutionLogEntry) -> None:
        self._entries.append(entry)
        self._write_to_disk(entry)

    def get_entries(
        self,
        workflow_id: str | None = None,
        agent_id: str | None = None,
        action: str | None = None,
    ) -> list[ExecutionLogEntry]:
        """按条件过滤查询"""
        ...

    def _write_to_disk(self, entry: ExecutionLogEntry) -> None:
        log_dir = self._workspace_dir / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"execution-{entry.workflow_id}.jsonl"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(entry), ensure_ascii=False) + "\n")
```

### 4.4 集成点

- `AutoFlowEngine` 初始化时创建 `ExecutionLogger` 实例
- 通过 `create_agent()` 传递给每个 Agent
- `BaseAgent.handle_message()` 中的 tool 调用循环记录每次 tool 执行
- `LLMGateway.chat()` 的 fallback 路径记录 LLM 错误
- Skill 加载阶段的 warning 也通过 ExecutionLogger 记录

---

## 5. 文件变更清单

### 修改现有文件

| 文件 | 变更 |
|------|------|
| `src/autoflow/llm/gateway.py` | LLMResponse 增加 tool_calls；chat() 解析 tool_calls |
| `src/autoflow/core/agent.py` | handle_message() 补全多轮工具调用循环；集成 ExecutionLogger |
| `src/autoflow/tools/base.py` | ToolRegistry 增加 execute() 调度方法 |
| `src/autoflow/config/models.py` | AgentConfig 增加 skills 字段 |
| `src/autoflow/config/loader.py` | 新增 load_skill_content()、_resolve_script_refs() |
| `src/autoflow/llm/prompt_builder.py` | system prompt 注入 skill 内容 |
| `src/autoflow/engine.py` | 初始化 ExecutionLogger，传递给 Agent |

### 新建文件

| 文件 | 用途 |
|------|------|
| `src/autoflow/observability/execution_log.py` | ExecutionLogEntry + ExecutionLogger |
| `config/skills/code-review/SKILL.md` | 示例 skill：代码审查 |
| `config/skills/code-review/scripts/lint.sh` | 示例脚本：运行 lint |

### 新建测试

| 文件 | 覆盖范围 |
|------|----------|
| `tests/unit/test_tool_calling.py` | tool calling 闭环：mock LLM 返回 tool_calls → 验证工具执行 → 验证结果回填 |
| `tests/unit/test_skill_loader.py` | skill 加载：目录/单文件、@script 替换、缺失处理 |
| `tests/unit/test_execution_log.py` | ExecutionLogger：记录、查询、磁盘持久化 |

---

## 6. 不在范围内

- Phase 2 自举工作流（构思者/编码者/测试者）— 单独 spec
- Sandbox 路径隔离增强 — 后续独立处理
- Tool 并行执行优化 — 当前按顺序执行，后续可优化
- 执行日志的 Web UI — 当前通过 jsonl 文件 + file_read 查看
