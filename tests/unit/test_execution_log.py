"""ExecutionLogger 单元测试"""

from __future__ import annotations

import json

import pytest

from autoflow.observability.execution_log import ExecutionLogEntry, ExecutionLogger


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
        logger = ExecutionLogger(workspace_dir="/tmp/test-autoflow-logs")
        entry = _make_entry()
        logger.log(entry)
        assert len(logger.get_entries()) == 1
        assert logger.get_entries()[0] is entry

    def test_filter_by_workflow_id(self):
        logger = ExecutionLogger(workspace_dir="/tmp/test-autoflow-logs")
        logger.log(_make_entry(workflow_id="wf-001"))
        logger.log(_make_entry(workflow_id="wf-002"))
        logger.log(_make_entry(workflow_id="wf-001"))

        results = logger.get_entries(workflow_id="wf-001")
        assert len(results) == 2

    def test_filter_by_agent_id(self):
        logger = ExecutionLogger(workspace_dir="/tmp/test-autoflow-logs")
        logger.log(_make_entry(agent_id="agent-a"))
        logger.log(_make_entry(agent_id="agent-b"))

        results = logger.get_entries(agent_id="agent-a")
        assert len(results) == 1

    def test_filter_by_action(self):
        logger = ExecutionLogger(workspace_dir="/tmp/test-autoflow-logs")
        logger.log(_make_entry(action="tool_call"))
        logger.log(_make_entry(action="tool_error"))
        logger.log(_make_entry(action="llm_error"))

        results = logger.get_entries(action="tool_error")
        assert len(results) == 1

    def test_combined_filters(self):
        logger = ExecutionLogger(workspace_dir="/tmp/test-autoflow-logs")
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
