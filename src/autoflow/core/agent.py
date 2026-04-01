"""Agent 基类、AgentRegistry 与 Agent 工厂"""

from __future__ import annotations

import asyncio
import importlib
from enum import Enum
from typing import Any

import structlog

from autoflow.config.models import AgentConfig
from autoflow.core.context import WorkflowContext
from autoflow.core.message import Message, MessageType
from autoflow.llm.gateway import LLMGateway
from autoflow.llm.prompt_builder import PromptBuilder
from autoflow.memory.base import MemoryRecord, MemoryScope, MemoryStore
from autoflow.memory.local import InMemoryStore
from autoflow.messaging.base import MessageBus
from autoflow.tools.base import ToolRegistry

logger = structlog.get_logger()


class AgentState(str, Enum):
    """智能体状态"""

    IDLE = "idle"
    RUNNING = "running"
    WORKING = "working"
    ERROR = "error"
    STOPPED = "stopped"


class BaseAgent:
    """智能体基类

    每个 Agent 是一个独立的异步任务，持续监听自己的消息队列，
    收到消息后调用 LLM 进行推理，并根据结果执行工具或向其他 Agent 发起请求。

    支持:
    - 记忆系统: Agent 可在处理消息时存取记忆，记忆可按 scope 跨 Agent/跨 Workflow 共享
    - 自定义参数: 通过 config.parameters 传递的参数可在子类中使用
    """

    def __init__(
        self,
        config: AgentConfig,
        message_bus: MessageBus,
        llm_gateway: LLMGateway,
        tool_registry: ToolRegistry,
        memory_store: MemoryStore | None = None,
    ) -> None:
        self.config = config
        self.id = config.id
        self.name = config.name
        self.message_bus = message_bus
        self.llm_gateway = llm_gateway
        self.tool_registry = tool_registry
        self.state = AgentState.IDLE
        self.parameters: dict[str, Any] = config.parameters

        # 记忆系统
        self.memory: MemoryStore = memory_store or InMemoryStore()

        # 当前活跃的工作流上下文（由 Orchestrator 注入）
        self._contexts: dict[str, WorkflowContext] = {}

    def set_context(self, workflow_id: str, context: WorkflowContext) -> None:
        """注入工作流上下文"""
        self._contexts[workflow_id] = context

    def get_context(self, workflow_id: str) -> WorkflowContext | None:
        """获取工作流上下文"""
        return self._contexts.get(workflow_id)

    async def start(self) -> None:
        """启动 Agent 消息监听循环"""
        self.state = AgentState.RUNNING
        logger.info("agent.started", agent_id=self.id, name=self.name)

        while self.state == AgentState.RUNNING:
            try:
                message = await self.message_bus.receive(self.id)
                if message is None:
                    continue

                self.state = AgentState.WORKING
                logger.info(
                    "agent.processing",
                    agent_id=self.id,
                    msg_type=message.type.value,
                    sender=message.sender,
                    workflow_id=message.workflow_id,
                )

                result = await self._process_with_retry(message)
                await self._send_response(message, result)

            except asyncio.CancelledError:
                logger.info("agent.cancelled", agent_id=self.id)
                break
            except Exception as e:
                logger.error("agent.error", agent_id=self.id, error=str(e))
                self.state = AgentState.ERROR
                await asyncio.sleep(1)  # 短暂等待后恢复
                self.state = AgentState.RUNNING

        self.state = AgentState.STOPPED
        logger.info("agent.stopped", agent_id=self.id)

    async def stop(self) -> None:
        """停止 Agent"""
        self.state = AgentState.STOPPED

    async def _process_with_retry(self, message: Message) -> dict:
        """带重试的消息处理"""
        last_error = None
        for attempt in range(1, self.config.retry_limit + 1):
            try:
                return await self.handle_message(message)
            except Exception as e:
                last_error = e
                logger.warning(
                    "agent.retry",
                    agent_id=self.id,
                    attempt=attempt,
                    max_retries=self.config.retry_limit,
                    error=str(e),
                )
                if attempt < self.config.retry_limit:
                    await asyncio.sleep(2**attempt)  # 指数退避

        return {
            "status": "error",
            "error": f"Failed after {self.config.retry_limit} attempts: {last_error}",
        }

    async def handle_message(self, message: Message) -> dict:
        """处理消息的核心逻辑

        1. 从记忆中检索相关信息
        2. 构建 Prompt（含记忆上下文）
        3. 调用 LLM
        4. 将结果存入记忆
        5. 返回结果
        """
        context = self.get_context(message.workflow_id)
        tool_schemas = self.tool_registry.get_schemas(self.config.tools)

        # 从记忆中检索相关信息
        memories = await self._recall_memories(message)

        # 构建初始消息列表（含记忆）
        messages = PromptBuilder.build(
            agent_config=self.config,
            incoming_message=message,
            context=context,
            tool_schemas=tool_schemas if tool_schemas else None,
            memories=memories,
        )

        # 多轮工具调用循环（最多 10 轮）
        max_tool_rounds = 10
        for _round in range(max_tool_rounds):
            llm_response = await self.llm_gateway.chat(
                messages=messages,
                model_config=self.config.model,
                tools=tool_schemas if tool_schemas else None,
            )

            if llm_response.content:
                result = {
                    "status": "success",
                    "content": llm_response.content,
                    "model": llm_response.model,
                    "tokens_used": llm_response.total_tokens,
                }

                # 记录到上下文
                if context:
                    context.add_message(message)

                # 将对话存入记忆
                await self._store_memory(message, result)

                self.state = AgentState.RUNNING
                return result

        return {
            "status": "error",
            "error": "Max tool call rounds exceeded",
        }

    async def _recall_memories(self, message: Message) -> list[MemoryRecord]:
        """从记忆系统中检索与当前任务相关的记忆"""
        if not self.config.memory.enabled:
            return []

        all_memories: list[MemoryRecord] = []

        # 检索 Agent 自身的记忆
        if "agent" in self.config.memory.scopes:
            agent_memories = await self.memory.search(
                query="",
                scope=MemoryScope.AGENT,
                agent_id=self.id,
                limit=5,
            )
            all_memories.extend(agent_memories)

        # 检索工作流共享记忆
        if "workflow" in self.config.memory.scopes and message.workflow_id:
            workflow_memories = await self.memory.search(
                query="",
                scope=MemoryScope.WORKFLOW,
                workflow_id=message.workflow_id,
                limit=5,
            )
            all_memories.extend(workflow_memories)

        # 检索全局记忆
        if "global" in self.config.memory.scopes:
            global_memories = await self.memory.search(
                query="",
                scope=MemoryScope.GLOBAL,
                limit=3,
            )
            all_memories.extend(global_memories)

        return all_memories

    async def _store_memory(self, message: Message, result: dict) -> None:
        """将对话结果存入记忆"""
        if not self.config.memory.enabled:
            return

        task_content = message.payload.get("task", message.payload.get("content", ""))
        response_content = result.get("content", "")

        # 存入 Agent 私有记忆
        agent_record = MemoryRecord(
            key=f"task:{message.id[:8]}",
            value={"task": task_content, "response": response_content[:500]},
            scope=MemoryScope.AGENT,
            agent_id=self.id,
            workflow_id=message.workflow_id,
            ttl=self.config.memory.default_ttl,
        )
        await self.memory.store(agent_record)

        # 存入工作流共享记忆（其他 Agent 可见）
        if message.workflow_id:
            workflow_record = MemoryRecord(
                key=f"{self.id}:result:{message.id[:8]}",
                value={
                    "agent": self.id,
                    "task": task_content,
                    "result": response_content[:500],
                    "status": result.get("status"),
                },
                scope=MemoryScope.WORKFLOW,
                agent_id=self.id,
                workflow_id=message.workflow_id,
                ttl=self.config.memory.default_ttl,
            )
            await self.memory.store(workflow_record)

    async def _send_response(self, original_message: Message, result: dict) -> None:
        """发送处理结果"""
        response = original_message.reply(
            payload=result,
            msg_type=(
                MessageType.TASK_RESPONSE
                if result.get("status") == "success"
                else MessageType.ERROR
            ),
        )
        await self.message_bus.send(response)

    async def send_request(
        self, target_agent_id: str, payload: dict, workflow_id: str = ""
    ) -> None:
        """主动向其他 Agent 发起请求"""
        if target_agent_id not in self.config.can_request:
            logger.warning(
                "agent.request_denied",
                agent_id=self.id,
                target=target_agent_id,
                allowed=self.config.can_request,
            )
            return

        message = Message(
            sender=self.id,
            receiver=target_agent_id,
            type=MessageType.TASK_REQUEST,
            payload=payload,
            workflow_id=workflow_id,
        )
        await self.message_bus.send(message)
        logger.info(
            "agent.request_sent",
            sender=self.id,
            target=target_agent_id,
        )


# ============================================================
# Agent 工厂 — 根据配置创建不同类型的 Agent
# ============================================================

# 内置 Agent 类型注册表
_AGENT_TYPE_REGISTRY: dict[str, type[BaseAgent]] = {
    "base": BaseAgent,
}


def register_agent_type(type_name: str, agent_class: type[BaseAgent]) -> None:
    """注册自定义 Agent 类型"""
    _AGENT_TYPE_REGISTRY[type_name] = agent_class
    logger.info("agent_type.registered", type_name=type_name, cls=agent_class.__name__)


def create_agent(
    config: AgentConfig,
    message_bus: MessageBus,
    llm_gateway: LLMGateway,
    tool_registry: ToolRegistry,
    memory_store: MemoryStore | None = None,
) -> BaseAgent:
    """Agent 工厂方法

    根据 config.agent_type 或 config.class_path 创建对应的 Agent 实例:
    - agent_type 匹配内置注册表 → 使用注册的类
    - class_path 指定了自定义类路径 → 动态导入该类
    - 都没有 → 使用 BaseAgent
    """
    agent_cls: type[BaseAgent]

    # 优先使用 class_path 动态导入
    if config.class_path:
        agent_cls = _import_agent_class(config.class_path)
    elif config.agent_type in _AGENT_TYPE_REGISTRY:
        agent_cls = _AGENT_TYPE_REGISTRY[config.agent_type]
    else:
        logger.warning(
            "agent_factory.unknown_type",
            agent_type=config.agent_type,
            fallback="BaseAgent",
        )
        agent_cls = BaseAgent

    return agent_cls(
        config=config,
        message_bus=message_bus,
        llm_gateway=llm_gateway,
        tool_registry=tool_registry,
        memory_store=memory_store,
    )


def _import_agent_class(class_path: str) -> type[BaseAgent]:
    """动态导入 Agent 类

    class_path 格式: "module.path.ClassName"
    例如: "autoflow.agents.planner.PlannerAgent"
    """
    try:
        module_path, class_name = class_path.rsplit(".", 1)
        module = importlib.import_module(module_path)
        cls = getattr(module, class_name)
        if not (isinstance(cls, type) and issubclass(cls, BaseAgent)):
            raise TypeError(f"{class_path} is not a subclass of BaseAgent")
        return cls
    except (ImportError, AttributeError, ValueError) as e:
        raise ImportError(f"Cannot import agent class '{class_path}': {e}") from e


# ============================================================
# AgentRegistry
# ============================================================


class AgentRegistry:
    """智能体注册中心"""

    def __init__(self) -> None:
        self._agents: dict[str, BaseAgent] = {}

    def register(self, agent: BaseAgent) -> None:
        """注册智能体"""
        self._agents[agent.id] = agent
        logger.info("agent_registry.registered", agent_id=agent.id, name=agent.name)

    def get(self, agent_id: str) -> BaseAgent | None:
        """获取智能体"""
        return self._agents.get(agent_id)

    def list_agents(self) -> list[BaseAgent]:
        """列出所有已注册智能体"""
        return list(self._agents.values())

    def get_states(self) -> dict[str, str]:
        """获取所有智能体状态"""
        return {agent.id: agent.state.value for agent in self._agents.values()}
