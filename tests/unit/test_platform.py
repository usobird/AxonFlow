"""Tests for the product-facing platform graph and SQLite persistence."""

from __future__ import annotations

import pytest

from axonflow.config.models import FlowConfig, Route, RouteCondition, WorkflowConfig
from axonflow.platform.models import PlatformWorkflow, WorkflowNode
from axonflow.platform.store import PlatformStore


def test_runtime_config_projects_to_visual_graph_and_back() -> None:
    config = WorkflowConfig(
        id="research-flow",
        name="Research flow",
        agents=["researcher", "writer"],
        flow=FlowConfig(
            entry="researcher",
            routes={
                "researcher": [
                    Route(
                        target="writer",
                        condition=RouteCondition(field="status", operator="eq", value="success"),
                    )
                ]
            },
        ),
    )

    workflow = PlatformWorkflow.from_workflow_config(config)
    restored = workflow.to_workflow_config()

    assert workflow.nodes[0].is_entry is True
    assert workflow.edges[0].condition is not None
    assert restored.flow.entry == "researcher"
    assert restored.flow.routes["researcher"][0].target == "writer"


def test_visual_graph_rejects_duplicate_agents() -> None:
    with pytest.raises(ValueError, match="only once"):
        PlatformWorkflow(
            id="invalid",
            name="Invalid",
            nodes=[
                WorkflowNode(id="a", agent_id="writer", label="Writer", is_entry=True),
                WorkflowNode(id="b", agent_id="writer", label="Writer again"),
            ],
        )


def test_store_persists_workflow_runs_nodes_and_events(tmp_path) -> None:
    store = PlatformStore(tmp_path / "axonflow.db")
    workflow = PlatformWorkflow(
        id="demo",
        name="Demo",
        nodes=[WorkflowNode(id="node-writer", agent_id="writer", label="Writer", is_entry=True)],
        edges=[],
    )
    store.save_workflow(workflow)
    store.create_run("run-1", workflow, "Draft an update")
    store.update_node_run("run-1", "node-writer", "writer", "running")
    store.update_node_run(
        "run-1",
        "node-writer",
        "writer",
        "completed",
        output={"status": "success", "content": "Done"},
    )
    store.record_event(
        "run-1",
        "node.result_ready",
        {"node_id": "node-writer"},
        "2026-01-01T00:00:00+00:00",
    )
    store.complete_run("run-1", "completed", {"iterations": 1})

    detail = store.get_run("demo", "run-1")
    assert detail is not None
    assert detail["status"] == "completed"
    assert detail["node_runs"][0]["status"] == "completed"
    assert detail["node_runs"][0]["output"]["content"] == "Done"
    assert detail["events"][0]["type"] == "node.result_ready"
    store.close()
