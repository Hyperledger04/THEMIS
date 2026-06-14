# tests/test_voice_stt.py — Unit tests for the STT backends.
#
# All tests use StubSTT so they run offline without any API key.
# Tests validate the backend protocol and factory function.

import pytest

from themis.voice.stt import StubSTT, WhisperSTT, DeepgramSTT, get_stt_backend, STTBackend
from themis.config import LexConfig


# ─── StubSTT ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_stub_stt_returns_fixed_text():
    stt = StubSTT(fixed_response="Test transcript")
    result = await stt.transcribe(b"fake-audio", language="en-IN")
    assert result == "Test transcript"


@pytest.mark.asyncio
async def test_stub_stt_default_response():
    stt = StubSTT()
    result = await stt.transcribe(b"\x00\x01\x02", language="en-IN")
    assert isinstance(result, str)
    assert len(result) > 0


@pytest.mark.asyncio
async def test_stub_stt_handles_empty_bytes():
    stt = StubSTT(fixed_response="Empty")
    result = await stt.transcribe(b"", language="en-IN")
    assert result == "Empty"


def test_stub_stt_implements_protocol():
    stt = StubSTT()
    # runtime_checkable lets us use isinstance() on Protocol
    assert isinstance(stt, STTBackend)


# ─── Factory ─────────────────────────────────────────────────────────────────

def test_get_stt_backend_defaults_to_stub(monkeypatch):
    """With no API key configured, factory should return StubSTT."""
    cfg = LexConfig()
    # Ensure stt_backend is 'stub' regardless of env
    monkeypatch.setattr(cfg, "stt_backend", "stub", raising=False)
    backend = get_stt_backend(cfg)
    assert isinstance(backend, StubSTT)


def test_get_stt_backend_whisper_without_key_falls_back_to_stub(monkeypatch):
    """Whisper backend with no OPENAI_API_KEY should fall back to StubSTT."""
    cfg = LexConfig()
    monkeypatch.setattr(cfg, "stt_backend", "whisper", raising=False)
    monkeypatch.setattr(cfg, "openai_api_key", None, raising=False)
    backend = get_stt_backend(cfg)
    assert isinstance(backend, StubSTT)


def test_get_stt_backend_deepgram_without_key_falls_back_to_stub(monkeypatch):
    """Deepgram backend with no DEEPGRAM_API_KEY should fall back to StubSTT."""
    cfg = LexConfig()
    monkeypatch.setattr(cfg, "stt_backend", "deepgram", raising=False)
    monkeypatch.setattr(cfg, "deepgram_api_key", None, raising=False)
    backend = get_stt_backend(cfg)
    assert isinstance(backend, StubSTT)


def test_get_stt_backend_returns_stt_protocol(monkeypatch):
    """Factory must always return an STTBackend-protocol-compatible object."""
    cfg = LexConfig()
    monkeypatch.setattr(cfg, "stt_backend", "stub", raising=False)
    backend = get_stt_backend(cfg)
    assert isinstance(backend, STTBackend)


def test_get_stt_backend_none_config():
    """Calling without cfg arg should not raise."""
    # Will read from env/.env; will fall back to stub if keys missing
    backend = get_stt_backend(None)
    assert backend is not None
