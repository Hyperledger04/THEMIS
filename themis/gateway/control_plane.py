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

from themis.config import LexConfig
from themis.graph import get_graph, setup_checkpointer
from themis.security.context import SecurityContext, Role
from themis.security.audit import AuditAction, log_action
from themis.state import LexState

logger = logging.getLogger(__name__)

app = FastAPI(title="Themis Control Plane", version="9.0")

# WHY: Personal mode uses wildcard CORS for local dev convenience.
# Multi-tenant/enterprise mode restricts to cfg.cors_origins (set via LEX_CORS_ORIGINS).
# V3 Phase 1: remove the permanent wildcard — it was forbidden in enterprise mode.
_boot_cfg = LexConfig()
_cors_origins = _boot_cfg.cors_origins if _boot_cfg.multi_tenant else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# WHY: TierFloorMiddleware must be registered AFTER CORS so CORS preflight
# OPTIONS requests are handled before tier enforcement (browsers send OPTIONS
# without X-Inference-Tier, which would produce spurious 403s otherwise).
from themis.gateway.tier_middleware import TierFloorMiddleware  # noqa: E402
app.add_middleware(TierFloorMiddleware)

# Phase 9B: Mount the voice gateway router at /voice.
# WHY: All gateways share the same FastAPI app so they reuse the Postgres
# checkpointer, auth middleware, and CORS config without a second process.
from themis.gateway.voice import router as _voice_router  # noqa: E402
app.include_router(_voice_router, prefix="/voice")


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def _get_cfg() -> LexConfig:
    return LexConfig()


def _emit_matter_audit(
    action: str,
    *,
    firm_id: str,
    user_id: str,
    matter_id: str,
    detail: Optional[dict] = None,
) -> None:
    """Non-blocking audit call — never raises.

    WHY: log_action() swallows all exceptions internally so this helper is
    safe to call from any request handler without disrupting the response.
    """
    log_action(
        action,
        firm_id=firm_id,
        user_id=user_id,
        resource_type="matter",
        resource_id=matter_id,
        detail=detail,
    )


def _verify_token(
    authorization: Optional[str] = Header(None),
    cfg: LexConfig = Depends(_get_cfg),
) -> SecurityContext:
    """
    JWT bearer auth. Returns SecurityContext — never a bare dict.
    Personal mode (no api_secret_key): returns SecurityContext.personal_default().
    Enterprise mode: verifies JWT and extracts firm_id/user_id/role from claims.

    WHY JWT over static bearer: tokens carry identity (firm_id/user_id/role)
    so the control plane does not need a DB lookup on every request. Stolen
    tokens expire in 15 minutes (ACCESS_TOKEN_EXPIRE_MINUTES in tokens.py).
    """
    if not cfg.api_secret_key:
        # Personal mode — single-lawyer local dev, no auth overhead.
        return SecurityContext.personal_default()

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")

    token = authorization.split(" ", 1)[1]
    try:
        from themis.security.tokens import decode_access_token
        payload = decode_access_token(token, cfg.api_secret_key)
        return SecurityContext.from_jwt_payload(payload, is_multi_tenant=cfg.multi_tenant)
    except Exception:
        raise HTTPException(status_code=403, detail="Invalid or expired token")


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def _startup() -> None:
    cfg = LexConfig()
    await setup_checkpointer(cfg)
    get_graph(cfg)
    logger.info("Themis control plane ready.")


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


class DocumentViewerOut(BaseModel):
    matter_id: str
    document_id: str
    page: Optional[int] = None
    line: Optional[int] = None
    anchor: Optional[str] = None
    highlight: Optional[str] = None


# ---------------------------------------------------------------------------
# REST: send a message and get the final state back (non-streaming)
# ---------------------------------------------------------------------------

@app.post("/api/v1/matters/{matter_id}/message", response_model=MatterOut)
async def send_message(
    matter_id: str,
    body: MessageIn,
    auth: SecurityContext = Depends(_verify_token),
    cfg: LexConfig = Depends(_get_cfg),
) -> MatterOut:
    """
    Invoke the LangGraph agent for a matter. Blocks until the graph reaches END.
    Returns the final state's key output fields.

    WHY non-streaming here: WhatsApp / Slack webhooks need a single response payload.
    For streaming, use the WebSocket endpoint /ws/{user_id}/{matter_id}.
    """
    _emit_matter_audit(AuditAction.MATTER_ACCESSED, firm_id=auth.firm_id,
                       user_id=auth.user_id, matter_id=matter_id)

    graph = get_graph(cfg)
    langgraph_cfg = {
        "configurable": {
            "thread_id": matter_id,
            "user_id": auth.user_id,
            "firm_id": auth.firm_id,
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
        "firm_id": auth.firm_id,
        "user_id": auth.user_id,
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

    if final.get("draft_output"):
        _emit_matter_audit(AuditAction.DRAFT_GENERATED, firm_id=auth.firm_id,
                           user_id=auth.user_id, matter_id=matter_id)

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
async def list_matters(auth: SecurityContext = Depends(_verify_token)) -> JSONResponse:
    """
    Return active matters for this user/tenant.
    WHY stub: full implementation requires a Postgres query over the LangGraph
    checkpoint tables. Returning an empty list for now so the web UI can connect.
    """
    return JSONResponse(content={"matters": [], "firm_id": auth.firm_id})


# ---------------------------------------------------------------------------
# Web: source-citation document viewer target
# ---------------------------------------------------------------------------

@app.get("/document-viewer/{matter_id}/{document_id}", response_model=DocumentViewerOut)
async def document_viewer(
    matter_id: str,
    document_id: str,
    page: Optional[int] = None,
    line: Optional[int] = None,
    anchor: Optional[str] = None,
    auth: SecurityContext = Depends(_verify_token),
) -> DocumentViewerOut:
    """
    Canonical target for clickable source footnotes like [F3].

    MVP: returns the requested page/line/anchor so web clients can open and
    highlight the source. Later this endpoint should load the source_anchor row
    from Postgres, verify tenant ownership, and serve a full document-view model.
    """
    return DocumentViewerOut(
        matter_id=matter_id,
        document_id=document_id,
        page=page,
        line=line,
        anchor=anchor,
        highlight=f"page={page} line={line} anchor={anchor}",
    )


# ---------------------------------------------------------------------------
# REST: upload a document for a matter
# ---------------------------------------------------------------------------

@app.post("/api/v1/matters/{matter_id}/documents")
async def upload_document(
    matter_id: str,
    file: UploadFile,
    auth: SecurityContext = Depends(_verify_token),
    cfg: LexConfig = Depends(_get_cfg),
) -> JSONResponse:
    """
    Accept a PDF/DOCX upload, save it temporarily, and index it into Qdrant.
    Returns the saved path so the caller can reference it in a subsequent message.
    """
    import tempfile
    from pathlib import Path

    _emit_matter_audit(AuditAction.DOCUMENT_UPLOADED, firm_id=auth.firm_id,
                       user_id=auth.user_id, matter_id=matter_id,
                       detail={"filename": file.filename})

    suffix = Path(file.filename or "upload.pdf").suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    # Phase 9: index the document into Qdrant if enabled.
    if cfg.qdrant_enabled:
        try:
            import pdfplumber
            from themis.tools.retriever import PersistentQdrantRetriever

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
                matter_id, firm_id=auth.firm_id, cfg=cfg
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

    # Auth: decode JWT before accepting the WebSocket upgrade so unauthorised
    # callers never get a connection. Personal mode (no api_secret_key) skips auth.
    # WHY SecurityContext here: uniform identity object across REST and WS paths —
    # no special-casing of dict vs dataclass downstream.
    ctx = SecurityContext.personal_default()
    if cfg.api_secret_key:
        if not token:
            await websocket.close(code=4403)
            return
        try:
            from themis.security.tokens import decode_access_token
            payload = decode_access_token(token, cfg.api_secret_key)
            ctx = SecurityContext.from_jwt_payload(payload, is_multi_tenant=cfg.multi_tenant)
        except Exception:
            await websocket.close(code=4403)
            return

    await websocket.accept()
    graph = get_graph(cfg)

    langgraph_cfg = {
        "configurable": {
            "thread_id": matter_id,
            "user_id": ctx.user_id,
            "firm_id": ctx.firm_id,
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
            "firm_id": ctx.firm_id,
            "user_id": ctx.user_id,
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
# F3: Runtime halt endpoint
# ---------------------------------------------------------------------------

@app.post("/api/v1/matters/{matter_id}/runs/{run_id}/halt")
async def halt_run(
    matter_id: str,
    run_id: str,
    claims: SecurityContext = Depends(_verify_token),
    cfg: LexConfig = Depends(_get_cfg),
) -> JSONResponse:
    """
    Externally cancel all queued/running jobs for a run.
    Sets agent_jobs.status='cancelled' for any job in this run that is
    not already completed/failed, then marks the run halt_state='external_halt'.

    WHY: Long-running parallel research jobs can be stopped mid-flight without
    killing the worker process. The worker's HaltFlag checks this status at
    the start of each step and stops cleanly.
    """
    if not cfg.postgres_url:
        raise HTTPException(status_code=503, detail="Runtime database not configured")

    try:
        from themis.runtime.postgres import PostgresRuntimeRepository
        repo = PostgresRuntimeRepository(cfg.postgres_url)

        # Cancel all active jobs belonging to this run
        with repo._connect() as conn:
            rows = conn.execute(
                """
                SELECT job_id FROM agent_jobs
                WHERE run_id = %s AND status IN ('queued', 'running', 'paused')
                """,
                (run_id,),
            ).fetchall()

        cancelled_count = 0
        for row in rows:
            repo.cancel_job(row[0], reason="external_halt")
            cancelled_count += 1

        # Mark the run itself as halted
        with repo._connect() as conn:
            conn.execute(
                "UPDATE agent_runs SET halt_state = 'external_halt' WHERE run_id = %s",
                (run_id,),
            )
            conn.commit()

        logger.info(
            "Run %s halted by user=%s: %d jobs cancelled",
            run_id, claims.user_id, cancelled_count,
        )
        return JSONResponse({"halted": True, "run_id": run_id, "jobs_cancelled": cancelled_count})

    except Exception as exc:
        logger.exception("halt_run failed for run_id=%s: %s", run_id, exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse(content={"status": "ok", "service": "themis-control-plane"})
