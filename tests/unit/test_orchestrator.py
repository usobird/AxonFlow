"""编排器测试 — BaseOrchestrator / FlatOrchestrator / 工厂"""

import pytest

from axonflow.config.models import (
    AgentConfig,
    FlowConfig,
    JoinConfig,
    ModelConfig,
    Route,
    RouteCondition,
    SupervisorConfig,
    WorkflowConfig,
)
from axonflow.core.agent import AgentRegistry, BaseAgent
from axonflow.core.message import Message, MessageType
from axonflow.core.orchestrator_factory import (
    _ORCHESTRATOR_REGISTRY,
    create_orchestrator,
    register_orchestrator_type,
)
from axonflow.core.workflow import (
    BaseOrchestrator,
    FlatOrchestrator,
    WorkflowOrchestrator,
    WorkflowResult,
)
from axonflow.llm.gateway import LLMGateway
from axonflow.messaging.memory_bus import InMemoryMessageBus
from axonflow.tools.base import ToolRegistry


def _make_agent(agent_id: str, bus: InMemoryMessageBus) -> BaseAgent:
    """创建测试用 Agent（不启动消息循环）"""
    config = AgentConfig(
        id=agent_id,
        name=f"Test {agent_id}",
        role="test",
        model=ModelConfig(provider="openai", name="gpt-4o-mini"),
    )
    return BaseAgent(
        config=config,
        message_bus=bus,
        llm_gateway=LLMGateway(),
        tool_registry=ToolRegistry(),
    )


def _make_registry(agent_ids: list[str], bus: InMemoryMessageBus) -> AgentRegistry:
    """创建含指定 agents 的注册表"""
    registry = AgentRegistry()
    for aid in agent_ids:
        registry.register(_make_agent(aid, bus))
    return registry


class TestWorkflowResult:
    def test_to_dict(self):
        result = WorkflowResult(
            workflow_id="wf-1",
            status="completed",
            output={"content": "ok"},
            iterations=3,
            duration_seconds=1.234,
        )
        d = result.to_dict()
        assert d["workflow_id"] == "wf-1"
        assert d["status"] == "completed"
        assert d["iterations"] == 3
        assert d["duration_seconds"] == 1.23


class TestBaseOrchestrator:
    def test_cannot_instantiate_abc(self):
        """BaseOrchestrator 是抽象类，不能直接实例化"""
        with pytest.raises(TypeError):
            BaseOrchestrator(
                config=WorkflowConfig(id="x", name="x", flow=FlowConfig(entry="a")),
                agent_registry=AgentRegistry(),
                message_bus=InMemoryMessageBus(),
            )

    def test_backward_compat_alias(self):
        """WorkflowOrchestrator 是 FlatOrchestrator 的别名"""
        assert WorkflowOrchestrator is FlatOrchestrator


class TestFlatOrchestratorRouting:
    @pytest.mark.asyncio
    async def test_resolve_next_unconditional(self):
        """无条件路由应始终匹配"""
        bus = InMemoryMessageBus()
        config = WorkflowConfig(
            id="wf",
            name="test",
            agents=["a", "b"],
            flow=FlowConfig(
                entry="a",
                routes={"a": [Route(target="b")]},
            ),
        )
        registry = _make_registry(["a", "b"], bus)
        orch = FlatOrchestrator(config, registry, bus)

        event = Message(
            sender="a",
            receiver="__orchestrator__",
            type=MessageType.TASK_RESPONSE,
            payload={"status": "success"},
        )
        targets = orch._resolve_next(event)
        assert len(targets) == 1
        assert targets[0][0] == "b"

    @pytest.mark.asyncio
    async def test_resolve_next_conditional(self):
        """条件路由应根据 payload 匹配"""
        bus = InMemoryMessageBus()
        config = WorkflowConfig(
            id="wf",
            name="test",
            agents=["a", "b", "c"],
            flow=FlowConfig(
                entry="a",
                routes={
                    "a": [
                        Route(
                            target="b",
                            condition=RouteCondition(
                                field="status", operator="eq", value="success"
                            ),
                        ),
                        Route(
                            target="c",
                            condition=RouteCondition(field="status", operator="eq", value="error"),
                        ),
                    ],
                },
            ),
        )
        registry = _make_registry(["a", "b", "c"], bus)
        orch = FlatOrchestrator(config, registry, bus)

        success_event = Message(
            sender="a",
            receiver="__orchestrator__",
            type=MessageType.TASK_RESPONSE,
            payload={"status": "success"},
        )
        targets = orch._resolve_next(success_event)
        assert len(targets) == 1
        assert targets[0][0] == "b"

        error_event = Message(
            sender="a",
            receiver="__orchestrator__",
            type=MessageType.TASK_RESPONSE,
            payload={"status": "error"},
        )
        targets = orch._resolve_next(error_event)
        assert len(targets) == 1
        assert targets[0][0] == "c"


class TestOrchestratorFactory:
    def test_create_flat(self):
        bus = InMemoryMessageBus()
        config = WorkflowConfig(
            id="wf",
            name="test",
            agents=["a"],
            flow=FlowConfig(mode="flat", entry="a"),
        )
        registry = _make_registry(["a"], bus)
        orch = create_orchestrator(config, registry, bus)
        assert isinstance(orch, FlatOrchestrator)

    def test_create_unknown_fallback(self):
        bus = InMemoryMessageBus()
        config = WorkflowConfig(
            id="wf",
            name="test",
            agents=["a"],
            flow=FlowConfig(mode="nonexistent_mode", entry="a"),
        )
        registry = _make_registry(["a"], bus)
        orch = create_orchestrator(config, registry, bus)
        assert isinstance(orch, FlatOrchestrator)

    def test_create_supervisor(self):
        bus = InMemoryMessageBus()
        config = WorkflowConfig(
            id="wf",
            name="test",
            agents=["a", "supervisor"],
            flow=FlowConfig(
                mode="supervisor",
                entry="a",
                supervisor=SupervisorConfig(agent_id="supervisor"),
            ),
        )
        registry = _make_registry(["a", "supervisor"], bus)
        from axonflow.core.supervisor import SupervisorOrchestrator

        orch = create_orchestrator(config, registry, bus, llm_gateway=LLMGateway())
        assert isinstance(orch, SupervisorOrchestrator)

    def test_register_custom_orchestrator(self):
        class CustomOrch(FlatOrchestrator):
            pass

        register_orchestrator_type("custom_test", CustomOrch)
        bus = InMemoryMessageBus()
        config = WorkflowConfig(
            id="wf",
            name="test",
            agents=["a"],
            flow=FlowConfig(mode="custom_test", entry="a"),
        )
        registry = _make_registry(["a"], bus)
        orch = create_orchestrator(config, registry, bus)
        assert isinstance(orch, CustomOrch)
        _ORCHESTRATOR_REGISTRY.pop("custom_test", None)

    def test_import_invalid_class_path(self):
        bus = InMemoryMessageBus()
        config = WorkflowConfig(
            id="wf",
            name="test",
            agents=["a"],
            flow=FlowConfig(mode="nonexistent.module.Class", entry="a"),
        )
        registry = _make_registry(["a"], bus)
        with pytest.raises(ImportError, match="Cannot import"):
            create_orchestrator(config, registry, bus)


class TestConfigModels:
    def test_join_config(self):
        cfg = JoinConfig(wait_for=["a", "b"], strategy="all")
        assert cfg.wait_for == ["a", "b"]
        assert cfg.strategy == "all"

    def test_supervisor_config(self):
        cfg = SupervisorConfig(agent_id="sup")
        assert cfg.planning_enabled is True
        assert cfg.intervention_on_failure is True

    def test_flow_config_mode_default(self):
        cfg = FlowConfig(entry="a")
        assert cfg.mode == "flat"
        assert cfg.join == {}
        assert cfg.supervisor is None

    def test_workflow_config_extends(self):
        cfg = WorkflowConfig(
            id="wf",
            name="test",
            extends="base-wf",
            flow=FlowConfig(entry="a"),
        )
        assert cfg.extends == "base-wf"
