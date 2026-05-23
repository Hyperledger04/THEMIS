# lexagent/voice/tts.py — Text-to-Speech backends.
#
# WHY: A unified TTSBackend protocol lets us swap providers
# (ElevenLabs → Google → local Piper) without touching any caller code.
#
# Backends implemented here:
#   - GoogleTTS      : Google Cloud TTS, en-IN Wavenet voices (needs GOOGLE_TTS_API_KEY or ADC)
#   - ElevenLabsTTS  : ElevenLabs Turbo v2 — high-quality Indian English (needs ELEVENLABS_API_KEY)
#   - StubTTS        : Returns empty bytes — used in tests and CI
#
# Usage:
#   tts = get_tts_backend(cfg)
#   audio_bytes = await tts.synthesize("Which court are you filing in?")

from __future__ import annotations

import logging
from typing import Optional, Protocol, runtime_checkable

from lexagent.config import LexConfig

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Protocol — every backend must implement this
# ---------------------------------------------------------------------------

@runtime_checkable
class TTSBackend(Protocol):
    async def synthesize(self, text: str, language: str = "en-IN") -> bytes:
        """Convert text to audio bytes (MP3 or WAV)."""
        ...

    def get_audio_mime_type(self) -> str:
        """Return the MIME type of the audio produced (e.g. 'audio/mpeg')."""
        ...


# ---------------------------------------------------------------------------
# Stub backend — returns silent bytes, for tests
# ---------------------------------------------------------------------------

class StubTTS:
    """Returns empty bytes. No API call. Used in tests and CI."""

    async def synthesize(self, text: str, language: str = "en-IN") -> bytes:
        logger.debug("StubTTS: would speak %d chars", len(text))
        # Return a minimal valid MP3 header so audio players don't crash
        return b"\xff\xfb\x90\x00" + b"\x00" * 100

    def get_audio_mime_type(self) -> str:
        return "audio/mpeg"


# ---------------------------------------------------------------------------
# Google Cloud Text-to-Speech backend
# ---------------------------------------------------------------------------

class GoogleTTS:
    """
    Synthesizes speech using Google Cloud Text-to-Speech.

    WHY Google TTS:
    - `en-IN-Wavenet-A` / `en-IN-Wavenet-D` are high quality Indian English voices
    - Free tier: 1 million chars/month for Wavenet voices
    - Works with Application Default Credentials (ADC) — no key needed in GCP
    - Or pass GOOGLE_TTS_API_KEY for REST-based auth

    Voice choices for Indian English:
      en-IN-Wavenet-A  — female, neutral
      en-IN-Wavenet-B  — male, neutral
      en-IN-Wavenet-C  — male, formal
      en-IN-Wavenet-D  — female, warm  ← best for a legal assistant
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        voice_name: str = "en-IN-Wavenet-D",
        speaking_rate: float = 0.95,   # Slightly slower for legal clarity
        pitch: float = -1.0,           # Slightly lower = more authoritative
    ):
        self._api_key = api_key
        self._voice_name = voice_name
        self._speaking_rate = speaking_rate
        self._pitch = pitch

    async def synthesize(self, text: str, language: str = "en-IN") -> bytes:
        import httpx

        # Clean text for TTS — remove markdown, code fences, bullet points
        clean = _clean_for_speech(text)

        # REST API (simpler than gRPC client library, no extra dep)
        url = "https://texttospeech.googleapis.com/v1/text:synthesize"
        if self._api_key:
            url += f"?key={self._api_key}"

        payload = {
            "input": {"text": clean},
            "voice": {
                "languageCode": language,
                "name": self._voice_name,
                "ssmlGender": "FEMALE",
            },
            "audioConfig": {
                "audioEncoding": "MP3",
                "speakingRate": self._speaking_rate,
                "pitch": self._pitch,
                "effectsProfileId": ["telephony-class-application"],
            },
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                import base64
                audio_content = response.json()["audioContent"]
                return base64.b64decode(audio_content)
        except Exception as e:
            logger.error("GoogleTTS synthesis failed: %s", e)
            raise

    def get_audio_mime_type(self) -> str:
        return "audio/mpeg"


# ---------------------------------------------------------------------------
# ElevenLabs backend
# ---------------------------------------------------------------------------

class ElevenLabsTTS:
    """
    Synthesizes speech using ElevenLabs Turbo v2.

    WHY ElevenLabs:
    - Highest quality Indian English available via "Matilda" or custom voice
    - Low latency Turbo v2 model: ~300ms first chunk
    - Supports voice cloning — firms can record their own lawyers' voice

    Default voice ID: ElevenLabs "Matilda" (warm, professional, Indian-English friendly)
    Get IDs from: https://api.elevenlabs.io/v1/voices
    """

    # WHY: Rachel is the default ElevenLabs voice ID — professionals choose
    # their own in SOUL.md via LEX_ELEVENLABS_VOICE_ID.
    DEFAULT_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"

    def __init__(self, api_key: str, voice_id: Optional[str] = None):
        self._api_key = api_key
        self._voice_id = voice_id or self.DEFAULT_VOICE_ID

    async def synthesize(self, text: str, language: str = "en-IN") -> bytes:
        import httpx

        clean = _clean_for_speech(text)
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{self._voice_id}"
        headers = {
            "xi-api-key": self._api_key,
            "Content-Type": "application/json",
        }
        payload = {
            "text": clean,
            "model_id": "eleven_turbo_v2",
            "voice_settings": {
                "stability": 0.6,
                "similarity_boost": 0.8,
                "style": 0.2,
                "use_speaker_boost": True,
            },
        }

        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                return response.content
        except Exception as e:
            logger.error("ElevenLabsTTS synthesis failed: %s", e)
            raise

    def get_audio_mime_type(self) -> str:
        return "audio/mpeg"


# ---------------------------------------------------------------------------
# Text cleaning helper
# ---------------------------------------------------------------------------

def _clean_for_speech(text: str) -> str:
    """
    Strip markdown formatting and legal notation that sounds unnatural when spoken.

    WHY: The LLM output may include bold (**text**), bullet points, or citation
    strings like "AIR 1978 SC 597". TTS reads these literally which sounds robotic.
    We normalise them to natural spoken equivalents.
    """
    import re

    # Remove markdown bold/italic
    text = re.sub(r"\*{1,3}(.+?)\*{1,3}", r"\1", text)
    # Remove markdown backticks
    text = re.sub(r"`+(.+?)`+", r"\1", text)
    # Remove bullet/list markers
    text = re.sub(r"^\s*[-*•]\s+", "", text, flags=re.MULTILINE)
    # Remove section headers (# Heading)
    text = re.sub(r"^#+\s+", "", text, flags=re.MULTILINE)
    # Expand common Indian legal abbreviations to spoken form
    # WHY: "CPC" sounds like three letters; "Civil Procedure Code" is clearer
    legal_expansions = {
        r"\bCPC\b": "Civil Procedure Code",
        r"\bCrPC\b": "Code of Criminal Procedure",
        r"\bIPC\b": "Indian Penal Code",
        r"\bHC\b": "High Court",
        r"\bSC\b": "Supreme Court",
        r"\bDC\b": "District Court",
        r"\bS\.\s*(\d+)": r"Section \1",
        r"\bArt\.\s*(\d+)": r"Article \1",
    }
    for pattern, replacement in legal_expansions.items():
        text = re.sub(pattern, replacement, text)

    return text.strip()


# ---------------------------------------------------------------------------
# Factory — returns the right backend from config
# ---------------------------------------------------------------------------

def get_tts_backend(cfg: Optional[LexConfig] = None) -> TTSBackend:
    """
    Return the configured TTS backend instance.

    Reads LEX_TTS_BACKEND from .env. Falls back to StubTTS so the
    system is always usable without API keys.
    """
    if cfg is None:
        cfg = LexConfig()

    backend = getattr(cfg, "tts_backend", "stub")

    if backend == "elevenlabs":
        api_key = getattr(cfg, "elevenlabs_api_key", None)
        if not api_key:
            logger.warning("TTS backend=elevenlabs but ELEVENLABS_API_KEY not set. Falling back to StubTTS.")
            return StubTTS()
        voice_id = getattr(cfg, "elevenlabs_voice_id", None)
        return ElevenLabsTTS(api_key=api_key, voice_id=voice_id)

    if backend == "google":
        api_key = getattr(cfg, "google_tts_api_key", None)
        voice_name = getattr(cfg, "google_tts_voice", "en-IN-Wavenet-D")
        return GoogleTTS(api_key=api_key, voice_name=voice_name)

    # Default / stub
    return StubTTS()
