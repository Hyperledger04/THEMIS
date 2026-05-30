# LexAgent: Phases 5–7 — Hermes Agent + OpenClaw Gateways

## Context

Phases 1–4 (LangGraph checkpointer, Qdrant RAG, FastAPI control plane, web UI) are complete as of Phase 8B. The remaining work maps directly onto two open-source frameworks:

- **OpenClaw** → Phase 5: Every gateway (WhatsApp, Slack, Discord, Voice, Telegram) becomes a thin adapter that POSTs to the control plane instead of calling `get_graph()` directly. One backend, all platforms.
- **Hermes Agent Five Pillars** → Phases 6–7: SOUL (per-lawyer DB identity injected by control plane), Crons (APScheduler proactive tasks), Skills (web UI management), and multi-tenant hardening.

**Current gaps confirmed by code inspection (2026-05-20):**
- No `lexagent/scheduler/` directory; APScheduler is in `pyproject.toml` but unused
- No `whatsapp.py`, `slack.py`, `discord.py`, `voice.py` in `lexagent/gateway/`
- Telegram still calls `get_graph()` directly — not the control plane
- `SOUL` reads from `~/.lexagent/SOUL.md` file; `LawyerSoul` Prisma model exists but is not hooked up to the graph
- No `/agent` control panel page or `/settings/soul` editor in lexanodes
- `ApiKey` model exists in DB but control plane never reads it (still uses global `LexConfig` keys)
- `multi_tenant` flag in `LexConfig` — not yet enforced anywhere

---

## Phase 5: OpenClaw Gateway Adapters

**Goal:** Every platform becomes a thin HTTP adapter to the control plane. Same matter state regardless of which app the lawyer uses.

### 5A — Make Telegram a thin client

Telegram currently calls `get_graph(cfg)` directly in `telegram.py`. Change it to POST to the control plane REST endpoint instead.

**File:** `lexagent/gateway/telegram.py`
- Replace direct `get_graph()` / `graph.astream()` calls with `httpx.AsyncClient().post(f"{cp_url}/api/v1/matters/{matter_id}/message", json={"text": user_text})`
- `cp_url` reads from `LexConfig.control_plane_url` (new config field, default `http://localhost:8000`)
- Matter ID still generated from Telegram chat ID (existing `M-{hex}` format)
- Remove the `setup_checkpointer` call from Telegram startup — that's the control plane's job

**Config addition (`lexagent/config.py`):**
```python
control_plane_url: str = Field("http://localhost:8000", validation_alias=AliasChoices("LEX_CONTROL_PLANE_URL", "control_plane_url"))
```

### 5B — WhatsApp Gateway (Evolution API)

Evolution API is a self-hosted WhatsApp HTTP bridge. It sends webhooks on incoming messages and accepts REST calls to send replies.

**New file:** `lexagent/gateway/whatsapp.py`

```python
# FastAPI sub-app mounted at /webhook/whatsapp on the control plane
# OR standalone FastAPI app on port 8001

# Incoming webhook shape from Evolution API:
# POST /webhook {"event": "messages.upsert", "data": {"key": {"remoteJid": "91XXXXXXXXXX@s.whatsapp.net"}, "message": {"conversation": "..."}}}

# Flow:
# 1. Extract phone number (remoteJid stripped of @s.whatsapp.net)
# 2. Map phone → user_id via a phone_to_user dict in config or DB lookup
# 3. Generate matter_id from phone (deterministic: M-{sha256(phone)[:8]})
# 4. POST to control plane: POST /api/v1/matters/{matter_id}/message {"text": message_body}
# 5. Reply via Evolution API: POST {EVOLUTION_API_URL}/message/sendText/{instance} {"number": phone, "text": reply}
```

**Config additions:**
```python
evolution_api_url: Optional[str]     # LEX_EVOLUTION_API_URL
evolution_api_key: Optional[str]     # LEX_EVOLUTION_API_KEY  
evolution_instance: str              # LEX_EVOLUTION_INSTANCE, default "default"
whatsapp_phone_map: dict             # LEX_WHATSAPP_PHONE_MAP as JSON (phone→user_id)
```

**CLI addition:** `lex gateway whatsapp` starts this on port 8001

### 5C — Slack Gateway

**New file:** `lexagent/gateway/slack.py`
- Uses `slack-bolt` SDK with async support
- Listens for `app_mention` events and DMs
- Extracts `slack_user_id` → maps to lexanodes `user_id` via config JSON map
- Posts to control plane, replies in the same Slack thread

**Config additions:**
```python
slack_bot_token: Optional[str]      # SLACK_BOT_TOKEN
slack_app_token: Optional[str]      # SLACK_APP_TOKEN (socket mode)
slack_user_map: dict                # LEX_SLACK_USER_MAP as JSON
```

**CLI addition:** `lex gateway slack`

**pyproject.toml addition:** `slack-bolt>=1.18`

### 5D — Discord Gateway

**New file:** `lexagent/gateway/discord.py`
- Uses `discord.py` library
- Watches `#legal-matters` channel (configurable)
- `on_message` → POST to control plane → reply in same channel thread

**Config additions:**
```python
discord_bot_token: Optional[str]    # DISCORD_BOT_TOKEN
discord_channel_id: Optional[int]   # LEX_DISCORD_CHANNEL_ID
discord_user_map: dict              # LEX_DISCORD_USER_MAP as JSON
```

**CLI addition:** `lex gateway discord`

**pyproject.toml addition:** `discord.py>=2.3`

### 5E — Voice Gateway (Twilio)

**New file:** `lexagent/gateway/voice.py`
- FastAPI app handling Twilio webhook POST `/voice`
- Twilio calls → `<Gather>` TwiML to collect speech → `/voice/transcribed` receives the transcript
- Transcript → POST to control plane → TTS reply via `<Say>` TwiML

**Config additions:**
```python
twilio_account_sid: Optional[str]   # TWILIO_ACCOUNT_SID
twilio_auth_token: Optional[str]    # TWILIO_AUTH_TOKEN
twilio_phone_number: Optional[str]  # TWILIO_PHONE_NUMBER
```

**CLI addition:** `lex gateway voice`

**pyproject.toml additions:** `twilio>=9.0`, `httpx>=0.27`

### 5F — CLI changes for all gateways

**File:** `lexagent/cli.py` — extend the existing `gateway` command:
```python
elif service.lower() == "whatsapp":
    from lexagent.gateway.whatsapp import run_whatsapp_gateway
    asyncio.run(run_whatsapp_gateway(cfg))
elif service.lower() == "slack":
    from lexagent.gateway.slack import run_slack_gateway
    asyncio.run(run_slack_gateway(cfg))
elif service.lower() == "discord":
    from lexagent.gateway.discord import run_discord_gateway
    asyncio.run(run_discord_gateway(cfg))
elif service.lower() == "voice":
    from lexagent.gateway.voice import run_voice_gateway
    uvicorn.run(voice_app, host=cfg.control_plane_host, port=cfg.control_plane_port + 1)
```

### Phase 5 file summary

| File | Action |
|------|--------|
| `lexagent/gateway/telegram.py` | Refactor: POST to control plane instead of direct graph call |
| `lexagent/gateway/whatsapp.py` | New: Evolution API webhook adapter |
| `lexagent/gateway/slack.py` | New: Slack Bolt async adapter |
| `lexagent/gateway/discord.py` | New: discord.py bot adapter |
| `lexagent/gateway/voice.py` | New: Twilio STT/TTS adapter |
| `lexagent/config.py` | Add: control_plane_url, evolution_*, slack_*, discord_*, twilio_* fields |
| `lexagent/cli.py` | Extend: `lex gateway` to support whatsapp/slack/discord/voice |
| `pyproject.toml` | Add: slack-bolt>=1.18, discord.py>=2.3, twilio>=9.0, httpx>=0.27 |

---

## Phase 6: Hermes Cron Engine — Proactive Agent

**Goal:** LexAgent works while the lawyer is offline. Hermes "Crons" pillar — the agent has a heartbeat.

### New directory: `lexagent/scheduler/`

```
lexagent/scheduler/
  __init__.py
  cron_engine.py          # APScheduler setup + job registry
  tasks/
    __init__.py
    morning_brief.py      # 8am daily per-user timezone
    hearing_radar.py      # pre-hearing countdown
    research_queue.py     # background research jobs
    deadline_radar.py     # limitation period warnings
```

### `cron_engine.py`

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler()

async def start_cron_engine(cfg: LexConfig):
    # Schedule 4 recurring jobs
    scheduler.add_job(run_morning_brief, "cron", hour=8, minute=0, kwargs={"cfg": cfg})
    scheduler.add_job(run_hearing_radar, "interval", minutes=60, kwargs={"cfg": cfg})
    scheduler.add_job(run_research_queue, "interval", minutes=15, kwargs={"cfg": cfg})
    scheduler.add_job(run_deadline_radar, "cron", hour=9, minute=0, kwargs={"cfg": cfg})
    scheduler.start()
    # Keep running until interrupted
    await asyncio.Event().wait()
```

### Task: `morning_brief.py`
- Query Postgres for all `LexMatter` rows with `status="active"` (via asyncpg or the control plane's DB connection)
- For each matter, POST to control plane: `{"text": "Generate a morning brief: summarise this matter's current status, next hearings from the reminders table, and any pending research tasks."}`
- Deliver the response via the matter's `preferred_gateway` (Telegram by default)
- Runs at 8am daily

### Task: `hearing_radar.py`
- Query the existing SQLite `reminders` table from `lexagent/memory/session_store.py`
- For reminders where `fire_at <= now` and `fired = 0`, deliver notification via Telegram/WhatsApp and mark `fired = 1`
- Also scan LangGraph state snapshots for date strings in `limitation_analysis` and `research_findings` — auto-create reminders when it finds court dates
- Runs hourly

### Task: `research_queue.py`
- Query LangGraph checkpoints where `state.background_task` is set to `"research"`
- For each pending background task, invoke the research node via control plane
- Clear `background_task` from state on completion, notify lawyer
- Runs every 15 minutes

### Task: `deadline_radar.py`
- Load all active matters from Postgres
- For each, load the LangGraph state snapshot and check `limitation_analysis` for limitation period warnings
- If a deadline is within 30 days, send an alert via the lawyer's preferred gateway
- Runs daily at 9am

### CLI addition

**File:** `lexagent/cli.py`
```python
elif service.lower() in ("cron", "scheduler"):
    from lexagent.scheduler.cron_engine import start_cron_engine
    console.print("[bold cyan]⏰ LexAgent Cron Engine starting...[/bold cyan]")
    asyncio.run(start_cron_engine(cfg))
```

### Config additions (`lexagent/config.py`)
```python
morning_brief_hour: int = Field(8, ...)         # LEX_BRIEF_HOUR
cron_timezone: str = Field("Asia/Calcutta", ...) # LEX_TIMEZONE
research_queue_interval: int = Field(15, ...)    # LEX_RESEARCH_INTERVAL_MINS
deadline_warning_days: int = Field(30, ...)      # LEX_DEADLINE_WARNING_DAYS
```

### Phase 6 file summary

| File | Action |
|------|--------|
| `lexagent/scheduler/__init__.py` | New: empty init |
| `lexagent/scheduler/cron_engine.py` | New: APScheduler setup, job registry, start fn |
| `lexagent/scheduler/tasks/__init__.py` | New: empty init |
| `lexagent/scheduler/tasks/morning_brief.py` | New: 8am daily matter summary |
| `lexagent/scheduler/tasks/hearing_radar.py` | New: reminder fire + auto-detect from state |
| `lexagent/scheduler/tasks/research_queue.py` | New: background research job processor |
| `lexagent/scheduler/tasks/deadline_radar.py` | New: limitation period warning scanner |
| `lexagent/config.py` | Add: cron timing fields |
| `lexagent/cli.py` | Add: `lex gateway cron` command |

---

## Phase 7: Hermes SOUL Migration + Web UI + Multi-Tenant

**Goal:** DB-backed per-lawyer soul, SOUL editor in browser, agent control panel, per-firm BYOK key routing.

### 7A — SOUL DB Migration (Hermes SOUL pillar)

The critical gap: `LawyerSoul` Prisma model exists, `matter.getSoul/saveSoul` tRPC procedures exist, but the graph still reads from `~/.lexagent/SOUL.md`.

**File: `lexagent/memory/soul.py`** — add `load_soul_from_db`:
```python
async def load_soul_from_db(user_id: str, postgres_url: str) -> Optional[dict]:
    """
    Load the lawyer's SOUL from the LawyerSoul Postgres table.
    Falls back to SOUL.md file if no DB record exists.
    """
    import asyncpg
    conn = await asyncpg.connect(postgres_url)
    row = await conn.fetchrow("SELECT content FROM \"LawyerSoul\" WHERE \"userId\" = $1", user_id)
    await conn.close()
    if row:
        return _parse_soul(row["content"])
    return None  # caller falls back to file
```

**File: `lexagent/gateway/control_plane.py`** — inject SOUL from DB into graph state:
- In both `send_message` and `ws_endpoint`, after resolving `user_id`:
  ```python
  from lexagent.memory.soul import load_soul_from_db
  soul = None
  if cfg.postgres_url:
      soul = await load_soul_from_db(auth["user_id"], cfg.postgres_url)
  if not soul:
      from lexagent.memory.soul import load_soul
      soul = load_soul(cfg.home_dir)  # fallback to file
  state["lawyer_soul"] = soul
  ```
- This means every graph invocation now has the correct per-lawyer soul without the graph needing DB access

### 7B — SOUL Editor (lexanodes web UI)

**New file:** `lexanodes/src/app/(dashboard)/settings/soul/page.tsx`
- Client component
- `useQuery(trpc.matter.getSoul.queryOptions())` to load current soul content
- Textarea with the full SOUL.md markdown (editable directly as raw markdown)
- OR: structured form with individual fields (name, bar enrollment, practice areas, etc.) matching SOUL_TEMPLATE fields
- `useMutation(trpc.matter.saveSoul.mutationOptions())` on save
- Add "Soul" nav link to Sidebar under Settings

### 7C — Agent Control Panel (lexanodes web UI)

**New file:** `lexanodes/src/app/(dashboard)/agent/page.tsx`
- Shows 4 sections:
  1. **Cron Status**: List of active scheduled jobs (morning brief, hearing radar, etc.) with last-run times — fetched from a new `GET /api/v1/crons/status` control plane endpoint
  2. **Gateway Status**: Which gateways are configured (Telegram, WhatsApp, Slack, Discord, Voice) — green/grey dots based on whether the relevant env vars are set, fetched from `GET /health` (extend to include gateway status)
  3. **SOUL Preview**: Shows the lawyer's name and practice profile from LawyerSoul, link to `/settings/soul` to edit
  4. **Actions**: "Run morning brief now" button → POST `/api/v1/crons/morning-brief/run`, "Clear research queue" button

**New control plane endpoints** (`lexagent/gateway/control_plane.py`):
```python
@app.get("/api/v1/crons/status")       # Returns scheduled jobs + last run times
@app.post("/api/v1/crons/{task}/run")  # Manually trigger a cron task
```

**Extend `/health`** to include gateway status:
```json
{"status": "ok", "gateways": {"telegram": true, "whatsapp": false, "slack": false}}
```

**Add to Sidebar** (`lexanodes/src/components/layout/Sidebar.tsx`): `{ name: "Agent", href: "/agent", icon: Bot }`

### 7D — Per-Firm BYOK API Key Routing

`ApiKey` model already in DB with `provider` and `key` fields. The control plane currently uses global `LexConfig` keys.

**File:** `lexagent/gateway/control_plane.py` — add `_get_user_api_key(user_id, provider, db_url)`:
```python
async def _get_user_api_key(user_id: str, provider: str, postgres_url: str) -> Optional[str]:
    import asyncpg
    conn = await asyncpg.connect(postgres_url)
    row = await conn.fetchrow(
        'SELECT key FROM "ApiKey" WHERE "userId"=$1 AND provider=$2 AND "isDefault"=true',
        user_id, provider
    )
    await conn.close()
    return row["key"] if row else None
```

Then in `send_message` and `ws_endpoint`:
```python
if cfg.postgres_url and cfg.multi_tenant:
    user_key = await _get_user_api_key(auth["user_id"], cfg.model_provider, cfg.postgres_url)
    if user_key:
        cfg = cfg.model_copy(update={"anthropic_api_key": user_key})
```

This means each firm/user brings their own Anthropic key — stored in lexanodes, used by the Python control plane.

### 7E — Firm Registration Page

**New file:** `lexanodes/src/app/(dashboard)/settings/firm/page.tsx`
- Shows current firm name and ID
- Form to create a firm (if none) or update firm name
- Backed by new tRPC `firm.get` / `firm.create` / `firm.update` procedures

**New tRPC router:** `lexanodes/src/trpc/routers/firm.ts`
```ts
export const firmRouter = createTRPCRouter({
  get: protectedProcedure.query(async ({ ctx }) => 
    prisma.firm.findFirst({ where: { users: { some: { id: ctx.user.id } } } })
  ),
  create: protectedProcedure.input(z.object({ name: z.string() })).mutation(...),
  update: protectedProcedure.input(z.object({ name: z.string() })).mutation(...),
});
```

Add `firm: firmRouter` to `_app.ts`.

### 7F — Sidebar navigation update

**File:** `lexanodes/src/components/layout/Sidebar.tsx`
```ts
const navigation = [
  { name: "Matters", href: "/matters", icon: Scale },
  { name: "Agent", href: "/agent", icon: Bot },        // new
  { name: "My Agents", href: "/agents", icon: Users },
  { name: "Explore", href: "/explore", icon: Search },
  { name: "API Keys", href: "/settings/api-keys", icon: Key },
  { name: "Soul", href: "/settings/soul", icon: User },  // new
  { name: "Firm", href: "/settings/firm", icon: Building }, // new
];
```

### Phase 7 file summary

| File | Action |
|------|--------|
| `lexagent/memory/soul.py` | Add `load_soul_from_db(user_id, postgres_url)` async function |
| `lexagent/gateway/control_plane.py` | Inject DB soul into state; add BYOK key lookup; add cron status endpoints; extend /health |
| `lexanodes/src/app/(dashboard)/settings/soul/page.tsx` | New: SOUL markdown editor |
| `lexanodes/src/app/(dashboard)/agent/page.tsx` | New: cron status + gateway status + soul preview + manual trigger |
| `lexanodes/src/app/(dashboard)/settings/firm/page.tsx` | New: firm registration/edit |
| `lexanodes/src/trpc/routers/firm.ts` | New: firm.get/create/update |
| `lexanodes/src/trpc/routers/_app.ts` | Add `firm: firmRouter` |
| `lexanodes/src/components/layout/Sidebar.tsx` | Add Agent, Soul, Firm nav items |

---

## Architecture After Phases 5–7

```
┌─────────────────────── Gateways ──────────────────────────────┐
│  Web (lexanodes/)  Telegram  WhatsApp  Slack  Discord  Voice   │
│  (all thin adapters — POST to control plane)                   │
└───────────────────────────┬───────────────────────────────────┘
                             │ HTTP + WebSocket
             ┌───────────────▼───────────────┐
             │  FastAPI Control Plane         │
             │  - Bearer auth                 │
             │  - SOUL injection from DB      │
             │  - BYOK API key routing        │
             │  - Cron status endpoints       │
             └───────────────┬───────────────┘
                             │ ainvoke / astream_events
             ┌───────────────▼───────────────┐
             │  LangGraph + AsyncPostgresSaver│
             │  thread_id == matter_id        │
             └────────┬──────────────────────┘
                      │
     ┌────────────────┼────────────────────┐
     │                │                    │
┌────▼──────┐  ┌──────▼──────┐  ┌────────▼──────┐
│ PostgreSQL │  │   Qdrant    │  │ APScheduler   │
│ LangGraph  │  │ per-matter  │  │ Cron Engine   │
│ LexMatter  │  │ RAG         │  │ - morning     │
│ LawyerSoul │  │             │  │ - hearings    │
│ ApiKey     │  │             │  │ - research Q  │
│ Firm       │  │             │  │ - deadlines   │
└────────────┘  └─────────────┘  └───────────────┘
```

---

## Build Order

1. **Phase 5A** (Telegram → control plane) — 30 min. Highest value: unifies all future gateways immediately.
2. **Phase 5B** (WhatsApp/Evolution API) — 2 hrs. Most requested gateway for Indian lawyers.
3. **Phase 6** (Cron engine) — 3 hrs. Core Hermes pillar.  
4. **Phase 7A+B** (SOUL DB migration + web editor) — 2 hrs. Hermes SOUL pillar complete.
5. **Phase 7C** (Agent control panel) — 2 hrs. Operational visibility.
6. **Phase 7D** (BYOK key routing) — 1 hr. Required for multi-tenant.
7. **Phase 5C/D/E** (Slack/Discord/Voice) — 1–2 hrs each.
8. **Phase 7E** (Firm registration) — 1 hr.

---

## Verification Checklist

- Phase 5A: Send a Telegram message → see control plane log `"Graph invocation for matter M-XXXX"` → receive reply. Confirm Telegram no longer calls `get_graph()` directly.
- Phase 5B: Send WhatsApp message to Evolution API instance → reply arrives on phone.
- Phase 6: `lex gateway cron` starts without error. Wait until next minute with `morning_brief_hour` set to current time → Telegram receives a morning brief message.
- Phase 7A: Set `LEX_MULTI_TENANT=true`, create a LawyerSoul row in DB → control plane injects that soul into graph → draft output includes lawyer's name from DB.
- Phase 7B: Navigate to `http://localhost:3000/settings/soul` → edit soul fields → save → verify in DB with `SELECT content FROM "LawyerSoul"`.
- Phase 7C: Navigate to `http://localhost:3000/agent` → see gateway status dots → click "Run morning brief now" → Telegram receives brief.
- Phase 7D: Add Anthropic key via API Keys page → send a message → control plane log shows `"Using per-user API key for user X"`.
