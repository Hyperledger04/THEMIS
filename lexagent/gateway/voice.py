# lexagent/gateway/voice.py — Voice AI Gateway for LexAgent.
#
# Provides two sub-gateways under the FastAPI app:
#
#   1. WebSocket Gateway  (/voice/ws/{session_id})
#      Browser opens a WebSocket, sends audio chunks (base64 encoded),
#      receives JSON with spoken responses and audio data.
#      No external account needed — works with StubSTT/StubTTS out of the box.
#
#   2. Twilio Phone Gateway  (/voice/incoming, /voice/gather)
#      Twilio calls /voice/incoming when a call arrives.
#      Twilio sends speech input to /voice/gather.
#      The gateway generates TwiML responses with <Say> or <Play> audio.
#
# Architecture:
#   audio bytes  →  STT  →  LangGraph step  →  TTS  →  audio bytes
#   (same LangGraph pipeline as Telegram; only the transport layer differs)
#
# WHY FastAPI router: mounted at /voice on the existing control_plane app,
# so we reuse auth, CORS, and startup lifecycle without a second server.

from __future__ import annotations

import asyncio
import base64
import json
import logging
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Form, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, PlainTextResponse
from lexagent.config import LexConfig
from lexagent.graph import get_graph
from lexagent.state import LexState
from lexagent.voice.session import VoiceSession, get_voice_session_store
from lexagent.voice.stt import get_stt_backend
from lexagent.voice.tts import get_tts_backend

logger = logging.getLogger(__name__)
router = APIRouter(tags=["voice"])


# ---------------------------------------------------------------------------
# Helper: load voice-optimised prompt text
# ---------------------------------------------------------------------------

def _load_prompt(name: str) -> str:
    """Load a voice prompt markdown file from the prompts/ directory."""
    path = Path(__file__).parent.parent / "voice" / "prompts" / name
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


_VOICE_INTAKE_PROMPT = _load_prompt("voice_intake_system.md")
_VOICE_DRAFT_SUMMARY_PROMPT = _load_prompt("voice_draft_summary.md")


# ---------------------------------------------------------------------------
# Core: run one LangGraph turn and return the agent's text response
# ---------------------------------------------------------------------------

async def _run_voice_turn(
    session: VoiceSession,
    user_text: str,
    cfg: LexConfig,
) -> str:
    """
    Execute one turn of the LangGraph pipeline for a voice session.

    Returns the agent's text response to speak back to the lawyer.
    This is the bridge between audio and the LangGraph state machine.

    WHY one-turn-at-a-time: Voice is sequential — the lawyer speaks,
    we process, we speak back. We pause the graph after intake to ask
    the next question, resuming on each new utterance.
    """
    graph = get_graph(cfg)
    langgraph_cfg = {
        "configurable": {
            "thread_id": session.matter_id,
            "user_id": session.session_id,
            "firm_id": cfg.default_firm_id,
        }
    }

    # If session already has pending questions, the next utterance is the answer
    if session.awaiting_free_text_for:
        field_name = session.awaiting_free_text_for
        session.awaiting_free_text_for = None
        # Inject the answer into state and continue from where we paused
        state: LexState = {  # type: ignore[assignment]
            "user_input": user_text,
            "matter_id": session.matter_id,
            "messages": [{"role": "user", "content": f"{field_name}: {user_text}"}],
            "intake_complete": False,
            "voice_session_id": session.session_id,
            "voice_channel": session.channel,
        }
    elif session.graph_state and session.graph_state.get("intake_complete"):
        # Intake is done — we're resuming a drafted matter
        state = {  # type: ignore[assignment]
            "user_input": user_text,
            "matter_id": session.matter_id,
            "messages": [{"role": "user", "content": user_text}],
            "voice_session_id": session.session_id,
            "voice_channel": session.channel,
        }
    else:
        # Fresh turn or continuing intake
        state = {  # type: ignore[assignment]
            "user_input": user_text,
            "matter_id": session.matter_id,
            "intake_complete": False,
            "citations_verified": False,
            "messages": [{"role": "user", "content": user_text}],
            "voice_session_id": session.session_id,
            "voice_channel": session.channel,
            "firm_id": cfg.default_firm_id,
            "user_id": session.session_id,
        }

    agent_response_text = ""
    intake_just_completed = False

    try:
        async for event in graph.astream(state, config=langgraph_cfg):
            for node_name, node_state in event.items():
                if not isinstance(node_state, dict):
                    continue

                session.update_from_node_state(node_state)

                # After intake node: check for questions or completion
                if node_name == "intake":
                    pending_qs = node_state.get("pending_questions")
                    if node_state.get("intake_complete"):
                        intake_just_completed = True
                        agent_response_text = (
                            "Perfect. I have everything I need. "
                            "Researching case law now — this will take about 30 seconds. "
                            "Please stay on the line."
                        )
                    elif pending_qs:
                        session.pending_questions = list(pending_qs)
                        q_text = session.next_question_text()
                        if q_text:
                            agent_response_text = q_text
                        break  # pause graph — wait for user's spoken answer

                # After review node: draft is complete
                if node_name == "review" and node_state.get("draft_output"):
                    summary = await _generate_voice_summary(
                        node_state.get("draft_output", ""),
                        session.graph_state or {},
                        cfg,
                    )
                    agent_response_text = summary
                    session.completed = True

                # Contract review
                if node_name == "contract_review" and node_state.get("contract_review_output"):
                    agent_response_text = (
                        "I've completed the contract risk analysis. "
                        "I found several risk areas which I'm summarising in the document. "
                        "Your report will be sent to your Telegram shortly."
                    )
                    session.completed = True

                # Surface errors
                if node_state.get("error"):
                    agent_response_text = (
                        f"I encountered an issue: {node_state['error'][:80]}. "
                        "Please try again or contact support."
                    )

        session.turn_count += 1

        if not agent_response_text:
            # Fallback: nudge the lawyer
            agent_response_text = "Could you please provide more details about your matter?"

    except Exception as e:
        logger.error("Voice turn failed for session %s: %s", session.session_id, e)
        agent_response_text = (
            "I'm sorry, something went wrong processing your request. "
            "Please try again."
        )

    return agent_response_text


async def _generate_voice_summary(
    draft_text: str,
    state: dict,
    cfg: LexConfig,
) -> str:
    """
    Use the LLM to produce a short spoken summary of the completed draft.
    Falls back to a canned summary if the LLM call fails.
    """
    try:
        from lexagent.nodes._llm import call_llm

        matter_type = state.get("matter_type", "document")
        snippet = draft_text[:800]

        result = await call_llm(
            [
                {"role": "system", "content": _VOICE_DRAFT_SUMMARY_PROMPT},
                {"role": "user", "content": f"Summarise this draft for voice delivery:\n{snippet}"},
            ],
            cfg,
        )
        return result["content"].strip()
    except Exception as e:
        logger.warning("Voice summary LLM call failed: %s", e)
        matter_type = state.get("matter_type", "document")
        return (
            f"I've drafted your {matter_type}. "
            "Your document is ready. I'm sending the Word file to your Telegram now."
        )


# ---------------------------------------------------------------------------
# WebSocket Gateway
# ---------------------------------------------------------------------------

@router.websocket("/ws/{session_id}")
async def voice_websocket(websocket: WebSocket, session_id: str) -> None:
    """
    WebSocket endpoint for browser-based voice.

    Protocol (JSON messages):
      Client → Server:
        {"type": "audio", "data": "<base64-encoded audio>", "mime": "audio/webm"}
        {"type": "text", "data": "raw text transcript"}  (bypass STT)
        {"type": "ping"}

      Server → Client:
        {"type": "transcript", "text": "..."}     — what STT heard
        {"type": "speaking", "text": "..."}        — what agent is saying
        {"type": "audio", "data": "<base64 MP3>", "mime": "audio/mpeg"}
        {"type": "status", "status": "thinking|speaking|done"}
        {"type": "matter_id", "matter_id": "M-XXXXXX"}
        {"type": "error", "error": "..."}
        {"type": "complete"}                       — draft is finished

    WHY base64 for audio: JSON WebSocket frames can't carry binary.
    The browser decodes base64 and feeds it to AudioContext for playback.
    """
    await websocket.accept()
    cfg = LexConfig()
    store = get_voice_session_store()
    session = store.get_or_create(session_id, channel="websocket")
    stt = get_stt_backend(cfg)
    tts = get_tts_backend(cfg)

    # Send matter ID so the browser can display it
    await websocket.send_json({"type": "matter_id", "matter_id": session.matter_id})

    # Send greeting
    greeting = (
        "Welcome to LexAgent. I'm ready to help you draft your legal document. "
        "Please describe your matter."
    )
    await _send_voice_response(websocket, greeting, tts, cfg)

    try:
        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)
            msg_type = msg.get("type", "")

            if msg_type == "ping":
                await websocket.send_json({"type": "pong"})
                continue

            # --- Receive audio or text ---
            user_text = ""

            if msg_type == "audio":
                audio_b64 = msg.get("data", "")
                mime = msg.get("mime", "audio/webm")
                if not audio_b64:
                    continue
                audio_bytes = base64.b64decode(audio_b64)

                await websocket.send_json({"type": "status", "status": "transcribing"})
                try:
                    user_text = await stt.transcribe(audio_bytes, language=cfg.stt_language, mime_type=mime)
                except Exception as e:
                    await websocket.send_json({"type": "error", "error": f"Transcription failed: {e}"})
                    continue

                # Echo transcript back so browser can display it
                await websocket.send_json({"type": "transcript", "text": user_text})

            elif msg_type == "text":
                # Direct text input (bypass STT) — useful for testing / hybrid mode
                user_text = msg.get("data", "").strip()

            if not user_text:
                continue

            # --- Run one LangGraph turn ---
            await websocket.send_json({"type": "status", "status": "thinking"})
            agent_text = await _run_voice_turn(session, user_text, cfg)

            # --- Speak the response ---
            await _send_voice_response(websocket, agent_text, tts, cfg)

            # --- Check if done ---
            if session.completed:
                await websocket.send_json({"type": "complete"})
                break

    except WebSocketDisconnect:
        logger.info("Voice WebSocket disconnected: %s", session_id)
        store.delete(session_id)
    except Exception as e:
        logger.error("Voice WebSocket error for session %s: %s", session_id, e)
        try:
            await websocket.send_json({"type": "error", "error": str(e)})
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


async def _send_voice_response(
    websocket: WebSocket,
    text: str,
    tts,
    cfg: LexConfig,
) -> None:
    """
    Send a spoken response to the browser:
    1. Send the text so the browser can display it
    2. Synthesize TTS audio and send as base64
    """
    await websocket.send_json({"type": "speaking", "text": text})
    await websocket.send_json({"type": "status", "status": "speaking"})

    try:
        audio_bytes = await tts.synthesize(text, language=cfg.stt_language)
        audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
        mime = tts.get_audio_mime_type()
        await websocket.send_json({"type": "audio", "data": audio_b64, "mime": mime})
    except Exception as e:
        logger.warning("TTS synthesis failed, sending text only: %s", e)
        # Browser will display text even if audio fails


# ---------------------------------------------------------------------------
# Twilio Phone Gateway
# ---------------------------------------------------------------------------

@router.post("/incoming")
async def twilio_incoming(request: Request) -> Response:
    """
    Twilio webhook: called when a call arrives on the Twilio number.

    Returns TwiML that greets the caller and starts speech gathering.
    Twilio will transcribe the lawyer's speech and POST it to /voice/gather.

    WHY Twilio STT (not our STT backend): For phone calls, Twilio's built-in
    speech recognition is simpler — it handles telephony audio codec conversion
    automatically. We use our STT backends for WebSocket (browser microphone).
    """
    form = await request.form()
    call_sid = str(form.get("CallSid", uuid.uuid4().hex))
    store = get_voice_session_store()
    session = store.get_or_create(call_sid, channel="twilio")

    greeting = (
        "Welcome to LexAgent, your AI legal assistant. "
        "Please describe your matter after the beep, "
        "and I will draft a court-ready document for you."
    )

    twiml = _make_gather_twiml(
        say_text=greeting,
        action_url="/voice/gather",
        call_sid=call_sid,
    )
    return Response(content=twiml, media_type="application/xml")


@router.post("/gather")
async def twilio_gather(request: Request) -> Response:
    """
    Twilio webhook: called after Twilio transcribes the lawyer's speech.

    Receives:
      SpeechResult — Twilio's transcription of what the lawyer said
      CallSid      — unique call identifier (maps to VoiceSession)

    Returns TwiML with the agent's spoken response and another <Gather>
    to listen for the next utterance.
    """
    form = await request.form()
    call_sid = str(form.get("CallSid", ""))
    speech_result = str(form.get("SpeechResult", "")).strip()

    store = get_voice_session_store()
    session = store.get(call_sid)
    if session is None:
        session = store.get_or_create(call_sid, channel="twilio")

    cfg = LexConfig()

    if not speech_result:
        # No speech detected — prompt again
        twiml = _make_gather_twiml(
            say_text="I didn't catch that. Could you please repeat?",
            action_url="/voice/gather",
            call_sid=call_sid,
        )
        return Response(content=twiml, media_type="application/xml")

    # Run one LangGraph turn
    try:
        agent_text = await _run_voice_turn(session, speech_result, cfg)
    except Exception as e:
        logger.error("Twilio gather error for call %s: %s", call_sid, e)
        agent_text = "I'm sorry, something went wrong. Please call back and try again."

    # If draft is complete — hang up after speaking the summary
    if session.completed:
        twiml = _make_say_hangup_twiml(agent_text)
        store.delete(call_sid)
        return Response(content=twiml, media_type="application/xml")

    # Otherwise, gather the next utterance
    twiml = _make_gather_twiml(
        say_text=agent_text,
        action_url="/voice/gather",
        call_sid=call_sid,
    )
    return Response(content=twiml, media_type="application/xml")


def _make_gather_twiml(say_text: str, action_url: str, call_sid: str) -> str:
    """
    Generate TwiML that speaks text then listens for speech.

    WHY <Gather input="speech">: This tells Twilio to:
    1. Play the <Say> prompt
    2. Record the caller's speech
    3. Transcribe it server-side
    4. POST SpeechResult to action_url

    speechTimeout="auto" lets Twilio detect end-of-speech automatically.
    language="en-IN" improves Indian English accuracy.
    """
    # Escape XML special characters in the spoken text
    safe_text = (
        say_text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Gather input="speech" action="{action_url}" method="POST"
          language="en-IN" speechTimeout="auto" timeout="5">
    <Say voice="Polly.Aditi" language="en-IN">{safe_text}</Say>
  </Gather>
  <Say voice="Polly.Aditi" language="en-IN">
    I didn't hear anything. Please call back when you are ready.
  </Say>
</Response>"""


def _make_say_hangup_twiml(text: str) -> str:
    """Generate TwiML that speaks text and hangs up."""
    safe_text = (
        text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Say voice="Polly.Aditi" language="en-IN">{safe_text}</Say>
  <Say voice="Polly.Aditi" language="en-IN">
    Goodbye. Your document will be delivered shortly.
  </Say>
  <Hangup/>
</Response>"""


# ---------------------------------------------------------------------------
# Browser Voice Client — serve the HTML file
# ---------------------------------------------------------------------------

@router.get("/client", response_class=HTMLResponse)
async def voice_client() -> HTMLResponse:
    """
    Serve the browser voice client UI.
    Lawyers open this URL to use voice via browser microphone (no phone needed).
    """
    html_path = Path(__file__).parent.parent / "voice" / "voice_client.html"
    if html_path.exists():
        return HTMLResponse(content=html_path.read_text(encoding="utf-8"))
    return HTMLResponse(
        content="<h1>Voice client not found. Please check installation.</h1>",
        status_code=404,
    )


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@router.get("/health")
async def voice_health() -> dict:
    """Voice gateway health check."""
    cfg = LexConfig()
    return {
        "status": "ok",
        "gateway": "voice",
        "voice_enabled": cfg.voice_gateway_enabled,
        "stt_backend": getattr(cfg, "stt_backend", "stub"),
        "tts_backend": getattr(cfg, "tts_backend", "stub"),
        "twilio_configured": bool(getattr(cfg, "twilio_account_sid", None)),
        "active_sessions": len(get_voice_session_store()),
    }
