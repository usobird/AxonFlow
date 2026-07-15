"""Tests for the product-facing platform graph and SQLite persistence."""

from __future__ import annotations

from axonflow.config.models import FlowConfig, ModelConfig, Route, RouteCondition, WorkflowConfig
from axonflow.engine import AxonFlowEngine
from axonflow.llm.gateway import LLMGateway
from axonflow.llm.providers import resolve_model_name
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
    assert restored.flow.entry == "research-flow--node-researcher"
    assert restored.flow.routes["research-flow--node-researcher"][0].target == (
        "research-flow--node-writer"
    )


def test_visual_graph_projects_duplicate_templates_as_distinct_entities() -> None:
    workflow = PlatformWorkflow(
        id="review-flow",
        name="Review flow",
        nodes=[
            WorkflowNode(
                id="draft",
                agent_id="writer",
                label="Draft writer",
                is_entry=True,
                config={"responsibility": "Write the first draft."},
            ),
            WorkflowNode(
                id="revision",
                agent_id="writer",
                label="Revision writer",
                config={
                    "responsibility": "Rewrite after review feedback.",
                    "model_profile_id": "profile-fast",
                    "terminate_on_success": True,
                },
            ),
        ],
        edges=[{"id": "draft-to-revision", "source": "draft", "target": "revision"}],
    )

    runtime = workflow.to_workflow_config()
    scoped = AxonFlowEngine()._scope_agent_instances(runtime)
    restored = PlatformWorkflow.from_workflow_config(runtime)

    assert [instance.template_id for instance in runtime.agent_instances] == ["writer", "writer"]
    assert runtime.agent_instances[0].id != runtime.agent_instances[1].id
    assert runtime.flow.routes[runtime.agent_instances[0].id][0].target == (
        runtime.agent_instances[1].id
    )
    assert runtime.context["agent_role_overrides"][runtime.agent_instances[1].id] == (
        "Rewrite after review feedback."
    )
    assert scoped.agent_instances[0].id != runtime.agent_instances[0].id
    assert scoped.agent_instances[0].id != scoped.agent_instances[1].id
    assert restored.nodes[1].config["model_profile_id"] == "profile-fast"


def test_workflow_node_responsibility_projects_to_runtime_context() -> None:
    workflow = PlatformWorkflow(
        id="content-flow",
        name="Content flow",
        nodes=[
            WorkflowNode(
                id="node-writer",
                agent_id="writer",
                label="Writer",
                is_entry=True,
                config={"responsibility": "Draft a concise first version for the reviewer."},
            )
        ],
    )

    runtime = workflow.to_workflow_config()
    restored = PlatformWorkflow.from_workflow_config(runtime)

    assert runtime.context["agent_role_overrides"]["content-flow--node-writer"] == (
        "Draft a concise first version for the reviewer."
    )
    assert restored.nodes[0].config["responsibility"] == (
        "Draft a concise first version for the reviewer."
    )


def test_workflow_end_node_projects_to_runtime_termination() -> None:
    workflow = PlatformWorkflow(
        id="review-flow",
        name="Review flow",
        nodes=[
            WorkflowNode(
                id="node-writer",
                agent_id="writer",
                label="Writer",
                is_entry=True,
                config={"terminate_on_success": False},
            ),
            WorkflowNode(
                id="node-reviewer",
                agent_id="reviewer",
                label="Reviewer",
                config={"terminate_on_success": True},
            ),
        ],
        terminate_on=[{"agent": "writer", "status": "error"}],
    )

    runtime = workflow.to_workflow_config()
    restored = PlatformWorkflow.from_workflow_config(runtime)

    assert {tuple(condition.items()) for condition in runtime.flow.terminate_on} == {
        (("agent", "review-flow--node-writer"), ("status", "error")),
        (("agent", "review-flow--node-reviewer"), ("status", "success")),
    }
    assert restored.nodes[1].config["terminate_on_success"] is True


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


def test_store_encrypts_credentials_and_persists_llm_spans(tmp_path) -> None:
    store = PlatformStore(tmp_path / "axonflow.db")
    credential = store.create_credential(
        name="qwen-production",
        provider="dashscope",
        source="encrypted",
        secret="sk-secret-value",
    )

    assert credential["masked_value"] == "sk-s****alue"
    assert "secret" not in credential
    assert store.resolve_credential(credential["id"])["secret"] == "sk-secret-value"

    store.create_llm_span(
        {
            "id": "span-1",
            "run_id": "run-1",
            "workflow_id": "workflow-1",
            "execution_id": "execution-1",
            "agent_id": "agent-writer",
            "provider": "dashscope",
            "model": "dashscope/qwen-plus",
            "credential_id": credential["id"],
            "started_at": "2026-01-01T00:00:00+00:00",
            "input_preview": "1 messages, 12 characters",
        }
    )
    store.complete_llm_span(
        "span-1",
        {
            "status": "completed",
            "completed_at": "2026-01-01T00:00:01+00:00",
            "latency_ms": 1000,
            "input_tokens": 10,
            "output_tokens": 20,
            "total_tokens": 30,
            "output_preview": "1 messages, 4 characters",
        },
    )

    span = store.list_llm_spans(run_id="run-1")[0]
    assert span["status"] == "completed"
    assert span["total_tokens"] == 30
    store.close()


def test_store_persists_reusable_model_profiles(tmp_path) -> None:
    store = PlatformStore(tmp_path / "axonflow.db")
    credential = store.create_credential(
        name="minimax-production",
        provider="minimax",
        source="environment",
        env_var="MINIMAX_API_KEY",
    )
    profile = store.create_model_profile(
        "minimax-m3",
        {
            "provider": "minimax",
            "name": "MiniMax-M3",
            "credential_id": credential["id"],
            "api_base": "https://api.minimaxi.com/v1",
            "temperature": 0.2,
            "max_tokens": 2048,
            "timeout": 60,
        },
    )

    stored = store.get_model_profile(profile["id"])
    assert stored is not None
    assert stored["name"] == "minimax-m3"
    assert stored["config"]["credential_id"] == credential["id"]
    assert store.list_model_profiles()[0]["id"] == profile["id"]
    store.close()


def test_agent_model_override_wins_over_global_default() -> None:
    gateway = LLMGateway(default_model=ModelConfig(provider="openai", name="gpt-4o"))
    selected = gateway._select_model_config(
        ModelConfig(provider="dashscope", name="qwen-plus"),
        prefer_default=True,
    )

    assert selected.provider == "dashscope"
    assert resolve_model_name("dashscope", "qwen-plus") == "dashscope/qwen-plus"
    assert resolve_model_name("openai_compatible", "custom-model", "https://example.test/v1") == (
        "openai/custom-model"
    )
