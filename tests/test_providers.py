"""Tests for provider-agnostic model layer — themis/providers/."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from themis.providers.base import ProviderProfile
from themis.providers.router import ModelRouter


class TestProviderProfile:
    def test_model_string(self):
        p = ProviderProfile(
            name="anthropic",
            display_name="Anthropic",
            litellm_prefix="anthropic/",
            env_vars=("ANTHROPIC_API_KEY",),
        )
        assert p.model_string("claude-sonnet-4-6") == "anthropic/claude-sonnet-4-6"

    def test_has_key_true(self):
        p = ProviderProfile(
            name="openai", display_name="OpenAI",
            litellm_prefix="openai/", env_vars=("OPENAI_API_KEY",),
        )
        assert p.has_key({"OPENAI_API_KEY": "sk-test"})

    def test_has_key_false_missing(self):
        p = ProviderProfile(
            name="openai", display_name="OpenAI",
            litellm_prefix="openai/", env_vars=("OPENAI_API_KEY",),
        )
        assert not p.has_key({})

    def test_no_env_vars_always_available(self):
        p = ProviderProfile(
            name="local", display_name="Local/Ollama",
            litellm_prefix="ollama/", local=True,
        )
        assert p.has_key({})

    def test_eu_sovereign_flag(self):
        p = ProviderProfile(
            name="mistral", display_name="Mistral",
            litellm_prefix="mistral/", eu_sovereign=True,
        )
        assert p.eu_sovereign

    def test_free_flag(self):
        p = ProviderProfile(
            name="groq", display_name="Groq",
            litellm_prefix="groq/", free=True,
        )
        assert p.free


class TestModelRouter:
    def _router(self, **cfg_overrides):
        from themis.config import LexConfig
        cfg = LexConfig(
            default_model="claude-sonnet-4-6",
            model_provider="anthropic",
            **cfg_overrides,
        )
        return ModelRouter(cfg=cfg)

    def test_model_name_with_explicit_path(self):
        r = self._router()
        assert r.model_name("openai/gpt-4o") == "openai/gpt-4o"

    def test_model_name_default(self):
        r = self._router()
        name = r.model_name()
        assert "claude-sonnet-4-6" in name

    def test_model_name_chat_profile(self):
        r = self._router(chat_model="anthropic/claude-haiku-4-5-20251001")
        name = r.model_name("chat_default")
        assert "haiku" in name

    @pytest.mark.asyncio
    async def test_generate_calls_litellm(self):
        r = self._router()
        fake_message = MagicMock()
        fake_message.content = "Here is the draft."
        fake_choice = MagicMock()
        fake_choice.message = fake_message
        fake_response = MagicMock()
        fake_response.choices = [fake_choice]

        with patch("themis.providers.router._litellm") as mock_llm_fn:
            mock_llm = MagicMock()
            mock_llm.acompletion = AsyncMock(return_value=fake_response)
            mock_llm_fn.return_value = mock_llm

            result = await r.generate(
                messages=[{"role": "user", "content": "Draft a legal notice."}]
            )

        assert result["content"] == "Here is the draft."
        assert "model" in result
        assert "raw" in result

    @pytest.mark.asyncio
    async def test_embed_calls_litellm(self):
        r = self._router()
        fake_response = {"data": [{"embedding": [0.1, 0.2, 0.3]}, {"embedding": [0.4, 0.5, 0.6]}]}

        with patch("themis.providers.router._litellm") as mock_llm_fn:
            mock_llm = MagicMock()
            mock_llm.aembedding = AsyncMock(return_value=fake_response)
            mock_llm_fn.return_value = mock_llm

            embeddings = await r.embed(texts=["fact one", "fact two"])

        assert len(embeddings) == 2
        assert embeddings[0] == [0.1, 0.2, 0.3]
