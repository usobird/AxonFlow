"""PromptBuilder 测试"""

from autoflow.config.models import AgentConfig, ModelConfig
from autoflow.core.message import Message, MessageType
from autoflow.llm.prompt_builder import PromptBuilder
from autoflow.memory.base import MemoryRecord, MemoryScope


def _make_config() -> AgentConfig:
    return AgentConfig(
        id="agent-test",
        name="测试",
        role="你是一个测试用的智能体。",
        model=ModelConfig(provider="openai", name="gpt-4o-mini"),
    )


def _make_message() -> Message:
    return Message(
        sender="user",
        receiver="agent-test",
        type=MessageType.TASK_REQUEST,
        payload={"task": "写一个 hello world"},
    )


class TestPromptBuilder:
    def test_basic_build(self):
        messages = PromptBuilder.build(
            agent_config=_make_config(),
            incoming_message=_make_message(),
        )
        assert len(messages) == 2  # system + user
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert "hello world" in messages[1]["content"]

    def test_build_includes_role(self):
        messages = PromptBuilder.build(
            agent_config=_make_config(),
            incoming_message=_make_message(),
        )
        assert "测试用的智能体" in messages[0]["content"]

    def test_build_with_no_memories(self):
        messages = PromptBuilder.build(
            agent_config=_make_config(),
            incoming_message=_make_message(),
            memories=None,
        )
        assert "相关记忆" not in messages[0]["content"]

    def test_build_with_empty_memories(self):
        messages = PromptBuilder.build(
            agent_config=_make_config(),
            incoming_message=_make_message(),
            memories=[],
        )
        assert "相关记忆" not in messages[0]["content"]

    def test_build_with_memories(self):
        memories = [
            MemoryRecord(
                key="task:001",
                value={"task": "previous task", "result": "success"},
                scope=MemoryScope.AGENT,
                agent_id="agent-test",
            ),
            MemoryRecord(
                key="shared:info",
                value="workflow context data",
                scope=MemoryScope.WORKFLOW,
                agent_id="agent-other",
                workflow_id="wf-001",
            ),
        ]
        messages = PromptBuilder.build(
            agent_config=_make_config(),
            incoming_message=_make_message(),
            memories=memories,
        )
        system_content = messages[0]["content"]
        assert "相关记忆" in system_content
        assert "task:001" in system_content
        assert "shared:info" in system_content
        assert "agent/agent-test" in system_content
        assert "workflow/agent-other" in system_content

    def test_build_with_tool_schemas(self):
        tool_schemas = [
            {"type": "function", "function": {"name": "shell_exec", "parameters": {}}},
        ]
        messages = PromptBuilder.build(
            agent_config=_make_config(),
            incoming_message=_make_message(),
            tool_schemas=tool_schemas,
        )
        assert "shell_exec" in messages[0]["content"]

    def test_build_with_memories_and_tools(self):
        """记忆和工具信息都应出现在 system prompt 中"""
        memories = [
            MemoryRecord(
                key="prev-result",
                value="some data",
                scope=MemoryScope.GLOBAL,
            ),
        ]
        tool_schemas = [
            {"type": "function", "function": {"name": "file_read", "parameters": {}}},
        ]
        messages = PromptBuilder.build(
            agent_config=_make_config(),
            incoming_message=_make_message(),
            tool_schemas=tool_schemas,
            memories=memories,
        )
        system_content = messages[0]["content"]
        assert "file_read" in system_content
        assert "相关记忆" in system_content
        assert "prev-result" in system_content
