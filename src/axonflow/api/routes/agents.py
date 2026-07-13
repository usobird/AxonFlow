"""Agent API — 列表、详情、编辑"""

from __future__ import annotations

import json
from pathlib import Path

import yaml
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from axonflow.api.deps import get_config_dir
from axonflow.config.loader import (
    load_all_agent_configs,
)
from axonflow.config.models import AgentConfig
from axonflow.platform.models import AgentManifest

router = APIRouter(prefix="/api/agents", tags=["agents"])


class YamlUpdateRequest(BaseModel):
    yaml_content: str


class PersonaUpdateRequest(BaseModel):
    content: str


def _agent_to_dict(config: AgentConfig) -> dict:
    data = json.loads(config.model_dump_json())
    # Include persona content
    if config.persona:
        data["persona"] = {
            "soul": config.persona.soul,
            "user": config.persona.user,
            "workflow": config.persona.workflow,
        }
    return data


@router.get("")
async def list_agents():
    config_dir = get_config_dir()
    agents_dir = config_dir / "agents"
    configs = load_all_agent_configs(agents_dir)
    return [_agent_to_dict(c) for c in configs]


@router.get("/manifests")
async def list_agent_manifests():
    """Return the stable Agent Library representation for visual workflows."""
    config_dir = get_config_dir()
    configs = load_all_agent_configs(config_dir / "agents")
    manifests = map(AgentManifest.from_agent_config, configs)
    return [manifest.model_dump(mode="json") for manifest in manifests]


@router.get("/{agent_id}")
async def get_agent(agent_id: str):
    config_dir = get_config_dir()
    agents_dir = config_dir / "agents"
    configs = load_all_agent_configs(agents_dir)
    for c in configs:
        if c.id == agent_id:
            result = _agent_to_dict(c)
            # Also return raw YAML for editor
            agent_path = _find_agent_path(agents_dir, agent_id)
            if agent_path:
                if agent_path.is_dir():
                    result["raw_yaml"] = (agent_path / "config.yaml").read_text(encoding="utf-8")
                else:
                    result["raw_yaml"] = agent_path.read_text(encoding="utf-8")
            return result
    raise HTTPException(status_code=404, detail=f"Agent not found: {agent_id}")


@router.put("/{agent_id}")
async def update_agent(agent_id: str, body: YamlUpdateRequest):
    config_dir = get_config_dir()
    agents_dir = config_dir / "agents"
    agent_path = _find_agent_path(agents_dir, agent_id)
    if agent_path is None:
        raise HTTPException(status_code=404, detail=f"Agent not found: {agent_id}")
    # Validate
    try:
        new_data = yaml.safe_load(body.yaml_content)
        if "agent" in new_data:
            new_data = new_data["agent"]
        validated = AgentConfig(**new_data)
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    # Write
    target = agent_path / "config.yaml" if agent_path.is_dir() else agent_path
    target.write_text(body.yaml_content, encoding="utf-8")
    return _agent_to_dict(validated)


@router.put("/{agent_id}/persona/{file_name}")
async def update_persona(agent_id: str, file_name: str, body: PersonaUpdateRequest):
    if file_name not in ("soul.md", "user.md", "workflow.md"):
        raise HTTPException(status_code=400, detail=f"Invalid persona file: {file_name}")
    config_dir = get_config_dir()
    agents_dir = config_dir / "agents"
    agent_path = _find_agent_path(agents_dir, agent_id)
    if agent_path is None or not agent_path.is_dir():
        raise HTTPException(status_code=404, detail=f"Agent directory not found: {agent_id}")
    persona_file = agent_path / file_name
    persona_file.write_text(body.content, encoding="utf-8")
    return {"status": "ok", "file": file_name}


def _find_agent_path(agents_dir: Path, agent_id: str) -> Path | None:
    """Find agent config path by id — check both directory and single-file format"""
    for entry in agents_dir.iterdir():
        if entry.is_dir() and (entry / "config.yaml").exists():
            try:
                data = yaml.safe_load((entry / "config.yaml").read_text(encoding="utf-8"))
                if data and (
                    data.get("id") == agent_id
                    or (isinstance(data.get("agent"), dict) and data["agent"].get("id") == agent_id)
                ):
                    return entry
            except Exception:
                continue
        elif entry.is_file() and entry.suffix in (".yaml", ".yml"):
            try:
                data = yaml.safe_load(entry.read_text(encoding="utf-8"))
                if data and (
                    data.get("id") == agent_id
                    or (isinstance(data.get("agent"), dict) and data["agent"].get("id") == agent_id)
                ):
                    return entry
            except Exception:
                continue
    return None
