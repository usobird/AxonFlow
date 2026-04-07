"""记忆系统测试"""

import pytest

from axonflow.memory.base import MemoryRecord, MemoryScope, MemoryStore
from axonflow.memory.local import InMemoryStore


class TestMemoryRecord:
    def test_create_record(self):
        record = MemoryRecord(
            key="test-key",
            value={"data": "hello"},
            scope=MemoryScope.AGENT,
            agent_id="agent-a",
        )
        assert record.key == "test-key"
        assert record.value == {"data": "hello"}
        assert record.scope == MemoryScope.AGENT
        assert record.agent_id == "agent-a"
        assert record.id  # UUID 自动生成

    def test_record_not_expired_without_ttl(self):
        record = MemoryRecord(key="k", value="v", ttl=None)
        assert not record.is_expired()

    def test_record_not_expired_with_large_ttl(self):
        record = MemoryRecord(key="k", value="v", ttl=99999)
        assert not record.is_expired()

    def test_scope_enum_values(self):
        assert MemoryScope.AGENT.value == "agent"
        assert MemoryScope.WORKFLOW.value == "workflow"
        assert MemoryScope.GLOBAL.value == "global"


class TestInMemoryStore:
    @pytest.mark.asyncio
    async def test_store_and_recall(self):
        store = InMemoryStore()
        record = MemoryRecord(
            key="task:001",
            value={"task": "build feature", "result": "done"},
            scope=MemoryScope.AGENT,
            agent_id="agent-coder",
        )
        await store.store(record)

        recalled = await store.recall(
            key="task:001",
            scope=MemoryScope.AGENT,
            agent_id="agent-coder",
        )
        assert recalled is not None
        assert recalled.key == "task:001"
        assert recalled.value["task"] == "build feature"

    @pytest.mark.asyncio
    async def test_recall_nonexistent_key(self):
        store = InMemoryStore()
        result = await store.recall(
            key="does-not-exist",
            scope=MemoryScope.AGENT,
            agent_id="x",
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_search_by_agent_scope(self):
        store = InMemoryStore()
        for i in range(3):
            await store.store(
                MemoryRecord(
                    key=f"task:{i}",
                    value=f"result-{i}",
                    scope=MemoryScope.AGENT,
                    agent_id="agent-a",
                )
            )
        # 另一个 Agent 的记忆
        await store.store(
            MemoryRecord(
                key="other",
                value="other-data",
                scope=MemoryScope.AGENT,
                agent_id="agent-b",
            )
        )

        results = await store.search(
            scope=MemoryScope.AGENT,
            agent_id="agent-a",
        )
        assert len(results) == 3
        # 不应包含 agent-b 的记忆
        assert all(r.agent_id == "agent-a" for r in results)

    @pytest.mark.asyncio
    async def test_search_by_workflow_scope(self):
        store = InMemoryStore()
        await store.store(
            MemoryRecord(
                key="step-1",
                value="data-1",
                scope=MemoryScope.WORKFLOW,
                workflow_id="wf-001",
                agent_id="agent-a",
            )
        )
        await store.store(
            MemoryRecord(
                key="step-2",
                value="data-2",
                scope=MemoryScope.WORKFLOW,
                workflow_id="wf-001",
                agent_id="agent-b",
            )
        )
        await store.store(
            MemoryRecord(
                key="step-3",
                value="data-3",
                scope=MemoryScope.WORKFLOW,
                workflow_id="wf-002",  # 不同的工作流
                agent_id="agent-a",
            )
        )

        results = await store.search(
            scope=MemoryScope.WORKFLOW,
            workflow_id="wf-001",
        )
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_search_global_scope(self):
        store = InMemoryStore()
        await store.store(
            MemoryRecord(
                key="global-info",
                value="shared data",
                scope=MemoryScope.GLOBAL,
            )
        )
        results = await store.search(scope=MemoryScope.GLOBAL)
        assert len(results) == 1
        assert results[0].key == "global-info"

    @pytest.mark.asyncio
    async def test_search_with_limit(self):
        store = InMemoryStore()
        for i in range(10):
            await store.store(
                MemoryRecord(
                    key=f"item:{i}",
                    value=f"val-{i}",
                    scope=MemoryScope.GLOBAL,
                )
            )
        results = await store.search(scope=MemoryScope.GLOBAL, limit=3)
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_delete(self):
        store = InMemoryStore()
        record = MemoryRecord(
            key="to-delete",
            value="temp",
            scope=MemoryScope.GLOBAL,
        )
        await store.store(record)
        assert await store.delete(record.id)

        # 确认已删除
        result = await store.recall(key="to-delete", scope=MemoryScope.GLOBAL)
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self):
        store = InMemoryStore()
        assert not await store.delete("nonexistent-id")

    @pytest.mark.asyncio
    async def test_clear_scope(self):
        store = InMemoryStore()
        for i in range(5):
            await store.store(
                MemoryRecord(
                    key=f"k:{i}",
                    value=f"v:{i}",
                    scope=MemoryScope.AGENT,
                    agent_id="agent-a",
                )
            )
        await store.store(
            MemoryRecord(
                key="global",
                value="global-val",
                scope=MemoryScope.GLOBAL,
            )
        )

        deleted = await store.clear(scope=MemoryScope.AGENT, agent_id="agent-a")
        assert deleted == 5

        # 全局记忆不受影响
        remaining = await store.search(scope=MemoryScope.GLOBAL)
        assert len(remaining) == 1

    @pytest.mark.asyncio
    async def test_store_many(self):
        store = InMemoryStore()
        records = [
            MemoryRecord(key=f"batch:{i}", value=f"v:{i}", scope=MemoryScope.GLOBAL)
            for i in range(5)
        ]
        await store.store_many(records)

        results = await store.search(scope=MemoryScope.GLOBAL)
        assert len(results) == 5
