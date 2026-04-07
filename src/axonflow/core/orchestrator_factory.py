"""编排器工厂 — 根据 mode 配置创建对应的编排器实例"""

from __future__ import annotations

import importlib

import structlog

from axonflow.config.models import WorkflowConfig
from axonflow.core.agent import AgentRegistry
from axonflow.core.workflow import BaseOrchestrator, FlatOrchestrator
from axonflow.messaging.base import MessageBus

logger = structlog.get_logger()

# 内置编排器注册表
_ORCHESTRATOR_REGISTRY: dict[str, type[BaseOrchestrator]] = {
    "flat": FlatOrchestrator,
}


def register_orchestrator_type(mode_name: str, orchestrator_class: type[BaseOrchestrator]) -> None:
    """注册自定义编排器类型"""
    _ORCHESTRATOR_REGISTRY[mode_name] = orchestrator_class
    logger.info("orchestrator_type.registered", mode=mode_name, cls=orchestrator_class.__name__)


def _import_orchestrator_class(class_path: str) -> type[BaseOrchestrator]:
    """动态导入自定义编排器类"""
    try:
        module_path, class_name = class_path.rsplit(".", 1)
        module = importlib.import_module(module_path)
        cls = getattr(module, class_name)
        if not (isinstance(cls, type) and issubclass(cls, BaseOrchestrator)):
            raise TypeError(f"{class_path} is not a subclass of BaseOrchestrator")
        return cls
    except (ImportError, AttributeError, ValueError) as e:
        raise ImportError(f"Cannot import orchestrator class '{class_path}': {e}") from e


def create_orchestrator(
    config: WorkflowConfig,
    agent_registry: AgentRegistry,
    message_bus: MessageBus,
    **kwargs,
) -> BaseOrchestrator:
    """编排器工厂方法

    根据 config.flow.mode 创建对应的编排器:
    - "flat" → FlatOrchestrator
    - "supervisor" → SupervisorOrchestrator (lazy import to avoid circular)
    - 含有 "." 的字符串 → 动态导入自定义编排器
    - 其他 → 查找注册表
    """
    mode = config.flow.mode

    if mode == "supervisor":
        # Lazy import to avoid circular dependency
        from axonflow.core.supervisor import SupervisorOrchestrator

        return SupervisorOrchestrator(
            config=config,
            agent_registry=agent_registry,
            message_bus=message_bus,
            **kwargs,
        )

    if "." in mode:
        # Custom class_path
        orchestrator_cls = _import_orchestrator_class(mode)
        return orchestrator_cls(
            config=config,
            agent_registry=agent_registry,
            message_bus=message_bus,
            **kwargs,
        )

    if mode in _ORCHESTRATOR_REGISTRY:
        orchestrator_cls = _ORCHESTRATOR_REGISTRY[mode]
        return orchestrator_cls(
            config=config,
            agent_registry=agent_registry,
            message_bus=message_bus,
            **kwargs,
        )

    logger.warning("orchestrator_factory.unknown_mode", mode=mode, fallback="flat")
    return FlatOrchestrator(
        config=config,
        agent_registry=agent_registry,
        message_bus=message_bus,
    )
