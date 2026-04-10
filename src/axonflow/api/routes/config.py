"""全局配置 API"""

from __future__ import annotations
import json
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from axonflow.api.deps import get_config_dir
from axonflow.config.loader import load_global_config
from axonflow.config.models import AxonFlowConfig
import yaml

router = APIRouter(prefix="/api/config", tags=["config"])


class YamlUpdateRequest(BaseModel):
    yaml_content: str


@router.get("")
async def get_config():
    config_dir = get_config_dir()
    config_path = config_dir / "axonflow.yaml"
    config = load_global_config(config_path)
    data = json.loads(config.model_dump_json())
    # Hide actual API key values — only show env var names
    if "default_model" in data and data["default_model"].get("api_key_env"):
        data["default_model"]["_api_key_env_note"] = "Value hidden for security"
    # Also return raw YAML for editor
    if config_path.exists():
        data["raw_yaml"] = config_path.read_text(encoding="utf-8")
    return data


@router.put("")
async def update_config(body: YamlUpdateRequest):
    config_dir = get_config_dir()
    config_path = config_dir / "axonflow.yaml"
    # Validate
    try:
        new_data = yaml.safe_load(body.yaml_content)
        validated = AxonFlowConfig(**new_data)
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))
    # Write
    config_path.write_text(body.yaml_content, encoding="utf-8")
    return json.loads(validated.model_dump_json())
