"""FastAPI 依赖注入"""

from __future__ import annotations
from pathlib import Path
from axonflow.engine import AxonFlowEngine

_engine: AxonFlowEngine | None = None
_config_dir: Path = Path("config")


def set_engine(engine: AxonFlowEngine) -> None:
    global _engine
    _engine = engine


def get_engine() -> AxonFlowEngine:
    if _engine is None:
        raise RuntimeError("Engine not initialized")
    return _engine


def set_config_dir(config_dir: Path) -> None:
    global _config_dir
    _config_dir = config_dir


def get_config_dir() -> Path:
    return _config_dir
