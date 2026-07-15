"""执行日志 — 记录 tool 调用、错误、异常"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger()

_MAX_RESULT_LENGTH = 2000

# Callback signature: (entry: ExecutionLogEntry, run_id: str | None) -> None
LogCallback = Callable[["ExecutionLogEntry", str | None], Any]


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
    """执行日志记录器 — 双写：内存 + JSONL 磁盘 + 可选回调"""

    def __init__(self, workspace_dir: str = "./workspace") -> None:
        self._entries: list[ExecutionLogEntry] = []
        self._workspace_dir = Path(workspace_dir)
        self._callbacks: list[LogCallback] = []
        # Mapping: workflow_id -> current run_id (set during workflow execution)
        self._active_run_ids: dict[str, str] = {}

    def add_callback(self, callback: LogCallback) -> None:
        """注册日志回调（如 WebSocket 广播）"""
        self._callbacks.append(callback)

    def remove_callback(self, callback: LogCallback) -> None:
        """移除日志回调"""
        self._callbacks = [cb for cb in self._callbacks if cb is not callback]

    def set_run_id(self, workflow_id: str, run_id: str) -> None:
        """设置 workflow_id 对应的当前 run_id"""
        self._active_run_ids[workflow_id] = run_id

    def clear_run_id(self, workflow_id: str) -> None:
        """清除 workflow_id 对应的 run_id"""
        self._active_run_ids.pop(workflow_id, None)

    def get_run_id(self, workflow_id: str) -> str | None:
        """Return the product-facing run ID associated with an engine execution ID."""
        return self._active_run_ids.get(workflow_id)

    def log(self, entry: ExecutionLogEntry) -> None:
        """记录一条执行日志"""
        self._entries.append(entry)
        self._write_to_disk(entry)

        # 触发回调
        run_id = self._active_run_ids.get(entry.workflow_id)
        for callback in self._callbacks:
            try:
                callback(entry, run_id)
            except Exception as e:
                logger.error("execution_log.callback_failed", error=str(e))

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
