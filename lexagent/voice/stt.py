# lexagent/voice/stt.py — Speech-to-Text backends.
#
# WHY: A unified STTBackend protocol means we can swap providers
# (Deepgram → Whisper → local Vosk) without touching any caller code.
# All backends expose the same `transcribe()` coroutine.
#
# Backends implemented here:
#   - WhisperSTT  : OpenAI Whisper API (batch, needs OPENAI_API_KEY)
#   - DeepgramSTT : Deepgram Nova-2 API (batch REST, needs DEEPGRAM_API_KEY)
#   - StubSTT     : Returns a fixed string — used in tests and CI (no API key needed)
#
# Usage:
#   stt = get_stt_backend(cfg)
#   text = await stt.transcribe(audio_bytes, language="en-IN")

from __future__ import annotations

import logging
from typing import Optional, Protocol, runtime_checkable

from lexagent.config import LexConfig

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Protocol — every backend must implement this
# ---------------------------------------------------------------------------

@runtime_checkable
class STTBackend(Protocol):
    async def transcribe(
        self,
        audio_bytes: bytes,
        language: str = "en-IN",
        mime_type: str = "audio/webm",
    ) -> str:
        """Transcribe raw audio bytes and return the transcript as a string."""
        ...


# ---------------------------------------------------------------------------
# Stub backend — no API key, for tests and development
# ---------------------------------------------------------------------------

class StubSTT:
    """Returns a hard-coded transcript. Useful for unit tests and CI."""

    def __init__(self, fixed_response: str = "I need to draft a writ petition in Delhi High Court."):
        self._fixed = fixed_response

    async def transcribe(
        self,
        audio_bytes: bytes,
        language: str = "en-IN",
        mime_type: str = "audio/webm",
    ) -> str:
        logger.debug("StubSTT returning fixed transcript (%d bytes received)", len(audio_bytes))
        return self._fixed


# ---------------------------------------------------------------------------
# Whisper backend — OpenAI Whisper API
# ---------------------------------------------------------------------------

class WhisperSTT:
    """
    Transcribes audio using the OpenAI Whisper API.

    WHY Whisper: Works out-of-the-box with an existing OPENAI_API_KEY,
    handles Indian English well, and has no streaming requirement for
    our use case (we send one utterance at a time).
    """

    def __init__(self, api_key: str, model: str = "whisper-1"):
        # WHY: Lazy import so `openai` is optional — only needed if
        # LEX_STT_BACKEND=whisper is set.
        try:
            import openai  # noqa: F401
        except ImportError as e:
            raise ImportError(
                "openai package is required for WhisperSTT. "
                "Install it with: uv add openai"
            ) from e
        self._api_key = api_key
        self._model = model

    async def transcribe(
        self,
        audio_bytes: bytes,
        language: str = "en-IN",
        mime_type: str = "audio/webm",
    ) -> str:
        import io
        import openai

        client = openai.AsyncOpenAI(api_key=self._api_key)

        # Whisper accepts a file-like object; we wrap the bytes.
        # WHY: We normalise to "en" because Whisper uses ISO 639-1,
        # not BCP-47 (so "en-IN" → "en").
        iso_lang = language.split("-")[0]

        # Determine file extension from mime type for Whisper
        ext_map = {
            "audio/webm": "webm",
            "audio/wav": "wav",
            "audio/mp3": "mp3",
            "audio/mpeg": "mp3",
            "audio/ogg": "ogg",
            "audio/flac": "flac",
            "audio/m4a": "m4a",
        }
        ext = ext_map.get(mime_type, "webm")
        audio_file = io.BytesIO(audio_bytes)
        audio_file.name = f"audio.{ext}"

        try:
            response = await client.audio.transcriptions.create(
                model=self._model,
                file=audio_file,
                language=iso_lang,
                response_format="text",
            )
            return str(response).strip()
        except Exception as e:
            logger.error("WhisperSTT transcription failed: %s", e)
            raise


# ---------------------------------------------------------------------------
# Deepgram backend — Nova-2 REST API
# ---------------------------------------------------------------------------

class DeepgramSTT:
    """
    Transcribes audio using the Deepgram Nova-2 REST API.

    WHY Deepgram: Best-in-class Indian English accuracy, supports custom
    keyword boosting (useful for court names, section numbers), and has
    a generous free tier. Nova-2 has ~95% WER on Indian English legal speech.
    """

    def __init__(self, api_key: str, model: str = "nova-2"):
        self._api_key = api_key
        self._model = model
        # Legal-domain keywords to boost accuracy.
        # WHY: Court names and section numbers are out-of-vocabulary for
        # general ASR models — boosting them by 1.5x reduces misrecognitions.
        self._keywords = [
            "writ petition", "habeas corpus", "injunction", "affidavit",
            "plaintiff", "defendant", "petitioner", "respondent",
            "High Court", "Supreme Court", "District Court",
            "Section 437", "Section 438", "Order XXXIX",
            "Indian Penal Code", "Code of Criminal Procedure",
            "Civil Procedure Code", "Specific Relief Act",
        ]

    async def transcribe(
        self,
        audio_bytes: bytes,
        language: str = "en-IN",
        mime_type: str = "audio/webm",
    ) -> str:
        import httpx

        # Deepgram REST endpoint for pre-recorded audio
        url = "https://api.deepgram.com/v1/listen"
        params = {
            "model": self._model,
            "language": language,
            "smart_format": "true",
            "punctuate": "true",
            # Keyword boosting (comma-separated URI-encoded list)
            "keywords": ":1.5|".join(self._keywords[:10]) + ":1.5",
        }
        headers = {
            "Authorization": f"Token {self._api_key}",
            "Content-Type": mime_type,
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    url,
                    content=audio_bytes,
                    headers=headers,
                    params=params,
                )
                response.raise_for_status()
                data = response.json()
                transcript = (
                    data.get("results", {})
                    .get("channels", [{}])[0]
                    .get("alternatives", [{}])[0]
                    .get("transcript", "")
                )
                return transcript.strip()
        except Exception as e:
            logger.error("DeepgramSTT transcription failed: %s", e)
            raise


# ---------------------------------------------------------------------------
# Factory — returns the right backend from config
# ---------------------------------------------------------------------------

def get_stt_backend(cfg: Optional[LexConfig] = None) -> STTBackend:
    """
    Return the configured STT backend instance.

    BYOK pattern: reads LEX_STT_BACKEND from .env, falls back to StubSTT
    so the system is always usable offline / in tests.
    """
    if cfg is None:
        cfg = LexConfig()

    backend = getattr(cfg, "stt_backend", "stub")

    if backend == "whisper":
        api_key = getattr(cfg, "openai_api_key", None)
        if not api_key:
            logger.warning("STT backend=whisper but OPENAI_API_KEY not set. Falling back to StubSTT.")
            return StubSTT()
        return WhisperSTT(api_key=api_key)

    if backend == "deepgram":
        api_key = getattr(cfg, "deepgram_api_key", None)
        if not api_key:
            logger.warning("STT backend=deepgram but DEEPGRAM_API_KEY not set. Falling back to StubSTT.")
            return StubSTT()
        return DeepgramSTT(api_key=api_key)

    # Default / stub
    return StubSTT()
