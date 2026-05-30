"""Provider-agnostic model router.

The runtime calls this module instead of calling a provider SDK directly. LiteLLM
is the transport for the MVP; provider-specific schema normalization can grow
behind this interface without changing runtime agents.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from pydantic import BaseModel

from lexagent.config import LexConfig
from lexagent.providers.profiles import get_profile

litellm = None


def _litellm():
    global litellm
    if litellm is None:
        try:
            import litellm as _llm  # type: ignore[import]
        except ImportError as exc:
            raise ImportError("litellm is required for ModelRouter generation") from exc
        litellm = _llm
    return litellm


class ModelRouter:
    """Provider-neutral LLM and embedding interface."""

    def __init__(self, cfg: Optional[LexConfig] = None) -> None:
        self._cfg = cfg or LexConfig()

    def model_name(self, model_profile: Optional[str] = None) -> str:
        """
        Resolve a model profile to a LiteLLM model string.

        `model_profile` can be either a full LiteLLM model string or a symbolic
        profile: drafting_default, chat_default, research_default.
        """
        if model_profile and "/" in model_profile:
            return model_profile

        raw_model = self._cfg.default_model
        if model_profile == "chat_default" and self._cfg.chat_model:
            raw_model = self._cfg.chat_model

        profile = get_profile(self._cfg.model_provider)
        if profile and not raw_model.startswith(profile.litellm_prefix):
            return profile.model_string(raw_model)
        return raw_model

    async def generate(
        self,
        *,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        model_profile: Optional[str] = None,
        response_schema: Optional[type[BaseModel]] = None,
        temperature: float = 0.2,
    ) -> dict:
        """
        Generate one assistant response.

        When response_schema is provided, the schema is sent as JSON guidance.
        This avoids binding the runtime to one provider's structured-output API.
        """
        effective_messages = list(messages)
        if response_schema is not None:
            schema = response_schema.model_json_schema()
            effective_messages.append({
                "role": "system",
                "content": (
                    "Return JSON that validates against this schema. "
                    f"Schema: {json.dumps(schema, ensure_ascii=False)}"
                ),
            })

        response = await _litellm().acompletion(
            model=self.model_name(model_profile),
            messages=effective_messages,
            tools=tools or None,
            temperature=temperature,
            api_base=self._cfg.model_base_url,
        )
        message = response.choices[0].message
        content = message.content or ""
        parsed: Any = None
        if response_schema is not None and content:
            parsed = response_schema.model_validate_json(content)
        return {
            "content": content,
            "parsed": parsed,
            "raw": response,
            "model": self.model_name(model_profile),
        }

    async def stream(
        self,
        *,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        model_profile: Optional[str] = None,
    ):
        """Stream provider output using the same neutral routing path."""
        return await _litellm().acompletion(
            model=self.model_name(model_profile),
            messages=messages,
            tools=tools or None,
            stream=True,
            api_base=self._cfg.model_base_url,
        )

    async def embed(
        self,
        *,
        texts: list[str],
        embedding_profile: Optional[str] = None,
    ) -> list[list[float]]:
        """
        Provider-neutral embeddings.

        MVP default remains local sentence-transformers elsewhere; this method
        supports provider embeddings for runtime agents that need them.
        """
        model = embedding_profile or self._cfg.embedding_model
        response = await _litellm().aembedding(model=model, input=texts)
        return [item["embedding"] for item in response["data"]]
