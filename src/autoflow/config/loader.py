"""YAML 配置文件加载器"""

from __future__ import annotations

from pathlib import Path
from typing import TypeVar

import yaml
from pydantic import BaseModel

from autoflow.config.models import AgentConfig, AutoFlowConfig, WorkflowConfig

T = TypeVar("T", bound=BaseModel)


def _load_yaml(path: Path) -> dict:
    """加载单个 YAML 文件"""
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if data is None:
        return {}
    return data


def load_global_config(path: Path | str = "config/autoflow.yaml") -> AutoFlowConfig:
    """加载全局配置"""
    path = Path(path)
    if not path.exists():
        return AutoFlowConfig()
    data = _load_yaml(path)
    return AutoFlowConfig(**data)


def load_agent_config(path: Path | str) -> AgentConfig:
    """加载单个智能体配置"""
    data = _load_yaml(Path(path))
    # 支持顶层 key 为 "agent" 的格式
    if "agent" in data:
        data = data["agent"]
    return AgentConfig(**data)


def load_all_agent_configs(directory: Path | str = "config/agents") -> list[AgentConfig]:
    """加载目录下所有智能体配置"""
    directory = Path(directory)
    if not directory.exists():
        return []
    configs = []
    for yaml_file in sorted(directory.glob("*.yaml")):
        configs.append(load_agent_config(yaml_file))
    for yml_file in sorted(directory.glob("*.yml")):
        configs.append(load_agent_config(yml_file))
    return configs


def load_workflow_config(path: Path | str) -> WorkflowConfig:
    """加载单个工作流配置"""
    data = _load_yaml(Path(path))
    if "workflow" in data:
        data = data["workflow"]
    return WorkflowConfig(**data)


def load_all_workflow_configs(
    directory: Path | str = "config/workflows",
) -> list[WorkflowConfig]:
    """加载目录下所有工作流配置"""
    directory = Path(directory)
    if not directory.exists():
        return []
    configs = []
    for yaml_file in sorted(directory.glob("*.yaml")):
        configs.append(load_workflow_config(yaml_file))
    for yml_file in sorted(directory.glob("*.yml")):
        configs.append(load_workflow_config(yml_file))
    return configs
