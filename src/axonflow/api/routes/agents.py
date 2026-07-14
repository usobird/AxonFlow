"""Agent API — 列表、详情、编辑"""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from axonflow.api.deps import get_config_dir, get_engine, get_platform_store
from axonflow.config.loader import (
    load_all_agent_configs,
)
from axonflow.config.models import AgentConfig, ModelConfig
from axonflow.platform.models import AgentManifest

router = APIRouter(prefix="/api/agents", tags=["agents"])


class YamlUpdateRequest(BaseModel):
    yaml_content: str


class PersonaUpdateRequest(BaseModel):
    content: str


class ModelUpdateRequest(BaseModel):
    model: ModelConfig


class AgentCreateRequest(BaseModel):
    id: str = Field(min_length=3, max_length=64)
    name: str = Field(min_length=1, max_length=100)
    role: str = Field(default="", max_length=4000)
    model_profile_id: str = Field(min_length=1)


class ModelProfileSelectionRequest(BaseModel):
    model_profile_id: str = Field(min_length=1)


_AGENT_ID_PATTERN = re.compile(r"^[a-z][a-z0-9-]{2,63}$")


def _agent_to_dict(config: AgentConfig) -> dict:
    data = json.loads(config.model_dump_json())
    data["model_profile_id"] = config.parameters.get("model_profile_id")
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


@router.post("", status_code=201)
async def create_agent(body: AgentCreateRequest) -> dict:
    """Create and start an Agent from a reusable model profile."""
    if not _AGENT_ID_PATTERN.fullmatch(body.id):
        raise HTTPException(
            status_code=422,
            detail=(
                "Agent ID must use lowercase letters, numbers, and hyphens, "
                "and start with a letter"
            ),
        )

    config_dir = get_config_dir()
    agents_dir = config_dir / "agents"
    if _find_agent_path(agents_dir, body.id) is not None:
        raise HTTPException(status_code=409, detail=f"Agent already exists: {body.id}")

    profile = _get_model_profile_or_404(body.model_profile_id)
    config = AgentConfig(
        id=body.id,
        name=body.name.strip(),
        role=body.role.strip(),
        model=ModelConfig.model_validate(profile["config"]),
        parameters={"model_profile_id": profile["id"]},
    )
    agents_dir.mkdir(parents=True, exist_ok=True)
    target = agents_dir / f"{config.id}.yaml"
    target.write_text(
        yaml.safe_dump(
            {"agent": config.model_dump(mode="json", exclude_none=True)},
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    try:
        await get_engine().add_agent(config)
    except Exception as exc:
        target.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Unable to start agent: {exc}") from exc
    return _agent_to_dict(config)


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


@router.put("/{agent_id}/model")
async def update_agent_model(agent_id: str, body: ModelUpdateRequest):
    """Persist a model override and apply it to the running Agent instance."""
    config_dir = get_config_dir()
    agents_dir = config_dir / "agents"
    agent_path = _find_agent_path(agents_dir, agent_id)
    if agent_path is None:
        raise HTTPException(status_code=404, detail=f"Agent not found: {agent_id}")

    target = agent_path / "config.yaml" if agent_path.is_dir() else agent_path
    raw = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    agent_data = raw["agent"] if isinstance(raw.get("agent"), dict) else raw
    agent_data["model"] = body.model.model_dump(mode="json", exclude_none=True)
    if isinstance(agent_data.get("parameters"), dict):
        agent_data["parameters"].pop("model_profile_id", None)
    target.write_text(
        yaml.safe_dump(raw, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    agent = get_engine().agent_registry.get(agent_id)
    if agent is not None:
        agent.config.model = body.model
        agent.config.parameters.pop("model_profile_id", None)
    return {"agent_id": agent_id, "model": body.model.model_dump(mode="json")}


@router.put("/{agent_id}/model-profile")
async def select_agent_model_profile(agent_id: str, body: ModelProfileSelectionRequest) -> dict:
    """Apply a saved model profile to an existing Agent."""
    profile = _get_model_profile_or_404(body.model_profile_id)
    config_dir = get_config_dir()
    agents_dir = config_dir / "agents"
    agent_path = _find_agent_path(agents_dir, agent_id)
    if agent_path is None:
        raise HTTPException(status_code=404, detail=f"Agent not found: {agent_id}")

    target = agent_path / "config.yaml" if agent_path.is_dir() else agent_path
    raw = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    agent_data = raw["agent"] if isinstance(raw.get("agent"), dict) else raw
    agent_data["model"] = profile["config"]
    parameters = agent_data.setdefault("parameters", {})
    parameters["model_profile_id"] = profile["id"]
    target.write_text(
        yaml.safe_dump(raw, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    agent = get_engine().agent_registry.get(agent_id)
    if agent is not None:
        agent.config.model = ModelConfig.model_validate(profile["config"])
        agent.config.parameters["model_profile_id"] = profile["id"]
    return {
        "agent_id": agent_id,
        "model_profile_id": profile["id"],
        "model": profile["config"],
    }


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


def _get_model_profile_or_404(profile_id: str) -> dict:
    profile = get_platform_store().get_model_profile(profile_id)
    if profile is None:
        raise HTTPException(status_code=422, detail="Model profile not found")
    return profile
