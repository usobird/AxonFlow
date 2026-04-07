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
