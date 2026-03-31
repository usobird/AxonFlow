"""Pydantic 配置模型定义"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# ============================================================
# LLM 模型配置
# ============================================================

class ModelConfig(BaseModel):
    """LLM 模型配置"""

    provider: str = "openai"
    name: str = "gpt-4o"
    temperature: float = 0.7
    max_tokens: int = 4096
    api_base: str | None = None
    api_key_env: str | None = None  # 环境变量名，如 OPENAI_API_KEY
    fallback_models: list[str] = Field(default_factory=list)


# ============================================================
# 智能体配置
# ============================================================

class AgentConfig(BaseModel):
    """智能体配置"""

    id: str
    name: str
    role: str  # System Prompt / 角色描述
    model: ModelConfig = Field(default_factory=ModelConfig)
    tools: list[str] = Field(default_factory=list)
    can_request: list[str] = Field(default_factory=list)
    max_concurrent: int = 1
    retry_limit: int = 3


# ============================================================
# 工作流配置
# ============================================================

class TriggerConfig(BaseModel):
    """触发器配置"""

    type: str = "manual"  # manual / cron / event
    cron: str | None = None
    event: str | None = None


class RouteCondition(BaseModel):
    """路由条件"""

    field: str
    operator: str = "eq"  # eq / neq / contains / gt / lt
    value: Any = None

    def evaluate(self, actual: Any) -> bool:
        """评估条件是否满足"""
        ops = {
            "eq": lambda a, b: a == b,
            "neq": lambda a, b: a != b,
            "contains": lambda a, b: b in str(a),
            "gt": lambda a, b: a > b,
            "lt": lambda a, b: a < b,
        }
        op_fn = ops.get(self.operator)
        if op_fn is None:
            return False
        try:
            return op_fn(actual, self.value)
        except (TypeError, ValueError):
            return False


class Route(BaseModel):
    """路由规则"""

    target: str  # 目标 Agent ID
    condition: RouteCondition | None = None


class FlowConfig(BaseModel):
    """工作流流程配置"""

    entry: str  # 入口 Agent ID
    max_iterations: int = 10
    timeout: int = 3600  # 秒
    routes: dict[str, list[Route]] = Field(default_factory=dict)
    terminate_on: list[dict[str, Any]] = Field(default_factory=list)


class WorkflowConfig(BaseModel):
    """工作流顶层配置"""

    id: str
    name: str
    trigger: TriggerConfig = Field(default_factory=TriggerConfig)
    agents: list[str] = Field(default_factory=list)
    flow: FlowConfig
    context: dict[str, Any] = Field(default_factory=dict)


# ============================================================
# 全局配置
# ============================================================

class RedisConfig(BaseModel):
    """Redis 连接配置"""

    url: str = "redis://localhost:6379"
    max_connections: int = 10


class SandboxConfig(BaseModel):
    """沙箱配置"""

    enabled: bool = False
    command_whitelist: list[str] = Field(default_factory=list)
    blocked_paths: list[str] = Field(default_factory=list)


class WebhookEndpoint(BaseModel):
    """Webhook 端点"""

    url: str
    events: list[str] = Field(default_factory=lambda: ["workflow.completed", "workflow.failed"])


class AutoFlowConfig(BaseModel):
    """AutoFlow 全局配置"""

    redis: RedisConfig = Field(default_factory=RedisConfig)
    sandbox: SandboxConfig = Field(default_factory=SandboxConfig)
    webhooks: list[WebhookEndpoint] = Field(default_factory=list)
    log_level: str = "INFO"
    log_format: str = "json"  # json / console
    workspace_dir: str = "./workspace"
    default_model: ModelConfig = Field(default_factory=ModelConfig)
    token_budget: int | None = None  # 全局 Token 预算上限
