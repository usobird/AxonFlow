"""Redis Streams 消息总线实现"""

from __future__ import annotations

import redis.asyncio as aioredis
import structlog

from autoflow.config.defaults import REDIS_KEY_PREFIX
from autoflow.core.message import Message
from autoflow.messaging.base import MessageBus

logger = structlog.get_logger()


class RedisMessageBus(MessageBus):
    """基于 Redis Streams 的消息总线

    每个 Agent 拥有独立的 Stream 作为收件箱，
    使用消费者组保证消息不被重复消费。
    """

    def __init__(self, redis_url: str = "redis://localhost:6379") -> None:
        self._redis_url = redis_url
        self._redis: aioredis.Redis | None = None

    def _stream_key(self, agent_id: str) -> str:
        return f"{REDIS_KEY_PREFIX}:agent:{agent_id}:inbox"

    def _group_name(self, agent_id: str) -> str:
        return f"agent-{agent_id}-group"

    def _consumer_name(self, agent_id: str) -> str:
        return f"agent-{agent_id}-consumer"

    async def start(self) -> None:
        """初始化 Redis 连接"""
        self._redis = aioredis.from_url(
            self._redis_url, decode_responses=True
        )
        logger.info("redis_bus.connected", url=self._redis_url)

    async def stop(self) -> None:
        """关闭 Redis 连接"""
        if self._redis:
            await self._redis.aclose()
            self._redis = None
            logger.info("redis_bus.disconnected")

    def _ensure_connected(self) -> aioredis.Redis:
        if self._redis is None:
            raise RuntimeError("RedisMessageBus not started. Call start() first.")
        return self._redis

    async def _ensure_group(self, stream_key: str, group_name: str) -> None:
        """确保消费者组存在"""
        r = self._ensure_connected()
        try:
            await r.xgroup_create(stream_key, group_name, id="0", mkstream=True)
        except aioredis.ResponseError as e:
            # 消费者组已存在，忽略
            if "BUSYGROUP" not in str(e):
                raise

    async def send(self, message: Message) -> None:
        r = self._ensure_connected()
        stream_key = self._stream_key(message.receiver)
        await r.xadd(stream_key, {"data": message.to_json()})
        logger.debug(
            "redis_bus.sent",
            sender=message.sender,
            receiver=message.receiver,
            stream=stream_key,
        )

    async def receive(self, agent_id: str, block_ms: int = 5000) -> Message | None:
        r = self._ensure_connected()
        stream_key = self._stream_key(agent_id)
        group_name = self._group_name(agent_id)
        consumer_name = self._consumer_name(agent_id)

        await self._ensure_group(stream_key, group_name)

        results = await r.xreadgroup(
            groupname=group_name,
            consumername=consumer_name,
            streams={stream_key: ">"},
            count=1,
            block=block_ms,
        )

        if not results:
            return None

        # results 格式: [[stream_key, [(msg_id, {field: value})]]]
        _stream, messages = results[0]
        msg_id, data = messages[0]
        message = Message.from_json(data["data"])

        # ACK 消息
        await r.xack(stream_key, group_name, msg_id)

        logger.debug(
            "redis_bus.received",
            agent_id=agent_id,
            msg_id=msg_id,
            sender=message.sender,
        )
        return message

    async def get_queue_depth(self, agent_id: str) -> int:
        r = self._ensure_connected()
        stream_key = self._stream_key(agent_id)
        try:
            return await r.xlen(stream_key)
        except aioredis.ResponseError:
            return 0
