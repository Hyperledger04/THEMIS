# FastAPI Control Plane — Phase 9
#
# OpenClaw-inspired single backend serving all gateways (Telegram, WhatsApp,
# Slack, Discord, Voice, Web UI). Each gateway is a thin adapter that POSTs
# here instead of calling get_graph() directly.
#
# WHY a control plane instead of per-gateway graphs:
#   - One Postgres checkpointer shared across gateways — matter state is the
#     same whether the lawyer messages via Telegram or the web UI.
#   - Centralised auth: every gateway identifies (firm_id, user_id, matter_id).
#   - WebSocket endpoint lets the web UI stream agent tokens in real time.
#   - REST endpoint lets non-streaming callers (WhatsApp webhooks) fire-and-forget.

import asyncio
import json
import logging
import uuid
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from lexagent.config import LexConfig
from lexagent.graph import get_graph, setup_checkpointer
from lexagent.state import LexState

logger = logging.getLogger(__name__)

app = FastAPI(title="LexAgent Control Plane", version="9.0")

# WHY: Allow all origins in dev mode. In production, restrict to the lexanodes/ domain.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Phase 9B: Mount the voice gateway router at /voice.
# WHY: All gateways share the same FastAPI app so they reuse the Postgres
# checkpointer, auth middleware, and CORS config without a second process.
from lexagent.gateway.voice import router as _voice_router  # noqa: E402
app.include_router(_voice_router, prefix="/voice")


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def _get_cfg() -> LexConfig:
    return LexConfig()


def _verify_token(
    authorization: Optional[str] = Header(None),
    cfg: LexConfig = Depends(_get_cfg),
) -> dict:
    """
    Simple bearer token auth. Passes firm_id and user_id extracted from the token.
    WHY: In single-lawyer mode (api_secret_key is None) auth is skipped so CLI
    and local dev work without any setup.
    """
    if not cfg.api_secret_key:
        return {"firm_id": cfg.default_firm_id, "user_id": "default"}

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")

    token = authorization.split(" ", 1)[1]
    if token != cfg.api_secret_key:
        raise HTTPException(status_code=403, detail="Invalid token")

    return {"firm_id": cfg.default_firm_id, "user_id": "default"}


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def _startup() -> None:
    cfg = LexConfig()
    await setup_checkpointer(cfg)
    get_graph(cfg)
    logger.info("LexAgent control plane ready.")


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class MessageIn(BaseModel):
    text: str
    matter_id: Optional[str] = None


class MatterOut(BaseModel):
    matter_id: str
    status: str
    draft_output: Optional[str] = None
    plain_english_summary: Optional[str] = None
    contract_review_output: Optional[str] = None
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# REST: send a message and get the final state back (non-streaming)
# ---------------------------------------------------------------------------

@app.post("/api/v1/matters/{matter_id}/message", response_model=MatterOut)
async def send_message(
    matter_id: str,
    body: MessageIn,
    auth: dict = Depends(_verify_token),
    cfg: LexConfig = Depends(_get_cfg),
) -> MatterOut:
    """
    Invoke the LangGraph agent for a matter. Blocks until the graph reaches END.
    Returns the final state's key output fields.

    WHY non-streaming here: WhatsApp / Slack webhooks need a single response payload.
    For streaming, use the WebSocket endpoint /ws/{user_id}/{matter_id}.
    """
    graph = get_graph(cfg)
    langgraph_cfg = {
        "configurable": {
            "thread_id": matter_id,
            "user_id": auth["user_id"],
            "firm_id": auth["firm_id"],
        }
    }

    # WHY: Check the checkpoint first. If this matter already has state, only
    # pass the new message — don't reset intake_complete or citations_verified.
    # LangGraph merges the passed dict with the checkpoint; passing False would
    # override a True checkpoint value and restart intake on every resumed call.
    snapshot = await graph.aget_state(langgraph_cfg)
    is_new = not snapshot or not snapshot.values

    state: LexState = {
        "user_input": body.text,
        "matter_id": matter_id,
        "messages": [{"role": "user", "content": body.text}],
        "firm_id": auth["firm_id"],
        "user_id": auth["user_id"],
    }
    if is_new:
        state["intake_complete"] = False
        state["citations_verified"] = False
        state["draft_output"] = None
        state["plain_english_summary"] = None

    try:
        final = await graph.ainvoke(state, config=langgraph_cfg)
    except Exception as e:
        logger.error("Graph invocation error for matter %s: %s", matter_id, e)
        return MatterOut(matter_id=matter_id, status="error", error=str(e))

    return MatterOut(
        matter_id=matter_id,
        status="draft_ready" if final.get("draft_output") else "in_progress",
        draft_output=final.get("draft_output"),
        plain_english_summary=final.get("plain_english_summary"),
        contract_review_output=final.get("contract_review_output"),
        error=final.get("error"),
    )


# ---------------------------------------------------------------------------
# REST: list matters for the authenticated user (stubs — expand with DB query)
# ---------------------------------------------------------------------------

@app.get("/api/v1/matters")
async def list_matters(auth: dict = Depends(_verify_token)) -> JSONResponse:
    """
    Return active matters for this user/tenant.
    WHY stub: full implementation requires a Postgres query over the LangGraph
    checkpoint tables. Returning an empty list for now so the web UI can connect.
    """
    return JSONResponse(content={"matters": [], "firm_id": auth["firm_id"]})


# ---------------------------------------------------------------------------
# REST: upload a document for a matter
# ---------------------------------------------------------------------------

@app.post("/api/v1/matters/{matter_id}/documents")
async def upload_document(
    matter_id: str,
    file: UploadFile,
    auth: dict = Depends(_verify_token),
    cfg: LexConfig = Depends(_get_cfg),
) -> JSONResponse:
    """
    Accept a PDF/DOCX upload, save it temporarily, and index it into Qdrant.
    Returns the saved path so the caller can reference it in a subsequent message.
    """
    import tempfile
    from pathlib import Path

    suffix = Path(file.filename or "upload.pdf").suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    # Phase 9: index the document into Qdrant if enabled.
    if cfg.qdrant_enabled:
        try:
            import pdfplumber
            from lexagent.tools.retriever import PersistentQdrantRetriever

            text_chunks: list[dict] = []
            with pdfplumber.open(tmp_path) as pdf:
                for i, page in enumerate(pdf.pages):
                    text = page.extract_text() or ""
                    if text.strip():
                        text_chunks.append({
                            "case_name": f"{file.filename} p{i+1}",
                            "citation": f"{file.filename}:page{i+1}",
                            "relevance": text[:500],
                            "url": tmp_path,
                            "source": "uploaded_document",
                        })

            qr = PersistentQdrantRetriever(
                matter_id, firm_id=auth["firm_id"], cfg=cfg
            )
            n = qr.index_findings(text_chunks)
            logger.info("Indexed %d chunks from %s for matter %s", n, file.filename, matter_id)
        except Exception as e:
            logger.warning("Document indexing failed: %s", e)

    return JSONResponse(content={"matter_id": matter_id, "path": tmp_path, "filename": file.filename})


# ---------------------------------------------------------------------------
# WebSocket: streaming agent for web UI
# ---------------------------------------------------------------------------

@app.websocket("/ws/{user_id}/{matter_id}")
async def ws_endpoint(
    websocket: WebSocket,
    user_id: str,
    matter_id: str,
    token: Optional[str] = None,
) -> None:
    """
    WebSocket endpoint for real-time token streaming to the web UI.

    Protocol:
      Client → {"text": "matter brief..."}
      Server → {"type": "token", "content": "..."} (one per streamed chunk)
      Server → {"type": "node", "node": "research"} (on node transitions)
      Server → {"type": "done", "state": {...}} (on graph completion)
      Server → {"type": "error", "error": "..."} (on exception)

    WHY WebSocket over SSE: bidirectional — client can send clarifying answers
    mid-stream, matching the multi-turn intake flow.
    WHY token as query param: WebSocket handshake cannot carry Authorization
    headers from browser JS, so the secret travels as ?token=... over TLS.
    """
    cfg = LexConfig()

    # Auth: mirror _verify_token logic. Reject before accept() to avoid
    # upgrading the connection for unauthorised callers.
    if cfg.api_secret_key and token != cfg.api_secret_key:
        await websocket.close(code=4403)
        return

    await websocket.accept()
    graph = get_graph(cfg)

    langgraph_cfg = {
        "configurable": {
            "thread_id": matter_id,
            "user_id": user_id,
            "firm_id": cfg.default_firm_id,
        }
    }

    try:
        raw = await websocket.receive_text()
        payload = json.loads(raw)
        user_text = payload.get("text", "")

        # WHY: Same checkpoint-first pattern as send_message — only reset
        # intake_complete/citations_verified for genuinely new matters.
        snapshot = await graph.aget_state(langgraph_cfg)
        is_new = not snapshot or not snapshot.values

        state: LexState = {
            "user_input": user_text,
            "matter_id": matter_id,
            "messages": [{"role": "user", "content": user_text}],
            "firm_id": cfg.default_firm_id,
            "user_id": user_id,
        }
        if is_new:
            state["intake_complete"] = False
            state["citations_verified"] = False
            state["draft_output"] = None
            state["plain_english_summary"] = None

        # LANGGRAPH: astream_events yields node-level events including token deltas.
        # "v2" event schema gives us both node transitions and LLM token streaming.
        async for event in graph.astream_events(state, config=langgraph_cfg, version="v2"):
            kind = event.get("event", "")
            if kind == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk")
                if chunk and hasattr(chunk, "content") and chunk.content:
                    await websocket.send_json({"type": "token", "content": chunk.content})
            elif kind == "on_chain_start":
                node = event.get("name", "")
                if node and not node.startswith("_"):
                    await websocket.send_json({"type": "node", "node": node})

        # Send final state on completion.
        final_snapshot = await graph.aget_state(langgraph_cfg)
        final_values = final_snapshot.values if final_snapshot else {}
        await websocket.send_json({
            "type": "done",
            "state": {
                "draft_output": final_values.get("draft_output"),
                "plain_english_summary": final_values.get("plain_english_summary"),
                "intake_complete": final_values.get("intake_complete"),
                "error": final_values.get("error"),
            },
        })

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected: user=%s matter=%s", user_id, matter_id)
    except Exception as e:
        logger.error("WebSocket error: %s", e)
        try:
            await websocket.send_json({"type": "error", "error": str(e)})
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse(content={"status": "ok", "service": "lexagent-control-plane"})
