"""Tool Calling 闭环测试"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autoflow.config.models import ModelConfig
from autoflow.llm.gateway import LLMGateway, LLMResponse
from autoflow.tools.base import ToolRegistry, ToolResult


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
