# WHY: Single entry point for all LLM calls. Every node and tool that needs the LLM
# goes through call_llm() — this ensures consistent model string construction,
# streaming callback support, Anthropic cache_control, and timeout handling
# in one place. Changing LEX_MODEL_PROVIDER and LEX_MODEL in .env (or via
# `lex config`) switches the model for every caller at once.
#
# CACHING ARCHITECTURE:
# Layer 1 — LiteLLM disk cache (all providers):
#   litellm.Cache caches exact prompt+response pairs on disk. Repeated identical
#   prompts (e.g., re-running tests) are served without API calls.
#
# Layer 2 — Anthropic server-side prompt caching (Anthropic only):
#   When provider="anthropic" + caching enabled, the system prompt is formatted as
#   content blocks with cache_control={"type": "ephemeral"}. Anthropic's servers
#   cache that block — even when the user message changes, system prompt tokens
#   are served from cache at ~10% of normal cost.
#
# CRITICAL RULE: Matter memory NEVER goes in the system prompt.
# Memory always goes in the user turn so the system prompt stays cacheable.

from pathlib import Path
from typing import Callable

import litellm

from lexagent.config import LexConfig
from lexagent.providers import build_model_string


async def call_llm(
    messages: list[dict],
    cfg: LexConfig,
    *,
    tools: list[dict] | None = None,
    stream_cb: Callable[[str], None] | None = None,
    system: str | None = None,
    model_override: str | None = None,
) -> dict:
    """
    Single async entry point for all LLM calls.

    Args:
        messages:       OpenAI-format dicts [{"role": "user"|"assistant"|"system", "content": "..."}]
        cfg:            LexConfig — provides model string, base_url, caching settings
        tools:          Optional list of tool schemas for function-calling
        stream_cb:      If provided, tokens are streamed to this callback as they arrive.
                        The function returns after all tokens are streamed.
        system:         Optional system prompt (prepended as {"role": "system", ...})
        model_override: Override the model string entirely (e.g. for cheap strategy calls)

    Returns:
        {"content": str, "tool_calls": list | None}
    """
    model = model_override or build_model_string(cfg)
    if system:
        messages = [{"role": "system", "content": system}] + messages

    kwargs: dict = {
        "model": model,
        "messages": messages,
        "request_timeout": 60,
        "caching": cfg.enable_prompt_caching,
    }
    if tools:
        kwargs["tools"] = tools
    if cfg.model_base_url and not model_override:
        kwargs["api_base"] = cfg.model_base_url

    if stream_cb:
        kwargs["stream"] = True
        response = await litellm.acompletion(**kwargs)
        full_text = ""
        async for chunk in response:
            token = (chunk.choices[0].delta.content) or ""
            if token:
                stream_cb(token)
                full_text += token
        return {"content": full_text, "tool_calls": None}

    response = await litellm.acompletion(**kwargs)
    msg = response.choices[0].message
    return {
        "content": msg.content or "",
        "tool_calls": msg.tool_calls if hasattr(msg, "tool_calls") else None,
    }


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

    litellm.cache = litellm.Cache(type="disk", disk_cache_dir=str(cache_dir))
