"""Pytest fixtures for AutoFlow tests."""

from __future__ import annotations

import pytest

from autoflow.config.models import AgentConfig, ModelConfig
from autoflow.core.message import Message, MessageType
from autoflow.llm.gateway import LLMGateway, LLMResponse
from autoflow.messaging.memory_bus import InMemoryMessageBus
from autoflow.tools.base import ToolRegistry
from autoflow.tools.file_ops import FileReadTool, FileWriteTool
from autoflow.tools.shell_exec import ShellExecTool


@pytest.fixture
def memory_bus() -> InMemoryMessageBus:
    """创建进程内消息总线"""
    return InMemoryMessageBus()


@pytest.fixture
def tool_registry() -> ToolRegistry:
    """创建并注册内置工具的工具注册中心"""
    registry = ToolRegistry()
    registry.register(ShellExecTool())
    registry.register(FileReadTool())
    registry.register(FileWriteTool())
    return registry


@pytest.fixture
def sample_agent_config() -> AgentConfig:
    """测试用智能体配置"""
    return AgentConfig(
        id="test-agent",
        name="测试智能体",
        role="你是一个用于测试的智能体。",
        model=ModelConfig(
            provider="openai",
            name="gpt-4o-mini",
            temperature=0.1,
        ),
        tools=["shell_exec", "file_read", "file_write"],
        can_request=["other-agent"],
    )


@pytest.fixture
def sample_message() -> Message:
    """测试用消息"""
    return Message(
        sender="agent-a",
        receiver="agent-b",
        type=MessageType.TASK_REQUEST,
        payload={"task": "Write a hello world program"},
        workflow_id="test-workflow-001",
        step_id="step-0",
    )
