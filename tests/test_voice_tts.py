# tests/test_voice_tts.py — Unit tests for the TTS backends.
#
# All tests use StubTTS so they run offline without any API key.
# Also validates the _clean_for_speech() helper.

import pytest

from themis.voice.tts import StubTTS, GoogleTTS, ElevenLabsTTS, get_tts_backend, TTSBackend, _clean_for_speech
from themis.config import LexConfig


# ─── StubTTS ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_stub_tts_returns_bytes():
    tts = StubTTS()
    result = await tts.synthesize("Hello, lawyer.")
    assert isinstance(result, bytes)
    assert len(result) > 0


@pytest.mark.asyncio
async def test_stub_tts_empty_text():
    tts = StubTTS()
    result = await tts.synthesize("")
    assert isinstance(result, bytes)


def test_stub_tts_mime_type():
    tts = StubTTS()
    assert tts.get_audio_mime_type() == "audio/mpeg"


def test_stub_tts_implements_protocol():
    tts = StubTTS()
    assert isinstance(tts, TTSBackend)


# ─── Text cleaner ────────────────────────────────────────────────────────────

def test_clean_for_speech_removes_bold():
    result = _clean_for_speech("**Important** point")
    assert "**" not in result
    assert "Important" in result


def test_clean_for_speech_removes_bullets():
    text = "Points:\n- First item\n- Second item"
    result = _clean_for_speech(text)
    assert "- " not in result
    assert "First item" in result


def test_clean_for_speech_expands_cpc():
    result = _clean_for_speech("Filed under CPC")
    assert "Civil Procedure Code" in result


def test_clean_for_speech_expands_ipc():
    result = _clean_for_speech("Section 302 IPC")
    assert "Indian Penal Code" in result


def test_clean_for_speech_removes_backticks():
    result = _clean_for_speech("Use `Section 437`")
    assert "`" not in result
    assert "Section 437" in result


def test_clean_for_speech_removes_headers():
    result = _clean_for_speech("## Introduction\nHello")
    assert "##" not in result
    assert "Introduction" in result


# ─── Factory ─────────────────────────────────────────────────────────────────

def test_get_tts_backend_defaults_to_stub(monkeypatch):
    cfg = LexConfig()
    monkeypatch.setattr(cfg, "tts_backend", "stub", raising=False)
    backend = get_tts_backend(cfg)
    assert isinstance(backend, StubTTS)


def test_get_tts_backend_elevenlabs_without_key_falls_back(monkeypatch):
    cfg = LexConfig()
    monkeypatch.setattr(cfg, "tts_backend", "elevenlabs", raising=False)
    monkeypatch.setattr(cfg, "elevenlabs_api_key", None, raising=False)
    backend = get_tts_backend(cfg)
    assert isinstance(backend, StubTTS)


def test_get_tts_backend_implements_protocol(monkeypatch):
    cfg = LexConfig()
    monkeypatch.setattr(cfg, "tts_backend", "stub", raising=False)
    backend = get_tts_backend(cfg)
    assert isinstance(backend, TTSBackend)


def test_get_tts_backend_none_config():
    backend = get_tts_backend(None)
    assert backend is not None
