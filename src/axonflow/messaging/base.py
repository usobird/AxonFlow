"""消息总线抽象接口"""

from __future__ import annotations

from abc import ABC, abstractmethod

from axonflow.core.message import Message


class MessageBus(ABC):
    """消息总线抽象基类

    所有消息总线实现（Redis / InMemory）都必须实现此接口。
    """

    @abstractmethod
    async def send(self, message: Message) -> None:
        """发送消息到目标 Agent 的收件箱"""
        ...

    @abstractmethod
    async def receive(self, agent_id: str, block_ms: int = 5000) -> Message | None:
        """从指定 Agent 的收件箱读取一条消息

        Args:
            agent_id: 接收方 Agent ID
            block_ms: 阻塞等待时间（毫秒），0 表示非阻塞

        Returns:
            消息对象，如果超时则返回 None
        """
        ...

    @abstractmethod
    async def get_queue_depth(self, agent_id: str) -> int:
        """获取指定 Agent 的待处理消息数量"""
        ...

    async def start(self) -> None:
        """启动消息总线（可选实现）"""

    async def stop(self) -> None:
        """关闭消息总线（可选实现）"""
