import pytest

from themis.config import LexConfig
from themis.providers.router import ModelRouter


def test_model_router_builds_provider_prefixed_model():
    cfg = LexConfig(model_provider="anthropic", default_model="claude-sonnet-4-6")
    router = ModelRouter(cfg)

    assert router.model_name("drafting_default") == "anthropic/claude-sonnet-4-6"


def test_model_router_leaves_full_litellm_model_string_unchanged():
    cfg = LexConfig(model_provider="anthropic", default_model="claude-sonnet-4-6")
    router = ModelRouter(cfg)

    assert router.model_name("openai/gpt-4o") == "openai/gpt-4o"


@pytest.mark.asyncio
async def test_generate_uses_litellm(monkeypatch):
    cfg = LexConfig(model_provider="openai", default_model="gpt-4o")
    router = ModelRouter(cfg)

    class _Message:
        content = "ok"

    class _Choice:
        message = _Message()

    class _Response:
        choices = [_Choice()]

    captured = {}

    async def fake_acompletion(**kwargs):
        captured.update(kwargs)
        return _Response()

    class _FakeLiteLLM:
        acompletion = staticmethod(fake_acompletion)

    monkeypatch.setattr("themis.providers.router.litellm", _FakeLiteLLM)

    result = await router.generate(messages=[{"role": "user", "content": "hi"}])

    assert result["content"] == "ok"
    assert captured["model"] == "openai/gpt-4o"
