"""工作流编排引擎"""

from __future__ import annotations

import asyncio
import time

import structlog

from autoflow.config.models import WorkflowConfig
from autoflow.core.agent import AgentRegistry
from autoflow.core.context import WorkflowContext
from autoflow.core.message import Message, MessageType
from autoflow.messaging.base import MessageBus

logger = structlog.get_logger()


class WorkflowResult:
    """工作流执行结果"""

    def __init__(
        self,
        workflow_id: str,
        status: str,
        output: dict | None = None,
        iterations: int = 0,
        duration_seconds: float = 0,
    ) -> None:
        self.workflow_id = workflow_id
        self.status = status
        self.output = output or {}
        self.iterations = iterations
        self.duration_seconds = duration_seconds

    def to_dict(self) -> dict:
        return {
            "workflow_id": self.workflow_id,
            "status": self.status,
            "output": self.output,
            "iterations": self.iterations,
            "duration_seconds": round(self.duration_seconds, 2),
        }


class WorkflowOrchestrator:
    """工作流编排器

    负责:
    - 初始化工作流上下文
    - 将初始任务分发给入口 Agent
    - 监听事件，根据路由规则驱动 Agent 间的消息流转
    - 检测终止条件，返回执行结果
    """

    # Orchestrator 本身也有一个虚拟 ID，用于收发控制消息
    ORCHESTRATOR_ID = "__orchestrator__"

    def __init__(
        self,
        config: WorkflowConfig,
        agent_registry: AgentRegistry,
        message_bus: MessageBus,
    ) -> None:
        self.config = config
        self.agents = agent_registry
        self.message_bus = message_bus

    async def execute(self, initial_input: str) -> WorkflowResult:
        """执行工作流"""
        start_time = time.monotonic()

        # 1. 创建上下文
        ctx = WorkflowContext(input=initial_input)
        ctx.shared_state.update(self.config.context)
        workflow_id = ctx.workflow_id

        logger.info(
            "workflow.started",
            workflow_id=workflow_id,
            name=self.config.name,
            entry=self.config.flow.entry,
        )

        # 2. 为所有参与的 Agent 注入上下文
        for agent_id in self.config.agents:
            agent = self.agents.get(agent_id)
            if agent:
                agent.set_context(workflow_id, ctx)

        # 3. 发送初始任务给入口 Agent
        entry_message = Message(
            sender=self.ORCHESTRATOR_ID,
            receiver=self.config.flow.entry,
            type=MessageType.TASK_REQUEST,
            payload={"task": initial_input},
            workflow_id=workflow_id,
            step_id="step-0",
        )
        await self.message_bus.send(entry_message)

        # 4. 事件循环
        iteration = 0
        max_iter = self.config.flow.max_iterations
        timeout = self.config.flow.timeout

        while iteration < max_iter:
            elapsed = time.monotonic() - start_time
            if elapsed > timeout:
                logger.warning("workflow.timeout", workflow_id=workflow_id)
                return WorkflowResult(
                    workflow_id=workflow_id,
                    status="timeout",
                    iterations=iteration,
                    duration_seconds=elapsed,
                )

            # 监听 Orchestrator 的收件箱（Agent 完成任务后会回复到这里）
            event = await self.message_bus.receive(
                self.ORCHESTRATOR_ID, block_ms=5000
            )
            if event is None:
                continue

            iteration += 1
            ctx.increment_iteration()
            ctx.add_message(event)

            logger.info(
                "workflow.event",
                workflow_id=workflow_id,
                iteration=iteration,
                sender=event.sender,
                msg_type=event.type.value,
                status=event.payload.get("status"),
            )

            # 检查终止条件
            if self._is_terminal(event):
                elapsed = time.monotonic() - start_time
                logger.info(
                    "workflow.completed",
                    workflow_id=workflow_id,
                    iterations=iteration,
                    duration=round(elapsed, 2),
                )
                return WorkflowResult(
                    workflow_id=workflow_id,
                    status="completed",
                    output=event.payload,
                    iterations=iteration,
                    duration_seconds=elapsed,
                )

            # 根据路由规则分发下一步
            next_targets = self._resolve_next(event)
            for target_id, payload in next_targets:
                next_msg = Message(
                    sender=self.ORCHESTRATOR_ID,
                    receiver=target_id,
                    type=MessageType.TASK_REQUEST,
                    payload=payload,
                    workflow_id=workflow_id,
                    step_id=f"step-{iteration}",
                    parent_message_id=event.id,
                )
                await self.message_bus.send(next_msg)

        elapsed = time.monotonic() - start_time
        logger.warning(
            "workflow.max_iterations",
            workflow_id=workflow_id,
            max=max_iter,
        )
        return WorkflowResult(
            workflow_id=workflow_id,
            status="max_iterations_reached",
            iterations=iteration,
            duration_seconds=elapsed,
        )

    def _is_terminal(self, event: Message) -> bool:
        """检查是否满足终止条件"""
        for condition in self.config.flow.terminate_on:
            agent_match = condition.get("agent") == event.sender
            status_match = condition.get("status") == event.payload.get("status")
            if agent_match and status_match:
                return True
        return False

    def _resolve_next(self, event: Message) -> list[tuple[str, dict]]:
        """根据路由规则解析下一步目标"""
        sender = event.sender
        routes = self.config.flow.routes.get(sender, [])

        targets = []
        for route in routes:
            if route.condition is None:
                # 无条件路由（默认路由）
                targets.append((route.target, event.payload))
            else:
                # 有条件路由
                actual_value = event.payload.get(route.condition.field)
                if route.condition.evaluate(actual_value):
                    targets.append((route.target, event.payload))

        return targets
