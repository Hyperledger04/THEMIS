# Phase 8 — Complete Reference

**Status: COMPLETE**
**Test suite: 279 tests passing**
**Last completed node: Phase 8 (Track 2 — Hearing + Deadline Intelligence)**

Phase 8 had two parallel tracks. Track 1 (UX Overhaul) shipped first and focused on making the
Telegram bot production-ready for lawyers. Track 2 (Hearing + Deadline Intelligence) shipped
second and added criminal-stage awareness, reminder scheduling, court fee calculation, and a
filing checklist skill.

---

## Overview

| Track | Theme | Key deliverable |
|-------|-------|-----------------|
| Track 1 | UX Overhaul | Inline keyboards, session persistence, setup wizard, .docx auto-delivery, post-draft actions |
| Track 2 | Hearing + Deadline Intelligence | Litigation-stage intake, SQLite reminder scheduler, court fee calculator, filing checklist skill |

---

## Track 1 — UX Overhaul

### 1. Data-driven adaptive intake

**File:** `lexagent/data/intake_questions.yaml`

Replaced the LLM-guessing approach with a structured YAML question bank. The bank has one entry
per matter type. Each entry has `required` and `optional` question lists. Every question is a
structured object:

```yaml
- field: litigation_stage
  label: "What stage has the case reached?"
  type: mcq
  options:
    - "FIR just registered — chargesheet not filed"
    - "Chargesheet filed — cognizance not yet taken"
    - "Cognizance taken — trial ongoing"
    - "Conviction — filing appeal"
  mandatory: true
```

Question types: `open` | `binary` | `mcq`. The `binary` type always resolves to Yes/No buttons
in Telegram; `mcq` gets one button per option; `open` gets a free-text message.

**Matter types covered:** `writ_petition`, `plaint`, `injunction`, `legal_notice`,
`bail_application`, `written_statement`, `contract_review`, `affidavit`, `criminal_revision`
(Track 2 addition).

`lexagent/nodes/intake.py` was fully rewritten. Key functions:

- `_load_question_bank()` — loads the YAML on each intake invocation (no caching, so edits are live)
- `_resolve_matter_key(matter_type)` — maps free-text matter type strings to a bank key
- `_get_unanswered_questions(questions, state)` — returns questions whose `field` has no value in state
- `_build_question_bank_prompt(...)` — builds the bank section of the system prompt with answered/unanswered summary
- `_build_system_prompt(...)` — wraps the bank section into the full intake system prompt
- `_matter_type_complete(state)` — checks all `required` questions for the detected matter type are answered

The LLM returns structured JSON with a `clarifying_questions` array containing typed question
objects. The node sets `pending_questions` (typed objects for Telegram) and `clarifying_questions`
(plain text strings for the CLI).

### 2. Telegram inline keyboards

**File:** `lexagent/gateway/telegram.py`

`InlineKeyboardMarkup` and `CallbackQueryHandler` added to `python-telegram-bot`. The session
object (`TelegramSession`) holds a `pending_questions` queue. The bot pops and sends one question
per message:

- `binary` questions get two buttons: `[Yes ✓]` `[No ✗]`
- `mcq` questions get one button per option
- `open` questions get a plain text message (no buttons)

Callback data format: `ans:{field}:{value}`. The handler writes the answer into the session state
and pops the next question.

### 3. Session persistence

**File:** `lexagent/memory/session_store.py`

`update_session()` (upsert) is called after every graph node turn, not only on completion. This
means in-progress matters survive a bot restart.

`_get_or_create_session()` in the gateway restores session state from SQLite when a user resumes
a conversation after a restart.

Telegram commands added:
- `/resume` — shows the last 5 matters as inline `[Resume]` buttons
- `/matters [query]` — full-text search over all saved matters using FTS5

### 4. Agentic tool routing

**Files:** `lexagent/gateway/telegram.py`, `lexagent/nodes/research.py`

Before the research node runs, the bot sends an inline keyboard:

```
[IndianKanoon]  [Skip research]
```

The user's selection is stored as `state["approved_tools"]`. The research node checks
`approved_tools` before calling any tool. An empty list means "user chose skip".

If IndianKanoon returns zero results, the bot sends an eCourts nudge message suggesting the
lawyer check eCourts directly.

### 5. Automatic .docx delivery

**Files:** `lexagent/gateway/telegram.py`, `lexagent/state.py`

`state["docx_path"]` is set in the graph before invocation (or by the review node). After the
graph completes and `docx_path` is set, the bot calls:

```python
await message.reply_document(document=f, filename=fname, caption="📄 Your court-ready document")
```

Filename format: `{matter_type}_{matter_id}.docx`.

### 6. Post-draft action menu

**Files:** `lexagent/gateway/telegram.py`, `lexagent/gateway/integrations.py`

After .docx delivery the bot sends an inline action menu:

```
[📧 Send by email]  [💾 Upload to Drive]
[🔍 eCourts lookup] [↩ Redraft]
[👤 Forward for review] [🔏 DocuSign]*
```

*DocuSign button shown only when `matter_type` contains "contract".

Each button triggers `_handle_post_draft_action()`. Actions that require further input (email
recipient, forward recipient, DocuSign recipient) set `session.awaiting_post_draft_input` and
wait for the next text message.

`lexagent/gateway/integrations.py` contains the actual action functions. Gmail, Google Drive, and
DocuSign are stubs that raise `NotImplementedError`. All stubs produce a user-facing message:
"⚙️ Not configured yet — use /setup". `lookup_ecourts` and `forward_draft` are functional.

### 7. In-Telegram setup wizard

**File:** `lexagent/gateway/setup_wizard.py`

Triggered by `/setup`. Five-step sequential wizard:

| Step | Key | Type | Notes |
|------|-----|------|-------|
| 1 | `name` | open | Written to SOUL.md |
| 2 | `bar_number` | open (optional) | Skip button shown |
| 3 | `primary_court` | mcq | Delhi HC / Bombay HC / Madras HC / SC / Other |
| 4 | `api_keys` | multi_action | Indian Kanoon / OpenAI / Anthropic; message deleted on receipt |
| 5 | `mcp_tools` | multi_action | eCourts MCP / Gmail MCP / Google Drive / All |

API key messages are deleted immediately via `await message.delete()` so they do not remain in
Telegram chat history. On completion, `_finish_wizard()` writes `~/.lexagent/SOUL.md` and appends
API key variables to `.env`.

Session state fields: `session.in_setup`, `session.setup_step`, `session.setup_data`.

### 8. Skill and progress visibility

**Files:** `lexagent/nodes/intake.py`, `lexagent/data/loading_messages.yaml`

When `intake.py` loads a skill it sets `state["active_skill_name"]` (e.g. `"Civil Litigation"`).
The Telegram gateway emits this as a visible message: `📚 Loaded: Civil Litigation skill`.

`lexagent/data/loading_messages.yaml` defines contextual progress message pools per graph node
(`intake`, `research`, `draft`, `cite`, `review`, `contract_review`, `skill_loaded`,
`kanoon_results`, `limitation`). Messages support `{placeholder}` substitution from state fields.
A random message is selected from each pool per invocation.

---

## Track 2 — Hearing + Deadline Intelligence

### 1. Litigation stage field

**File:** `lexagent/state.py`

Two new fields added to `LexState`:

```python
litigation_stage: Optional[str]   # "fir" | "charge_sheet" | "cognizance" | "trial" | "appeal"
hearing_date: Optional[str]       # ISO date or free-text (e.g. "2026-08-15")
```

`litigation_stage` drives document selection (e.g., anticipatory bail at FIR stage vs. default
bail under S.167 when chargesheet deadline passes) and applies the correct court fee row.

### 2. Stage-aware intake questions

**File:** `lexagent/data/intake_questions.yaml`

- `bail_application` — `litigation_stage` is a required MCQ: FIR / chargesheet / cognizance / conviction-appeal.
- `bail_application` — `hearing_date` added as an optional field.
- `writ_petition` — `hearing_date` added as an optional field.
- `criminal_revision` — new matter type added with 7 required + 4 optional questions. Required fields: `parties`, `jurisdiction`, `litigation_stage`, `offence_section`, `purpose`, `relief_sought`, `cause_of_action_date`. Optional: `hearing_date`, `previous_orders`, `urgency`, `citations_required`.

### 3. Reminders table and CRUD

**File:** `lexagent/memory/session_store.py`

New `reminders` table in `sessions.db`:

```sql
CREATE TABLE IF NOT EXISTS reminders (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    matter_id        TEXT NOT NULL,
    telegram_user_id TEXT,
    hearing_date     TEXT NOT NULL,
    note             TEXT,
    days_before      INTEGER NOT NULL DEFAULT 1,
    fire_at          TEXT NOT NULL,
    fired            INTEGER NOT NULL DEFAULT 0,
    created_at       TEXT NOT NULL
);
```

`fire_at` is computed as `hearing_date − days_before` at 09:00.

Five CRUD functions added:

| Function | Purpose |
|----------|---------|
| `add_reminder(matter_id, hearing_date, note, days_before, telegram_user_id)` | Insert row; compute `fire_at`; return row ID |
| `list_reminders(matter_id, include_fired)` | List reminders filtered by matter and fired status |
| `delete_reminder(reminder_id)` | Delete by ID; returns bool |
| `get_due_reminders()` | Return all unfired rows where `fire_at <= now` |
| `mark_reminder_fired(reminder_id)` | Set `fired = 1` |

### 4. Reminder scheduler

**File:** `lexagent/scheduler/reminders.py`

Uses `python-telegram-bot`'s built-in `JobQueue` (APScheduler backend). The JobQueue is
ephemeral — jobs are lost on process restart. The persistence strategy is: store all reminders
in SQLite as the source of truth; re-register with the job queue on every bot startup.

Key functions:

- `schedule_pending_reminders(app, sessions_db, matters_dir)` — called at bot startup; reads all
  unfired reminders from SQLite and registers a `run_once` job for each. Returns the count
  scheduled. Reminders already past their `fire_at` are scheduled for 1 second from now.

- `add_reminder_and_schedule(app, ...)` — atomic: inserts into SQLite AND registers with the
  running job queue immediately. Use this from the live Telegram bot so there is no need to restart.

- `_fire_reminder(context)` — the APScheduler job callback. Sends the Telegram message, then
  calls `mark_reminder_fired()`. Injects the last 500 characters of the matter's `MEMORY.md` as
  context.

Reminder message format:
```
⏰ Hearing reminder — 2026-08-15
Matter: `M-ABCD1234`
Note: Delhi HC hearing
Recent context from matter memory:
```...last 500 chars of MEMORY.md...```
Use /matters to view the full matter file.
```

### 5. CLI reminder commands

**File:** `lexagent/cli.py`

Three subcommands under `lex reminder`:

```bash
lex reminder add --matter-id M001 --date 2026-08-15 --note "HC hearing" [--days-before 2]
lex reminder list [--matter-id M001] [--all]
lex reminder delete <id>
```

`reminder_app` is a `typer.Typer()` sub-application attached to `app` via `app.add_typer()`.
Output uses `rich` tables and panels consistently with the rest of the CLI.

### 6. Telegram reminder delivery

**File:** `lexagent/gateway/telegram.py`

Two Telegram commands added:

- `/reminder <matter_id> <YYYY-MM-DD> [note text]` — calls `add_reminder_and_schedule()` to
  insert into SQLite and register with the job queue atomically.
- `/reminders` — lists the current user's pending reminders (filtered by `telegram_user_id`).

Bot startup sequence:
```python
from lexagent.scheduler.reminders import schedule_pending_reminders
n = schedule_pending_reminders(app, sessions_db=cfg.sessions_db, matters_dir=cfg.matters_dir)
```

### 7. Court fee calculator

**Files:** `lexagent/tools/court_fees.py`, `lexagent/data/court_fees.yaml`

Registered as the `calculate_court_fee` tool via `@ToolRegistry.register(...)`. YAML-backed so
lawyers can update the fee schedule without touching Python.

`court_fees.yaml` covers 15+ matter types including civil suit (ad valorem, 10% up to ₹75,000),
writ petition (HC/SC fixed), bail (nominal ₹10–50), injunction (₹50–200), execution petition
(ad valorem 50%), appeal, revision, legal notice (nil), consumer complaint (District/State/National
Commission tiers), NI Act 138, divorce, plaint, written statement, affidavit, contract review,
and SLP.

Ad valorem computation for civil suits: when `suit_value` is provided and the fee description
contains "ad valorem", the tool applies the 10%-up-to-₹75,000 Delhi formula automatically:

```python
estimated_fee = min(suit_value * 0.10, 75_000)
```

Returns: `matter_type`, `fee_description`, `statutory_basis`, `notes`, `suit_value`, `disclaimer`.

Fallback: if `court_fees.yaml` is absent or unparseable, a hardcoded Python dict is used so the
tool never fails.

### 8. Filing checklist skill

**File:** `lexagent/skills/filing_checklist.md`

Skill YAML frontmatter:
```yaml
name: Filing Checklist
trigger_keywords:
  - checklist
  - filing checklist
  - what to file
  - documents required
  - court filing
  - procedural compliance
  - what do I need to file
  - how to file
  - next steps after draft
matter_types:
  - writ petition, plaint, injunction, bail application,
    written statement, legal notice, criminal revision, affidavit
```

The skill instructs the agent to append a **Pre-Filing Checklist** section after every draft.
Checklist sections are conditional on `matter_type`:

- Universal: court copies, vakalatnama, court fee receipt, index of documents, affidavit verifying pleadings
- Writ: impugned order copy, alternative remedy proof, previous orders
- Plaint: documentary evidence, valuation certificate, limitation affidavit
- Injunction: I.A. affidavit, prima facie evidence, proposed draft order (ex-parte)
- Bail: FIR copy, chargesheet, remand orders, surety documents, accused background affidavit
- Legal notice: postal tracking receipt, proof of delivery
- Written statement: plaint copy, defence documents, counterclaim (Order VIII Rule 6A)
- Affidavit: non-judicial stamp paper, notarisation, exhibits

Includes a **Procedural Deadlines** reference table:

| Document | Deadline |
|----------|---------|
| Written Statement | 30 days from summons (max 90 days, Order VIII Rule 1 CPC) |
| Default bail (S.167 CrPC) | 60 days (non-serious) / 90 days (serious) if no chargesheet |
| First Appeal | 30 days (Order XLII CPC); 90 days to High Court |
| Writ Petition | No fixed period — laches after ~3 years |
| Consumer Complaint | 2 years from cause of action (S.69 CP Act 2019) |
| Revision | 90 days from impugned order (S.115 CPC; S.397 CrPC) |

---

## New Files

| File | Purpose |
|------|---------|
| `lexagent/data/intake_questions.yaml` | Per-matter-type structured question banks (9 matter types) |
| `lexagent/data/loading_messages.yaml` | Contextual progress message pools per graph node |
| `lexagent/data/court_fees.yaml` | YAML court fee schedule covering 15+ matter types |
| `lexagent/gateway/setup_wizard.py` | In-Telegram 5-step setup wizard; writes SOUL.md and .env |
| `lexagent/gateway/integrations.py` | Post-draft action functions (Gmail, Drive, eCourts, forward, DocuSign) |
| `lexagent/scheduler/__init__.py` | Package init for the scheduler module |
| `lexagent/scheduler/reminders.py` | Hearing reminder scheduler using python-telegram-bot JobQueue |
| `lexagent/tools/court_fees.py` | `calculate_court_fee` tool; YAML-backed; ad valorem computation |
| `lexagent/skills/filing_checklist.md` | Filing checklist skill with court-specific document lists |

---

## Modified Files

| File | Key changes |
|------|------------|
| `lexagent/state.py` | +17 fields: `pending_questions`, `active_skill_name`, `approved_tools`, `pending_action`, `litigation_stage`, `hearing_date`, `telegram_user_id`, plus 10 deep intake fields (`fundamental_right`, `article_invoked`, `cause_of_action_date`, `relief_sought`, `alternative_remedy`, `urgency`, `previous_orders`, `plaint_valuation`, `limitation_applicable`, `notice_period`, `bail_type`, `offence_section`, `custody_duration`) |
| `lexagent/nodes/intake.py` | Full rewrite: question bank loading, `_resolve_matter_key`, `_get_unanswered_questions`, `_matter_type_complete`, `active_skill_name` emission, structured `pending_questions` output |
| `lexagent/nodes/research.py` | `approved_tools` gate: skip research if empty list; eCourts nudge on zero Kanoon results |
| `lexagent/memory/session_store.py` | `update_session()` upsert (called per turn); `reminders` table DDL; 5 reminder CRUD functions |
| `lexagent/gateway/telegram.py` | Inline keyboards (`InlineKeyboardMarkup`, `CallbackQueryHandler`); pending question queue; session persistence and `/resume` command; tool routing buttons; post-draft action menu (`_make_post_draft_keyboard`, `_handle_post_draft_action`); .docx `reply_document`; setup wizard wiring; `/reminder` and `/reminders` commands; `schedule_pending_reminders()` on startup |
| `lexagent/cli.py` | `reminder_app` sub-typer; `reminder add`, `reminder list`, `reminder delete` commands |
| `lexagent/data/intake_questions.yaml` | `litigation_stage` MCQ in `bail_application`; `hearing_date` optional in `writ_petition` and `bail_application`; new `criminal_revision` matter type (7 required + 4 optional) |

---

## Test Status

**279 tests passing.**

`tests/test_kanoon.py` is excluded from CI runs — it performs live scraping against Indian Kanoon
and the DOM structure changed after Phase 8 shipped. It pre-dates Phase 8 and is not a regression.

Test files relevant to Phase 8:
- `tests/test_state.py` — LexState field coverage including all Phase 8 additions
- `tests/test_skills.py` — skill loader and filing checklist skill trigger matching
- `tests/test_telegram_gateway.py` — inline keyboard rendering, session persistence, reminder commands
- `tests/test_registry.py` — `calculate_court_fee` tool registration and ad valorem computation
- `tests/test_memory.py` — `add_reminder`, `list_reminders`, `delete_reminder`, `mark_reminder_fired`

---

## Architecture Notes for Phase 9

### Session persistence pattern

`update_session()` is an upsert keyed on `matter_id`. It is called from the Telegram gateway
after every graph node completes, not just at the end of the session. This guarantees in-progress
matters can be resumed after a bot restart. The call site is inside the gateway, not inside the
graph nodes — nodes stay stateless.

### Reminder persistence pattern

SQLite is the source of truth. The JobQueue is a runtime cache. On every bot startup,
`schedule_pending_reminders()` replays all unfired SQLite rows into the job queue. When a new
reminder is added while the bot is running, `add_reminder_and_schedule()` writes to SQLite AND
registers the job queue entry in a single call. This avoids the race condition where a crash
between the two writes would lose the job.

### Integration stubs

`lexagent/gateway/integrations.py` contains five action functions. `send_draft_email`,
`upload_to_drive`, and `send_docusign` all raise `NotImplementedError`. The Telegram gateway
catches this and sends "⚙️ Not configured yet — use /setup". The stubs have clear docstrings
explaining the MCP tool to wire in. `forward_draft` and `lookup_ecourts` are functional.

### Court fee tool

The tool reads `court_fees.yaml` on every call (no module-level caching) so fee schedule edits
are live immediately without a restart. If the YAML file is absent, missing, or unparseable, the
function silently falls back to the hardcoded `_FALLBACK_FEES` dict so the tool never raises.

---

## What to Build in Phase 9

### MCP wiring (highest priority)
- Wire `send_draft_email` in `integrations.py` to `mcp__claude_ai_Gmail__create_draft`
- Wire `upload_to_drive` to `mcp__claude_ai_Google_Drive__create_file`
- Wire `send_docusign` to DocuSign MCP when available (add `DOCUSIGN_API_KEY` to config)
- Wire `lookup_ecourts` to `mcp__claude_ai_E-courts__search_cases` (config guard already present via `cfg.ecourts_backend`)

### Litigation stage tracker
- Add a `stage_router` node (or conditional edge) that reads `litigation_stage` from state and suggests the next document to draft (e.g., default bail application when `stage == "fir"` and custody > 60 days)
- Skill files should declare `litigation_stages` in YAML frontmatter to allow auto-selection

### Limitation deadline surface
- The `review` node should inject a `limitation_deadline_warning` into the draft preamble when `limitation_analysis` flags a risk — currently limitation analysis is computed but not surfaced in the final document

### Court fee auto-injection
- Call `calculate_court_fee(matter_type, suit_value)` in the draft node and inject the result into the document preamble so lawyers see the fee estimate inline without having to ask separately

### Procedural next-step detection
- Parse the filing checklist skill output to produce a structured `next_steps` list in state
- Surface `next_steps` in the Telegram post-draft menu so the lawyer sees "next: serve copies" as a menu item, not just a text block
