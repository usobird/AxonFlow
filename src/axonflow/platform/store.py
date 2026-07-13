"""Small SQLite repository for platform definitions and run observability."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from typing import Any

from axonflow.platform.models import PlatformWorkflow


def _now() -> str:
    return datetime.now(UTC).isoformat()


class PlatformStore:
    """Persistence that works locally today and has clear PostgreSQL seams later."""

    def __init__(self, database_path: Path | str) -> None:
        path = Path(database_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._lock = RLock()
        self._create_schema()

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def _create_schema(self) -> None:
        with self._lock:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS workflow_definitions (
                    id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    revision INTEGER NOT NULL DEFAULT 1,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS workflow_runs (
                    run_id TEXT PRIMARY KEY,
                    workflow_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    input_data TEXT NOT NULL,
                    workflow_snapshot TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    result TEXT
                );
                CREATE TABLE IF NOT EXISTS node_runs (
                    run_id TEXT NOT NULL,
                    node_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    output TEXT,
                    error TEXT,
                    PRIMARY KEY (run_id, node_id)
                );
                CREATE TABLE IF NOT EXISTS run_events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    data TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS artifacts (
                    id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    node_id TEXT,
                    name TEXT NOT NULL,
                    uri TEXT NOT NULL,
                    media_type TEXT,
                    created_at TEXT NOT NULL
                );
                """
            )
            self._connection.commit()

    def get_workflow(self, workflow_id: str) -> PlatformWorkflow | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT payload FROM workflow_definitions WHERE id = ?", (workflow_id,)
            ).fetchone()
        return PlatformWorkflow.model_validate_json(row["payload"]) if row else None

    def list_workflows(self) -> list[PlatformWorkflow]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT payload FROM workflow_definitions ORDER BY updated_at DESC"
            ).fetchall()
        return [PlatformWorkflow.model_validate_json(row["payload"]) for row in rows]

    def save_workflow(self, workflow: PlatformWorkflow) -> PlatformWorkflow:
        payload = workflow.model_dump_json()
        now = _now()
        with self._lock:
            self._connection.execute(
                """
                INSERT INTO workflow_definitions(id, payload, revision, updated_at)
                VALUES (?, ?, 1, ?)
                ON CONFLICT(id) DO UPDATE SET
                  payload = excluded.payload,
                  revision = workflow_definitions.revision + 1,
                  updated_at = excluded.updated_at
                """,
                (workflow.id, payload, now),
            )
            self._connection.commit()
        return workflow

    def create_run(self, run_id: str, workflow: PlatformWorkflow, input_data: str) -> None:
        with self._lock:
            self._connection.execute(
                """
                INSERT INTO workflow_runs(
                  run_id, workflow_id, status, input_data, workflow_snapshot, started_at
                ) VALUES (?, ?, 'running', ?, ?, ?)
                """,
                (run_id, workflow.id, input_data, workflow.model_dump_json(), _now()),
            )
            self._connection.commit()

    def complete_run(self, run_id: str, status: str, result: dict[str, Any]) -> None:
        with self._lock:
            self._connection.execute(
                "UPDATE workflow_runs "
                "SET status = ?, completed_at = ?, result = ? "
                "WHERE run_id = ?",
                (status, _now(), json.dumps(result, ensure_ascii=False), run_id),
            )
            self._connection.commit()

    def update_node_run(
        self,
        run_id: str,
        node_id: str,
        agent_id: str,
        status: str,
        output: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        now = _now()
        terminal = status in {"completed", "error"}
        with self._lock:
            self._connection.execute(
                """
                INSERT INTO node_runs(
                  run_id, node_id, agent_id, status, started_at, completed_at, output, error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id, node_id) DO UPDATE SET
                  status = excluded.status,
                  started_at = COALESCE(node_runs.started_at, excluded.started_at),
                  completed_at = excluded.completed_at,
                  output = COALESCE(excluded.output, node_runs.output),
                  error = COALESCE(excluded.error, node_runs.error)
                """,
                (
                    run_id,
                    node_id,
                    agent_id,
                    status,
                    now,
                    now if terminal else None,
                    json.dumps(output, ensure_ascii=False) if output is not None else None,
                    error,
                ),
            )
            self._connection.commit()

    def record_event(
        self,
        run_id: str,
        event_type: str,
        data: dict[str, Any],
        timestamp: str,
    ) -> dict:
        with self._lock:
            cursor = self._connection.execute(
                "INSERT INTO run_events(run_id, event_type, timestamp, data) VALUES (?, ?, ?, ?)",
                (run_id, event_type, timestamp, json.dumps(data, ensure_ascii=False)),
            )
            self._connection.commit()
        return {
            "sequence": cursor.lastrowid,
            "type": event_type,
            "run_id": run_id,
            "timestamp": timestamp,
            "data": data,
        }

    def list_runs(self, workflow_id: str) -> list[dict]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM workflow_runs WHERE workflow_id = ? ORDER BY started_at DESC",
                (workflow_id,),
            ).fetchall()
        return [self._run_row(row) for row in rows]

    def get_run(self, workflow_id: str, run_id: str) -> dict | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM workflow_runs WHERE workflow_id = ? AND run_id = ?",
                (workflow_id, run_id),
            ).fetchone()
            node_rows = self._connection.execute(
                "SELECT * FROM node_runs WHERE run_id = ? ORDER BY started_at", (run_id,)
            ).fetchall()
            event_rows = self._connection.execute(
                "SELECT * FROM run_events WHERE run_id = ? ORDER BY sequence", (run_id,)
            ).fetchall()
        if row is None:
            return None
        result = self._run_row(row)
        result["node_runs"] = [
            {
                **dict(node_row),
                "output": json.loads(node_row["output"]) if node_row["output"] else None,
            }
            for node_row in node_rows
        ]
        result["events"] = [
            {
                "sequence": event_row["sequence"],
                "type": event_row["event_type"],
                "run_id": run_id,
                "timestamp": event_row["timestamp"],
                "data": json.loads(event_row["data"]),
            }
            for event_row in event_rows
        ]
        return result

    @staticmethod
    def _run_row(row: sqlite3.Row) -> dict:
        return {
            "run_id": row["run_id"],
            "workflow_id": row["workflow_id"],
            "status": row["status"],
            "input": row["input_data"],
            "started_at": row["started_at"],
            "completed_at": row["completed_at"],
            "result": json.loads(row["result"]) if row["result"] else None,
        }
