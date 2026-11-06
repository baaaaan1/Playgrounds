from __future__ import annotations

from .base import ProviderInfo
from .openai_compat import OpenAICompatProvider

PROVIDERS: tuple[ProviderInfo, ...] = (
    ProviderInfo(
        id="openai",
        label="OpenAI",
        base_url="https://api.openai.com/v1",
        default_model="gpt-4o-mini",
        models=("gpt-4o-mini", "gpt-4o", "gpt-4.1-mini", "o4-mini"),
    ),
    ProviderInfo(
        id="openrouter",
        label="OpenRouter",
        base_url="https://openrouter.ai/api/v1",
        default_model="openai/gpt-4o-mini",
        models=(
            "openai/gpt-4o-mini",
            "anthropic/claude-3.5-sonnet",
            "google/gemini-2.0-flash-001",
            "meta-llama/llama-3.3-70b-instruct",
        ),
    ),
    ProviderInfo(
        id="groq",
        label="Groq",
        base_url="https://api.groq.com/openai/v1",
        default_model="llama-3.3-70b-versatile",
        models=("llama-3.3-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768"),
    ),
    ProviderInfo(
        id="ollama",
        label="Ollama (local)",
        base_url="http://localhost:11434/v1",
        default_model="llama3.2",
        models=("llama3.2", "qwen2.5", "mistral", "phi4"),
        requires_key=False,
        hint="Run ollama serve first",
    ),
    ProviderInfo(
        id="custom",
        label="Custom (OpenAI-compatible)",
        base_url="",
        default_model="",
        models=(),
        requires_key=False,
        hint="API key is optional; enter a base URL, e.g. https://host/v1",
    ),
)


def provider_infos() -> tuple[ProviderInfo, ...]:
    return PROVIDERS


def get_provider(provider_id: str) -> OpenAICompatProvider:
    for info in PROVIDERS:
        if info.id == provider_id:
            return OpenAICompatProvider(info)
    return OpenAICompatProvider(PROVIDERS[0])


def provider_info(provider_id: str) -> ProviderInfo:
    return get_provider(provider_id).info
