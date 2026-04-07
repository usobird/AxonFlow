"""进程内记忆存储 — 基于字典，支持 scope 隔离和 TTL 过期"""

from __future__ import annotations

import structlog

from axonflow.memory.base import MemoryRecord, MemoryScope, MemoryStore

logger = structlog.get_logger()


class InMemoryStore(MemoryStore):
    """进程内记忆存储

    使用嵌套字典按 scope 隔离：
    - GLOBAL: _global[key] = record
    - WORKFLOW: _workflows[workflow_id][key] = record
    - AGENT: _agents[agent_id][key] = record
    """

    def __init__(self) -> None:
        self._global: dict[str, MemoryRecord] = {}
        self._workflows: dict[str, dict[str, MemoryRecord]] = {}
        self._agents: dict[str, dict[str, MemoryRecord]] = {}
        self._by_id: dict[str, MemoryRecord] = {}  # id -> record 快速查找

    def _get_bucket(
        self,
        scope: MemoryScope,
        agent_id: str = "",
        workflow_id: str = "",
    ) -> dict[str, MemoryRecord]:
        """获取对应 scope 的存储桶"""
        if scope == MemoryScope.GLOBAL:
            return self._global
        elif scope == MemoryScope.WORKFLOW:
            if workflow_id not in self._workflows:
                self._workflows[workflow_id] = {}
            return self._workflows[workflow_id]
        elif scope == MemoryScope.AGENT:
            if agent_id not in self._agents:
                self._agents[agent_id] = {}
            return self._agents[agent_id]
        return self._global

    async def store(self, record: MemoryRecord) -> None:
        bucket = self._get_bucket(record.scope, record.agent_id, record.workflow_id)
        bucket[record.key] = record
        self._by_id[record.id] = record
        logger.debug(
            "memory.stored",
            key=record.key,
            scope=record.scope.value,
            agent_id=record.agent_id,
        )

    async def recall(
        self,
        key: str,
        scope: MemoryScope = MemoryScope.WORKFLOW,
        agent_id: str = "",
        workflow_id: str = "",
    ) -> MemoryRecord | None:
        bucket = self._get_bucket(scope, agent_id, workflow_id)
        record = bucket.get(key)
        if record is None:
            return None
        if record.is_expired():
            del bucket[key]
            self._by_id.pop(record.id, None)
            return None
        return record

    async def search(
        self,
        query: str = "",
        scope: MemoryScope = MemoryScope.WORKFLOW,
        agent_id: str = "",
        workflow_id: str = "",
        limit: int = 10,
    ) -> list[MemoryRecord]:
        bucket = self._get_bucket(scope, agent_id, workflow_id)

        # 过滤过期记录
        valid_records = []
        expired_keys = []
        for key, record in bucket.items():
            if record.is_expired():
                expired_keys.append(key)
            else:
                valid_records.append(record)

        # 清理过期记录
        for key in expired_keys:
            rec = bucket.pop(key)
            self._by_id.pop(rec.id, None)

        # 模糊匹配
        if query:
            query_lower = query.lower()
            valid_records = [
                r
                for r in valid_records
                if query_lower in r.key.lower() or query_lower in str(r.value).lower()
            ]

        # 按创建时间倒序
        valid_records.sort(key=lambda r: r.created_at, reverse=True)

        return valid_records[:limit]

    async def delete(self, record_id: str) -> bool:
        record = self._by_id.pop(record_id, None)
        if record is None:
            return False
        bucket = self._get_bucket(record.scope, record.agent_id, record.workflow_id)
        bucket.pop(record.key, None)
        return True

    async def clear(
        self,
        scope: MemoryScope = MemoryScope.WORKFLOW,
        agent_id: str = "",
        workflow_id: str = "",
    ) -> int:
        bucket = self._get_bucket(scope, agent_id, workflow_id)
        count = len(bucket)
        for rec in bucket.values():
            self._by_id.pop(rec.id, None)
        bucket.clear()
        return count
