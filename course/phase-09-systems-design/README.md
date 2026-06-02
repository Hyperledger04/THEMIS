# Phase 9 — Systems Design: FastAPI, Postgres, Qdrant, Multi-tenancy, Voice

> **Status: Coming soon.** Complete Phases 0-8 first.

## What you will build

By the end of this phase, you will understand the full production architecture:
- FastAPI control plane that multiple gateways POST to
- Postgres for durable LangGraph checkpoints (state survives restarts)
- Qdrant vector database for per-matter persistent embeddings
- Multi-tenant isolation (one firm's data never touches another's)
- Voice AI gateway: Twilio phone calls + browser WebSocket + STT + TTS

## The files you will understand

- `lexagent/gateway/control_plane.py` — FastAPI app, `/draft`, `/research`, `/chat` endpoints
- `lexagent/runtime/postgres.py` — Postgres connection pool, Alembic migrations
- `lexagent/tools/retriever.py` — `PersistentQdrantRetriever` (persists across sessions)
- `lexagent/security/` — JWT auth, encryption, RBAC, audit log
- `lexagent/gateway/voice.py` — WebSocket handler, Twilio webhook
- `lexagent/voice/stt.py` — speech-to-text (Whisper / Deepgram / stub)
- `lexagent/voice/tts.py` — text-to-speech (Google / ElevenLabs / stub)

## Architecture diagram

```
                     ┌──────────────┐
  Telegram ─────────►│              │
  CLI      ─────────►│  FastAPI     │────► LangGraph Graph
  Voice    ─────────►│  Control     │         │
  Web API  ─────────►│  Plane       │         ▼
                     └──────────────┘    ┌─────────────┐
                            │            │  Postgres   │ (LangGraph checkpoints)
                            │            └─────────────┘
                            │            ┌─────────────┐
                            │            │  Qdrant     │ (matter embeddings)
                            └───────────►└─────────────┘
```

## Key concepts

**FastAPI** — async HTTP framework. Each endpoint is an `async def` function.
  - Dependency injection (`Depends()`) for auth
  - Pydantic models for request/response validation
  - Background tasks for long-running graph invocations

**Qdrant** — vector database. Each matter gets its own collection.
  - `client.upsert(collection_name, points)` stores embeddings
  - `client.search(collection_name, query_vector, limit)` retrieves nearest neighbors
  - Per-matter isolation: collection named `{firm_id}_{matter_id}`

**Multi-tenancy** — `firm_id` + `user_id` in LexState.
  - Qdrant: separate collection per firm
  - Postgres: `firm_id` column on every row
  - SOUL.md: `~/.lexagent/{firm_id}/SOUL.md`

**Voice AI**:
  - Twilio: phone call → webhook → STT → graph → TTS → audio
  - WebSocket: browser mic → audio stream → STT → graph → TTS → browser speaker
  - Both use the same graph — voice is just another gateway

## Coming in this phase

1. `01_fastapi_basics.py` — async endpoints, Pydantic models, Depends
2. `02_postgres_async.py` — asyncpg, connection pools, LangGraph checkpoints
3. `03_qdrant_vectors.py` — Qdrant client, collections, upsert, search
4. `04_multi_tenancy.py` — tenant isolation patterns
5. `05_voice_gateway.py` — STT/TTS architecture, WebSocket streaming
6. `06_security.py` — JWT, RBAC, encryption, audit log
7. `exercises/ex01_add_api_endpoint.py` — add a new FastAPI endpoint
8. `exercises/ex02_add_qdrant_collection.py` — store and retrieve embeddings
