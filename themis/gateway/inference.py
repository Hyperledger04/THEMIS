"""
Inference gateway — anonymization, routing, and audit logging for LLM calls.

This module is the single choke-point between Themis node logic and cloud
LLM providers. When cfg.anonymization_enabled=True it:
  1. Anonymizes client PII in user/assistant messages via LegalAnonymizer.
  2. Calls the underlying LLM (through the existing call_llm path — note:
     the gateway is called FROM call_llm, so it calls litellm directly here
     to avoid recursion).
  3. Restores pseudonyms in the response.
  4. Writes a routing log entry for cost tracking and audit.

When disabled (default), call_llm() never reaches this module.

WHY a separate module rather than inlining in _llm.py:
  - Keeps _llm.py as a thin, fast-path caller.
  - Anonymizer has heavy lazy-loaded deps (Presidio + spaCy) that must not
    be imported at module load time.
  - InferenceGateway can be tested in isolation with a mock LLM.

Circular import rule: this module imports ONLY from themis.config,
themis.security.audit, and themis.gateway.anonymizer. Never from
themis.nodes, themis.graph, or any other LangGraph layer.
"""
from __future__ import annotations

from typing import Callable, Optional

import litellm

from themis.config import LexConfig
from themis.providers import build_model_string
from themis.security.audit import AuditAction, log_action


# Module-level singleton — created once per process.
_gateway_instance: Optional["InferenceGateway"] = None


def get_gateway(cfg: LexConfig) -> "InferenceGateway":
    """Return (or create) the module-level InferenceGateway singleton."""
    global _gateway_instance
    if _gateway_instance is None:
        _gateway_instance = InferenceGateway()
    return _gateway_instance


class InferenceGateway:
    """
    Wraps litellm.acompletion with optional PII anonymization and routing log.

    Lazy-loads LegalAnonymizer only when anonymization is actually needed,
    keeping process startup fast for the common (anonymization_disabled) case.
    """

    def __init__(self) -> None:
        self._anonymizer: Optional[object] = None

    def _get_anonymizer(self):
        if self._anonymizer is None:
            from themis.gateway.anonymizer import LegalAnonymizer
            self._anonymizer = LegalAnonymizer()
        return self._anonymizer

    def _should_anonymize(
        self,
        cfg: LexConfig,
        matter_id: Optional[str],
        is_document_context: bool,
    ) -> bool:
        """True when anonymization should be applied to this call."""
        if not cfg.anonymization_enabled:
            return False
        if is_document_context:
            return False
        if matter_id and matter_id in cfg.anonymization_privileged_matters:
            return False
        return True

    async def call(
        self,
        messages: list[dict],
        cfg: LexConfig,
        *,
        matter_id: Optional[str] = None,
        is_document_context: bool = False,
        tools: list[dict] | None = None,
        stream_cb: Callable[[str], None] | None = None,
        system: str | None = None,
        model_override: str | None = None,
    ) -> dict:
        """
        Anonymize → call LLM → restore → log. Returns {"content": str, "tool_calls": ...}.
        """
        anonymized = self._should_anonymize(cfg, matter_id, is_document_context)
        pmap: dict = {}

        # Apply anonymization to user/assistant messages
        working_messages = messages
        if system:
            working_messages = [{"role": "system", "content": system}] + working_messages

        if anonymized:
            anon = self._get_anonymizer()
            working_messages, pmap = anon.anonymize(working_messages)  # type: ignore[union-attr]
            log_action(
                AuditAction.PII_ANONYMIZED,
                detail={"matter_id": matter_id, "pseudonyms": len(pmap)},
            )

        model = model_override or build_model_string(cfg)
        kwargs: dict = {
            "model": model,
            "messages": working_messages,
            "request_timeout": 60,
            "caching": cfg.enable_prompt_caching,
        }
        if tools:
            kwargs["tools"] = tools
        if cfg.model_base_url and not model_override:
            kwargs["api_base"] = cfg.model_base_url

        # Execute LLM call (streaming or non-streaming)
        if stream_cb:
            kwargs["stream"] = True
            response = await litellm.acompletion(**kwargs)
            full_text = ""
            async for chunk in response:
                token = (chunk.choices[0].delta.content) or ""
                if token:
                    stream_cb(token)
                    full_text += token
            content = full_text
            tool_calls = None
            input_tokens = 0
            output_tokens = len(full_text.split())  # approximate
        else:
            response = await litellm.acompletion(**kwargs)
            msg = response.choices[0].message
            content = msg.content or ""
            tool_calls = msg.tool_calls if hasattr(msg, "tool_calls") else None
            usage = getattr(response, "usage", None)
            input_tokens = getattr(usage, "prompt_tokens", 0) or 0
            output_tokens = getattr(usage, "completion_tokens", 0) or 0

        # Restore pseudonyms in the response content
        if anonymized and pmap:
            anon = self._get_anonymizer()
            content = anon.restore(content, pmap)  # type: ignore[union-attr]
            log_action(
                AuditAction.PII_RESTORED,
                detail={"matter_id": matter_id, "pseudonyms_restored": len(pmap)},
            )

        # Write routing log (fire-and-forget — never blocks the response)
        self._write_routing_log(
            matter_id=matter_id,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            anonymized=anonymized,
            cfg=cfg,
        )

        return {"content": content, "tool_calls": tool_calls}

    def _write_routing_log(
        self,
        *,
        matter_id: Optional[str],
        model: str,
        input_tokens: int,
        output_tokens: int,
        anonymized: bool,
        cfg: LexConfig,
    ) -> None:
        """Append an entry to the inference routing log. Never raises."""
        try:
            # Derive provider name from model string prefix (e.g. "anthropic/...")
            provider = model.split("/")[0] if "/" in model else "unknown"
            # Simple cost estimate using well-known per-token pricing
            cost_usd = _estimate_cost(provider, input_tokens, output_tokens)

            log_action(
                AuditAction.INFERENCE_ROUTED,
                detail={
                    "matter_id": matter_id,
                    "provider": provider,
                    "model": model,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "cost_usd": cost_usd,
                    "anonymized": anonymized,
                },
            )
        except Exception:
            pass  # routing log must never crash the inference call


# ---------------------------------------------------------------------------
# Cost estimation helpers
# ---------------------------------------------------------------------------

# Per-million-token prices (input, output) in USD — approximate 2025 values.
_COST_TABLE: dict[str, tuple[float, float]] = {
    "anthropic": (3.0, 15.0),    # claude-sonnet-4-x
    "openai":    (2.5, 10.0),    # gpt-4o
    "gemini":    (1.25, 5.0),    # gemini-1.5-pro
    "groq":      (0.05, 0.08),   # llama via groq
    "deepseek":  (0.14, 0.28),
    "mistral":   (2.0, 6.0),
    "ollama":    (0.0, 0.0),     # local
    "lmstudio":  (0.0, 0.0),     # local
}


def _estimate_cost(provider: str, input_tokens: int, output_tokens: int) -> float:
    """Return an approximate USD cost for the given token counts."""
    rates = _COST_TABLE.get(provider, (3.0, 15.0))
    return (input_tokens * rates[0] + output_tokens * rates[1]) / 1_000_000
