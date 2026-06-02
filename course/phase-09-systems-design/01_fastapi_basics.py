"""
Phase 9 — 01: FastAPI Control Plane Basics
==========================================
Run:  pip install fastapi uvicorn httpx
      python 01_fastapi_basics.py
"""

# ── SECTION 1: WHY FASTAPI ──────────────────────────────────────────────────
#
# LexAgent has three gateways today: CLI, Telegram, and (soon) Voice.
# Each gateway captures user input and feeds it to the same LangGraph graph.
#
# Without a central HTTP layer:
#   CLI  ──► graph.invoke(state)
#   Telegram ──► graph.invoke(state)   ← duplicated invocation logic
#   Voice ──► graph.invoke(state)      ← duplicated again
#
# With FastAPI as the "control plane":
#   CLI  ──► POST /draft ──► graph.invoke(state)
#   Telegram ──► POST /draft ──► same handler
#   Voice ──► POST /draft ──► same handler
#
# Result: one place to add auth, rate-limiting, logging, tracing.
# The graph never knows which gateway called it.

import asyncio
import sys
import uuid
from datetime import datetime

try:
    from fastapi import Depends, FastAPI, HTTPException, status
    from fastapi.testclient import TestClient
    from pydantic import BaseModel, Field
except ImportError:
    print("Install deps:  pip install fastapi uvicorn httpx")
    sys.exit(1)

# ── SECTION 2: PYDANTIC REQUEST / RESPONSE MODELS ───────────────────────────
#
# Pydantic validates incoming JSON automatically.
# If the client sends wrong types, FastAPI returns 422 before your handler runs.


class DraftRequest(BaseModel):
    """What the client POSTs to /draft."""
    matter: str = Field(..., description="Plain-English matter brief")
    firm_id: str = Field(default="personal", description="Tenant identifier")
    user_id: str = Field(default="u1", description="Authenticated user")
    # WHY: include firm_id here so every request is tenant-aware from the first
    # touch — no chance of accidentally cross-contaminating firm data downstream.


class DraftResponse(BaseModel):
    """What /draft returns."""
    matter_id: str
    status: str          # "queued" | "complete" | "error"
    draft: str | None    # None when status == "queued"
    created_at: str


class MatterResponse(BaseModel):
    """What GET /matter/{matter_id} returns."""
    matter_id: str
    firm_id: str
    status: str
    summary: str


class HealthResponse(BaseModel):
    """What GET /health returns — useful for load-balancer liveness probes."""
    status: str
    version: str
    timestamp: str


# ── SECTION 3: DEPENDENCY INJECTION WITH Depends() ──────────────────────────
#
# `Depends()` is FastAPI's DI system. You declare what a function needs,
# FastAPI resolves it before calling your handler.
# Common uses:
#   - inject a config object
#   - verify a JWT token (Section 6)
#   - get a DB connection from a pool
#
# WHY not just import config at module level?
# Because you can swap the dependency in tests without patching globals.


class LexConfig:
    """Simplified stand-in for lexagent/config.py LexConfig."""
    model: str = "claude-sonnet-4-20250514"
    max_draft_tokens: int = 4096
    version: str = "0.9.0"


def get_config() -> LexConfig:
    """
    Dependency factory — FastAPI calls this before your handler and passes
    the result as the `cfg` parameter.

    In production this would read env vars via Pydantic BaseSettings.
    See: lexagent/config.py → class LexConfig(BaseSettings)
    """
    return LexConfig()


# ── SECTION 4: IN-MEMORY STORE (stand-in for Postgres) ──────────────────────
#
# In real code this is a Postgres table accessed via asyncpg (see 02_postgres_async.py).
# Here we use a plain dict so this file runs without a DB.

_matter_store: dict[str, dict] = {}


# ── SECTION 5: THE FASTAPI APP AND ENDPOINTS ────────────────────────────────

app = FastAPI(
    title="LexAgent Control Plane",
    description="Single HTTP surface for all LexAgent gateways",
    version="0.9.0",
)


@app.post("/draft", response_model=DraftResponse, status_code=status.HTTP_202_ACCEPTED)
async def draft_handler(
    req: DraftRequest,
    cfg: LexConfig = Depends(get_config),   # ← DI in action
) -> DraftResponse:
    """
    Receives a matter brief from ANY gateway (Telegram, CLI, voice, web)
    and kicks off the LangGraph graph run.

    In production:
      1. Verify JWT from request headers (Depends(verify_jwt)).
      2. Enqueue a background task (BackgroundTasks) so /draft returns fast.
      3. The background task calls graph.ainvoke(state) and writes result to DB.

    Here we return a stub draft immediately.
    """
    matter_id = str(uuid.uuid4())[:8]

    # Stub: pretend the graph produced a draft.
    stub_draft = (
        f"[STUB — model={cfg.model}] "
        f"Draft for matter: '{req.matter[:60]}...' "
        f"(matter_id={matter_id})"
    )

    record = {
        "matter_id": matter_id,
        "firm_id": req.firm_id,
        "user_id": req.user_id,
        "matter": req.matter,
        "status": "complete",
        "draft": stub_draft,
        "created_at": datetime.utcnow().isoformat(),
    }
    _matter_store[matter_id] = record

    return DraftResponse(
        matter_id=matter_id,
        status="complete",
        draft=stub_draft,
        created_at=record["created_at"],
    )


@app.get("/health", response_model=HealthResponse)
async def health_handler(cfg: LexConfig = Depends(get_config)) -> HealthResponse:
    """
    Liveness probe for load balancers and monitoring systems.
    Returns quickly — no DB calls.
    """
    return HealthResponse(
        status="ok",
        version=cfg.version,
        timestamp=datetime.utcnow().isoformat(),
    )


@app.get("/matter/{matter_id}", response_model=MatterResponse)
async def get_matter_handler(matter_id: str) -> MatterResponse:
    """
    Retrieve a previously created matter by its ID.

    Path parameters (like matter_id here) are extracted automatically
    from the URL pattern — no manual parsing.

    In production this queries Postgres:
      SELECT * FROM matters WHERE matter_id = $1 AND firm_id = $2
    The firm_id comes from the verified JWT (not the URL) to prevent
    tenants from reading each other's matters.
    """
    record = _matter_store.get(matter_id)
    if not record:
        # HTTPException sets the correct HTTP status code and JSON error body.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"matter_id '{matter_id}' not found",
        )
    return MatterResponse(
        matter_id=record["matter_id"],
        firm_id=record["firm_id"],
        status=record["status"],
        summary=record["matter"][:80],
    )


# ── SECTION 6: TESTS WITH TestClient ────────────────────────────────────────
#
# FastAPI ships with a synchronous TestClient backed by httpx.
# No server process needed — it calls your handlers in-process.
# This is the same pattern used in lexagent/tests/ for gateway tests.


def run_tests() -> None:
    client = TestClient(app)

    print("\n── Test 1: POST /draft ──")
    resp = client.post("/draft", json={"matter": "Writ petition for bail in Delhi HC"})
    assert resp.status_code == 202, f"Expected 202, got {resp.status_code}"
    body = resp.json()
    assert body["status"] == "complete"
    assert "matter_id" in body
    print(f"   ✓ matter_id={body['matter_id']}  status={body['status']}")
    matter_id = body["matter_id"]

    print("\n── Test 2: GET /health ──")
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    print(f"   ✓ version={body['version']}  timestamp={body['timestamp']}")

    print("\n── Test 3: GET /matter/{matter_id} ──")
    resp = client.get(f"/matter/{matter_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["matter_id"] == matter_id
    print(f"   ✓ matter_id={body['matter_id']}  firm_id={body['firm_id']}")

    print("\n── Test 4: GET /matter/nonexistent (should 404) ──")
    resp = client.get("/matter/doesnotexist")
    assert resp.status_code == 404
    print(f"   ✓ 404 returned as expected")

    print("\n── Test 5: Gateway transparency ──")
    # Telegram gateway sends the same JSON shape as CLI.
    # The handler doesn't care — it sees only DraftRequest.
    for gateway in ["telegram", "cli", "voice"]:
        resp = client.post(
            "/draft",
            json={
                "matter": f"Test matter from {gateway}",
                "firm_id": "firm_abc",
                "user_id": "u99",
            },
        )
        assert resp.status_code == 202
    print("   ✓ All 3 gateways produce identical 202 responses")

    print("\n── All tests passed ──\n")


# ── SECTION 7: HOW GATEWAYS CONNECT ─────────────────────────────────────────
#
# This diagram shows why the graph never needs to know its caller:
#
#  Telegram bot                   Control Plane (this file)
#  ─────────────────              ───────────────────────────────────
#  on_message(update):            @app.post("/draft")
#    text = update.message.text   async def draft_handler(req):
#    resp = httpx.post(              state = build_state(req)
#      "http://api/draft",           result = await graph.ainvoke(state)
#      json={"matter": text}         return DraftResponse(...)
#    )
#    await bot.send(resp["draft"])
#
#  Voice gateway
#  ─────────────────
#  audio = receive_from_twilio()
#  text = stt.transcribe(audio)   ← STT converts voice to text
#  resp = httpx.post(             ← same POST as Telegram
#    "http://api/draft",
#    json={"matter": text}
#  )
#  audio_out = tts.synthesize(resp["draft"])
#  send_to_twilio(audio_out)
#
# The graph sees: {"matter": "...", "firm_id": "...", "user_id": "..."}
# It does NOT see whether this came from voice, Telegram, or CLI.


if __name__ == "__main__":
    run_tests()
    print("To run the live server:")
    print("  uvicorn 01_fastapi_basics:app --reload --port 8000")
    print("Then visit: http://localhost:8000/docs")


# ── PAUSE AND THINK ──────────────────────────────────────────────────────────
#
# 1. Open lexagent/gateway/control_plane.py.
#    Which endpoints does it define?
#    How does it authenticate requests before reaching the handler?
#
# 2. The /draft handler above returns 202 (Accepted) immediately with a stub.
#    In control_plane.py, does /draft block until the graph finishes,
#    or does it use BackgroundTasks to run async?  Why does that matter for
#    long-running LangGraph runs (e.g. multi-step research)?
#
# 3. `Depends(get_config)` injects LexConfig into every handler.
#    In control_plane.py, what does `Depends(verify_jwt)` inject,
#    and what does it do when the token is missing or expired?
#
# 4. TestClient lets tests run without a server process.
#    Look at the tests in lexagent/tests/test_gateway*.py.
#    Do they use TestClient or do they spin up a real server?  Why?
#
# 5. Suppose you add a new `/summarise` endpoint.
#    List every file you would need to touch in lexagent/ to wire it up
#    end-to-end (router, handler, state field, node, test).
