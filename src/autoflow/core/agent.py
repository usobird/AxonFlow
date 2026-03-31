"""Agent 基类与 AgentRegistry"""

from __future__ import annotations

import asyncio
from enum import Enum

import structlog

from autoflow.config.models import AgentConfig
from autoflow.core.context import WorkflowContext
from autoflow.core.message import Message, MessageType
from autoflow.llm.gateway import LLMGateway, LLMResponse
from autoflow.llm.prompt_builder import PromptBuilder
from autoflow.messaging.base import MessageBus
from autoflow.tools.base import ToolRegistry, ToolResult

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
    """

    def __init__(
        self,
        config: AgentConfig,
        message_bus: MessageBus,
        llm_gateway: LLMGateway,
        tool_registry: ToolRegistry,
    ) -> None:
        self.config = config
        self.id = config.id
        self.name = config.name
        self.message_bus = message_bus
        self.llm_gateway = llm_gateway
        self.tool_registry = tool_registry
        self.state = AgentState.IDLE

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

        1. 构建 Prompt
        2. 调用 LLM
        3. 解析输出，判断是否需要调用工具
        4. 执行工具调用（循环直到 LLM 给出最终回答）
        5. 返回结果
        """
        context = self.get_context(message.workflow_id)
        tool_schemas = self.tool_registry.get_schemas(self.config.tools)

        # 构建初始消息列表
        messages = PromptBuilder.build(
            agent_config=self.config,
            incoming_message=message,
            context=context,
            tool_schemas=tool_schemas if tool_schemas else None,
        )

        # 多轮工具调用循环（最多 10 轮）
        max_tool_rounds = 10
        for _round in range(max_tool_rounds):
            llm_response = await self.llm_gateway.chat(
                messages=messages,
                model_config=self.config.model,
                tools=tool_schemas if tool_schemas else None,
            )

            # 如果 LLM 没有请求工具调用，直接返回
            # 注: 当前简化版本不解析 function calling 的结构化输出，
            # 后续迭代中将集成完整的 tool_calls 解析
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

                self.state = AgentState.RUNNING
                return result

        return {
            "status": "error",
            "error": "Max tool call rounds exceeded",
        }

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

    async def send_request(self, target_agent_id: str, payload: dict, workflow_id: str = "") -> None:
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
