"""Tool Calling 闭环测试"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from axonflow.config.models import ModelConfig
from axonflow.llm.gateway import LLMGateway, LLMResponse
from axonflow.tools.base import ToolRegistry, ToolResult


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


class TestGatewayParsesToolCalls:
    @pytest.mark.asyncio
    async def test_chat_returns_tool_calls_when_present(self):
        """LLM 返回 tool_calls 时，chat() 应解析并填入 LLMResponse"""
        gateway = LLMGateway(
            default_model=ModelConfig(provider="openai", name="test-model"),
        )

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


class TestToolRegistryExecute:
    @pytest.mark.asyncio
    async def test_execute_known_tool(self):
        """已注册的工具应正常执行"""
        registry = ToolRegistry()

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
        assert "Unknown tool" in result.error

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


# ============================================================
# Tool Calling Loop 集成测试
# ============================================================

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
        mock_tool.to_schema.return_value = {
            "type": "function",
            "function": {
                "name": "shell_exec",
                "description": "Run shell commands",
                "parameters": {},
            },
        }
        registry.register(mock_tool)

        gateway = MagicMock()

        resp1 = LLMResponse(
            content="",
            model="test-model",
            tool_calls=[
                {
                    "id": "call_001",
                    "function": {"name": "shell_exec", "arguments": '{"command": "echo hello"}'},
                    "type": "function",
                }
            ],
        )
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
        assert "Done" in result["content"]

        mock_tool.execute.assert_called_once_with(command="echo hello")
        assert gateway.chat.call_count == 2

        # Verify second call has tool result message
        second_call_messages = gateway.chat.call_args_list[1][1]["messages"]
        tool_msgs = [m for m in second_call_messages if m.get("role") == "tool"]
        assert len(tool_msgs) == 1
        assert tool_msgs[0]["tool_call_id"] == "call_001"

        # Verify execution log
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
            tool_calls=[
                {
                    "id": "call_bad",
                    "function": {"name": "nonexistent_tool", "arguments": "{}"},
                    "type": "function",
                }
            ],
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
        mock_tool.to_schema.return_value = {
            "type": "function",
            "function": {
                "name": "shell_exec",
                "description": "Run shell commands",
                "parameters": {},
            },
        }
        registry.register(mock_tool)

        gateway = MagicMock()

        resp1 = LLMResponse(
            content="",
            model="test-model",
            tool_calls=[
                {
                    "id": "call_bad_json",
                    "function": {"name": "shell_exec", "arguments": "not valid json!!!"},
                    "type": "function",
                }
            ],
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
        mock_tool.to_schema.return_value = {
            "type": "function",
            "function": {
                "name": "shell_exec",
                "description": "Run shell commands",
                "parameters": {},
            },
        }
        registry.register(mock_tool)

        gateway = MagicMock()

        endless_resp = LLMResponse(
            content="",
            model="test-model",
            tool_calls=[
                {
                    "id": "call_loop",
                    "function": {"name": "shell_exec", "arguments": '{"command": "echo loop"}'},
                    "type": "function",
                }
            ],
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
        assert "exceeded" in result["error"].lower() or "rounds" in result["error"].lower()

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
