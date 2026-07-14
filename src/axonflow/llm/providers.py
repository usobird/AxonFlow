"""Provider metadata and LiteLLM model-name resolution."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderDefinition:
    id: str
    label: str
    litellm_prefix: str
    default_key_env: str | None
    supports_api_base: bool = False


_PROVIDERS = (
    ProviderDefinition("openai", "OpenAI", "openai", "OPENAI_API_KEY", True),
    ProviderDefinition("dashscope", "Qwen / DashScope", "dashscope", "DASHSCOPE_API_KEY"),
    ProviderDefinition("minimax", "MiniMax", "minimax", "MINIMAX_API_KEY"),
    ProviderDefinition("deepseek", "DeepSeek", "deepseek", "DEEPSEEK_API_KEY"),
    ProviderDefinition("anthropic", "Anthropic", "anthropic", "ANTHROPIC_API_KEY"),
    ProviderDefinition("gemini", "Google Gemini", "gemini", "GEMINI_API_KEY"),
    ProviderDefinition("groq", "Groq", "groq", "GROQ_API_KEY"),
    ProviderDefinition("ollama", "Ollama", "ollama", None, True),
    ProviderDefinition("openai_compatible", "OpenAI Compatible", "openai", None, True),
)

_ALIASES = {
    "qwen": "dashscope",
    "openai-compatible": "openai_compatible",
    "custom": "openai_compatible",
}
_BY_ID = {provider.id: provider for provider in _PROVIDERS}


def normalize_provider(provider: str) -> str:
    return _ALIASES.get(provider.lower().strip(), provider.lower().strip())


def get_provider(provider: str) -> ProviderDefinition:
    normalized = normalize_provider(provider)
    return _BY_ID.get(
        normalized,
        ProviderDefinition(normalized, provider, normalized, None, True),
    )


def provider_catalog() -> list[dict[str, str | None | bool]]:
    return [
        {
            "id": provider.id,
            "label": provider.label,
            "default_key_env": provider.default_key_env,
            "supports_api_base": provider.supports_api_base,
        }
        for provider in _PROVIDERS
    ]


def resolve_model_name(provider: str, name: str, api_base: str | None = None) -> str:
    definition = get_provider(provider)
    normalized = normalize_provider(provider)
    if normalized == "openai" and not api_base:
        return name
    return f"{definition.litellm_prefix}/{name}"
