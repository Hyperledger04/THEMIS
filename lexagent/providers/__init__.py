"""
Provider registry public API.

Usage:
    from lexagent.providers import build_model_string, get_provider_profile

    model_str = build_model_string(cfg)   # → "anthropic/claude-sonnet-4-6"
    profile = get_provider_profile("ollama")
"""

from lexagent.providers.base import ProviderProfile
from lexagent.providers.profiles import get_profile, list_profiles


def build_model_string(cfg) -> str:
    """
    Build the LiteLLM model string from a LexConfig.

    WHY: Centralises model string construction so every call site (nodes,
    call_llm, cli config test) uses the same logic.

    Returns strings like:
        "anthropic/claude-sonnet-4-6"
        "ollama/llama3.2"
        "groq/llama-3.3-70b-versatile"
    """
    profile = get_profile(cfg.model_provider)
    if profile and profile.litellm_prefix:
        return f"{profile.litellm_prefix}{cfg.default_model}"
    # Fallback: trust whatever the user set — allows arbitrary LiteLLM strings
    return f"{cfg.model_provider}/{cfg.default_model}"


def get_provider_profile(name: str) -> ProviderProfile | None:
    return get_profile(name)


def list_providers() -> list[ProviderProfile]:
    return list_profiles()


__all__ = [
    "ProviderProfile",
    "build_model_string",
    "get_provider_profile",
    "list_providers",
]
