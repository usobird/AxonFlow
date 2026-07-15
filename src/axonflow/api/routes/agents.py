"""Agent API — 列表、详情、编辑"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Literal

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
    model_profile_id: str | None = None
    agent_type: Literal["base", "remote"] = "base"
    remote_endpoint: str | None = None
    remote_credential_id: str | None = None
    remote_api_key_env: str | None = None


class ModelProfileSelectionRequest(BaseModel):
    model_profile_id: str = Field(min_length=1)


class CapabilitiesUpdateRequest(BaseModel):
    tools: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)


_AGENT_ID_PATTERN = re.compile(r"^[a-z][a-z0-9-]{2,63}$")


def _agent_to_dict(config: AgentConfig) -> dict:
    data = json.loads(config.model_dump_json())
    data["model_profile_id"] = config.parameters.get("model_profile_id")
    # Include persona content
    if config.persona:
        data["persona"] = {
            "soul": config.persona.soul or config.role,
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


@router.get("/catalog/tools")
async def list_tool_catalog() -> list[dict]:
    registry = get_engine()._tool_registry
    if registry is None:
        return []
    return [
        {
            "id": name,
            "description": registry.get(name).description if registry.get(name) else "",
        }
        for name in sorted(registry.list_tools())
    ]


@router.get("/catalog/skills")
async def list_skill_catalog() -> list[dict]:
    skills_dir = get_config_dir() / "skills"
    if not skills_dir.exists():
        return []
    return [
        {"id": path.name, "has_scripts": (path / "scripts").is_dir()}
        for path in sorted(skills_dir.iterdir(), key=lambda item: item.name)
        if path.is_dir() and (path / "SKILL.md").exists()
    ]


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

    if body.agent_type == "base" and not body.model_profile_id:
        raise HTTPException(status_code=422, detail="Model profile is required for a base Agent")
    if body.agent_type == "remote" and not body.remote_endpoint:
        raise HTTPException(
            status_code=422,
            detail="Remote endpoint is required for a Remote Agent",
        )
    if (
        body.remote_credential_id
        and not get_platform_store().get_credential(body.remote_credential_id)
    ):
        raise HTTPException(status_code=422, detail="Remote credential not found")
    profile = _get_model_profile_or_404(body.model_profile_id) if body.model_profile_id else None
    parameters: dict = {}
    if profile:
        parameters["model_profile_id"] = profile["id"]
    if body.agent_type == "remote":
        parameters["remote"] = {
            "endpoint": body.remote_endpoint,
            **({"credential_id": body.remote_credential_id} if body.remote_credential_id else {}),
            **({"api_key_env": body.remote_api_key_env} if body.remote_api_key_env else {}),
        }
    config = AgentConfig(
        id=body.id,
        name=body.name.strip(),
        role=body.role.strip(),
        agent_type=body.agent_type,
        model=ModelConfig.model_validate(profile["config"]) if profile else ModelConfig(),
        parameters=parameters,
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
    if agent_path is None:
        raise HTTPException(status_code=404, detail=f"Agent not found: {agent_id}")
    config = _load_agent_from_path(agent_path)
    if agent_path.is_file():
        directory = agents_dir / config.id
        if directory.exists():
            raise HTTPException(
                status_code=409,
                detail=f"Agent directory already exists: {config.id}",
            )
        directory.mkdir(parents=True)
        _write_agent_config(directory, config)
        agent_path.unlink()
        agent_path = directory
    persona_file = agent_path / file_name
    persona_file.write_text(body.content, encoding="utf-8")
    field_name = file_name.removesuffix(".md")
    setattr(config.persona, field_name, body.content)
    running_agent = get_engine().agent_registry.get(agent_id)
    if running_agent is not None:
        setattr(running_agent.config.persona, field_name, body.content)
    return {"status": "ok", "file": file_name}


@router.put("/{agent_id}/capabilities")
async def update_agent_capabilities(agent_id: str, body: CapabilitiesUpdateRequest) -> dict:
    config_dir = get_config_dir()
    agent_path = _find_agent_path(config_dir / "agents", agent_id)
    if agent_path is None:
        raise HTTPException(status_code=404, detail=f"Agent not found: {agent_id}")
    config = _load_agent_from_path(agent_path)
    config.tools = list(dict.fromkeys(body.tools))
    config.skills = list(dict.fromkeys(body.skills))
    _write_agent_config(agent_path, config)
    running_agent = get_engine().agent_registry.get(agent_id)
    if running_agent is not None:
        running_agent.config.tools = config.tools
        running_agent.config.skills = config.skills
    return {"agent_id": agent_id, "tools": config.tools, "skills": config.skills}


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


def _load_agent_from_path(agent_path: Path) -> AgentConfig:
    source = agent_path / "config.yaml" if agent_path.is_dir() else agent_path
    raw = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
    return AgentConfig.model_validate(raw.get("agent", raw))


def _write_agent_config(agent_path: Path, config: AgentConfig) -> None:
    target = agent_path / "config.yaml" if agent_path.is_dir() else agent_path
    target.write_text(
        yaml.safe_dump(
            {"agent": config.model_dump(mode="json", exclude_none=True)},
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def _get_model_profile_or_404(profile_id: str) -> dict:
    profile = get_platform_store().get_model_profile(profile_id)
    if profile is None:
        raise HTTPException(status_code=422, detail="Model profile not found")
    return profile
