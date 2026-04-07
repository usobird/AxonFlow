"""消息总线测试"""

import pytest

from axonflow.core.message import Message, MessageType
from axonflow.messaging.memory_bus import InMemoryMessageBus


class TestInMemoryMessageBus:
    @pytest.mark.asyncio
    async def test_send_and_receive(self):
        bus = InMemoryMessageBus()
        msg = Message(
            sender="agent-a",
            receiver="agent-b",
            type=MessageType.TASK_REQUEST,
            payload={"task": "test"},
        )

        await bus.send(msg)
        received = await bus.receive("agent-b", block_ms=1000)

        assert received is not None
        assert received.sender == "agent-a"
        assert received.payload == {"task": "test"}

    @pytest.mark.asyncio
    async def test_receive_timeout(self):
        bus = InMemoryMessageBus()
        result = await bus.receive("agent-x", block_ms=100)
        assert result is None

    @pytest.mark.asyncio
    async def test_queue_depth(self):
        bus = InMemoryMessageBus()

        for i in range(3):
            msg = Message(
                sender="a", receiver="b",
                type=MessageType.TASK_REQUEST,
                payload={"i": i},
            )
            await bus.send(msg)

        assert await bus.get_queue_depth("b") == 3
        assert await bus.get_queue_depth("nonexistent") == 0

    @pytest.mark.asyncio
    async def test_priority_ordering(self):
        bus = InMemoryMessageBus()

        low = Message(
            sender="a", receiver="b",
            type=MessageType.TASK_REQUEST,
            payload={"priority": "low"},
            priority=1,
        )
        high = Message(
            sender="a", receiver="b",
            type=MessageType.TASK_REQUEST,
            payload={"priority": "high"},
            priority=10,
        )

        # 先发低优先级，后发高优先级
        await bus.send(low)
        await bus.send(high)

        # 高优先级应该先被取出
        first = await bus.receive("b", block_ms=100)
        assert first.payload["priority"] == "high"

        second = await bus.receive("b", block_ms=100)
        assert second.payload["priority"] == "low"

    @pytest.mark.asyncio
    async def test_message_isolation(self):
        """不同 Agent 的消息隔离"""
        bus = InMemoryMessageBus()

        msg_b = Message(
            sender="a", receiver="b",
            type=MessageType.TASK_REQUEST,
            payload={"for": "b"},
        )
        msg_c = Message(
            sender="a", receiver="c",
            type=MessageType.TASK_REQUEST,
            payload={"for": "c"},
        )

        await bus.send(msg_b)
        await bus.send(msg_c)

        # Agent B 只能收到自己的消息
        received = await bus.receive("b", block_ms=100)
        assert received.payload["for"] == "b"

        # Agent C 只能收到自己的消息
        received = await bus.receive("c", block_ms=100)
        assert received.payload["for"] == "c"
