"""Memory 抽象基类 — 定义记忆存储的统一接口"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4


class MemoryScope(str, Enum):
    """记忆作用域"""

    AGENT = "agent"  # 仅当前 Agent 可见
    WORKFLOW = "workflow"  # 当前工作流内所有 Agent 共享
    GLOBAL = "global"  # 跨工作流持久共享


@dataclass
class MemoryRecord:
    """单条记忆记录"""

    key: str  # 记忆键（语义标识）
    value: Any  # 记忆内容
    scope: MemoryScope = MemoryScope.WORKFLOW
    agent_id: str = ""  # 创建者 Agent ID
    workflow_id: str = ""  # 所属工作流 ID
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    ttl: int | None = None  # 过期时间（秒），None 表示永不过期
    metadata: dict = field(default_factory=dict)  # 附加元数据
    id: str = field(default_factory=lambda: str(uuid4()))

    def is_expired(self) -> bool:
        """检查是否已过期"""
        if self.ttl is None:
            return False
        created = datetime.fromisoformat(self.created_at)
        elapsed = (datetime.now(timezone.utc) - created).total_seconds()
        return elapsed > self.ttl


class MemoryStore(ABC):
    """记忆存储抽象基类

    所有记忆后端（InMemory / Redis / 文件 / 向量数据库）都实现此接口。
    支持按 scope 隔离：Agent 级、Workflow 级、Global 级。
    """

    @abstractmethod
    async def store(self, record: MemoryRecord) -> None:
        """存储一条记忆"""
        ...

    @abstractmethod
    async def recall(
        self,
        key: str,
        scope: MemoryScope = MemoryScope.WORKFLOW,
        agent_id: str = "",
        workflow_id: str = "",
    ) -> MemoryRecord | None:
        """按 key 精确检索一条记忆"""
        ...

    @abstractmethod
    async def search(
        self,
        query: str = "",
        scope: MemoryScope = MemoryScope.WORKFLOW,
        agent_id: str = "",
        workflow_id: str = "",
        limit: int = 10,
    ) -> list[MemoryRecord]:
        """搜索记忆（支持模糊匹配）

        Args:
            query: 搜索关键词，空字符串表示返回全部
            scope: 搜索范围
            agent_id: 按 Agent 过滤（scope=AGENT 时必填）
            workflow_id: 按工作流过滤（scope=WORKFLOW 时必填）
            limit: 最大返回条数

        Returns:
            匹配的记忆列表，按创建时间倒序
        """
        ...

    @abstractmethod
    async def delete(self, record_id: str) -> bool:
        """删除一条记忆"""
        ...

    @abstractmethod
    async def clear(
        self,
        scope: MemoryScope = MemoryScope.WORKFLOW,
        agent_id: str = "",
        workflow_id: str = "",
    ) -> int:
        """清空指定范围的记忆，返回删除条数"""
        ...

    async def store_many(self, records: list[MemoryRecord]) -> None:
        """批量存储（默认实现为逐条调用）"""
        for record in records:
            await self.store(record)
