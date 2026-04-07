"""进程内消息总线 — 基于 asyncio.Queue，用于开发/测试及 Redis 不可用时的降级"""

from __future__ import annotations

import asyncio

import structlog

from axonflow.core.message import Message
from axonflow.messaging.base import MessageBus

logger = structlog.get_logger()


class InMemoryMessageBus(MessageBus):
    """进程内消息总线

    使用 asyncio.PriorityQueue 实现优先级排序。
    适用于单进程开发/测试场景，或作为 Redis 不可用时的降级方案。
    """

    def __init__(self) -> None:
        self._queues: dict[str, asyncio.PriorityQueue[tuple[int, str, Message]]] = {}
        self._counter = 0  # 保证同优先级 FIFO

    def _get_queue(
        self, agent_id: str
    ) -> asyncio.PriorityQueue[tuple[int, str, Message]]:
        if agent_id not in self._queues:
            self._queues[agent_id] = asyncio.PriorityQueue()
        return self._queues[agent_id]

    async def send(self, message: Message) -> None:
        queue = self._get_queue(message.receiver)
        # 优先级取反：数值越大优先级越高，但 PriorityQueue 是最小堆
        self._counter += 1
        priority_key = (-message.priority, self._counter)
        await queue.put((*priority_key, message))  # type: ignore[arg-type]
        logger.debug(
            "memory_bus.sent",
            sender=message.sender,
            receiver=message.receiver,
            msg_type=message.type.value,
        )

    async def receive(self, agent_id: str, block_ms: int = 5000) -> Message | None:
        queue = self._get_queue(agent_id)
        try:
            _, _, message = await asyncio.wait_for(
                queue.get(), timeout=block_ms / 1000
            )
            logger.debug(
                "memory_bus.received",
                agent_id=agent_id,
                msg_type=message.type.value,
                sender=message.sender,
            )
            return message
        except asyncio.TimeoutError:
            return None

    async def get_queue_depth(self, agent_id: str) -> int:
        if agent_id not in self._queues:
            return 0
        return self._queues[agent_id].qsize()
