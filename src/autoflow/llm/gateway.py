"""LLM 统一调用网关 — 基于 LiteLLM 适配多模型"""

from __future__ import annotations

import os
from dataclasses import dataclass

import litellm
import structlog

from autoflow.config.models import ModelConfig
from autoflow.llm.token_tracker import TokenTracker

logger = structlog.get_logger()


class BudgetExceededError(Exception):
    """Token 预算超限"""


class LLMUnavailableError(Exception):
    """所有 LLM 模型不可用"""


@dataclass
class LLMResponse:
    """LLM 调用结果"""

    content: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


class LLMGateway:
    """统一 LLM 调用网关

    - 通过 LiteLLM 适配 OpenAI / Anthropic / Ollama 等多种后端
    - 支持模型降级（主模型不可用时自动切换备用模型）
    - Token 用量追踪与预算控制
    """

    def __init__(
        self,
        default_model: ModelConfig | None = None,
        token_budget: int | None = None,
    ) -> None:
        self._default_model = default_model or ModelConfig()
        self.token_tracker = TokenTracker(budget=token_budget)

        # 关闭 litellm 自带的冗余日志
        litellm.suppress_debug_info = True

    def _validate_model_config(self, config: ModelConfig | None) -> tuple[bool, str | None]:
        """检查模型配置是否可用"""
        if config is None:
            return False, "missing_config"
        if not config.provider or not config.provider.strip():
            return False, "missing_provider"
        if not config.name or not config.name.strip():
            return False, "missing_model_name"
        if config.max_tokens <= 0:
            return False, "invalid_max_tokens"
        if config.api_key_env is not None and not config.api_key_env.strip():
            return False, "invalid_api_key_env"
        return True, None

    def _select_model_config(
        self,
        override: ModelConfig | None,
        prefer_default: bool,
    ) -> ModelConfig:
        """决定本次调用使用的模型配置"""
        if prefer_default:
            default_ok, default_reason = self._validate_model_config(self._default_model)
            if default_ok:
                return self._default_model
            logger.warning(
                "llm.default_model_invalid",
                reason=default_reason,
            )

        if override:
            override_ok, override_reason = self._validate_model_config(override)
            if override_ok:
                if prefer_default:
                    logger.info("llm.agent_model_fallback", reason=override_reason)
                return override
            logger.error(
                "llm.agent_model_invalid",
                reason=override_reason,
            )

        raise LLMUnavailableError("No valid LLM model configuration available")

    def _resolve_model_string(self, config: ModelConfig) -> str:
        """构建 litellm 识别的模型字符串

        例如: openai/gpt-4o, anthropic/claude-3-opus, ollama/llama3
        """
        provider = config.provider.lower()
        name = config.name

        # 部分 provider 需要前缀
        if provider == "openai":
            return name  # litellm 默认就是 openai
        if provider in ("anthropic", "ollama", "deepseek", "groq"):
            return f"{provider}/{name}"
        # 自定义 API base 的通用兼容
        return name

    def _setup_env(self, config: ModelConfig) -> None:
        """设置 LLM API 环境变量"""
        if config.api_key_env:
            # 确保环境变量存在
            key = os.environ.get(config.api_key_env)
            if not key:
                logger.warning(
                    "llm.api_key_missing",
                    env_var=config.api_key_env,
                )
        if config.api_base:
            os.environ["OPENAI_API_BASE"] = config.api_base

    async def chat(
        self,
        messages: list[dict],
        model_config: ModelConfig | None = None,
        tools: list[dict] | None = None,
        prefer_default: bool = True,
        **kwargs,
    ) -> LLMResponse:
        """统一 LLM 调用入口

        Args:
            messages: OpenAI 格式的消息列表
            model_config: 模型配置，不传则使用默认配置
            tools: Function Calling 工具定义
            prefer_default: 是否优先尝试全局默认模型
            **kwargs: 传递给 litellm 的额外参数

        Returns:
            LLMResponse 包含回复内容和 Token 用量
        """
        config = self._select_model_config(model_config, prefer_default=prefer_default)

        # 预算检查
        if self.token_tracker.is_budget_exceeded():
            raise BudgetExceededError(
                f"Token budget exceeded: {self.token_tracker.total_tokens}"
            )

        self._setup_env(config)
        model_str = self._resolve_model_string(config)

        call_kwargs: dict = {
            "model": model_str,
            "messages": messages,
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
            **kwargs,
        }
        if tools:
            call_kwargs["tools"] = tools

        try:
            response = await litellm.acompletion(**call_kwargs)

            input_tokens = response.usage.prompt_tokens if response.usage else 0
            output_tokens = response.usage.completion_tokens if response.usage else 0

            self.token_tracker.record(
                model=model_str,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )

            content = response.choices[0].message.content or ""

            logger.info(
                "llm.call_completed",
                model=model_str,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )

            return LLMResponse(
                content=content,
                model=model_str,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=input_tokens + output_tokens,
            )

        except Exception as e:
            logger.error("llm.call_failed", model=model_str, error=str(e))
            # 尝试降级
            if config.fallback_models:
                return await self._fallback(messages, config, e, tools=tools, **kwargs)
            raise LLMUnavailableError(f"LLM call failed: {e}") from e

    async def _fallback(
        self,
        messages: list[dict],
        original_config: ModelConfig,
        error: Exception,
        **kwargs,
    ) -> LLMResponse:
        """模型降级"""
        for fallback_model_name in original_config.fallback_models:
            try:
                logger.warning(
                    "llm.fallback",
                    original_error=str(error),
                    fallback_model=fallback_model_name,
                )
                fallback_config = ModelConfig(
                    provider=original_config.provider,
                    name=fallback_model_name,
                    temperature=original_config.temperature,
                    max_tokens=original_config.max_tokens,
                    api_base=original_config.api_base,
                    api_key_env=original_config.api_key_env,
                )
                return await self.chat(
                    messages,
                    model_config=fallback_config,
                    prefer_default=False,
                    **kwargs,
                )
            except Exception as fallback_err:
                logger.error(
                    "llm.fallback_failed",
                    model=fallback_model_name,
                    error=str(fallback_err),
                )
                continue

        raise LLMUnavailableError("All LLM models unavailable") from error
