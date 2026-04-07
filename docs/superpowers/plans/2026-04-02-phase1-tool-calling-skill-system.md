# Phase 1: Tool Calling 闭环 + Skill 系统 + 执行日志 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 AxonFlow Agent 能真正调用工具（tool calling 闭环）、加载高阶策略（skill 系统）、并记录所有执行过程（执行日志），构成 Phase 2 自举工作流的基础。

**Architecture:** 三个子系统协同工作——(A) LLMGateway 解析 tool_calls，BaseAgent 实现多轮工具调用循环；(B) Skill 系统通过 loader 加载 SKILL.md 并注入 system prompt；(C) ExecutionLogger 双写（内存+JSONL）记录所有 tool 调用和错误。子系统 C 被 A 集成使用，B 独立于 A/C。

**Tech Stack:** Python 3.11+, asyncio, Pydantic, structlog, pytest + pytest-asyncio

---

## File Map

### Files to Create

| File | Responsibility |
|------|---------------|
| `src/axonflow/observability/execution_log.py` | ExecutionLogEntry dataclass + ExecutionLogger (dual-write: memory + JSONL) |
| `tests/unit/test_execution_log.py` | ExecutionLogger 单元测试 |
| `tests/unit/test_tool_calling.py` | Tool calling 闭环测试（mock LLM） |
| `tests/unit/test_skill_loader.py` | Skill 加载、@script 替换、边界处理测试 |
| `config/skills/code-review/SKILL.md` | 示例 skill：代码审查指引 |
| `config/skills/code-review/scripts/lint.sh` | 示例脚本 |

### Files to Modify

| File | What Changes |
|------|-------------|
| `src/axonflow/llm/gateway.py:26-33` | LLMResponse 加 `tool_calls` 字段 |
| `src/axonflow/llm/gateway.py:187-207` | chat() 解析 `msg.tool_calls` 并填入 LLMResponse |
| `src/axonflow/tools/base.py:81-100` | ToolRegistry.execute() 改签名为 `(tool_name, arguments: dict)` |
| `src/axonflow/core/agent.py:139-193` | handle_message() 实现多轮工具调用循环 |
| `src/axonflow/core/agent.py:46-53` | BaseAgent.__init__() 接受 execution_logger 参数 |
| `src/axonflow/config/models.py:70-91` | AgentConfig 加 `skills: list[str]` 字段 |
| `src/axonflow/config/loader.py` | 新增 `load_skill_content()` 和 `_resolve_script_refs()` |
| `src/axonflow/llm/prompt_builder.py:30-69` | system prompt 组装加入 skill 内容 |
| `src/axonflow/engine.py:81-128` | initialize() 创建 ExecutionLogger 并传给 Agent |

---

## Task 1: ExecutionLogger — 数据模型与双写

**Files:**
- Create: `src/axonflow/observability/execution_log.py`
- Create: `tests/unit/test_execution_log.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_execution_log.py`:

```python
"""ExecutionLogger 单元测试"""

from __future__ import annotations

import json

import pytest

from axonflow.observability.execution_log import ExecutionLogEntry, ExecutionLogger


def _make_entry(**overrides) -> ExecutionLogEntry:
    defaults = {
        "timestamp": "2026-04-02T12:00:00Z",
        "workflow_id": "wf-001",
        "agent_id": "agent-coder",
        "action": "tool_call",
        "tool_name": "shell_exec",
        "arguments": {"command": "echo hello"},
        "result": "hello\n",
        "error": None,
        "round": 1,
    }
    defaults.update(overrides)
    return ExecutionLogEntry(**defaults)


class TestExecutionLogEntry:
    def test_fields(self):
        entry = _make_entry()
        assert entry.workflow_id == "wf-001"
        assert entry.action == "tool_call"
        assert entry.round == 1

    def test_error_entry(self):
        entry = _make_entry(action="tool_error", result=None, error="timeout")
        assert entry.action == "tool_error"
        assert entry.error == "timeout"


class TestExecutionLogger:
    def test_log_and_get_entries(self):
        logger = ExecutionLogger(workspace_dir="/tmp/test-axonflow-logs")
        entry = _make_entry()
        logger.log(entry)
        assert len(logger.get_entries()) == 1
        assert logger.get_entries()[0] is entry

    def test_filter_by_workflow_id(self):
        logger = ExecutionLogger(workspace_dir="/tmp/test-axonflow-logs")
        logger.log(_make_entry(workflow_id="wf-001"))
        logger.log(_make_entry(workflow_id="wf-002"))
        logger.log(_make_entry(workflow_id="wf-001"))

        results = logger.get_entries(workflow_id="wf-001")
        assert len(results) == 2

    def test_filter_by_agent_id(self):
        logger = ExecutionLogger(workspace_dir="/tmp/test-axonflow-logs")
        logger.log(_make_entry(agent_id="agent-a"))
        logger.log(_make_entry(agent_id="agent-b"))

        results = logger.get_entries(agent_id="agent-a")
        assert len(results) == 1

    def test_filter_by_action(self):
        logger = ExecutionLogger(workspace_dir="/tmp/test-axonflow-logs")
        logger.log(_make_entry(action="tool_call"))
        logger.log(_make_entry(action="tool_error"))
        logger.log(_make_entry(action="llm_error"))

        results = logger.get_entries(action="tool_error")
        assert len(results) == 1

    def test_combined_filters(self):
        logger = ExecutionLogger(workspace_dir="/tmp/test-axonflow-logs")
        logger.log(_make_entry(workflow_id="wf-001", agent_id="a", action="tool_call"))
        logger.log(_make_entry(workflow_id="wf-001", agent_id="b", action="tool_call"))
        logger.log(_make_entry(workflow_id="wf-002", agent_id="a", action="tool_error"))

        results = logger.get_entries(workflow_id="wf-001", agent_id="a")
        assert len(results) == 1

    def test_disk_write(self, tmp_path):
        logger = ExecutionLogger(workspace_dir=str(tmp_path))
        entry = _make_entry(workflow_id="wf-disk-test")
        logger.log(entry)

        log_file = tmp_path / "logs" / "execution-wf-disk-test.jsonl"
        assert log_file.exists()

        lines = log_file.read_text().strip().split("\n")
        assert len(lines) == 1

        data = json.loads(lines[0])
        assert data["workflow_id"] == "wf-disk-test"
        assert data["action"] == "tool_call"
        assert data["tool_name"] == "shell_exec"

    def test_disk_write_appends(self, tmp_path):
        logger = ExecutionLogger(workspace_dir=str(tmp_path))
        logger.log(_make_entry(workflow_id="wf-append", round=1))
        logger.log(_make_entry(workflow_id="wf-append", round=2))

        log_file = tmp_path / "logs" / "execution-wf-append.jsonl"
        lines = log_file.read_text().strip().split("\n")
        assert len(lines) == 2

    def test_result_truncation(self, tmp_path):
        long_result = "x" * 5000
        logger = ExecutionLogger(workspace_dir=str(tmp_path))
        logger.log(_make_entry(workflow_id="wf-trunc", result=long_result))

        log_file = tmp_path / "logs" / "execution-wf-trunc.jsonl"
        data = json.loads(log_file.read_text().strip())
        assert len(data["result"]) <= 2000
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/test_execution_log.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'axonflow.observability.execution_log'`

- [ ] **Step 3: Implement ExecutionLogEntry and ExecutionLogger**

Create `src/axonflow/observability/execution_log.py`:

```python
"""执行日志 — 记录 tool 调用、错误、异常"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import structlog

logger = structlog.get_logger()

_MAX_RESULT_LENGTH = 2000


@dataclass
class ExecutionLogEntry:
    """单条执行日志"""

    timestamp: str  # ISO 8601
    workflow_id: str
    agent_id: str
    action: str  # tool_call | tool_error | llm_error | skill_error
    tool_name: str | None
    arguments: dict | None
    result: str | None
    error: str | None
    round: int


class ExecutionLogger:
    """执行日志记录器 — 双写：内存 + JSONL 磁盘"""

    def __init__(self, workspace_dir: str = "./workspace") -> None:
        self._entries: list[ExecutionLogEntry] = []
        self._workspace_dir = Path(workspace_dir)

    def log(self, entry: ExecutionLogEntry) -> None:
        """记录一条执行日志"""
        self._entries.append(entry)
        self._write_to_disk(entry)

    def get_entries(
        self,
        workflow_id: str | None = None,
        agent_id: str | None = None,
        action: str | None = None,
    ) -> list[ExecutionLogEntry]:
        """按条件过滤查询"""
        results = self._entries
        if workflow_id is not None:
            results = [e for e in results if e.workflow_id == workflow_id]
        if agent_id is not None:
            results = [e for e in results if e.agent_id == agent_id]
        if action is not None:
            results = [e for e in results if e.action == action]
        return results

    def _write_to_disk(self, entry: ExecutionLogEntry) -> None:
        """追加写入 JSONL 文件"""
        try:
            log_dir = self._workspace_dir / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file = log_dir / f"execution-{entry.workflow_id}.jsonl"

            data = asdict(entry)
            # 截断过长的 result
            if data.get("result") and len(data["result"]) > _MAX_RESULT_LENGTH:
                data["result"] = data["result"][:_MAX_RESULT_LENGTH]

            with open(log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(data, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error("execution_log.write_failed", error=str(e))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/unit/test_execution_log.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/axonflow/observability/execution_log.py tests/unit/test_execution_log.py
git commit -m "feat: add ExecutionLogger with dual-write (memory + JSONL)"
```

---

## Task 2: LLMResponse — 添加 tool_calls 字段

**Files:**
- Modify: `src/axonflow/llm/gateway.py:26-33`
- Modify: `tests/conftest.py:9` (import 会自动兼容)

- [ ] **Step 1: Write the failing test**

We'll add a test directly in `tests/unit/test_tool_calling.py` (create file). This test checks that `LLMResponse` accepts a `tool_calls` field:

Create `tests/unit/test_tool_calling.py`:

```python
"""Tool Calling 闭环测试"""

from __future__ import annotations

from axonflow.llm.gateway import LLMResponse


class TestLLMResponseToolCalls:
    def test_tool_calls_default_none(self):
        resp = LLMResponse(content="hello", model="test-model")
        assert resp.tool_calls is None

    def test_tool_calls_with_data(self):
        tc = [
            {
                "id": "call_001",
                "function": {"name": "shell_exec", "arguments": '{"command": "ls"}'},
                "type": "function",
            }
        ]
        resp = LLMResponse(content="", model="test-model", tool_calls=tc)
        assert resp.tool_calls is not None
        assert len(resp.tool_calls) == 1
        assert resp.tool_calls[0]["function"]["name"] == "shell_exec"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_tool_calling.py::TestLLMResponseToolCalls -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'tool_calls'`

- [ ] **Step 3: Add tool_calls field to LLMResponse**

In `src/axonflow/llm/gateway.py`, modify the `LLMResponse` dataclass:

```python
@dataclass
class LLMResponse:
    """LLM 调用结果"""

    content: str
    model: str
    tool_calls: list[dict] | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_tool_calling.py::TestLLMResponseToolCalls -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/axonflow/llm/gateway.py tests/unit/test_tool_calling.py
git commit -m "feat: add tool_calls field to LLMResponse"
```

---

## Task 3: LLMGateway.chat() — 解析 tool_calls

**Files:**
- Modify: `src/axonflow/llm/gateway.py:187-207`
- Test: `tests/unit/test_tool_calling.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_tool_calling.py`:

```python
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from axonflow.config.models import ModelConfig
from axonflow.llm.gateway import LLMGateway


class TestGatewayParsesToolCalls:
    @pytest.mark.asyncio
    async def test_chat_returns_tool_calls_when_present(self):
        """LLM 返回 tool_calls 时，chat() 应解析并填入 LLMResponse"""
        gateway = LLMGateway(
            default_model=ModelConfig(provider="openai", name="test-model"),
        )

        # Mock litellm.acompletion 返回带 tool_calls 的响应
        mock_tool_call = MagicMock()
        mock_tool_call.id = "call_abc123"
        mock_tool_call.type = "function"
        mock_tool_call.function.name = "shell_exec"
        mock_tool_call.function.arguments = '{"command": "echo hi"}'

        mock_msg = MagicMock()
        mock_msg.content = None
        mock_msg.tool_calls = [mock_tool_call]
        mock_msg.reasoning_content = None

        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 10
        mock_usage.completion_tokens = 5

        mock_choice = MagicMock()
        mock_choice.message = mock_msg

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = mock_usage

        with patch("litellm.acompletion", new_callable=AsyncMock, return_value=mock_response):
            result = await gateway.chat(messages=[{"role": "user", "content": "test"}])

        assert result.tool_calls is not None
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0]["id"] == "call_abc123"
        assert result.tool_calls[0]["function"]["name"] == "shell_exec"
        assert result.tool_calls[0]["function"]["arguments"] == '{"command": "echo hi"}'

    @pytest.mark.asyncio
    async def test_chat_returns_none_tool_calls_when_absent(self):
        """LLM 没有返回 tool_calls 时，chat() 的 tool_calls 应为 None"""
        gateway = LLMGateway(
            default_model=ModelConfig(provider="openai", name="test-model"),
        )

        mock_msg = MagicMock()
        mock_msg.content = "Hello world"
        mock_msg.tool_calls = None

        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 10
        mock_usage.completion_tokens = 5

        mock_choice = MagicMock()
        mock_choice.message = mock_msg

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = mock_usage

        with patch("litellm.acompletion", new_callable=AsyncMock, return_value=mock_response):
            result = await gateway.chat(messages=[{"role": "user", "content": "test"}])

        assert result.tool_calls is None
        assert result.content == "Hello world"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/test_tool_calling.py::TestGatewayParsesToolCalls -v`
Expected: FAIL — `result.tool_calls` is `None` even when LLM returned tool_calls (current code ignores them)

- [ ] **Step 3: Modify chat() to parse tool_calls**

In `src/axonflow/llm/gateway.py`, replace the section after `msg = response.choices[0].message` (lines 187-207):

```python
            msg = response.choices[0].message
            content = msg.content or ""

            # 部分模型（如 Qwen3 thinking 模式）将内容放在 reasoning_content 中
            if not content.strip() and hasattr(msg, "reasoning_content") and msg.reasoning_content:
                content = msg.reasoning_content

            # 解析 tool_calls
            tool_calls = None
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                tool_calls = [
                    {
                        "id": tc.id,
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                        "type": tc.type,
                    }
                    for tc in msg.tool_calls
                ]

            logger.info(
                "llm.call_completed",
                model=model_str,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                has_tool_calls=tool_calls is not None,
            )

            return LLMResponse(
                content=content,
                model=model_str,
                tool_calls=tool_calls,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=input_tokens + output_tokens,
            )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/unit/test_tool_calling.py -v`
Expected: All PASS

- [ ] **Step 5: Run full test suite to check for regressions**

Run: `python -m pytest tests/ -v`
Expected: All 75+ tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/axonflow/llm/gateway.py tests/unit/test_tool_calling.py
git commit -m "feat: parse tool_calls from LLM response in gateway.chat()"
```

---

## Task 4: ToolRegistry.execute() — 签名调整

**Files:**
- Modify: `src/axonflow/tools/base.py:81-100`
- Test: `tests/unit/test_tool_calling.py` (append)

The existing `ToolRegistry.execute()` uses `**kwargs`. The spec wants `execute(tool_name, arguments: dict)` so that the agent loop can pass a parsed dict directly. We change the signature to accept `arguments: dict` and spread it internally.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_tool_calling.py`:

```python
from axonflow.tools.base import ToolRegistry, ToolResult


class TestToolRegistryExecute:
    @pytest.mark.asyncio
    async def test_execute_known_tool(self):
        """已注册的工具应正常执行"""
        registry = ToolRegistry()

        # 创建一个简单的 mock tool
        mock_tool = MagicMock()
        mock_tool.name = "test_tool"
        mock_tool.execute = AsyncMock(return_value=ToolResult(success=True, output="ok"))

        registry.register(mock_tool)

        result = await registry.execute("test_tool", arguments={"key": "value"})
        assert result.success is True
        assert result.output == "ok"
        mock_tool.execute.assert_called_once_with(key="value")

    @pytest.mark.asyncio
    async def test_execute_unknown_tool(self):
        """未注册的工具应返回错误 ToolResult"""
        registry = ToolRegistry()
        result = await registry.execute("nonexistent", arguments={})
        assert result.success is False
        assert "not found" in result.error.lower() or "Unknown" in result.error

    @pytest.mark.asyncio
    async def test_execute_tool_exception(self):
        """工具抛异常应被捕获并返回 error ToolResult"""
        registry = ToolRegistry()

        mock_tool = MagicMock()
        mock_tool.name = "boom_tool"
        mock_tool.execute = AsyncMock(side_effect=RuntimeError("kaboom"))

        registry.register(mock_tool)

        result = await registry.execute("boom_tool", arguments={"x": 1})
        assert result.success is False
        assert "kaboom" in result.error
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_tool_calling.py::TestToolRegistryExecute -v`
Expected: FAIL — `TypeError: execute() got an unexpected keyword argument 'arguments'`

- [ ] **Step 3: Change ToolRegistry.execute() signature**

In `src/axonflow/tools/base.py`, replace the existing `execute` method (lines 81-100):

```python
    async def execute(self, tool_name: str, arguments: dict | None = None) -> ToolResult:
        """根据工具名称调度执行

        Args:
            tool_name: 工具名称
            arguments: 工具参数字典，会解包为 **kwargs 传给 tool.execute()
        """
        tool = self._tools.get(tool_name)
        if tool is None:
            return ToolResult(
                success=False,
                error=f"Unknown tool: {tool_name}. Available: {', '.join(self._tools.keys())}",
            )
        try:
            args = arguments or {}
            logger.info("tool.executing", name=tool_name, args=args)
            result = await tool.execute(**args)
            logger.info("tool.completed", name=tool_name, success=result.success)
            return result
        except Exception as e:
            logger.error("tool.failed", name=tool_name, error=str(e))
            return ToolResult(success=False, error=f"Tool execution failed: {e}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/unit/test_tool_calling.py::TestToolRegistryExecute -v`
Expected: All PASS

- [ ] **Step 5: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: All tests PASS (existing tests that call `registry.execute(name, **kwargs)` — check there are none that break)

- [ ] **Step 6: Commit**

```bash
git add src/axonflow/tools/base.py tests/unit/test_tool_calling.py
git commit -m "feat: ToolRegistry.execute() accepts arguments dict for dispatch"
```

---

## Task 5: BaseAgent.handle_message() — 多轮工具调用循环

**Files:**
- Modify: `src/axonflow/core/agent.py:46-53` (constructor)
- Modify: `src/axonflow/core/agent.py:139-193` (handle_message)
- Modify: `src/axonflow/core/agent.py:325-360` (create_agent factory)
- Test: `tests/unit/test_tool_calling.py` (append)

This is the core task — wiring up the tool calling loop.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_tool_calling.py`:

```python
import json

from axonflow.config.models import AgentConfig, ModelConfig
from axonflow.core.agent import BaseAgent, create_agent
from axonflow.core.message import Message, MessageType
from axonflow.messaging.memory_bus import InMemoryMessageBus
from axonflow.observability.execution_log import ExecutionLogger


def _make_message(task: str = "test task") -> Message:
    return Message(
        sender="user",
        receiver="test-agent",
        type=MessageType.TASK_REQUEST,
        payload={"task": task},
        workflow_id="wf-test",
    )


def _make_agent_config(**overrides) -> AgentConfig:
    defaults = {
        "id": "test-agent",
        "name": "Test Agent",
        "role": "You are a test agent.",
        "model": ModelConfig(provider="openai", name="test-model"),
        "tools": ["shell_exec"],
    }
    defaults.update(overrides)
    return AgentConfig(**defaults)


class TestToolCallingLoop:
    @pytest.mark.asyncio
    async def test_single_tool_call_then_text(self):
        """LLM 先返回 tool_call，执行后 LLM 返回 text → 成功"""
        bus = InMemoryMessageBus()
        registry = ToolRegistry()
        exec_logger = ExecutionLogger(workspace_dir="/tmp/test-tc-loop")

        mock_tool = MagicMock()
        mock_tool.name = "shell_exec"
        mock_tool.execute = AsyncMock(return_value=ToolResult(success=True, output="hello\n"))
        registry.register(mock_tool)

        gateway = MagicMock()

        # 第 1 次调用: LLM 返回 tool_call
        resp1 = LLMResponse(
            content="",
            model="test-model",
            tool_calls=[{
                "id": "call_001",
                "function": {"name": "shell_exec", "arguments": '{"command": "echo hello"}'},
                "type": "function",
            }],
        )
        # 第 2 次调用: LLM 看到工具结果后返回 text
        resp2 = LLMResponse(content="Done! Output was hello.", model="test-model")

        gateway.chat = AsyncMock(side_effect=[resp1, resp2])

        agent = BaseAgent(
            config=_make_agent_config(),
            message_bus=bus,
            llm_gateway=gateway,
            tool_registry=registry,
            execution_logger=exec_logger,
        )

        result = await agent.handle_message(_make_message())

        assert result["status"] == "success"
        assert "hello" in result["content"].lower() or "Done" in result["content"]

        # 验证工具被调用
        mock_tool.execute.assert_called_once_with(command="echo hello")

        # 验证 LLM 被调用 2 次
        assert gateway.chat.call_count == 2

        # 验证第 2 次调用的 messages 中包含 tool result
        second_call_messages = gateway.chat.call_args_list[1][1]["messages"]
        tool_msg = [m for m in second_call_messages if m.get("role") == "tool"]
        assert len(tool_msg) == 1
        assert tool_msg[0]["tool_call_id"] == "call_001"

        # 验证 execution logger 记录了 tool_call
        entries = exec_logger.get_entries(action="tool_call")
        assert len(entries) == 1

    @pytest.mark.asyncio
    async def test_unknown_tool_error_fed_back(self):
        """LLM 请求不存在的工具 → error 回填给 LLM → LLM 产出 text"""
        bus = InMemoryMessageBus()
        registry = ToolRegistry()
        exec_logger = ExecutionLogger(workspace_dir="/tmp/test-tc-unknown")

        gateway = MagicMock()

        resp1 = LLMResponse(
            content="",
            model="test-model",
            tool_calls=[{
                "id": "call_bad",
                "function": {"name": "nonexistent_tool", "arguments": "{}"},
                "type": "function",
            }],
        )
        resp2 = LLMResponse(content="Sorry, I used the wrong tool.", model="test-model")

        gateway.chat = AsyncMock(side_effect=[resp1, resp2])

        agent = BaseAgent(
            config=_make_agent_config(),
            message_bus=bus,
            llm_gateway=gateway,
            tool_registry=registry,
            execution_logger=exec_logger,
        )

        result = await agent.handle_message(_make_message())
        assert result["status"] == "success"

        # 验证 tool_error 被记录
        entries = exec_logger.get_entries(action="tool_error")
        assert len(entries) == 1

    @pytest.mark.asyncio
    async def test_json_parse_error_fed_back(self):
        """LLM 返回无效 JSON 参数 → error 回填 → LLM 纠正"""
        bus = InMemoryMessageBus()
        registry = ToolRegistry()
        exec_logger = ExecutionLogger(workspace_dir="/tmp/test-tc-json")

        mock_tool = MagicMock()
        mock_tool.name = "shell_exec"
        mock_tool.execute = AsyncMock(return_value=ToolResult(success=True, output="ok"))
        registry.register(mock_tool)

        gateway = MagicMock()

        resp1 = LLMResponse(
            content="",
            model="test-model",
            tool_calls=[{
                "id": "call_bad_json",
                "function": {"name": "shell_exec", "arguments": "not valid json!!!"},
                "type": "function",
            }],
        )
        resp2 = LLMResponse(content="Fixed my approach.", model="test-model")

        gateway.chat = AsyncMock(side_effect=[resp1, resp2])

        agent = BaseAgent(
            config=_make_agent_config(),
            message_bus=bus,
            llm_gateway=gateway,
            tool_registry=registry,
            execution_logger=exec_logger,
        )

        result = await agent.handle_message(_make_message())
        assert result["status"] == "success"

        entries = exec_logger.get_entries(action="tool_error")
        assert len(entries) == 1

    @pytest.mark.asyncio
    async def test_max_rounds_exceeded(self):
        """10 轮 tool_calls 后仍无 content → 返回 error"""
        bus = InMemoryMessageBus()
        registry = ToolRegistry()
        exec_logger = ExecutionLogger(workspace_dir="/tmp/test-tc-max")

        mock_tool = MagicMock()
        mock_tool.name = "shell_exec"
        mock_tool.execute = AsyncMock(return_value=ToolResult(success=True, output="ok"))
        registry.register(mock_tool)

        gateway = MagicMock()

        # 每轮都返回 tool_calls，没有 content
        endless_resp = LLMResponse(
            content="",
            model="test-model",
            tool_calls=[{
                "id": "call_loop",
                "function": {"name": "shell_exec", "arguments": '{"command": "echo loop"}'},
                "type": "function",
            }],
        )
        gateway.chat = AsyncMock(return_value=endless_resp)

        agent = BaseAgent(
            config=_make_agent_config(),
            message_bus=bus,
            llm_gateway=gateway,
            tool_registry=registry,
            execution_logger=exec_logger,
        )

        result = await agent.handle_message(_make_message())
        assert result["status"] == "error"
        assert "rounds" in result["error"].lower() or "exceeded" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_no_tool_calls_no_content_retries(self):
        """LLM 返回空（无 content 无 tool_calls）→ 重试 → 最终有 content"""
        bus = InMemoryMessageBus()
        registry = ToolRegistry()
        exec_logger = ExecutionLogger(workspace_dir="/tmp/test-tc-empty")

        gateway = MagicMock()

        empty_resp = LLMResponse(content="", model="test-model")
        good_resp = LLMResponse(content="Finally got it.", model="test-model")

        gateway.chat = AsyncMock(side_effect=[empty_resp, good_resp])

        agent = BaseAgent(
            config=_make_agent_config(),
            message_bus=bus,
            llm_gateway=gateway,
            tool_registry=registry,
            execution_logger=exec_logger,
        )

        result = await agent.handle_message(_make_message())
        assert result["status"] == "success"
        assert gateway.chat.call_count == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/test_tool_calling.py::TestToolCallingLoop -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'execution_logger'`

- [ ] **Step 3: Modify BaseAgent to accept execution_logger**

In `src/axonflow/core/agent.py`, update `BaseAgent.__init__()`:

```python
    def __init__(
        self,
        config: AgentConfig,
        message_bus: MessageBus,
        llm_gateway: LLMGateway,
        tool_registry: ToolRegistry,
        memory_store: MemoryStore | None = None,
        execution_logger: ExecutionLogger | None = None,
    ) -> None:
        self.config = config
        self.id = config.id
        self.name = config.name
        self.message_bus = message_bus
        self.llm_gateway = llm_gateway
        self.tool_registry = tool_registry
        self.state = AgentState.IDLE
        self.parameters: dict[str, Any] = config.parameters
        self.memory: MemoryStore = memory_store or InMemoryStore()
        self._contexts: dict[str, WorkflowContext] = {}
        self.execution_logger = execution_logger
```

Add the import at the top of the file:

```python
from axonflow.observability.execution_log import ExecutionLogEntry, ExecutionLogger
```

Also add `import json` and `from datetime import datetime, timezone` to the imports.

- [ ] **Step 4: Implement the multi-turn tool calling loop in handle_message()**

Replace `handle_message()` (lines 139-193) with:

```python
    async def handle_message(self, message: Message) -> dict:
        """处理消息的核心逻辑 — 含多轮工具调用循环

        1. 构建 Prompt（含记忆上下文）
        2. 循环：调用 LLM → 检查 tool_calls → 执行工具 → 回填结果 → 重新调用 LLM
        3. LLM 产出 text content 时结束循环
        """
        context = self.get_context(message.workflow_id)
        tool_schemas = self.tool_registry.get_schemas(self.config.tools)

        memories = await self._recall_memories(message)

        messages = PromptBuilder.build(
            agent_config=self.config,
            incoming_message=message,
            context=context,
            tool_schemas=tool_schemas if tool_schemas else None,
            memories=memories,
        )

        max_tool_rounds = 10
        for round_num in range(1, max_tool_rounds + 1):
            llm_response = await self.llm_gateway.chat(
                messages=messages,
                model_config=self.config.model,
                tools=tool_schemas if tool_schemas else None,
            )

            # Case 1: LLM 返回了 tool_calls
            if llm_response.tool_calls:
                # 追加 assistant message（含 tool_calls 信息）
                assistant_msg: dict[str, Any] = {"role": "assistant", "content": llm_response.content or ""}
                assistant_msg["tool_calls"] = llm_response.tool_calls
                messages.append(assistant_msg)

                # 逐个执行 tool call
                for tc in llm_response.tool_calls:
                    tc_id = tc["id"]
                    func_name = tc["function"]["name"]
                    func_args_raw = tc["function"]["arguments"]

                    # 解析 JSON 参数
                    try:
                        func_args = json.loads(func_args_raw) if isinstance(func_args_raw, str) else func_args_raw
                    except json.JSONDecodeError as e:
                        error_msg = f"Invalid JSON in tool arguments: {e}"
                        self._log_execution(
                            workflow_id=message.workflow_id,
                            action="tool_error",
                            tool_name=func_name,
                            arguments={"raw": func_args_raw[:500]},
                            error=error_msg,
                            round_num=round_num,
                        )
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc_id,
                            "content": f"Error: {error_msg}",
                        })
                        continue

                    # 执行工具
                    tool_result = await self.tool_registry.execute(func_name, arguments=func_args)

                    if tool_result.success:
                        result_content = tool_result.output or ""
                        self._log_execution(
                            workflow_id=message.workflow_id,
                            action="tool_call",
                            tool_name=func_name,
                            arguments=func_args,
                            result=result_content,
                            round_num=round_num,
                        )
                    else:
                        result_content = f"Error: {tool_result.error}"
                        self._log_execution(
                            workflow_id=message.workflow_id,
                            action="tool_error",
                            tool_name=func_name,
                            arguments=func_args,
                            error=tool_result.error,
                            round_num=round_num,
                        )

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc_id,
                        "content": result_content,
                    })

                continue  # 回到循环，让 LLM 看到工具结果

            # Case 2: LLM 返回了 text content（无 tool_calls）
            if llm_response.content and llm_response.content.strip():
                result = {
                    "status": "success",
                    "content": llm_response.content,
                    "model": llm_response.model,
                    "tokens_used": llm_response.total_tokens,
                }
                if context:
                    context.add_message(message)
                await self._store_memory(message, result)
                self.state = AgentState.RUNNING
                return result

            # Case 3: 既无 tool_calls 也无 content — 给 LLM 重试机会
            logger.warning(
                "agent.empty_llm_response",
                agent_id=self.id,
                round=round_num,
            )
            # 不 break，继续循环让 LLM 再试

        # 10 轮用尽
        self._log_execution(
            workflow_id=message.workflow_id,
            action="tool_error",
            tool_name=None,
            arguments=None,
            error="Max tool call rounds exceeded",
            round_num=max_tool_rounds,
        )
        return {
            "status": "error",
            "error": "Max tool call rounds exceeded",
        }

    def _log_execution(
        self,
        workflow_id: str,
        action: str,
        tool_name: str | None,
        arguments: dict | None,
        round_num: int,
        result: str | None = None,
        error: str | None = None,
    ) -> None:
        """记录执行日志（如果 logger 存在）"""
        if self.execution_logger is None:
            return
        entry = ExecutionLogEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            workflow_id=workflow_id,
            agent_id=self.id,
            action=action,
            tool_name=tool_name,
            arguments=arguments,
            result=result,
            error=error,
            round=round_num,
        )
        self.execution_logger.log(entry)
```

- [ ] **Step 5: Update create_agent() to accept and pass execution_logger**

In `src/axonflow/core/agent.py`, update the `create_agent()` function signature and body:

```python
def create_agent(
    config: AgentConfig,
    message_bus: MessageBus,
    llm_gateway: LLMGateway,
    tool_registry: ToolRegistry,
    memory_store: MemoryStore | None = None,
    execution_logger: ExecutionLogger | None = None,
) -> BaseAgent:
    """Agent 工厂方法 ..."""
    agent_cls: type[BaseAgent]

    if config.class_path:
        agent_cls = _import_agent_class(config.class_path)
    elif config.agent_type in _AGENT_TYPE_REGISTRY:
        agent_cls = _AGENT_TYPE_REGISTRY[config.agent_type]
    else:
        logger.warning(
            "agent_factory.unknown_type",
            agent_type=config.agent_type,
            fallback="BaseAgent",
        )
        agent_cls = BaseAgent

    return agent_cls(
        config=config,
        message_bus=message_bus,
        llm_gateway=llm_gateway,
        tool_registry=tool_registry,
        memory_store=memory_store,
        execution_logger=execution_logger,
    )
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/unit/test_tool_calling.py -v`
Expected: All PASS

- [ ] **Step 7: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: All tests PASS (existing tests create BaseAgent without execution_logger, which defaults to None — no breakage)

- [ ] **Step 8: Commit**

```bash
git add src/axonflow/core/agent.py tests/unit/test_tool_calling.py
git commit -m "feat: implement multi-turn tool calling loop in BaseAgent.handle_message()"
```

---

## Task 6: Engine — 创建 ExecutionLogger 并传递给 Agent

**Files:**
- Modify: `src/axonflow/engine.py:81-128` (initialize)
- Modify: `src/axonflow/engine.py:200-223` (_load_agents)

- [ ] **Step 1: Add ExecutionLogger import and creation in engine.py**

In `src/axonflow/engine.py`, add the import:

```python
from axonflow.observability.execution_log import ExecutionLogger
```

In `__init__()`, add:

```python
        self._execution_logger: ExecutionLogger | None = None
```

In `initialize()`, after `self._memory_store = InMemoryStore()` (line 116), add:

```python
        # 5.6 初始化执行日志
        self._execution_logger = ExecutionLogger(
            workspace_dir=self.config.workspace_dir,
        )
```

In `_load_agents()`, update the `create_agent()` call:

```python
            agent = create_agent(
                config=cfg,
                message_bus=self._message_bus,
                llm_gateway=self._llm_gateway,
                tool_registry=self._tool_registry,
                memory_store=self._memory_store,
                execution_logger=self._execution_logger,
            )
```

- [ ] **Step 2: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add src/axonflow/engine.py
git commit -m "feat: create ExecutionLogger in engine and pass to agents"
```

---

## Task 7: AgentConfig — 添加 skills 字段

**Files:**
- Modify: `src/axonflow/config/models.py:70-91`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_tool_calling.py` (or create a section — we'll use the skill loader test file for this):

Create `tests/unit/test_skill_loader.py`:

```python
"""Skill 系统测试"""

from __future__ import annotations

from axonflow.config.models import AgentConfig, ModelConfig


class TestAgentConfigSkills:
    def test_skills_default_empty(self):
        config = AgentConfig(id="a", name="A")
        assert config.skills == []

    def test_skills_from_yaml_data(self):
        config = AgentConfig(
            id="a",
            name="A",
            skills=["code-review", "tdd"],
        )
        assert config.skills == ["code-review", "tdd"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_skill_loader.py::TestAgentConfigSkills -v`
Expected: FAIL — `unexpected keyword argument 'skills'`

- [ ] **Step 3: Add skills field to AgentConfig**

In `src/axonflow/config/models.py`, add to `AgentConfig`:

```python
    skills: list[str] = Field(default_factory=list)  # Skill 名称列表，如 ["code-review", "tdd"]
```

Add it after the `persona` field (line 90).

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_skill_loader.py::TestAgentConfigSkills -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/axonflow/config/models.py tests/unit/test_skill_loader.py
git commit -m "feat: add skills field to AgentConfig"
```

---

## Task 8: Skill Loader — load_skill_content() 和 _resolve_script_refs()

**Files:**
- Modify: `src/axonflow/config/loader.py`
- Create: `config/skills/code-review/SKILL.md`
- Create: `config/skills/code-review/scripts/lint.sh`
- Test: `tests/unit/test_skill_loader.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_skill_loader.py`:

```python
from pathlib import Path

from axonflow.config.loader import load_skill_content, _resolve_script_refs


class TestResolveScriptRefs:
    def test_replaces_existing_script(self, tmp_path):
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()
        (scripts_dir / "lint.sh").write_text("#!/bin/bash\necho lint")

        content = "Run: @script:lint.sh {file}"
        result = _resolve_script_refs(content, scripts_dir)
        assert "@script:" not in result
        assert "shell_exec" in result
        assert str((scripts_dir / "lint.sh").resolve()) in result

    def test_preserves_missing_script(self, tmp_path):
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()

        content = "Run: @script:missing.sh"
        result = _resolve_script_refs(content, scripts_dir)
        assert "@script:missing.sh" in result  # 保留原始文本

    def test_multiple_refs(self, tmp_path):
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()
        (scripts_dir / "a.sh").write_text("#!/bin/bash")
        (scripts_dir / "b.sh").write_text("#!/bin/bash")

        content = "First @script:a.sh then @script:b.sh then @script:c.sh"
        result = _resolve_script_refs(content, scripts_dir)
        assert "@script:a.sh" not in result
        assert "@script:b.sh" not in result
        assert "@script:c.sh" in result  # c.sh 不存在，保留


class TestLoadSkillContent:
    def test_load_directory_format(self, tmp_path):
        skill_dir = tmp_path / "code-review"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# Code Review\nDo careful review.")

        result = load_skill_content(tmp_path, ["code-review"])
        assert "Code Review" in result
        assert "careful review" in result

    def test_load_single_file_format(self, tmp_path):
        (tmp_path / "gap-analysis.md").write_text("# Gap Analysis\nFind the gaps.")

        result = load_skill_content(tmp_path, ["gap-analysis"])
        assert "Gap Analysis" in result

    def test_directory_preferred_over_single_file(self, tmp_path):
        # 同时存在目录和单文件，目录优先
        skill_dir = tmp_path / "review"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("Directory version")
        (tmp_path / "review.md").write_text("File version")

        result = load_skill_content(tmp_path, ["review"])
        assert "Directory version" in result
        assert "File version" not in result

    def test_load_with_script_refs(self, tmp_path):
        skill_dir = tmp_path / "lint-skill"
        scripts_dir = skill_dir / "scripts"
        scripts_dir.mkdir(parents=True)
        (scripts_dir / "run.sh").write_text("#!/bin/bash\necho lint")
        (skill_dir / "SKILL.md").write_text("Execute @script:run.sh to lint.")

        result = load_skill_content(tmp_path, ["lint-skill"])
        assert "@script:" not in result
        assert "shell_exec" in result

    def test_missing_skill_returns_empty(self, tmp_path):
        result = load_skill_content(tmp_path, ["nonexistent"])
        assert result == ""

    def test_missing_skill_md_in_directory(self, tmp_path):
        (tmp_path / "empty-skill").mkdir()
        result = load_skill_content(tmp_path, ["empty-skill"])
        assert result == ""

    def test_multiple_skills_joined(self, tmp_path):
        (tmp_path / "skill-a.md").write_text("Skill A content")
        (tmp_path / "skill-b.md").write_text("Skill B content")

        result = load_skill_content(tmp_path, ["skill-a", "skill-b"])
        assert "Skill A content" in result
        assert "Skill B content" in result
        assert "---" in result  # 分隔符

    def test_skills_dir_not_exists(self, tmp_path):
        nonexistent = tmp_path / "no-such-dir"
        result = load_skill_content(nonexistent, ["anything"])
        assert result == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/test_skill_loader.py -v`
Expected: FAIL — `ImportError: cannot import name 'load_skill_content' from 'axonflow.config.loader'`

- [ ] **Step 3: Implement load_skill_content() and _resolve_script_refs()**

In `src/axonflow/config/loader.py`, add imports at top:

```python
import re
import structlog

logger = structlog.get_logger()
```

Add at the end of the file:

```python
def load_skill_content(skills_dir: Path, skill_names: list[str]) -> str:
    """加载指定 skill 的内容，拼接返回

    支持两种格式:
    - 目录格式: skills_dir/{name}/SKILL.md (+ scripts/ 子目录)
    - 单文件格式: skills_dir/{name}.md

    目录格式优先于单文件格式。
    """
    skills_dir = Path(skills_dir)
    if not skills_dir.exists():
        logger.info("skill.skills_dir_not_found", path=str(skills_dir))
        return ""

    sections: list[str] = []
    for name in skill_names:
        # 优先查找目录格式
        skill_dir = skills_dir / name
        if skill_dir.is_dir():
            skill_md = skill_dir / "SKILL.md"
            if skill_md.exists():
                content = skill_md.read_text(encoding="utf-8")
                content = _resolve_script_refs(content, skill_dir / "scripts")
                sections.append(content)
            else:
                logger.warning("skill.missing_skill_md", skill=name)
            continue

        # 回退到单文件格式
        skill_file = skills_dir / f"{name}.md"
        if skill_file.exists():
            sections.append(skill_file.read_text(encoding="utf-8"))
        else:
            logger.warning("skill.not_found", skill=name)

    return "\n\n---\n\n".join(sections)


def _resolve_script_refs(content: str, scripts_dir: Path) -> str:
    """将 @script:xxx 标记替换为绝对路径的 shell_exec 指引"""

    def _replacer(m: re.Match) -> str:
        script_name = m.group(1)
        script_path = scripts_dir / script_name
        if script_path.exists():
            return f"使用 shell_exec 工具执行 {script_path.resolve()}"
        logger.warning("skill.script_not_found", script=script_name)
        return m.group(0)  # 保留原始文本

    return re.sub(r"@script:(\S+)", _replacer, content)
```

- [ ] **Step 4: Create example skill files**

Create `config/skills/code-review/SKILL.md`:

```markdown
# Code Review Skill

你是一个代码审查专家。收到代码后，请按以下步骤进行审查：

1. **正确性** — 逻辑是否正确，有无 bug
2. **可维护性** — 命名、结构、注释是否清晰
3. **安全性** — 有无注入、越权、信息泄露风险
4. **性能** — 有无明显的性能问题

## 工具使用

- 运行 lint 检查：执行 @script:lint.sh {file_path}
- 读取文件内容：使用 file_read 工具

## 输出格式

请以 markdown 格式输出审查报告，包含：问题列表、严重级别、修复建议。
```

Create `config/skills/code-review/scripts/lint.sh`:

```bash
#!/bin/bash
# 简单的 lint 检查脚本
# 用法: lint.sh <file_path>

set -e

if [ -z "$1" ]; then
    echo "Usage: lint.sh <file_path>"
    exit 1
fi

FILE="$1"

if [ ! -f "$FILE" ]; then
    echo "Error: File not found: $FILE"
    exit 1
fi

echo "Running lint check on $FILE..."

# 检查 Python 文件
if [[ "$FILE" == *.py ]]; then
    python -m py_compile "$FILE" 2>&1 || echo "Syntax error detected"
    echo "Lint check completed."
else
    echo "Skipping non-Python file."
fi
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/unit/test_skill_loader.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/axonflow/config/loader.py config/skills/ tests/unit/test_skill_loader.py
git commit -m "feat: add skill loader with @script resolution and example skill"
```

---

## Task 9: PromptBuilder — 注入 Skill 内容

**Files:**
- Modify: `src/axonflow/llm/prompt_builder.py:30-69`
- Test: `tests/unit/test_prompt_builder.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_prompt_builder.py`:

```python
    def test_build_with_skill_content(self):
        """skill_content 应出现在 system prompt 中"""
        messages = PromptBuilder.build(
            agent_config=_make_config(),
            incoming_message=_make_message(),
            skill_content="# TDD Skill\nAlways write tests first.",
        )
        system_content = messages[0]["content"]
        assert "TDD Skill" in system_content
        assert "write tests first" in system_content

    def test_skill_content_between_role_and_tools(self):
        """skill 内容应在 role 之后、tool 描述之前"""
        tool_schemas = [
            {"type": "function", "function": {"name": "file_read", "parameters": {}}},
        ]
        messages = PromptBuilder.build(
            agent_config=_make_config(),
            incoming_message=_make_message(),
            tool_schemas=tool_schemas,
            skill_content="# Review Skill\nCheck code quality.",
        )
        system_content = messages[0]["content"]
        role_pos = system_content.find("测试用的智能体")
        skill_pos = system_content.find("Review Skill")
        tool_pos = system_content.find("file_read")
        assert role_pos < skill_pos < tool_pos

    def test_build_without_skill_content(self):
        """不传 skill_content 时不影响现有行为"""
        messages = PromptBuilder.build(
            agent_config=_make_config(),
            incoming_message=_make_message(),
        )
        # 应与现有行为一致
        assert len(messages) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_prompt_builder.py::TestPromptBuilder::test_build_with_skill_content -v`
Expected: FAIL — `TypeError: build() got an unexpected keyword argument 'skill_content'`

- [ ] **Step 3: Add skill_content parameter to PromptBuilder.build()**

In `src/axonflow/llm/prompt_builder.py`, update the `build()` method signature and body:

```python
    @staticmethod
    def build(
        agent_config: AgentConfig,
        incoming_message: Message,
        context: WorkflowContext | None = None,
        tool_schemas: list[dict] | None = None,
        memories: list[MemoryRecord] | None = None,
        skill_content: str | None = None,
    ) -> list[dict]:
        """构建完整的 prompt 消息列表

        组装顺序:
        1. Persona (soul/user/workflow)
        2. Role
        3. Skills (SKILL.md 内容)
        4. Tool schemas 描述
        5. Memory 上下文

        Returns:
            OpenAI 格式的 messages 列表
        """
        messages: list[dict] = []

        # 1. System Prompt
        system_parts: list[str] = []

        # 1a. Persona 人设注入（在 role 之前）
        if agent_config.persona.soul:
            system_parts.append(f"## 价值观与行为准则\n{agent_config.persona.soul}")
        if agent_config.persona.user:
            system_parts.append(f"## 用户档案\n{agent_config.persona.user}")
        if agent_config.persona.workflow:
            system_parts.append(f"## 工作流程指南\n{agent_config.persona.workflow}")

        # 1b. 角色描述
        if agent_config.role:
            system_parts.append(agent_config.role)

        # 1c. Skill 内容注入（在 role 之后，tool schemas 之前）
        if skill_content:
            system_parts.append(f"\n## Skills\n{skill_content}")

        if context and context.shared_state:
            state_str = "\n".join(f"- {k}: {v}" for k, v in context.shared_state.items())
            system_parts.append(f"\n当前工作流上下文:\n{state_str}")

        if tool_schemas:
            tool_names = [t["function"]["name"] for t in tool_schemas]
            system_parts.append(
                f"\n你可以使用以下工具: {', '.join(tool_names)}"
                "\n当需要执行操作时，使用 function calling 调用对应工具。"
            )

        # 记忆上下文注入
        if memories:
            memory_lines: list[str] = []
            for mem in memories:
                scope_label = mem.scope.value if hasattr(mem.scope, "value") else str(mem.scope)
                agent_label = mem.agent_id or "global"
                value_summary = str(mem.value)[:200]
                memory_lines.append(f"- [{scope_label}/{agent_label}] {mem.key}: {value_summary}")
            system_parts.append("\n相关记忆:\n" + "\n".join(memory_lines))

        messages.append(
            {
                "role": "system",
                "content": "\n".join(system_parts),
            }
        )

        # 2. 历史消息
        if context and context.history:
            recent = context.history[-10:]
            for hist_msg in recent:
                role = "assistant" if hist_msg.sender == agent_config.id else "user"
                content = hist_msg.payload.get("content", str(hist_msg.payload))
                messages.append({"role": role, "content": content})

        # 3. 当前任务消息
        task_content = incoming_message.payload.get(
            "task",
            incoming_message.payload.get("content", str(incoming_message.payload)),
        )
        messages.append({"role": "user", "content": task_content})

        return messages
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/unit/test_prompt_builder.py -v`
Expected: All PASS

- [ ] **Step 5: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/axonflow/llm/prompt_builder.py tests/unit/test_prompt_builder.py
git commit -m "feat: inject skill content into system prompt via PromptBuilder"
```

---

## Task 10: BaseAgent — 加载并传递 Skill 内容

**Files:**
- Modify: `src/axonflow/core/agent.py` (handle_message — add skill loading)

Now we wire up the skill loading in `handle_message()` so that skills configured on the agent are loaded and passed to `PromptBuilder.build()`.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_skill_loader.py`:

```python
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from axonflow.config.models import AgentConfig, ModelConfig
from axonflow.core.agent import BaseAgent
from axonflow.core.message import Message, MessageType
from axonflow.llm.gateway import LLMResponse
from axonflow.messaging.memory_bus import InMemoryMessageBus
from axonflow.tools.base import ToolRegistry


class TestAgentSkillIntegration:
    @pytest.mark.asyncio
    async def test_agent_loads_skills_into_prompt(self, tmp_path):
        """Agent 配置了 skills 时，handle_message 应加载 skill 内容到 prompt"""
        # 创建 skill 文件
        skill_dir = tmp_path / "skills" / "test-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("# Test Skill\nDo testing stuff.")

        config = AgentConfig(
            id="skill-agent",
            name="Skill Agent",
            role="You are a test agent.",
            model=ModelConfig(provider="openai", name="test-model"),
            skills=["test-skill"],
        )

        bus = InMemoryMessageBus()
        registry = ToolRegistry()
        gateway = MagicMock()
        gateway.chat = AsyncMock(
            return_value=LLMResponse(content="Done.", model="test-model"),
        )

        agent = BaseAgent(
            config=config,
            message_bus=bus,
            llm_gateway=gateway,
            tool_registry=registry,
            skills_dir=tmp_path / "skills",
        )

        msg = Message(
            sender="user",
            receiver="skill-agent",
            type=MessageType.TASK_REQUEST,
            payload={"task": "test"},
            workflow_id="wf-skill",
        )

        await agent.handle_message(msg)

        # 验证 LLM 调用的 messages 中包含 skill 内容
        call_args = gateway.chat.call_args
        messages = call_args[1]["messages"]
        system_content = messages[0]["content"]
        assert "Test Skill" in system_content
        assert "testing stuff" in system_content
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_skill_loader.py::TestAgentSkillIntegration -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'skills_dir'`

- [ ] **Step 3: Add skills_dir to BaseAgent and wire up skill loading**

In `src/axonflow/core/agent.py`, update `__init__()` to accept `skills_dir`:

```python
    def __init__(
        self,
        config: AgentConfig,
        message_bus: MessageBus,
        llm_gateway: LLMGateway,
        tool_registry: ToolRegistry,
        memory_store: MemoryStore | None = None,
        execution_logger: ExecutionLogger | None = None,
        skills_dir: Path | None = None,
    ) -> None:
        ...
        self.execution_logger = execution_logger
        self._skills_dir = skills_dir
```

Add import:

```python
from pathlib import Path
from axonflow.config.loader import load_skill_content
```

In `handle_message()`, before building messages, load skill content:

```python
        # 加载 skill 内容
        skill_content: str | None = None
        if self.config.skills and self._skills_dir:
            skill_content = load_skill_content(self._skills_dir, self.config.skills)
            if not skill_content:
                skill_content = None
```

Update the `PromptBuilder.build()` call to pass `skill_content`:

```python
        messages = PromptBuilder.build(
            agent_config=self.config,
            incoming_message=message,
            context=context,
            tool_schemas=tool_schemas if tool_schemas else None,
            memories=memories,
            skill_content=skill_content,
        )
```

Update `create_agent()` to accept and pass `skills_dir`:

```python
def create_agent(
    config: AgentConfig,
    message_bus: MessageBus,
    llm_gateway: LLMGateway,
    tool_registry: ToolRegistry,
    memory_store: MemoryStore | None = None,
    execution_logger: ExecutionLogger | None = None,
    skills_dir: Path | None = None,
) -> BaseAgent:
    ...
    return agent_cls(
        config=config,
        message_bus=message_bus,
        llm_gateway=llm_gateway,
        tool_registry=tool_registry,
        memory_store=memory_store,
        execution_logger=execution_logger,
        skills_dir=skills_dir,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/unit/test_skill_loader.py -v`
Expected: All PASS

- [ ] **Step 5: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/axonflow/core/agent.py tests/unit/test_skill_loader.py
git commit -m "feat: agent loads skill content and injects into prompt"
```

---

## Task 11: Engine — 传递 skills_dir 给 Agent

**Files:**
- Modify: `src/axonflow/engine.py` (_load_agents)

- [ ] **Step 1: Update engine to pass skills_dir**

In `src/axonflow/engine.py`, update `_load_agents()`:

```python
    async def _load_agents(self) -> None:
        """从配置目录加载所有 Agent"""
        assert self._agent_registry is not None
        assert self._message_bus is not None
        assert self._llm_gateway is not None
        assert self._tool_registry is not None

        agents_dir = self._config_dir / "agents"
        skills_dir = self._config_dir / "skills"
        agent_configs = load_all_agent_configs(agents_dir)

        for cfg in agent_configs:
            agent = create_agent(
                config=cfg,
                message_bus=self._message_bus,
                llm_gateway=self._llm_gateway,
                tool_registry=self._tool_registry,
                memory_store=self._memory_store,
                execution_logger=self._execution_logger,
                skills_dir=skills_dir,
            )
            self._agent_registry.register(agent)

        logger.info(
            "engine.agents_loaded",
            count=len(agent_configs),
        )
```

- [ ] **Step 2: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add src/axonflow/engine.py
git commit -m "feat: engine passes skills_dir to agent factory"
```

---

## Task 12: Final Integration Test & Full Regression

**Files:**
- All files from Tasks 1-11

- [ ] **Step 1: Run full test suite**

Run: `python -m pytest tests/ -v --tb=short`
Expected: All tests PASS (original 75 + new tests from Tasks 1-11)

- [ ] **Step 2: Count new tests**

Run: `python -m pytest tests/unit/test_tool_calling.py tests/unit/test_skill_loader.py tests/unit/test_execution_log.py -v --co -q`
Expected: Should show ~25-30 new test cases

- [ ] **Step 3: Verify lint.sh is executable**

Run: `chmod +x config/skills/code-review/scripts/lint.sh`

- [ ] **Step 4: Final commit (if any unstaged changes)**

```bash
git status
# If there are any remaining changes:
git add -A
git commit -m "chore: final cleanup for Phase 1 implementation"
```

---

## Summary

| Task | Component | Tests | Commit Message |
|------|-----------|-------|---------------|
| 1 | ExecutionLogger | 10 | `feat: add ExecutionLogger with dual-write (memory + JSONL)` |
| 2 | LLMResponse.tool_calls | 2 | `feat: add tool_calls field to LLMResponse` |
| 3 | Gateway.chat() parse | 2 | `feat: parse tool_calls from LLM response in gateway.chat()` |
| 4 | ToolRegistry.execute() | 3 | `feat: ToolRegistry.execute() accepts arguments dict for dispatch` |
| 5 | BaseAgent tool loop | 5 | `feat: implement multi-turn tool calling loop in BaseAgent.handle_message()` |
| 6 | Engine + ExecutionLogger | 0 | `feat: create ExecutionLogger in engine and pass to agents` |
| 7 | AgentConfig.skills | 2 | `feat: add skills field to AgentConfig` |
| 8 | Skill loader | 10 | `feat: add skill loader with @script resolution and example skill` |
| 9 | PromptBuilder + skills | 3 | `feat: inject skill content into system prompt via PromptBuilder` |
| 10 | Agent + skill loading | 1 | `feat: agent loads skill content and injects into prompt` |
| 11 | Engine + skills_dir | 0 | `feat: engine passes skills_dir to agent factory` |
| 12 | Integration check | 0 | (cleanup if needed) |

**Total: ~38 new tests, 11 commits, 1 new module + 3 new test files + 2 skill files**
