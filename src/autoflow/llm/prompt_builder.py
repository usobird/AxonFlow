"""Prompt 构建器 — 将 Agent 配置、上下文、工具转化为 LLM 消息列表"""

from __future__ import annotations

from autoflow.config.models import AgentConfig
from autoflow.core.context import WorkflowContext
from autoflow.core.message import Message
from autoflow.memory.base import MemoryRecord


class PromptBuilder:
    """构建发送给 LLM 的消息列表"""

    @staticmethod
    def build(
        agent_config: AgentConfig,
        incoming_message: Message,
        context: WorkflowContext | None = None,
        tool_schemas: list[dict] | None = None,
        memories: list[MemoryRecord] | None = None,
    ) -> list[dict]:
        """构建完整的 prompt 消息列表

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

        # 2. 历史消息（最近的 N 条，避免上下文过长）
        if context and context.history:
            recent = context.history[-10:]  # 最近 10 条
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
