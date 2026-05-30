# LexAgent Phase 8B — Checkpoint

**Status:** Complete  
**Tests:** 279 / 279 passing  
**Date:** 2026-05-20

---

## What Phase 8B Is

Phase 8B transforms LexAgent from a single-lawyer Telegram bot into a multi-tenant SaaS backend with a web UI. It implements Phases 1–4 of the "24/7 Legal Employee" architecture plan, building directly on the Phase 8 UX overhaul (279 tests, Telegram inline buttons, .docx delivery, structured intake).

The four sub-phases are numbered **Phase 9** in code comments to distinguish them from the original Phase 8 work.

---

## Phase 9 (8B.1): LangGraph Native Persistence

**Goal:** Replace manual SQLite session hacking with LangGraph's built-in checkpointer so matter state is fully persisted across restarts, resumable from any gateway, and compatible with human-in-the-loop and time-travel.

### Files changed
| File | Change |
|------|--------|
| `lexagent/graph.py` | Added `_GRAPHS` dict keyed by `"postgres"/"memory"`. `get_graph(cfg)` compiles the graph with `AsyncPostgresSaver` (falls back to `MemorySaver` when no `POSTGRES_URL` set). `build_graph()` returns uncompiled `StateGraph` for tests. `setup_checkpointer(cfg)` is async and idempotent. |
| `lexagent/config.py` | Added `postgres_url`, `qdrant_url`, `qdrant_api_key`, `embedding_model`, `embedding_dim`, `qdrant_enabled`, `control_plane_host`, `control_plane_port`, `api_secret_key`, `default_firm_id`, `multi_tenant`. |
| `lexagent/state.py` | Added `firm_id`, `user_id`, `preferred_gateway`, `background_task` fields. |
| `lexagent/gateway/telegram.py` | `run_telegram_bot` calls `asyncio.run(setup_checkpointer(cfg))` on startup then `get_graph(cfg)` — ensures Postgres checkpoint tables exist before the first message arrives. |
| `tests/test_contract_review.py` | `build_graph()` now returns uncompiled `StateGraph`; changed `graph = build_graph()` → `graph = build_graph().compile()`. |
| `pyproject.toml` | Added: `langgraph-checkpoint-postgres>=2.0`, `psycopg[binary,pool]>=3.1`, `qdrant-client>=1.9`, `sentence-transformers>=3.0`, `fastapi>=0.115`, `uvicorn[standard]>=0.30`, `python-multipart>=0.0.9`, `apscheduler>=3.10`. |

### How it works
```
matter_id == LangGraph thread_id
graph.ainvoke(state, config={"configurable": {"thread_id": matter_id}})
# State is auto-persisted after every node.
# Resume any matter: just pass the same thread_id — no re-questioning.
```

When `POSTGRES_URL` is not set (offline dev / tests), `MemorySaver` is used automatically.

---

## Phase 9 (8B.2): Persistent Qdrant Retriever

**Goal:** Replace in-memory TF-IDF (rebuilt from scratch every session) with a per-matter Qdrant vector store so research findings, uploaded documents, and citation history accumulate across restarts.

### Files changed
| File | Change |
|------|--------|
| `lexagent/tools/retriever.py` | Added `PersistentQdrantRetriever` class. Collection naming: `{firm_id}_matter_{matter_id}`. Lazy-initialises `QdrantClient` and `SentenceTransformer` on first use. `index_findings()` embeds + upserts; `retrieve()` returns `[]` on any error (graceful fallback). |
| `lexagent/nodes/research.py` | After assembling `all_findings`, indexes them into Qdrant when `config.qdrant_enabled` and `state.matter_id` are set. Wrapped in try/except so Qdrant failures never crash the research node. |
| `lexagent/nodes/cite.py` | Before building `HybridRetriever`, queries Qdrant for prior-session findings (top-3 per citation). Deduplicates by citation string before merging into `findings`. |

### Key design decisions
- `qdrant_enabled = False` by default — zero overhead unless opted in via `LEX_QDRANT_ENABLED=true`.
- Embedding model: `sentence-transformers/all-MiniLM-L6-v2` (22 MB, local, no API key).
- `HybridRetriever` (BM25 + TF-IDF) is kept for offline/stub mode; Qdrant augments it rather than replacing it.
- Variable naming note: `research.py` uses `config` (not `cfg`) for `LexConfig` — the Qdrant block uses `config.qdrant_enabled`, `config.default_firm_id`, `cfg=config`.

---

## Phase 9 (8B.3): FastAPI Control Plane

**Goal:** OpenClaw-inspired single backend that all gateways (Telegram, WhatsApp, Slack, web UI) POST to instead of calling `get_graph()` directly. One Postgres checkpointer shared across all gateways — matter state is the same whether the lawyer messages via Telegram or the browser.

### Files changed
| File | Change |
|------|--------|
| `lexagent/gateway/control_plane.py` | **New file.** FastAPI app with bearer-token auth, startup checkpointer setup, REST + WebSocket endpoints, CORS middleware. |
| `lexagent/cli.py` | `lex gateway web` (aliases: `api`, `control-plane`, `server`) starts the control plane via uvicorn. |

### API surface
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/matters/{matter_id}/message` | POST | Non-streaming (WhatsApp/Slack webhooks). Blocks until graph reaches END; returns `MatterOut`. |
| `/api/v1/matters` | GET | Lists matters for tenant (stub — expand with Postgres query). |
| `/api/v1/matters/{matter_id}/documents` | POST | PDF/DOCX upload → `pdfplumber` → Qdrant index. |
| `/ws/{user_id}/{matter_id}` | WebSocket | Token-level streaming for web UI via `graph.astream_events(..., version="v2")`. |
| `/health` | GET | `{"status": "ok"}` |

### WebSocket protocol
```
Client → {"text": "matter brief..."}
Server → {"type": "token", "content": "..."}   # one per LLM token
Server → {"type": "node", "node": "research"}   # on node transitions
Server → {"type": "done", "state": {...}}        # on graph completion
Server → {"type": "error", "error": "..."}       # on exception
```

### Auth
- `api_secret_key = None` (default) → auth skipped for CLI / local dev.
- Set `LEX_API_SECRET_KEY=<token>` → bearer token required on all requests.

---

## Phase 9 (8B.4): Web UI — lexanodes/

**Goal:** Extend the existing Next.js + tRPC app with a full legal matter dashboard so lawyers can use a browser instead of Telegram.

### Files changed
| File | Change |
|------|--------|
| `lexanodes/prisma/schema.prisma` | Added `Firm`, `LexMatter`, `LawyerSoul` models. Added `matters`, `soul`, `firmId` relations to `User`. |
| `lexanodes/src/trpc/routers/matter.ts` | **New file.** `matter.list/get/create/delete`, `matter.sendMessage` (proxy to control plane), `matter.getSoul/saveSoul`. |
| `lexanodes/src/trpc/routers/_app.ts` | Added `matter: matterRouter`. |
| `lexanodes/src/trpc/routers/auth.ts` | Fixed `logout` procedure: added `.input(z.void())` to resolve tRPC v11 `useMutation` type error. |
| `lexanodes/src/app/(dashboard)/matters/page.tsx` | **New file.** Matter list dashboard with card grid, "New Matter" dialog, status badges, delete. |
| `lexanodes/src/app/(dashboard)/matters/[id]/page.tsx` | **New file.** Matter detail: WebSocket streaming chat to control plane, node-transition status breadcrumbs, draft side-panel, PDF/DOCX upload. |
| `lexanodes/src/components/layout/Sidebar.tsx` | Added "Matters" as top nav item; rebranded to "LexAgent"; fixed `useMutation` to use tRPC v11 `mutationOptions()` pattern. |

### LexMatter model
```prisma
model LexMatter {
  id           String    @id   // == LangGraph thread_id / matter_id
  firmId       String?
  userId       String
  title        String
  matterType   String?
  jurisdiction String?
  status       String    @default("active")  // "active" | "draft_ready" | "closed"
  lastActivity DateTime  @default(now())
  createdAt    DateTime  @default(now())
  updatedAt    DateTime  @updatedAt
}
```

### Web UI → Control Plane connection
The browser connects directly to the FastAPI control plane. Set `NEXT_PUBLIC_CONTROL_PLANE_URL` (default: `http://localhost:8000`).

- Streaming chat: WebSocket to `/ws/{userId}/{matterId}`
- Document upload: `fetch POST` to `/api/v1/matters/{id}/documents`
- Non-streaming fallback: `matter.sendMessage` tRPC mutation → control plane REST

### tRPC v11 API note
The existing lexanodes codebase was using the old `trpc.proc.useQuery()` / `.useMutation()` pattern which was removed in `@trpc/tanstack-react-query@11`. All new Phase 8B code uses the correct v11 pattern:
```ts
const { data } = useQuery(trpc.matter.list.queryOptions());
const mutation = useMutation(trpc.matter.create.mutationOptions({ onSuccess: ... }));
```

---

## Architecture After Phase 8B

```
┌──────────────────── Gateways ────────────────────────┐
│  Web (lexanodes/)      Telegram      [WhatsApp/Slack] │
└──────────────────────┬───────────────────────────────┘
                        │ HTTP + WebSocket
         ┌──────────────▼──────────────┐
         │  FastAPI Control Plane       │
         │  lexagent/gateway/           │
         │  control_plane.py            │
         │  port 8000 (configurable)    │
         └──────────────┬──────────────┘
                        │ async ainvoke / astream_events
         ┌──────────────▼──────────────┐
         │  LangGraph StateGraph        │
         │  + AsyncPostgresSaver        │
         │  thread_id == matter_id      │
         └───────┬──────────┬──────────┘
                 │          │
    ┌────────────▼──┐  ┌────▼──────────────────┐
    │  PostgreSQL    │  │  Qdrant Vector Store   │
    │  - LangGraph   │  │  {firm}_matter_{id}    │
    │    checkpoints │  │  - Kanoon findings     │
    │  - LexMatter   │  │  - uploaded docs       │
    │  - LawyerSoul  │  │  - cross-session RAG   │
    └───────────────┘  └────────────────────────┘
```

---

## Running Phase 8B

```bash
# Terminal 1: LexAgent control plane
cd Lexagent
LEX_QDRANT_ENABLED=true uv run lex gateway web
# → http://localhost:8000

# Terminal 2: lexanodes web UI
cd lexanodes
NEXT_PUBLIC_CONTROL_PLANE_URL=http://localhost:8000 npm run dev
# → http://localhost:3000/matters

# Telegram bot (optional, runs in parallel)
cd Lexagent
uv run lex gateway telegram
```

Environment variables:
```
# Lexagent (.env or shell)
POSTGRES_URL=postgresql://...          # LangGraph checkpointer (MemorySaver if unset)
LEX_QDRANT_ENABLED=true                # Enable Qdrant persistence
QDRANT_URL=http://localhost:6333       # Qdrant instance
LEX_API_SECRET_KEY=<token>             # Control plane bearer auth (skip if unset)

# lexanodes (.env)
DATABASE_URL=postgresql://...          # Prisma / LexMatter records
NEXT_PUBLIC_CONTROL_PLANE_URL=http://localhost:8000
```

---

## What's Next (Phases 5–7)

| Phase | Description | Key Files |
|-------|-------------|-----------|
| **5** | Gateway adapters — WhatsApp (Evolution API), Slack Events, Discord bot, Twilio voice STT/TTS | `lexagent/gateway/whatsapp.py`, `slack.py`, `discord.py`, `voice.py` |
| **6** | Proactive cron engine — morning brief (8am), hearing countdown auto-detection, background research queue, deadline radar | `lexagent/scheduler/cron_engine.py` (APScheduler already in `pyproject.toml`) |
| **7** | Multi-tenant SaaS hardening — firm registration flow, per-firm BYOK API keys, matter access control, usage tracking | `lexanodes/` firm onboarding pages, per-firm Anthropic key routing |
