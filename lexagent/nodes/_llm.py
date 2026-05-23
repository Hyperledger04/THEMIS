# WHY: Centralise LLM construction so all nodes use the same config-driven model.
# Changing LEX_MODEL and LEX_MODEL_PROVIDER in .env switches the model for every
# node at once — no code changes needed. This is the BYOK pattern in practice.
#
# CACHING ARCHITECTURE (Phase 3):
# Layer 1 — LiteLLM disk cache (all providers):
#   litellm.Cache caches exact prompt+response pairs on disk. If the exact same
#   messages are sent again (e.g., repeated identical drafts in development/testing),
#   LiteLLM returns the cached response without making an API call. Free for all providers.
#
# Layer 2 — Anthropic server-side prompt caching (Anthropic only, bonus):
#   When provider="anthropic" + caching enabled, the system prompt is formatted as
#   a list of content blocks with cache_control={"type": "ephemeral"}.
#   Anthropic's servers cache that block — even when the user message changes,
#   the system prompt tokens are served from cache at ~10% of normal cost.
#   This is passed via litellm.acompletion() directly (supports native Anthropic format).
#
# CRITICAL RULE: Matter memory NEVER goes in the system prompt.
# If memory went in the system prompt, it would change every turn → cache miss every turn.
# Memory always goes in the user turn (see draft.py: inject_memory_into_user_turn).

from pathlib import Path

import litellm
from langchain_litellm import ChatLiteLLM

from lexagent.config import LexConfig


def get_llm(config: LexConfig) -> ChatLiteLLM:
    # WHY: LiteLLM uses a "provider/model" string format so it knows which
    # SDK to call under the hood. Examples:
    #   "anthropic/claude-sonnet-4-6"     → calls Anthropic SDK
    #   "openai/gpt-4o"                   → calls OpenAI SDK
    #   "google/gemini-pro"               → calls Google SDK
    #   "openrouter/mistral-7b"           → routes via OpenRouter
    #   "ollama/llama3"                   → calls local Ollama server
    model_string = f"{config.model_provider}/{config.default_model}"

    kwargs: dict = {"model": model_string}

    if config.model_base_url:
        # WHY: api_base overrides the default endpoint. Required for local models
        # (Ollama) and custom LiteLLM proxy deployments.
        kwargs["api_base"] = config.model_base_url

    return ChatLiteLLM(**kwargs)


def setup_litellm_cache(config: LexConfig) -> None:
    """
    Enable LiteLLM's disk-based response cache (Layer 1 — all providers).

    WHY disk over in-memory: disk cache survives process restarts, making it
    useful across CLI invocations — not just within a single session.
    During development, repeated identical prompts (e.g., re-running tests)
    are served instantly without API calls.

    Call once at CLI startup before any LLM calls.
    """
    if not config.enable_prompt_caching:
        return

    cache_dir = Path(config.home_dir).expanduser() / "llm_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    # LANGGRAPH / LITELLM: litellm.cache is a module-level singleton.
    # Setting it here affects all litellm.completion() and ChatLiteLLM calls globally.
    litellm.cache = litellm.Cache(type="disk", disk_cache_dir=str(cache_dir))
