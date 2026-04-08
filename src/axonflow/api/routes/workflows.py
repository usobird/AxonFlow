"""Workflow API — 列表、详情、编辑、执行"""

from __future__ import annotations
import asyncio
import uuid
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from axonflow.api.deps import get_engine, get_config_dir
from axonflow.api.ws import broadcaster
from axonflow.config.loader import load_all_workflow_configs, load_workflow_config
from axonflow.config.models import WorkflowConfig
from datetime import datetime, timezone
import json
import yaml
import structlog

logger = structlog.get_logger()
router = APIRouter(prefix="/api/workflows", tags=["workflows"])

# In-memory store for run history
_run_history: list[dict] = []


class RunRequest(BaseModel):
    input: str = "Hello"


class YamlUpdateRequest(BaseModel):
    yaml_content: str


@router.get("")
async def list_workflows():
    config_dir = get_config_dir()
    workflows_dir = config_dir / "workflows"
    configs = load_all_workflow_configs(workflows_dir)
    return [json.loads(c.model_dump_json()) for c in configs]


@router.get("/{workflow_id}")
async def get_workflow(workflow_id: str):
    config_dir = get_config_dir()
    workflows_dir = config_dir / "workflows"
    configs = load_all_workflow_configs(workflows_dir)
    for c in configs:
        if c.id == workflow_id:
            result = json.loads(c.model_dump_json())
            # Include raw YAML for editor
            for f in workflows_dir.glob("*.yaml"):
                try:
                    data = yaml.safe_load(f.read_text(encoding="utf-8"))
                    wf_id = data.get("id") if data else None
                    if wf_id is None and isinstance(data.get("workflow"), dict):
                        wf_id = data["workflow"].get("id")
                    if wf_id == workflow_id:
                        result["raw_yaml"] = f.read_text(encoding="utf-8")
                        break
                except Exception:
                    continue
            return result
    raise HTTPException(status_code=404, detail=f"Workflow not found: {workflow_id}")


@router.put("/{workflow_id}")
async def update_workflow(workflow_id: str, body: YamlUpdateRequest):
    config_dir = get_config_dir()
    workflows_dir = config_dir / "workflows"
    # Find the file
    target_file = None
    for f in workflows_dir.glob("*.yaml"):
        try:
            data = yaml.safe_load(f.read_text(encoding="utf-8"))
            if data and (
                data.get("id") == workflow_id
                or (
                    isinstance(data.get("workflow"), dict)
                    and data["workflow"].get("id") == workflow_id
                )
            ):
                target_file = f
                break
        except Exception:
            continue
    if target_file is None:
        raise HTTPException(status_code=404, detail=f"Workflow file not found: {workflow_id}")
    # Validate
    try:
        new_data = yaml.safe_load(body.yaml_content)
        if "workflow" in new_data:
            new_data = new_data["workflow"]
        validated = WorkflowConfig(**new_data)
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))
    # Write
    target_file.write_text(body.yaml_content, encoding="utf-8")
    return json.loads(validated.model_dump_json())


@router.post("/{workflow_id}/run")
async def run_workflow(workflow_id: str, body: RunRequest):
    engine = get_engine()
    run_id = f"run-{uuid.uuid4().hex[:8]}"

    async def _execute():
        # Wire run_id to execution logger for WebSocket broadcasting
        if engine._execution_logger is not None:
            engine._execution_logger.set_run_id(workflow_id, run_id)

        try:
            # Notify start
            await broadcaster.broadcast(
                run_id,
                {
                    "type": "workflow.started",
                    "workflow_id": workflow_id,
                    "run_id": run_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "data": {"input": body.input},
                },
            )
            result = await engine.run_workflow(workflow_id, body.input)
            run_record = {
                "run_id": run_id,
                "workflow_id": workflow_id,
                "status": result.status,
                "iterations": result.iterations,
                "duration_seconds": result.duration_seconds,
                "output": result.output,
                "started_at": datetime.now(timezone.utc).isoformat(),
            }
            _run_history.append(run_record)
            # Notify complete
            await broadcaster.broadcast(
                run_id,
                {
                    "type": "workflow.completed",
                    "workflow_id": workflow_id,
                    "run_id": run_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "data": result.to_dict(),
                },
            )
        except Exception as e:
            logger.error("api.workflow_run_failed", error=str(e))
            await broadcaster.broadcast(
                run_id,
                {
                    "type": "workflow.failed",
                    "workflow_id": workflow_id,
                    "run_id": run_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "data": {"error": str(e)},
                },
            )
        finally:
            # Clean up run_id mapping
            if engine._execution_logger is not None:
                engine._execution_logger.clear_run_id(workflow_id)

    asyncio.create_task(_execute())
    return {"run_id": run_id, "workflow_id": workflow_id, "status": "started"}


@router.get("/{workflow_id}/runs")
async def get_runs(workflow_id: str):
    return [r for r in _run_history if r["workflow_id"] == workflow_id]
