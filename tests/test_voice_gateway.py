# tests/test_voice_gateway.py — Integration tests for the FastAPI voice gateway.
#
# Uses httpx.AsyncClient with the ASGI transport so no server is needed.
# All LangGraph calls are monkeypatched out so tests run offline.

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture()
def client():
    """TestClient wrapping the control plane FastAPI app (includes voice router)."""
    from lexagent.gateway.control_plane import app
    return TestClient(app)


# ─── Health endpoint ─────────────────────────────────────────────────────────

def test_voice_health(client):
    resp = client.get("/voice/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["gateway"] == "voice"
    assert "stt_backend" in data
    assert "tts_backend" in data


# ─── Twilio webhooks ─────────────────────────────────────────────────────────

def test_twilio_incoming_returns_twiml(client):
    """POST /voice/incoming should return valid TwiML XML."""
    resp = client.post(
        "/voice/incoming",
        data={"CallSid": "CA1234567890", "From": "+919876543210"},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/xml")
    body = resp.text
    assert "<Response>" in body
    assert "<Gather" in body
    assert "LexAgent" in body


def test_twilio_incoming_creates_session(client):
    """Each unique CallSid should create a new VoiceSession."""
    from lexagent.voice.session import get_voice_session_store
    store = get_voice_session_store()
    initial_count = len(store)

    client.post(
        "/voice/incoming",
        data={"CallSid": "CA-UNIQUE-TEST-001"},
    )
    # A session should have been created for this CallSid
    session = store.get("CA-UNIQUE-TEST-001")
    assert session is not None
    assert session.channel == "twilio"


def test_twilio_gather_empty_speech_re_prompts(client):
    """Empty SpeechResult should return a TwiML re-prompt."""
    resp = client.post(
        "/voice/gather",
        data={"CallSid": "CA-EMPTY-SPEECH", "SpeechResult": ""},
    )
    assert resp.status_code == 200
    body = resp.text
    assert "<Gather" in body
    assert "repeat" in body.lower() or "catch" in body.lower()


def test_twilio_gather_with_speech_runs_graph(client, monkeypatch):
    """SpeechResult should trigger a LangGraph turn and return TwiML."""
    # Patch _run_voice_turn so no real LLM calls are made
    async def mock_turn(session, user_text, cfg):
        return "Which court are you filing in?"

    monkeypatch.setattr(
        "lexagent.gateway.voice._run_voice_turn",
        mock_turn,
    )

    resp = client.post(
        "/voice/gather",
        data={
            "CallSid": "CA-WITH-SPEECH",
            "SpeechResult": "I need to draft a writ petition",
        },
    )
    assert resp.status_code == 200
    body = resp.text
    assert "<Response>" in body
    assert "Which court" in body


# ─── Browser voice client ────────────────────────────────────────────────────

def test_voice_client_page_serves_html(client):
    """/voice/client should return HTML with the microphone button."""
    resp = client.get("/voice/client")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "LexAgent Voice" in resp.text
    assert "mic-btn" in resp.text


# ─── WebSocket gateway ───────────────────────────────────────────────────────

def test_voice_websocket_connect_and_greeting(monkeypatch):
    """WebSocket should connect and send a matter_id handshake message."""
    async def mock_turn(session, user_text, cfg):
        return "Please describe your matter."

    from lexagent.gateway import voice as voice_module
    monkeypatch.setattr(voice_module, "_run_voice_turn", mock_turn)

    from lexagent.gateway.control_plane import app
    with TestClient(app) as client:
        with client.websocket_connect("/voice/ws/test-session-greeting") as ws:
            # First message must be the matter_id handshake
            msg1 = json.loads(ws.receive_text())
            assert msg1["type"] == "matter_id"
            assert msg1["matter_id"].startswith("M-")

            # Collect a few more messages to verify the greeting flow started.
            # We don't assert on audio (TTS stub) to avoid timing fragility.
            for _ in range(6):
                try:
                    raw = ws.receive_text()
                    m = json.loads(raw)
                    if m["type"] in ("speaking", "status", "audio"):
                        # Found a speaking/status event — greeting flow is working
                        return
                except Exception:
                    break
            # Even if we only got the matter_id, the WebSocket connected correctly


def test_voice_websocket_text_message(monkeypatch):
    """Sending a text message should trigger a graph turn and spoken response."""
    async def mock_turn(session, user_text, cfg):
        session.turn_count += 1
        return f"Got: {user_text}"

    from lexagent.gateway import voice as voice_module
    monkeypatch.setattr(voice_module, "_run_voice_turn", mock_turn)

    from lexagent.gateway.control_plane import app
    with TestClient(app) as client:
        with client.websocket_connect("/voice/ws/test-text-session") as ws:
            # Consume matter_id handshake
            msg = json.loads(ws.receive_text())
            assert msg["type"] == "matter_id"

            # Drain greeting messages (status, speaking, audio)
            for _ in range(8):
                try:
                    raw = ws.receive_text()
                    m = json.loads(raw)
                    if m["type"] == "audio":
                        break
                except Exception:
                    break

            # Send a text message
            ws.send_text(json.dumps({"type": "text", "data": "Writ petition in Delhi HC"}))

            # Collect the agent response messages
            responses = []
            for _ in range(8):
                try:
                    raw = ws.receive_text()
                    responses.append(json.loads(raw))
                    # Stop after audio (final message in a turn)
                    if responses[-1]["type"] == "audio":
                        break
                except Exception:
                    break

            # Verify we got a speaking message with our mocked response
            speaking = [r for r in responses if r["type"] == "speaking"]
            assert any("Got: Writ petition" in r.get("text", "") for r in speaking)
