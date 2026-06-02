"""
Phase 9 — 05: Voice AI Gateway
================================
Run:  pip install fastapi uvicorn httpx
      python 05_voice_gateway.py

Demonstrates the full voice pipeline without Twilio or browser deps.
All STT/TTS calls are stubbed.
"""

import asyncio
import sys

try:
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect
    from fastapi.testclient import TestClient
    FASTAPI_AVAILABLE = True
except ImportError:
    print("Install:  pip install fastapi uvicorn httpx")
    FASTAPI_AVAILABLE = False


# ── SECTION 1: TWO PATHS TO THE SAME GRAPH ───────────────────────────────────
#
# Voice input reaches LexAgent through two physical paths:
#
#  PATH A — Twilio phone call
#  ─────────────────────────
#  Lawyer phones the LexAgent number
#    → Twilio records audio
#    → Twilio POSTs audio bytes to /voice/twilio (webhook)
#    → STT: audio → text
#    → graph.ainvoke(state)  ← same as CLI / Telegram
#    → TTS: response text → audio bytes
#    → return audio to Twilio as <Response><Play>...</Play></Response>
#    → Twilio plays audio to caller
#
#  PATH B — Browser WebSocket
#  ──────────────────────────
#  Lawyer opens browser, clicks mic button
#    → browser streams audio chunks over WebSocket to /voice/ws
#    → server accumulates chunks until silence detected
#    → STT: audio → text
#    → graph.ainvoke(state)
#    → TTS: response text → audio bytes
#    → server streams audio chunks back over same WebSocket
#    → browser plays audio through speaker
#
# KEY INSIGHT: after STT, both paths are identical — plain text goes to the graph.
# The graph has NO knowledge of whether input came from a phone or a browser.
#
# In LexAgent:
#   lexagent/gateway/voice.py   — FastAPI WebSocket handler + Twilio webhook
#   lexagent/voice/stt.py       — STT (Whisper / Deepgram / stub)
#   lexagent/voice/tts.py       — TTS (Google / ElevenLabs / stub)


# ── SECTION 2: STT STUB ───────────────────────────────────────────────────────
#
# Real STT: send audio bytes to Whisper or Deepgram API, receive text.
# The function signature is the same regardless of the STT provider.
# To swap providers: change the body of `transcribe()`, not the callers.
#
# In lexagent/voice/stt.py:
#   async def transcribe(audio_bytes: bytes, cfg: LexConfig) -> str:
#       if cfg.stt_provider == "whisper":
#           return await whisper_transcribe(audio_bytes)
#       elif cfg.stt_provider == "deepgram":
#           return await deepgram_transcribe(audio_bytes)
#       else:
#           return stub_transcribe(audio_bytes)

def transcribe_stub(audio_bytes: bytes) -> str:
    """
    Stand-in for a real STT call.
    Returns a hard-coded transcript so this file runs without audio APIs.

    Replace with: openai.audio.transcriptions.create(file=audio_bytes, model="whisper-1")
    """
    # Decode if the "audio" is actually UTF-8 text bytes (our test sends text)
    try:
        decoded = audio_bytes.decode("utf-8")
        return f"[STT transcript] {decoded}"
    except UnicodeDecodeError:
        return "I need a writ petition for anticipatory bail in Delhi High Court."


# ── SECTION 3: TTS STUB ───────────────────────────────────────────────────────
#
# Real TTS: send text to Google Text-to-Speech or ElevenLabs, receive audio bytes.
# The caller doesn't care which provider is used.
#
# In lexagent/voice/tts.py:
#   async def synthesize(text: str, cfg: LexConfig) -> bytes:
#       if cfg.tts_provider == "google":
#           return await google_tts(text)
#       elif cfg.tts_provider == "elevenlabs":
#           return await elevenlabs_tts(text)
#       else:
#           return stub_tts(text)

def synthesize_stub(text: str) -> bytes:
    """
    Stand-in for a real TTS call.
    Encodes text as UTF-8 bytes — a real call would return MP3/WAV bytes.
    """
    return f"[TTS audio] {text}".encode("utf-8")


# ── SECTION 4: STUB GRAPH INVOCATION ─────────────────────────────────────────
#
# In production this is:
#   from lexagent.graph import build_graph
#   graph = build_graph(cfg)
#   result = await graph.ainvoke(state, config={"configurable": {"thread_id": session_id}})
#   return result["draft_output"] or result["messages"][-1].content
#
# We stub it here to keep this file self-contained.

async def stub_graph_invoke(transcript: str) -> str:
    """Pretend the LangGraph graph ran and returned a draft."""
    await asyncio.sleep(0.01)   # simulate async work
    return (
        f"[GRAPH RESPONSE] Based on your matter: '{transcript[:60]}...', "
        f"I recommend filing a petition under Article 226."
    )


# ── SECTION 5: TWILIO WEBHOOK HANDLER ────────────────────────────────────────
#
# Twilio POSTs a multipart/form-data request with audio to your webhook URL.
# The response must be TwiML XML that tells Twilio what to play to the caller.
#
# Real implementation (lexagent/gateway/voice.py):
#   @app.post("/voice/twilio")
#   async def twilio_webhook(request: Request):
#       form = await request.form()
#       audio_url = form["RecordingUrl"]
#       audio_bytes = httpx.get(audio_url).content
#       transcript = await stt.transcribe(audio_bytes, cfg)
#       response_text = await stub_graph_invoke(transcript)
#       audio_bytes = await tts.synthesize(response_text, cfg)
#       # save audio_bytes to a public URL, return TwiML
#       twiml = f'<Response><Play>{audio_url}</Play></Response>'
#       return Response(content=twiml, media_type="application/xml")
#
# Here we simplify: accept raw bytes, return JSON (no TwiML).


# ── SECTION 6: WEBSOCKET HANDLER ─────────────────────────────────────────────
#
# WebSocket lets the browser and server exchange binary messages over one
# persistent TCP connection — no HTTP overhead per audio chunk.
#
# Protocol in this demo:
#   1. Client connects to /voice/ws
#   2. Client sends: b"audio:<text>" (simulates audio bytes)
#   3. Server transcribes, runs graph, synthesizes
#   4. Server sends: response audio bytes
#   5. Repeat until client disconnects

def build_voice_app() -> "FastAPI":
    app = FastAPI(title="LexAgent Voice Gateway")

    @app.post("/voice/twilio")
    async def twilio_webhook(audio: bytes = b"I need a writ petition") -> dict:
        """
        Simplified Twilio webhook.  In production: parse TwiML, fetch recording,
        respond with <Play> TwiML.
        """
        transcript = transcribe_stub(audio)
        response_text = await stub_graph_invoke(transcript)
        audio_out = synthesize_stub(response_text)
        return {
            "transcript": transcript,
            "response_text": response_text,
            "audio_size_bytes": len(audio_out),
        }

    @app.websocket("/voice/ws")
    async def voice_ws(websocket: WebSocket):
        """
        Browser WebSocket handler.

        Flow per message:
          receive bytes → STT → graph → TTS → send bytes

        In production, STT and TTS are streaming:
          stream audio chunks in → partial transcripts back → graph starts early
        """
        await websocket.accept()
        print("   [WS] Client connected")
        try:
            while True:
                audio_bytes = await websocket.receive_bytes()
                print(f"   [WS] Received {len(audio_bytes)} bytes")

                # STT
                transcript = transcribe_stub(audio_bytes)
                print(f"   [WS] Transcript: '{transcript[:60]}'")

                # Graph
                response_text = await stub_graph_invoke(transcript)

                # TTS
                audio_out = synthesize_stub(response_text)
                print(f"   [WS] Sending {len(audio_out)} audio bytes")

                await websocket.send_bytes(audio_out)

        except WebSocketDisconnect:
            print("   [WS] Client disconnected")

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok", "gateway": "voice"}

    return app


# ── SECTION 7: TESTS ──────────────────────────────────────────────────────────

def run_tests() -> None:
    if not FASTAPI_AVAILABLE:
        print("FastAPI not installed — skipping tests.")
        return

    app = build_voice_app()
    client = TestClient(app)

    print("\n── Test 1: STT stub ──")
    result = transcribe_stub(b"bail petition for my client")
    print(f"   Input bytes: {len(b'bail petition for my client')}")
    print(f"   Transcript : '{result}'")
    assert "bail petition" in result or "[STT" in result

    print("\n── Test 2: TTS stub ──")
    audio = synthesize_stub("File a writ under Article 226.")
    print(f"   Text input  : 'File a writ under Article 226.'")
    print(f"   Audio bytes : {len(audio)} bytes")
    assert len(audio) > 0

    print("\n── Test 3: POST /voice/twilio ──")
    resp = client.post("/voice/twilio", content=b"I need anticipatory bail")
    assert resp.status_code == 200
    body = resp.json()
    assert "transcript" in body and "response_text" in body
    print(f"   transcript   : '{body['transcript'][:60]}'")
    print(f"   response_text: '{body['response_text'][:60]}'")
    print(f"   audio_size   : {body['audio_size_bytes']} bytes")

    print("\n── Test 4: WebSocket /voice/ws ──")
    with client.websocket_connect("/voice/ws") as ws:
        ws.send_bytes(b"I need a bail application")
        response = ws.receive_bytes()
        print(f"   Sent   : 25 bytes")
        print(f"   Received: {len(response)} bytes")
        assert len(response) > 0

    print("\n── Test 5: GET /health ──")
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["gateway"] == "voice"
    print(f"   ✓ {resp.json()}")

    print("\n── All voice gateway tests passed ──\n")


# ── SECTION 8: FULL ARCHITECTURE PICTURE ─────────────────────────────────────
#
#  ┌──────────────────────────────────────────────────────────────────┐
#  │                     Voice Gateway                                │
#  │                                                                  │
#  │  Phone → Twilio → POST /voice/twilio                             │
#  │                        │                                         │
#  │                        ▼                                         │
#  │              transcribe_stub(audio_bytes)                        │
#  │              ─────────────────────────────── STT layer          │
#  │                        │  plain text                             │
#  │                        ▼                                         │
#  │              graph.ainvoke(state)           LangGraph            │
#  │                        │  response text                          │
#  │                        ▼                                         │
#  │              synthesize_stub(text)          TTS layer            │
#  │              ─────────────────────────────────                   │
#  │                        │  audio bytes                            │
#  │                        ▼                                         │
#  │              return to Twilio → plays to caller                  │
#  │                                                                  │
#  │  Browser → WebSocket /voice/ws  (same STT → graph → TTS flow)   │
#  └──────────────────────────────────────────────────────────────────┘


if __name__ == "__main__":
    run_tests()
    print("To run with a real WebSocket client:")
    print("  uvicorn 05_voice_gateway:build_voice_app --factory --reload")
    print("  Then connect a WebSocket client to ws://localhost:8000/voice/ws")


# ── PAUSE AND THINK ──────────────────────────────────────────────────────────
#
# 1. Open lexagent/gateway/voice.py.
#    Which STT provider does it use by default?
#    Where is the provider selection controlled — in the handler or in config?
#
# 2. Open lexagent/voice/stt.py and lexagent/voice/tts.py.
#    Do they implement streaming STT (partial transcripts) or batch STT
#    (full audio → full text)?  How does that affect latency?
#
# 3. The WebSocket handler in this file processes one message at a time.
#    Real voice is continuous.  What would you need to add to detect
#    sentence boundaries in a stream (end-of-utterance detection)?
#
# 4. Twilio's webhook must respond within 15 seconds or the call drops.
#    If the LangGraph run takes 30 seconds (multi-step research), what
#    pattern would you use to avoid the timeout?
#    (Hint: look up Twilio's <Gather> and <Redirect> TwiML verbs.)
#
# 5. The graph output is `result["draft_output"]` — a long legal draft.
#    Voice output should be much shorter (30–60 seconds of speech).
#    Where in the pipeline would you truncate or summarise the draft
#    before passing it to TTS?
