"""Platform workflow API: visual definitions, runs, and live events."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog
import yaml
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, model_validator

from axonflow.api.deps import get_config_dir, get_engine, get_platform_store
from axonflow.api.ws import broadcaster
from axonflow.config.loader import load_all_agent_configs, load_all_workflow_configs
from axonflow.config.models import WorkflowConfig
from axonflow.platform.models import PlatformWorkflow

logger = structlog.get_logger()
router = APIRouter(prefix="/api/workflows", tags=["workflows"])


class RunRequest(BaseModel):
    input: str = "Hello"


class WorkflowUpdateRequest(BaseModel):
    """Visual graph update, with YAML accepted for existing API clients."""

    workflow: PlatformWorkflow | None = None
    yaml_content: str | None = None

    @model_validator(mode="after")
    def validate_update(self) -> WorkflowUpdateRequest:
        if (self.workflow is None) == (self.yaml_content is None):
            raise ValueError("Provide exactly one of workflow or yaml_content")
        return self


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _response(workflow: PlatformWorkflow) -> dict[str, Any]:
    payload = workflow.model_dump(mode="json")
    payload["agent_count"] = len(workflow.nodes)
    return payload


def _config_for_id(workflow_id: str) -> WorkflowConfig:
    configs = load_all_workflow_configs(get_config_dir() / "workflows")
    for config in configs:
        if config.id == workflow_id:
            return config
    raise HTTPException(status_code=404, detail=f"Workflow not found: {workflow_id}")


def _get_or_seed_workflow(workflow_id: str) -> PlatformWorkflow:
    store = get_platform_store()
    workflow = store.get_workflow(workflow_id)
    if workflow is not None:
        return workflow
    workflow = PlatformWorkflow.from_workflow_config(_config_for_id(workflow_id))
    store.save_workflow(workflow)
    return workflow


def _find_workflow_file(workflow_id: str) -> Path:
    workflow_dir = get_config_dir() / "workflows"
    for path in list(workflow_dir.glob("*.yaml")) + list(workflow_dir.glob("*.yml")):
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            config = raw.get("workflow", raw)
            if config.get("id") == workflow_id:
                return path
        except (OSError, yaml.YAMLError, AttributeError):
            continue
    return workflow_dir / f"{workflow_id}.yaml"


def _write_runtime_config(workflow: PlatformWorkflow) -> None:
    """Keep YAML as the runtime/CLI source while SQLite retains visual metadata."""
    path = _find_workflow_file(workflow.id)
    path.parent.mkdir(parents=True, exist_ok=True)
    runtime = workflow.to_workflow_config().model_dump(mode="json")
    path.write_text(
        yaml.safe_dump({"workflow": runtime}, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def _validate_agents(workflow: PlatformWorkflow) -> None:
    available = {agent.id for agent in load_all_agent_configs(get_config_dir() / "agents")}
    missing = sorted({node.agent_id for node in workflow.nodes} - available)
    if missing:
        raise HTTPException(status_code=422, detail=f"Unknown Agent IDs: {', '.join(missing)}")


async def _publish_event(
    run_id: str,
    workflow_id: str,
    event_type: str,
    data: dict[str, Any],
) -> dict[str, Any]:
    timestamp = _now()
    event = {
        "type": event_type,
        "workflow_id": workflow_id,
        "run_id": run_id,
        "timestamp": timestamp,
        "data": data,
    }
    get_platform_store().record_event(run_id, event_type, data, timestamp)
    await broadcaster.broadcast(run_id, event)
    return event


@router.get("")
async def list_workflows() -> list[dict[str, Any]]:
    store = get_platform_store()
    # Existing YAML workflows are materialized once; subsequent edits retain canvas positions.
    for config in load_all_workflow_configs(get_config_dir() / "workflows"):
        if store.get_workflow(config.id) is None:
            store.save_workflow(PlatformWorkflow.from_workflow_config(config))
    return [_response(workflow) for workflow in store.list_workflows()]


@router.get("/{workflow_id}")
async def get_workflow(workflow_id: str) -> dict[str, Any]:
    return _response(_get_or_seed_workflow(workflow_id))


@router.put("/{workflow_id}")
async def update_workflow(workflow_id: str, body: WorkflowUpdateRequest) -> dict[str, Any]:
    if body.workflow is not None:
        if body.workflow.id != workflow_id:
            raise HTTPException(status_code=422, detail="Workflow ID cannot be changed")
        workflow = body.workflow
    else:
        try:
            raw = yaml.safe_load(body.yaml_content or "") or {}
            config_data = raw.get("workflow", raw)
            workflow = PlatformWorkflow.from_workflow_config(WorkflowConfig(**config_data))
        except Exception as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if workflow.id != workflow_id:
            raise HTTPException(status_code=422, detail="Workflow ID cannot be changed")

    _validate_agents(workflow)
    _write_runtime_config(workflow)
    get_platform_store().save_workflow(workflow)
    return _response(workflow)


@router.post("/{workflow_id}/run")
async def run_workflow(workflow_id: str, body: RunRequest) -> dict[str, str]:
    engine = get_engine()
    store = get_platform_store()
    workflow = _get_or_seed_workflow(workflow_id)
    run_id = f"run-{uuid.uuid4().hex[:8]}"
    execution_ids: set[str] = set()
    store.create_run(run_id, workflow, body.input)

    async def _execute() -> None:
        async def _on_orchestrator_event(event_type: str, data: dict[str, Any]) -> None:
            if event_type == "workflow.context_ready":
                execution_id = str(data["execution_id"])
                execution_ids.add(execution_id)
                if engine._execution_logger is not None:
                    engine._execution_logger.set_run_id(execution_id, run_id)
                return

            event_data = dict(data)
            agent_id = event_data.get("agent_id")
            if agent_id:
                node_id = workflow.node_id_for_agent(agent_id)
                if node_id:
                    event_data["node_id"] = node_id
                    if event_type == "node.task_assigned":
                        store.update_node_run(run_id, node_id, agent_id, "queued")
                    elif event_type == "node.task_started":
                        store.update_node_run(run_id, node_id, agent_id, "running")
                    elif event_type == "node.result_ready":
                        store.update_node_run(
                            run_id, node_id, agent_id, "completed", output=event_data.get("payload")
                        )
                    elif event_type == "node.error":
                        store.update_node_run(
                            run_id,
                            node_id,
                            agent_id,
                            "error",
                            output=event_data.get("payload"),
                            error=event_data.get("error"),
                        )
            await _publish_event(run_id, workflow_id, event_type, event_data)

        try:
            await _publish_event(run_id, workflow_id, "workflow.started", {"input": body.input})
            result = await engine.run_workflow(
                workflow_id, body.input, event_callback=_on_orchestrator_event
            )
            result_data = result.to_dict()
            store.complete_run(run_id, result.status, result_data)
            event_type = "workflow.completed" if result.status == "completed" else "workflow.failed"
            await _publish_event(run_id, workflow_id, event_type, result_data)
        except Exception as exc:
            logger.exception("api.workflow_run_failed", workflow_id=workflow_id)
            error = {"error": str(exc)}
            store.complete_run(run_id, "error", error)
            await _publish_event(run_id, workflow_id, "workflow.failed", error)
        finally:
            if engine._execution_logger is not None:
                for execution_id in execution_ids:
                    engine._execution_logger.clear_run_id(execution_id)

    asyncio.create_task(_execute())
    return {"run_id": run_id, "workflow_id": workflow_id, "status": "started"}


@router.get("/{workflow_id}/runs")
async def get_runs(workflow_id: str) -> list[dict[str, Any]]:
    _get_or_seed_workflow(workflow_id)
    return get_platform_store().list_runs(workflow_id)


@router.get("/{workflow_id}/runs/{run_id}")
async def get_run(workflow_id: str, run_id: str) -> dict[str, Any]:
    run = get_platform_store().get_run(workflow_id, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
    return run
