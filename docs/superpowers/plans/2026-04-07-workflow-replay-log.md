# Workflow Replay Log Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend `ExecutionLogger` to capture agent routing decisions, LLM call summaries, and inter-agent messages — enabling full workflow replay from a single JSONL file.

**Architecture:** Add three new event types (`routing`, `llm_summary`, `agent_message`) to the existing `ExecutionLogEntry` dataclass. Inject `ExecutionLogger` into `FlatOrchestrator` for routing events, and add LLM summary logging in `BaseAgent.handle_message()`. All events flow through the same dual-write (memory + JSONL) pipeline.

**Tech Stack:** Python 3.12, dataclasses, pytest, asyncio

---

### File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `src/axonflow/observability/execution_log.py` | Modify | Add new action types, extend `ExecutionLogEntry` with optional fields for routing/LLM/message data |
| `src/axonflow/core/workflow.py` | Modify | Accept `ExecutionLogger`, emit `routing` and `agent_message` events |
| `src/axonflow/core/agent.py` | Modify | Emit `llm_summary` events after each LLM call, emit `agent_message` on send/receive |
| `src/axonflow/engine.py` | Modify | Pass `ExecutionLogger` to orchestrator via `create_orchestrator` / `run_workflow` |
| `src/axonflow/core/orchestrator_factory.py` | Modify | Accept and forward `execution_logger` parameter |
| `tests/unit/test_execution_log.py` | Modify | Add tests for new event types |
| `tests/unit/test_replay_log.py` | Create | Integration-style tests for routing + LLM summary + agent_message events |

---

### Task 1: Extend ExecutionLogEntry with new action types and optional fields

**Files:**
- Modify: `src/axonflow/observability/execution_log.py:16-28`
- Test: `tests/unit/test_execution_log.py`

- [ ] **Step 1: Write failing tests for new entry types**

Add to `tests/unit/test_execution_log.py`:

```python
class TestReplayLogEntryTypes:
    """Tests for new replay log event types"""

    def test_routing_entry(self):
        entry = ExecutionLogEntry(
            timestamp="2026-04-07T12:00:00Z",
            workflow_id="wf-001",
            agent_id="__orchestrator__",
            action="routing",
            tool_name=None,
            arguments=None,
            result=None,
            error=None,
            round=0,
            routing={"source": "coder", "targets": ["tester"], "reason": "default_route"},
        )
        assert entry.action == "routing"
        assert entry.routing["source"] == "coder"
        assert entry.routing["targets"] == ["tester"]

    def test_llm_summary_entry(self):
        entry = ExecutionLogEntry(
            timestamp="2026-04-07T12:00:00Z",
            workflow_id="wf-001",
            agent_id="agent-coder",
            action="llm_summary",
            tool_name=None,
            arguments=None,
            result=None,
            error=None,
            round=1,
            llm_summary={
                "model": "qwen3-32b",
                "input_tokens": 500,
                "output_tokens": 120,
                "has_tool_calls": True,
                "content_preview": "I'll create the file...",
            },
        )
        assert entry.action == "llm_summary"
        assert entry.llm_summary["model"] == "qwen3-32b"
        assert entry.llm_summary["has_tool_calls"] is True

    def test_agent_message_entry(self):
        entry = ExecutionLogEntry(
            timestamp="2026-04-07T12:00:00Z",
            workflow_id="wf-001",
            agent_id="__orchestrator__",
            action="agent_message",
            tool_name=None,
            arguments=None,
            result=None,
            error=None,
            round=0,
            agent_message={
                "sender": "__orchestrator__",
                "receiver": "coder",
                "msg_type": "task_request",
                "payload_keys": ["task"],
                "message_id": "msg-001",
            },
        )
        assert entry.action == "agent_message"
        assert entry.agent_message["sender"] == "__orchestrator__"

    def test_new_fields_default_to_none(self):
        """Existing entries without new fields should still work"""
        entry = _make_entry()
        assert entry.routing is None
        assert entry.llm_summary is None
        assert entry.agent_message is None

    def test_disk_write_with_routing(self, tmp_path):
        logger = ExecutionLogger(workspace_dir=str(tmp_path))
        entry = ExecutionLogEntry(
            timestamp="2026-04-07T12:00:00Z",
            workflow_id="wf-routing",
            agent_id="__orchestrator__",
            action="routing",
            tool_name=None,
            arguments=None,
            result=None,
            error=None,
            round=0,
            routing={"source": "coder", "targets": ["tester"], "reason": "default_route"},
        )
        logger.log(entry)

        log_file = tmp_path / "logs" / "execution-wf-routing.jsonl"
        data = json.loads(log_file.read_text().strip())
        assert data["action"] == "routing"
        assert data["routing"]["source"] == "coder"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/test_execution_log.py::TestReplayLogEntryTypes -v`
Expected: FAIL with `TypeError: __init__() got an unexpected keyword argument 'routing'`

- [ ] **Step 3: Extend ExecutionLogEntry dataclass**

In `src/axonflow/observability/execution_log.py`, update the `ExecutionLogEntry` dataclass to add three optional fields:

```python
@dataclass
class ExecutionLogEntry:
    """单条执行日志

    action 取值:
    - tool_call:      工具调用成功
    - tool_error:     工具调用失败
    - llm_error:      LLM 调用失败
    - skill_error:    Skill 加载失败
    - routing:        编排器路由决策（新增）
    - llm_summary:    LLM 调用摘要（新增）
    - agent_message:  Agent 间消息传递（新增）
    """

    timestamp: str  # ISO 8601
    workflow_id: str
    agent_id: str
    action: str
    tool_name: str | None
    arguments: dict | None
    result: str | None
    error: str | None
    round: int

    # ---- Replay Log 扩展字段 ----
    routing: dict | None = None       # action=routing 时填充
    llm_summary: dict | None = None   # action=llm_summary 时填充
    agent_message: dict | None = None # action=agent_message 时填充
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/unit/test_execution_log.py -v`
Expected: ALL PASS (including existing tests — the new fields default to `None`)

- [ ] **Step 5: Commit**

```bash
git add src/axonflow/observability/execution_log.py tests/unit/test_execution_log.py
git commit -m "feat: extend ExecutionLogEntry with routing/llm_summary/agent_message fields"
```

---

### Task 2: Add LLM summary logging in BaseAgent

**Files:**
- Modify: `src/axonflow/core/agent.py:152-301`
- Test: `tests/unit/test_replay_log.py` (create)

- [ ] **Step 1: Write failing test for LLM summary logging**

Create `tests/unit/test_replay_log.py`:

```python
"""Replay log integration tests — verify that routing, LLM summary, and agent_message events are emitted"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from axonflow.config.models import AgentConfig, ModelConfig
from axonflow.core.agent import BaseAgent
from axonflow.core.message import Message, MessageType
from axonflow.llm.gateway import LLMResponse
from axonflow.observability.execution_log import ExecutionLogger


def _make_agent(execution_logger: ExecutionLogger) -> BaseAgent:
    """Create a minimal BaseAgent with mocked dependencies"""
    config = AgentConfig(
        id="test-agent",
        name="Test Agent",
        persona="You are a test agent",
        model=ModelConfig(name="test-model"),
    )
    message_bus = AsyncMock()
    llm_gateway = AsyncMock()
    tool_registry = MagicMock()
    tool_registry.get_schemas.return_value = []

    agent = BaseAgent(
        config=config,
        message_bus=message_bus,
        llm_gateway=llm_gateway,
        tool_registry=tool_registry,
        execution_logger=execution_logger,
    )
    return agent


def _make_message(workflow_id: str = "wf-test") -> Message:
    return Message(
        sender="__orchestrator__",
        receiver="test-agent",
        type=MessageType.TASK_REQUEST,
        payload={"task": "write hello world"},
        workflow_id=workflow_id,
    )


class TestLLMSummaryLogging:
    @pytest.mark.asyncio
    async def test_llm_summary_logged_on_text_response(self, tmp_path):
        """When LLM returns text content, an llm_summary entry should be logged"""
        exec_logger = ExecutionLogger(workspace_dir=str(tmp_path))
        agent = _make_agent(exec_logger)

        # Mock LLM to return text
        agent.llm_gateway.chat = AsyncMock(return_value=LLMResponse(
            content="Hello world!",
            model="test-model",
            input_tokens=100,
            output_tokens=20,
            total_tokens=120,
        ))

        msg = _make_message()
        await agent.handle_message(msg)

        summaries = exec_logger.get_entries(action="llm_summary")
        assert len(summaries) == 1
        assert summaries[0].llm_summary["model"] == "test-model"
        assert summaries[0].llm_summary["has_tool_calls"] is False
        assert "Hello" in summaries[0].llm_summary["content_preview"]

    @pytest.mark.asyncio
    async def test_llm_summary_logged_on_tool_call(self, tmp_path):
        """When LLM returns tool_calls, an llm_summary entry should be logged per round"""
        exec_logger = ExecutionLogger(workspace_dir=str(tmp_path))
        agent = _make_agent(exec_logger)

        # Round 1: tool call
        tool_response = LLMResponse(
            content="",
            model="test-model",
            tool_calls=[{
                "id": "call_1",
                "type": "function",
                "function": {"name": "shell_exec", "arguments": '{"command": "echo hi"}'},
            }],
            input_tokens=200,
            output_tokens=30,
            total_tokens=230,
        )
        # Round 2: text response
        text_response = LLMResponse(
            content="Done!",
            model="test-model",
            input_tokens=300,
            output_tokens=10,
            total_tokens=310,
        )
        agent.llm_gateway.chat = AsyncMock(side_effect=[tool_response, text_response])

        # Mock tool execution
        tool_result = MagicMock()
        tool_result.success = True
        tool_result.output = "hi\n"
        agent.tool_registry.execute = AsyncMock(return_value=tool_result)

        msg = _make_message()
        await agent.handle_message(msg)

        summaries = exec_logger.get_entries(action="llm_summary")
        assert len(summaries) == 2
        assert summaries[0].llm_summary["has_tool_calls"] is True
        assert summaries[1].llm_summary["has_tool_calls"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_replay_log.py::TestLLMSummaryLogging -v`
Expected: FAIL — no `llm_summary` entries are logged yet

- [ ] **Step 3: Add LLM summary logging to BaseAgent.handle_message()**

In `src/axonflow/core/agent.py`, add a private method `_log_llm_summary` and call it after each `llm_gateway.chat()` call inside `handle_message()`.

Add this method to `BaseAgent` (after the existing `_log_execution` method around line 327):

```python
    def _log_llm_summary(
        self,
        workflow_id: str,
        llm_response: "LLMResponse",
        round_num: int,
    ) -> None:
        """记录 LLM 调用摘要"""
        if self.execution_logger is None:
            return

        content_preview = ""
        if llm_response.content:
            content_preview = llm_response.content[:200]

        entry = ExecutionLogEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            workflow_id=workflow_id,
            agent_id=self.id,
            action="llm_summary",
            tool_name=None,
            arguments=None,
            result=None,
            error=None,
            round=round_num,
            llm_summary={
                "model": llm_response.model,
                "input_tokens": llm_response.input_tokens,
                "output_tokens": llm_response.output_tokens,
                "has_tool_calls": bool(llm_response.tool_calls),
                "content_preview": content_preview,
            },
        )
        self.execution_logger.log(entry)
```

Then in `handle_message()`, right after the `llm_gateway.chat()` call (currently line 182-186), add the summary logging:

```python
            llm_response = await self.llm_gateway.chat(
                messages=messages,
                model_config=self.config.model,
                tools=tool_schemas if tool_schemas else None,
            )

            # ---- Replay: log LLM call summary ----
            self._log_llm_summary(
                workflow_id=message.workflow_id,
                llm_response=llm_response,
                round_num=round_num,
            )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/unit/test_replay_log.py::TestLLMSummaryLogging -v`
Expected: ALL PASS

- [ ] **Step 5: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: ALL 117+ tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/axonflow/core/agent.py tests/unit/test_replay_log.py
git commit -m "feat: log LLM call summaries in BaseAgent for workflow replay"
```

---

### Task 3: Add routing and agent_message logging in FlatOrchestrator

**Files:**
- Modify: `src/axonflow/core/workflow.py:52-67` (BaseOrchestrator.__init__), `99-117` (_dispatch), `134-276` (FlatOrchestrator.execute)
- Test: `tests/unit/test_replay_log.py`

- [ ] **Step 1: Write failing tests for routing and agent_message events**

Add to `tests/unit/test_replay_log.py`:

```python
from axonflow.config.models import (
    WorkflowConfig,
    FlowConfig,
    RouteConfig,
    TriggerConfig,
)
from axonflow.core.agent import AgentRegistry, BaseAgent
from axonflow.core.workflow import FlatOrchestrator
from axonflow.messaging.memory_bus import InMemoryMessageBus


class TestOrchestratorReplayLogging:
    @pytest.mark.asyncio
    async def test_routing_event_logged(self, tmp_path):
        """Orchestrator should log a routing event when dispatching to next agent"""
        exec_logger = ExecutionLogger(workspace_dir=str(tmp_path))
        bus = InMemoryMessageBus()

        # Create minimal workflow: entry=agent-a, route agent-a -> agent-b
        wf_config = WorkflowConfig(
            id="wf-replay-test",
            name="Replay Test",
            agents=["agent-a", "agent-b"],
            trigger=TriggerConfig(type="manual"),
            flow=FlowConfig(
                entry="agent-a",
                routes={
                    "agent-a": [RouteConfig(target="agent-b")],
                },
                terminate_on=[{"agent": "agent-b", "status": "success"}],
                max_iterations=5,
                timeout=10,
            ),
        )

        # Mock agents — they immediately reply with success
        agent_a = _make_agent(exec_logger)
        agent_a.id = "agent-a"
        agent_b = _make_agent(exec_logger)
        agent_b.id = "agent-b"

        registry = AgentRegistry()
        registry.register(agent_a)
        registry.register(agent_b)

        orchestrator = FlatOrchestrator(
            config=wf_config,
            agent_registry=registry,
            message_bus=bus,
            execution_logger=exec_logger,
        )

        # Simulate: agent-a replies, then agent-b replies
        async def simulate_agents():
            import asyncio
            # Wait for orchestrator to dispatch to agent-a
            msg_a = await bus.receive("agent-a", block_ms=2000)
            if msg_a:
                reply_a = msg_a.reply(
                    payload={"status": "success", "content": "done by a"},
                )
                await bus.send(reply_a)

            # Wait for orchestrator to dispatch to agent-b
            msg_b = await bus.receive("agent-b", block_ms=2000)
            if msg_b:
                reply_b = msg_b.reply(
                    payload={"status": "success", "content": "done by b"},
                )
                await bus.send(reply_b)

        import asyncio
        sim_task = asyncio.create_task(simulate_agents())
        result = await orchestrator.execute("test input")
        await sim_task

        assert result.status == "completed"

        # Check routing events
        routing_events = exec_logger.get_entries(action="routing")
        assert len(routing_events) >= 1  # At least the agent-a -> agent-b routing

        # Check agent_message events
        msg_events = exec_logger.get_entries(action="agent_message")
        assert len(msg_events) >= 2  # initial dispatch + agent-a -> agent-b dispatch
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_replay_log.py::TestOrchestratorReplayLogging -v`
Expected: FAIL — `FlatOrchestrator.__init__() got an unexpected keyword argument 'execution_logger'`

- [ ] **Step 3: Add execution_logger to BaseOrchestrator**

In `src/axonflow/core/workflow.py`, update `BaseOrchestrator.__init__` to accept an optional `execution_logger`:

```python
class BaseOrchestrator(ABC):
    """编排器抽象基类 — 所有协作模式的公共接口"""

    ORCHESTRATOR_ID = "__orchestrator__"

    def __init__(
        self,
        config: WorkflowConfig,
        agent_registry: AgentRegistry,
        message_bus: MessageBus,
        execution_logger: ExecutionLogger | None = None,
        **kwargs,
    ) -> None:
        self.config = config
        self.agents = agent_registry
        self.message_bus = message_bus
        self.execution_logger = execution_logger
```

Add import at the top of `workflow.py`:

```python
from axonflow.observability.execution_log import ExecutionLogEntry, ExecutionLogger
```

- [ ] **Step 4: Add _log_routing and _log_agent_message helpers to BaseOrchestrator**

Add these methods to `BaseOrchestrator` (after the `_dispatch` method):

```python
    def _log_routing(
        self,
        workflow_id: str,
        source: str,
        targets: list[str],
        reason: str,
    ) -> None:
        """记录路由决策"""
        if self.execution_logger is None:
            return
        from datetime import datetime, timezone

        entry = ExecutionLogEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            workflow_id=workflow_id,
            agent_id=self.ORCHESTRATOR_ID,
            action="routing",
            tool_name=None,
            arguments=None,
            result=None,
            error=None,
            round=0,
            routing={
                "source": source,
                "targets": targets,
                "reason": reason,
            },
        )
        self.execution_logger.log(entry)

    def _log_agent_message(
        self,
        workflow_id: str,
        sender: str,
        receiver: str,
        msg_type: str,
        payload_keys: list[str],
        message_id: str,
    ) -> None:
        """记录 Agent 间消息传递"""
        if self.execution_logger is None:
            return
        from datetime import datetime, timezone

        entry = ExecutionLogEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            workflow_id=workflow_id,
            agent_id=self.ORCHESTRATOR_ID,
            action="agent_message",
            tool_name=None,
            arguments=None,
            result=None,
            error=None,
            round=0,
            agent_message={
                "sender": sender,
                "receiver": receiver,
                "msg_type": msg_type,
                "payload_keys": payload_keys,
                "message_id": message_id,
            },
        )
        self.execution_logger.log(entry)
```

- [ ] **Step 5: Instrument _dispatch to log agent_message events**

Update `BaseOrchestrator._dispatch()` to log after sending:

```python
    async def _dispatch(
        self,
        target_id: str,
        payload: dict,
        workflow_id: str,
        step_id: str,
        parent_id: str = "",
    ) -> None:
        """发送任务消息给指定 Agent"""
        msg = Message(
            sender=self.ORCHESTRATOR_ID,
            receiver=target_id,
            type=MessageType.TASK_REQUEST,
            payload=payload,
            workflow_id=workflow_id,
            step_id=step_id,
            parent_message_id=parent_id,
        )
        await self.message_bus.send(msg)

        # ---- Replay: log agent message ----
        self._log_agent_message(
            workflow_id=workflow_id,
            sender=self.ORCHESTRATOR_ID,
            receiver=target_id,
            msg_type=MessageType.TASK_REQUEST.value,
            payload_keys=list(payload.keys()),
            message_id=msg.id,
        )
```

- [ ] **Step 6: Instrument FlatOrchestrator.execute to log routing decisions**

In `FlatOrchestrator.execute()`, after the `_resolve_next()` call (around line 252), add routing logging:

```python
            # ---- 常规路由 ----
            next_targets = self._resolve_next(event)

            # ---- Replay: log routing decision ----
            if next_targets:
                self._log_routing(
                    workflow_id=workflow_id,
                    source=event.sender,
                    targets=[t[0] for t in next_targets],
                    reason="default_route",
                )
```

Also log when a terminal condition is met (around line 204):

```python
            # 检查终止条件
            if self._is_terminal(event):
                # ---- Replay: log terminal routing ----
                self._log_routing(
                    workflow_id=workflow_id,
                    source=event.sender,
                    targets=[],
                    reason="terminal_condition_met",
                )
```

Also log when fan-in/join dispatches (around line 240-247):

```python
                    if ready:
                        # 合并所有已收集的 payload
                        merged_payload: dict = {}
                        for agent_id, p in join_pending[join_target].items():
                            merged_payload[agent_id] = p

                        # ---- Replay: log fan-in routing ----
                        self._log_routing(
                            workflow_id=workflow_id,
                            source=event.sender,
                            targets=[join_target],
                            reason=f"fan_in_join_{cfg.strategy}",
                        )

                        await self._dispatch(
                            target_id=join_target,
                            ...
                        )
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `python -m pytest tests/unit/test_replay_log.py -v`
Expected: ALL PASS

- [ ] **Step 8: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: ALL tests PASS (existing orchestrator tests should be unaffected since `execution_logger` defaults to `None`)

- [ ] **Step 9: Commit**

```bash
git add src/axonflow/core/workflow.py tests/unit/test_replay_log.py
git commit -m "feat: log routing decisions and agent messages in orchestrator for workflow replay"
```

---

### Task 4: Wire ExecutionLogger through engine and orchestrator factory

**Files:**
- Modify: `src/axonflow/engine.py:316-323`
- Modify: `src/axonflow/core/orchestrator_factory.py:87-92` (fix fallback branch missing `**kwargs`)

`create_orchestrator()` already uses `**kwargs` to forward extra arguments, so no signature change is needed. However, the fallback branch at line 88-92 does NOT pass `**kwargs` — this is a bug that needs fixing.

- [ ] **Step 1: Fix orchestrator_factory.py fallback branch**

In `src/axonflow/core/orchestrator_factory.py`, fix the fallback at line 87-92 to pass `**kwargs`:

```python
    logger.warning("orchestrator_factory.unknown_mode", mode=mode, fallback="flat")
    return FlatOrchestrator(
        config=config,
        agent_registry=agent_registry,
        message_bus=message_bus,
        **kwargs,
    )
```

- [ ] **Step 2: Update engine.py run_workflow to pass execution_logger**

In `AxonFlowEngine.run_workflow()` (line 316-323), pass `self._execution_logger` to `create_orchestrator` via kwargs:

```python
        orchestrator = create_orchestrator(
            config=wf_config,
            agent_registry=self._agent_registry,
            message_bus=self._message_bus,
            llm_gateway=self._llm_gateway,
            execution_logger=self._execution_logger,
        )
```

- [ ] **Step 3: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: ALL tests PASS

- [ ] **Step 4: Commit**

```bash
git add src/axonflow/engine.py src/axonflow/core/orchestrator_factory.py
git commit -m "feat: wire ExecutionLogger to orchestrator for replay log support"
```

---

### Task 5: Add agent_message logging for received messages in FlatOrchestrator

**Files:**
- Modify: `src/axonflow/core/workflow.py:186-201`
- Test: `tests/unit/test_replay_log.py`

- [ ] **Step 1: Write failing test**

Add to `TestOrchestratorReplayLogging` in `tests/unit/test_replay_log.py`:

```python
    @pytest.mark.asyncio
    async def test_received_message_logged(self, tmp_path):
        """Orchestrator should log agent_message when receiving a response from an agent"""
        # (Same setup as test_routing_event_logged)
        # Assert that agent_message events include both sent and received messages
        # Received messages should have msg_type "task_response"
        exec_logger = ExecutionLogger(workspace_dir=str(tmp_path))
        bus = InMemoryMessageBus()

        wf_config = WorkflowConfig(
            id="wf-recv-test",
            name="Recv Test",
            agents=["agent-a"],
            trigger=TriggerConfig(type="manual"),
            flow=FlowConfig(
                entry="agent-a",
                routes={},
                terminate_on=[{"agent": "agent-a", "status": "success"}],
                max_iterations=5,
                timeout=10,
            ),
        )

        agent_a = _make_agent(exec_logger)
        agent_a.id = "agent-a"
        registry = AgentRegistry()
        registry.register(agent_a)

        orchestrator = FlatOrchestrator(
            config=wf_config,
            agent_registry=registry,
            message_bus=bus,
            execution_logger=exec_logger,
        )

        async def simulate():
            msg = await bus.receive("agent-a", block_ms=2000)
            if msg:
                reply = msg.reply(payload={"status": "success", "content": "done"})
                await bus.send(reply)

        import asyncio
        sim = asyncio.create_task(simulate())
        result = await orchestrator.execute("test")
        await sim

        msg_events = exec_logger.get_entries(action="agent_message")
        # At least 1 sent (dispatch) + 1 received (response)
        sent = [e for e in msg_events if e.agent_message["msg_type"] == "task_request"]
        received = [e for e in msg_events if e.agent_message["msg_type"] == "task_response"]
        assert len(sent) >= 1
        assert len(received) >= 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_replay_log.py::TestOrchestratorReplayLogging::test_received_message_logged -v`
Expected: FAIL — no received message events logged yet

- [ ] **Step 3: Add received-message logging in FlatOrchestrator.execute()**

In `FlatOrchestrator.execute()`, right after the `event = await self.message_bus.receive(...)` block (around line 186-192), log the received event:

```python
            event = await self.message_bus.receive(self.ORCHESTRATOR_ID, block_ms=5000)
            if event is None:
                continue

            # ---- Replay: log received agent message ----
            self._log_agent_message(
                workflow_id=workflow_id,
                sender=event.sender,
                receiver=self.ORCHESTRATOR_ID,
                msg_type=event.type.value,
                payload_keys=list(event.payload.keys()),
                message_id=event.id,
            )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/unit/test_replay_log.py -v`
Expected: ALL PASS

- [ ] **Step 5: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: ALL tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/axonflow/core/workflow.py tests/unit/test_replay_log.py
git commit -m "feat: log received agent messages in orchestrator for complete replay trail"
```

---

### Task 6: Final verification and cleanup

- [ ] **Step 1: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: ALL tests PASS (should be 117 + new tests)

- [ ] **Step 2: Verify JSONL output format**

Manually inspect a generated JSONL log file to confirm all three new event types appear with correct structure. Run:

```bash
python -c "
import json
# Print a sample of each event type
sample = {
    'routing': {'source': 'coder', 'targets': ['tester'], 'reason': 'default_route'},
    'llm_summary': {'model': 'qwen3-32b', 'input_tokens': 500, 'output_tokens': 120, 'has_tool_calls': True, 'content_preview': 'I will create...'},
    'agent_message': {'sender': '__orchestrator__', 'receiver': 'coder', 'msg_type': 'task_request', 'payload_keys': ['task'], 'message_id': 'msg-001'},
}
for k, v in sample.items():
    print(json.dumps({'action': k, k: v}, ensure_ascii=False))
"
```

- [ ] **Step 3: Verify backward compatibility**

Confirm that the existing `_make_entry()` helper in `test_execution_log.py` still works without passing the new fields — the defaults should be `None`.

- [ ] **Step 4: Final commit (if any cleanup needed)**

Only if there are loose ends. Otherwise skip.
