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
        agent_ids = [node.agent_id for node in self.nodes]
        if len(agent_ids) != len(set(agent_ids)):
            raise ValueError("An Agent may appear only once in an MVP workflow")
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
        nodes = [
            WorkflowNode(
                id=f"node-{agent_id}",
                agent_id=agent_id,
                label=agent_id,
                position=CanvasPosition(x=80 + index * 260, y=220),
                is_entry=agent_id == config.flow.entry,
            )
            for index, agent_id in enumerate(config.agents)
        ]
        node_id_by_agent = {node.agent_id: node.id for node in nodes}
        edges: list[WorkflowEdge] = []
        for source_agent, routes in config.flow.routes.items():
            for index, route in enumerate(routes):
                source = node_id_by_agent.get(source_agent)
                target = node_id_by_agent.get(route.target)
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
        node_by_id = {node.id: node for node in self.nodes}
        routes: dict[str, list[Route]] = {}
        for edge in self.edges:
            source_agent = node_by_id[edge.source].agent_id
            target_agent = node_by_id[edge.target].agent_id
            routes.setdefault(source_agent, []).append(
                Route(target=target_agent, condition=edge.condition)
            )
        return WorkflowConfig(
            id=self.id,
            name=self.name,
            trigger=self.trigger,
            agents=[node.agent_id for node in self.nodes],
            flow=FlowConfig(
                mode=self.mode,
                entry=entry.agent_id,
                max_iterations=self.max_iterations,
                timeout=self.timeout,
                routes=routes,
                terminate_on=self.terminate_on,
                supervisor=self.supervisor,
            ),
            context=self.context,
        )

    def node_id_for_agent(self, agent_id: str) -> str | None:
        for node in self.nodes:
            if node.agent_id == agent_id:
                return node.id
        return None
