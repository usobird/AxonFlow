"""Models used by the visual AgentFlow platform layer.

The runtime still consumes ``WorkflowConfig``.  ``PlatformWorkflow`` is the
stable product-facing representation and can be projected to that runtime
format without losing the existing orchestration features.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from axonflow.config.models import (
    AgentConfig,
    AgentInstanceConfig,
    FlowConfig,
    Route,
    RouteCondition,
    TriggerConfig,
    WorkflowConfig,
)


class CanvasPosition(BaseModel):
    """A deterministic position for a workflow node on the canvas."""

    x: float = 0
    y: float = 0


class AgentManifest(BaseModel):
    """Public metadata used by the Agent Library and future marketplace."""

    id: str
    name: str
    version: str = "0.1.0"
    description: str = ""
    tags: list[str] = Field(default_factory=lambda: ["built-in"])
    input_schema: dict[str, Any] = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {"task": {"type": "string"}},
            "required": ["task"],
        }
    )
    output_schema: dict[str, Any] = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "content": {"type": "string"},
            },
        }
    )
    deploy_mode: Literal["platform", "local_runner", "remote"] = "platform"
    tools: list[str] = Field(default_factory=list)
    model: str | None = None

    @classmethod
    def from_agent_config(cls, config: AgentConfig) -> AgentManifest:
        description = " ".join(config.role.strip().split())
        return cls(
            id=config.id,
            name=config.name,
            description=description[:240],
            tags=["built-in", config.agent_type],
            tools=config.tools,
            model=config.model.name,
        )


class WorkflowNode(BaseModel):
    """An executable Agent node in a visual workflow."""

    id: str
    agent_id: str
    label: str
    position: CanvasPosition = Field(default_factory=CanvasPosition)
    is_entry: bool = False
    config: dict[str, Any] = Field(default_factory=dict)


class WorkflowEdge(BaseModel):
    """A directed execution path between two Agent nodes."""

    id: str
    source: str
    target: str
    condition: RouteCondition | None = None


class PlatformWorkflow(BaseModel):
    """Product-facing workflow graph, independent from its storage format."""

    id: str
    name: str
    description: str = ""
    nodes: list[WorkflowNode] = Field(default_factory=list)
    edges: list[WorkflowEdge] = Field(default_factory=list)
    trigger: TriggerConfig = Field(default_factory=TriggerConfig)
    context: dict[str, Any] = Field(default_factory=dict)
    max_iterations: int = 10
    timeout: int = 3600
    mode: str = "flat"
    terminate_on: list[dict[str, Any]] = Field(default_factory=list)
    supervisor: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_graph(self) -> PlatformWorkflow:
        node_ids = [node.id for node in self.nodes]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("Workflow node IDs must be unique")
        if self.nodes and sum(node.is_entry for node in self.nodes) != 1:
            raise ValueError("A workflow must have exactly one entry node")
        known = set(node_ids)
        for edge in self.edges:
            if edge.source not in known or edge.target not in known:
                raise ValueError(f"Edge '{edge.id}' references an unknown node")
            if edge.source == edge.target:
                raise ValueError("A node cannot route to itself")
        return self

    @classmethod
    def from_workflow_config(cls, config: WorkflowConfig) -> PlatformWorkflow:
        role_overrides = config.context.get("agent_role_overrides", {})
        if not isinstance(role_overrides, dict):
            role_overrides = {}
        success_terminations = {
            str(condition.get("agent"))
            for condition in config.flow.terminate_on
            if condition.get("status") == "success" and condition.get("agent")
        }
        if config.agent_instances:
            nodes = [
                WorkflowNode(
                    id=instance.node_id,
                    agent_id=instance.template_id,
                    label=instance.name,
                    position=CanvasPosition(x=80 + index * 260, y=220),
                    is_entry=instance.id == config.flow.entry,
                    config={
                        **(
                            {"responsibility": responsibility}
                            if isinstance(
                                responsibility := role_overrides.get(instance.id), str
                            )
                            and responsibility.strip()
                            else {}
                        ),
                        **(
                            {"model_profile_id": instance.model_profile_id}
                            if instance.model_profile_id
                            else {}
                        ),
                        **(
                            {"terminate_on_success": True}
                            if instance.id in success_terminations
                            else {}
                        ),
                    },
                )
                for index, instance in enumerate(config.agent_instances)
            ]
            node_id_by_runtime_id = {
                instance.id: instance.node_id for instance in config.agent_instances
            }
        else:
            nodes = [
                WorkflowNode(
                    id=f"node-{agent_id}",
                    agent_id=agent_id,
                    label=agent_id,
                    position=CanvasPosition(x=80 + index * 260, y=220),
                    is_entry=agent_id == config.flow.entry,
                    config={
                        **(
                            {"responsibility": responsibility}
                            if isinstance(responsibility := role_overrides.get(agent_id), str)
                            and responsibility.strip()
                            else {}
                        ),
                        **(
                            {"terminate_on_success": True}
                            if agent_id in success_terminations
                            else {}
                        ),
                    },
                )
                for index, agent_id in enumerate(config.agents)
            ]
            node_id_by_runtime_id = {node.agent_id: node.id for node in nodes}
        edges: list[WorkflowEdge] = []
        for source_agent, routes in config.flow.routes.items():
            for index, route in enumerate(routes):
                source = node_id_by_runtime_id.get(source_agent)
                target = node_id_by_runtime_id.get(route.target)
                if source and target:
                    edges.append(
                        WorkflowEdge(
                            id=f"edge-{source_agent}-{route.target}-{index}",
                            source=source,
                            target=target,
                            condition=route.condition,
                        )
                    )
        supervisor = config.flow.supervisor.model_dump() if config.flow.supervisor else None
        return cls(
            id=config.id,
            name=config.name,
            nodes=nodes,
            edges=edges,
            trigger=config.trigger,
            context=config.context,
            max_iterations=config.flow.max_iterations,
            timeout=config.flow.timeout,
            mode=config.flow.mode,
            terminate_on=config.flow.terminate_on,
            supervisor=supervisor,
        )

    def to_workflow_config(self) -> WorkflowConfig:
        entry = next(node for node in self.nodes if node.is_entry)
        runtime_id_by_node_id = {
            node.id: self.runtime_agent_id(node) for node in self.nodes
        }
        runtime_id_by_template_id = {
            node.agent_id: runtime_id_by_node_id[node.id] for node in self.nodes
        }
        routes: dict[str, list[Route]] = {}
        for edge in self.edges:
            source_agent = runtime_id_by_node_id[edge.source]
            target_agent = runtime_id_by_node_id[edge.target]
            routes.setdefault(source_agent, []).append(
                Route(target=target_agent, condition=edge.condition)
            )
        context = dict(self.context)
        role_overrides = {
            runtime_id_by_node_id[node.id]: responsibility.strip()
            for node in self.nodes
            if isinstance(responsibility := node.config.get("responsibility"), str)
            and responsibility.strip()
        }
        if role_overrides:
            context["agent_role_overrides"] = role_overrides
        else:
            context.pop("agent_role_overrides", None)
        has_termination_settings = any(
            "terminate_on_success" in node.config for node in self.nodes
        )
        if has_termination_settings:
            configured_agents = set(runtime_id_by_node_id.values())
            terminate_on = [
                self._runtime_condition(condition, runtime_id_by_template_id)
                for condition in self.terminate_on
                if not (
                    condition.get("status") == "success"
                    and runtime_id_by_template_id.get(
                        condition.get("agent"), condition.get("agent")
                    )
                    in configured_agents
                )
            ]
            terminate_on.extend(
                {
                    "agent": runtime_id_by_node_id[node.id],
                    "status": "success",
                }
                for node in self.nodes
                if node.config.get("terminate_on_success") is True
            )
        else:
            terminate_on = [
                self._runtime_condition(condition, runtime_id_by_template_id)
                for condition in self.terminate_on
            ]
        supervisor = dict(self.supervisor) if self.supervisor else None
        if supervisor and isinstance(supervisor.get("agent_id"), str):
            supervisor["agent_id"] = runtime_id_by_template_id.get(
                supervisor["agent_id"], supervisor["agent_id"]
            )
        return WorkflowConfig(
            id=self.id,
            name=self.name,
            trigger=self.trigger,
            agents=list(runtime_id_by_node_id.values()),
            agent_instances=[
                AgentInstanceConfig(
                    id=runtime_id_by_node_id[node.id],
                    node_id=node.id,
                    template_id=node.agent_id,
                    name=node.label,
                    model_profile_id=(
                        node.config.get("model_profile_id")
                        if isinstance(node.config.get("model_profile_id"), str)
                        else None
                    ),
                )
                for node in self.nodes
            ],
            flow=FlowConfig(
                mode=self.mode,
                entry=runtime_id_by_node_id[entry.id],
                max_iterations=self.max_iterations,
                timeout=self.timeout,
                routes=routes,
                terminate_on=terminate_on,
                supervisor=supervisor,
            ),
            context=context,
        )

    def runtime_agent_id(self, node: WorkflowNode) -> str:
        """Return the stable workflow-scoped identity for a node entity."""
        return f"{self.id}--{node.id}"

    @staticmethod
    def _runtime_condition(
        condition: dict[str, Any], runtime_id_by_template_id: dict[str, str]
    ) -> dict[str, Any]:
        runtime_condition = dict(condition)
        agent_id = runtime_condition.get("agent")
        if isinstance(agent_id, str):
            runtime_condition["agent"] = runtime_id_by_template_id.get(agent_id, agent_id)
        return runtime_condition

    def node_id_for_agent(self, agent_id: str) -> str | None:
        for node in self.nodes:
            runtime_id = self.runtime_agent_id(node)
            if agent_id in {node.agent_id, runtime_id} or agent_id.endswith(f"--{runtime_id}"):
                return node.id
        return None
