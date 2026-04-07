"""工作流上下文管理"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from axonflow.core.message import Message


@dataclass
class WorkflowContext:
    """工作流执行上下文 — 各 Agent 可读写的共享状态"""

    workflow_id: str = field(default_factory=lambda: str(uuid4()))
    input: str = ""
    shared_state: dict[str, Any] = field(default_factory=dict)
    history: list[Message] = field(default_factory=list)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    iteration: int = 0

    def update_state(self, key: str, value: Any) -> None:
        """更新共享状态"""
        self.shared_state[key] = value

    def get_state(self, key: str, default: Any = None) -> Any:
        """读取共享状态"""
        return self.shared_state.get(key, default)

    def add_message(self, message: Message) -> None:
        """记录消息到历史"""
        self.history.append(message)

    def increment_iteration(self) -> int:
        """迭代计数器 +1，返回新值"""
        self.iteration += 1
        return self.iteration
