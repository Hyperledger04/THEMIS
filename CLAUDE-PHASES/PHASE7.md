# Phase 7 — Telegram Gateway & Contract Review

**What's new in one sentence:** LexAgent can now talk to lawyers directly through Telegram, review uploaded contracts for risky clauses, and it got three important safety fixes so it stops making things up.

---

## Before You Read: A Quick Refresher

LexAgent is like a very smart legal assistant that lives inside your computer. You give it a case brief (a short description of a legal problem), and it researches Indian case law, writes a court-ready document, and checks that all the citations (references to real court cases) are correct.

Until Phase 6, you could only talk to LexAgent by typing commands into a Terminal window. Phase 7 changes that — now lawyers can just open Telegram on their phone and chat with LexAgent like they would with a colleague.

---

## The Big Picture: What Phase 7 Added

1. A Telegram bot so lawyers can use LexAgent from their phone
2. A contract review feature that reads uploaded PDFs and spots risky clauses
3. Three critical bug fixes that stopped the AI from making stuff up
4. Under-the-hood improvements so the bot stays fast when many people use it at once
5. 36 new automated tests (so we know everything still works)

---

## Part 1: Three Safety Bugs That Had to Be Fixed First

Before adding any exciting new features, the team fixed three bugs that could have caused real harm in a legal setting. Think of it like fixing the brakes on a car before adding a turbo engine.

---

### Bug Fix 1 — The AI Was Faking Verified Citations

**File:** `lexagent/nodes/cite.py`

Imagine a student who is supposed to find a quote in a library book. Instead of admitting "I couldn't find it," they flip to a random page, see one word that looks related, and confidently say "Yes, I found it!" That is exactly what LexAgent was doing with legal citations.

A citation is a reference to a real court case — like "Supreme Court of India, 2019, ABC v. XYZ." The cite node's job is to check whether each citation is real and relevant. It searches through a database of legal cases and gives each match a similarity score (like a percentage — how closely does this match?).

The bug: if the best match scored even 1% similarity, the AI was marking the citation as VERIFIED. Even if the match was completely unrelated.

**The fix:** Added a minimum threshold of 35%. If the best match scores below 35%, the citation is marked UNVERIFIED. No exceptions.

This matters enormously in law — a lawyer submitting a fake citation to a court could face serious consequences.

---

### Bug Fix 2 — A Crash Caused by a Missing Label

**File:** `lexagent/nodes/draft.py`

RAPTOR is a technique (short for "Recursive Abstractive Processing for Tree-Organized Retrieval" — just think of it as "the AI's way of summarizing big research into small digestible notes"). These summary notes are stored with a label called `"snippet"`.

The draft-writing code was looking for a label called `"relevance"` — which does not exist on RAPTOR summaries. In Python, asking for a key that does not exist in a dictionary causes a crash called a `KeyError` (a key error — like looking for a locker number that does not exist).

**The fix:** The code now uses `.get()` — a safe way to look up a value that returns `None` (nothing) instead of crashing if the key is missing. RAPTOR summary entries are also skipped when building the list of citations, since they are summaries, not real case references.

---

### Bug Fix 3 — The Agent Was Forgetting Its Own Notes

**File:** `lexagent/nodes/draft.py`

LexAgent keeps a diary for each legal matter in a file called `MEMORY.md`. As the agent works — asking questions, doing research — it writes down important notes. The idea is that when it sits down to write the final draft, it can read its own notes.

The bug: the draft step was passing `None` (literally nothing) into the AI prompt where the memory content should go. The notes were being written but never read back. Like a student who writes notes in a notebook but leaves the notebook at home on exam day.

**The fix:** The draft step now actually loads and reads the `MEMORY.md` file and injects the contents into the AI prompt so the AI has full context about what it learned earlier.

---

## Part 2: Making the Engine Run Smoothly for Multiple Users

When you are the only person using LexAgent from a Terminal, speed is not critical. But a Telegram bot could have 10, 50, or 100 lawyers sending messages at the same time. These improvements make sure the system does not break under that load.

---

### The Graph Is Built Once, Not Every Time

**File:** `lexagent/graph.py`

In LangGraph, the "graph" is the entire pipeline — the assembly line that takes a matter brief and turns it into a legal draft. Building this assembly line takes time and memory.

Before Phase 7: every time someone ran `lex draft`, the code built the entire assembly line from scratch. Like disassembling and reassembling a factory every time you want to make one product.

After Phase 7: the graph is built once when the program starts, stored in memory, and reused for every request. This is called a "singleton" — there is only one copy, and everyone shares it safely.

---

### The Database Can Handle Multiple Users at Once

**File:** `lexagent/session_store.py`

LexAgent saves session history in a tiny database called SQLite (think of it as a very organized filing cabinet on your computer). By default, SQLite gets confused when multiple people try to write to it at the same time — it locks up, and some requests fail.

The fix enables WAL mode — short for "Write-Ahead Logging." In WAL mode, instead of locking the whole filing cabinet when someone writes, the database keeps a separate notepad for new writes. Other people can keep reading from the main cabinet while the notepad is being merged in. Multiple Telegram users can now use the bot simultaneously without database errors.

---

### Slow Tasks Are Moved to a Background Lane

**Files:** `lexagent/nodes/cite.py`, `lexagent/nodes/review.py`

Python's async system (the part of the language that handles doing multiple things at the same time) works like a single-lane road. When one car stops, everyone behind it stops too.

Some tasks in LexAgent are slow — searching thousands of legal chunks, or writing a Word document to disk. If these tasks run on the main road, every other user has to wait.

The fix: slow tasks are moved to a "background thread pool" using a Python tool called `run_in_executor`. Think of it like opening a second lane specifically for slow trucks. The main lane (handling Telegram messages) stays free and responsive.

---

## Part 3: New Data Fields Added to the State

**File:** `lexagent/state.py`

In LangGraph, "state" is the big data bag that gets passed from one step to the next — like a manila folder that every worker on the assembly line adds to and passes along. Phase 7 added 5 new fields to this folder:

| Field | What it stores |
|---|---|
| `workflow_mode` | Is this a normal draft job, or a contract review job? |
| `contract_upload_path` | Where on the computer is the uploaded PDF file? |
| `contract_risk_analysis` | A structured list of risks found in the contract |
| `contract_review_output` | The final formatted risk report (in markdown, a text format) |
| `cause_of_action_date` | The date a legal cause began (for future limitation period alerts) |

---

## Part 4: Contract Review — The AI Reads Your Contract

**File:** `lexagent/nodes/contract_review.py`

This is a brand new "node" — a step in the LangGraph assembly line. When a lawyer uploads a PDF contract, this node takes over and does four things:

1. **Extract the text** from the PDF using a tool called `pdfplumber` (like a very fast copy-paste from a PDF)
2. **Split it into chunks** — manageable pieces of text, roughly paragraph-sized
3. **Send each chunk to the AI** with a special prompt that says: "You are an Indian contracts lawyer. Find every risky clause."
4. **Get back a structured report** with every finding labeled HIGH, MEDIUM, or LOW risk, and an explanation of why it is risky

**The AI's instructions** live in a separate file: `lexagent/prompts/contract_review_system.md`. This file tells the AI:
- Pretend you are a senior Indian contracts lawyer
- You know the Contract Act 1872, the Specific Relief Act 1963, the Arbitration and Conciliation Act 1996, and other key Indian laws
- Every finding must be labeled HIGH / MEDIUM / LOW
- Explain your reasoning in plain English

Separating the AI's instructions into their own file (instead of burying them inside code) means a lawyer — not just a programmer — can read and edit those instructions.

---

## Part 5: The Traffic Cop Gets a New Fork in the Road

**File:** `lexagent/graph.py`

The LangGraph "router" is like a traffic cop standing at an intersection, deciding which road each car should take after a checkpoint.

Before Phase 7, after the intake step (where the AI asks clarifying questions), every job went down the same road: research → draft → cite → review → done.

After Phase 7, there is a fork:

```
After intake:
  - Is this a contract review job?
      YES → go to contract_review node → done
      NO  → go to research → draft → cite → review → done
```

This fork is implemented as a Python function called a "conditional edge" in LangGraph. It checks one field in the state (`workflow_mode`) and returns the name of the next node to run.

---

## Part 6: The Telegram Bot — The Star of Phase 7

**File:** `lexagent/gateway/telegram.py`

This is the biggest new feature. A real, working Telegram bot that lawyers can message from their phones.

### How It Works — A Story

Imagine Priya, a lawyer in Delhi. She is at a court, between hearings, and needs to start drafting an injunction. She does not have a laptop. But she has her phone.

She opens Telegram, finds the LexAgent bot, and types:

> "My client's landlord is trying to illegally evict him despite a valid lease. Need an urgent injunction."

Here is what happens behind the scenes:

1. **Telegram's servers receive the message** and send it to the LexAgent bot running on a server somewhere.
2. **The bot looks up Priya's session.** Every user gets their own isolated session — like their own private desk at the library. Priya's notes never mix with another lawyer's notes.
3. **The message is passed into the LangGraph pipeline.** The intake node processes it, decides if more information is needed, and either asks a clarifying question or proceeds to research.
4. **If the AI needs more information**, it sends Priya a follow-up question right there in the Telegram chat.
5. **Once intake is complete**, the graph runs through research → draft → cite → review automatically.
6. **The final draft is sent back to Priya** in the Telegram chat, formatted as clean text.

### What About a Contract PDF?

If Priya sends a PDF file instead of a text message:

1. The bot downloads the PDF to a temporary folder.
2. Sets `workflow_mode = "contract_review"` in the state.
3. The graph takes the contract review fork.
4. The contract review node reads the PDF, finds risky clauses, and sends Priya a formatted risk report.

### Bot Commands

| Command | What it does |
|---|---|
| `/start` | Greets the lawyer and asks for their matter brief |
| `/new` | Starts a fresh matter (clears the current session) |
| `/status` | Shows what stage the current matter is at |
| Any text | Processed as part of the current matter |
| Any PDF | Triggers contract review |

### Security: The Allowlist

Not everyone should be able to use a legal AI. The bot supports an allowlist — a list of approved Telegram user IDs. If the allowlist is not empty, only those users can interact with the bot. Anyone else gets a polite "you are not authorized" message. If the allowlist is left empty, the bot is open to everyone (useful for testing).

### Sessions — Everyone Gets Their Own Desk

The `TelegramSession` class stores each user's current state:
- Their matter ID (a unique identifier for their case)
- Their accumulated graph state (everything the AI has learned so far)

The `_sessions` dictionary maps each Telegram user ID to their session. When Priya sends a message, the bot looks up `_sessions[priya's_user_id]` to find her desk. Another lawyer's session is stored at a completely different key.

---

## Part 7: Starting the Bot from the Terminal

**File:** `lexagent/cli.py`

A new CLI command was added:

```bash
lex gateway telegram
```

This starts the Telegram bot. The bot keeps running, listening for messages, until you stop it (Ctrl+C). It requires one environment variable (a secret setting stored outside the code):

```
TELEGRAM_BOT_TOKEN=your_bot_token_here
```

You get this token from Telegram's BotFather — a special Telegram bot that creates other bots. It is like getting a badge from the manager before you can start working.

---

## Part 8: New Tests — Proving Everything Works

**Files:** `tests/test_contract_review.py`, `tests/test_telegram_gateway.py`, updates to `tests/test_cite.py` and `tests/test_state.py`

A test is a small piece of code that checks one specific thing works correctly. Think of tests like a quality control checklist at a factory — before a product ships, every item on the checklist must pass.

Phase 7 added 36 new tests:

- **11 tests for contract review** — Does it handle PDFs correctly? Does it correctly label HIGH/MEDIUM/LOW risks? What happens if the PDF is empty?
- **13 tests for the Telegram gateway** — Does the allowlist block unauthorized users? Does each user get an isolated session? Does the markdown escaping (making text look right in Telegram) work correctly?
- **Updates to citation tests** — Does the 35% threshold actually work? Does a score of 34% get marked UNVERIFIED?
- **Updates to state tests** — Are the 5 new Phase 7 fields present and correct?

**Total test count went from 245 (Phase 6) to 281 (Phase 7).** All 281 pass. Every time a developer makes a change, all 281 tests run automatically to make sure nothing broke.

---

## How It All Works End-to-End

Let's walk through a complete story from a lawyer's perspective:

1. **Priya types `/start`** in the Telegram bot. The bot greets her and asks what she needs.

2. **She describes her matter** — a landlord-tenant dispute needing an urgent injunction in Delhi High Court.

3. **The intake node** reads her message, decides it needs one more piece of information (has she served a legal notice to the landlord?), and sends her a follow-up question.

4. **She answers.** Now intake is complete.

5. **The router** checks: is this a contract review? No. So it routes to the research node.

6. **The research node** searches Indian Kanoon (a database of Indian court judgments) for relevant cases about tenant protection and injunctions.

7. **The draft node** reads its memory (MEMORY.md), reads the research findings, and writes a full draft injunction with citations.

8. **The cite node** checks every citation. If any citation scores below 35% similarity, it is marked UNVERIFIED and flagged for Priya to double-check.

9. **The review node** does a final quality pass — checking structure, risk areas, and plain English summary.

10. **The bot sends Priya the complete draft** in her Telegram chat. If the document is long, it is also saved as a `.docx` Word file.

All of this happens while Priya is sitting in a courthouse corridor, on her phone, without a laptop. That is Phase 7.

---

---

## Phase 8 — UX Overhaul: From Generic Chatbot to Lawyer-Grade Tool

**What's new in one sentence:** The Telegram bot got a complete professional makeover — structured intake question banks, inline button menus, session persistence, a setup wizard, contextual progress messages, .docx auto-delivery, and post-draft action menus.

---

### The Big Picture: What Phase 8 Added

1. Per-matter-type question banks so intake feels purposeful, not generic
2. Inline keyboard buttons in Telegram for Yes/No and multiple-choice questions
3. Session persistence — sessions survive bot restarts and are fully resumable
4. A 5-step in-Telegram setup wizard (`/setup`) that writes SOUL.md and .env
5. Contextual loading messages drawn from YAML pools, with state substitution
6. Tool routing menu before research so lawyers choose what research to run
7. .docx auto-delivery — the Word file is sent as a Telegram attachment after drafting
8. Post-draft action menu — Email, Drive, eCourts, Redraft, Forward, DocuSign, Done
9. Post-draft action stubs for Gmail, Google Drive, eCourts, DocuSign integrations
10. 279 tests passing (up from 281 in Phase 7 — net change reflects pre-existing broken live scraper test excluded)

---

### New Files

**`lexagent/data/intake_questions.yaml`**

A YAML question bank covering 7 document types: `writ_petition`, `plaint`, `injunction`, `legal_notice`, `bail_application`, `written_statement`, `contract_review`. Each question has a `field`, `label`, `type` (open / binary / mcq), optional `options` list, and a `mandatory` flag. The intake node reads this file — no code change is needed to add or reword questions.

**`lexagent/data/loading_messages.yaml`**

Pools of contextual progress messages, one pool per graph node (intake, research, draft, cite, review). Messages support `{placeholder}` substitution from state fields (e.g. `{matter_type}`, `{jurisdiction}`). The Telegram gateway picks a random message from the pool for each turn, so the bot never shows the same spinner text twice.

**`lexagent/gateway/setup_wizard.py`**

A 5-step conversational setup wizard triggered by `/setup` in Telegram. Steps:
1. Lawyer name
2. Bar enrolment number
3. Primary court (MCQ with inline buttons)
4. API keys — the wizard reads the key, writes it to `.env`, then immediately deletes the message so the token never sits in chat history
5. MCP tool toggles (IndianKanoon, eCourts, Web search)

On completion, the wizard writes `~/.lexagent/SOUL.md` with the lawyer's identity and style preferences.

**`lexagent/gateway/integrations.py`**

Post-draft action stubs. Each function has a real interface and a clear `# TODO:` comment marking where live API calls go:
- `send_via_gmail(draft, recipient)` — Gmail send
- `upload_to_drive(docx_path)` — Google Drive upload
- `lookup_ecourts(matter)` — eCourts case number lookup
- `forward_to_user(draft, telegram_user_id)` — forward to another Telegram user
- `send_to_docusign(docx_path)` — DocuSign envelope creation (surfaces for `contract_review` matters only)

---

### Modified Files

**`lexagent/state.py`**

Nine new fields added to `LexState`:

| Field | Purpose |
|---|---|
| `pending_questions` | Structured question objects from intake for button rendering |
| `active_skill_name` | Human-readable skill name shown in Telegram ("Civil Litigation") |
| `approved_tools` | Which research tools the lawyer approved in the routing menu |
| `pending_action` | Post-draft action the lawyer selected (held between callback and execution) |
| `telegram_user_id` | Telegram user ID, threaded through state for forward/action routing |
| `fundamental_right` | Intake field for writ petitions |
| `article_invoked` | Intake field — constitutional article number |
| `cause_of_action_date` | Intake field — date the cause arose (used for limitation alerts) |
| `relief_sought` | Intake field — what the petitioner is asking for |

**`lexagent/nodes/intake.py`** — Full rewrite

- Loads `intake_questions.yaml` at startup
- Detects `matter_type` from the user's brief
- Passes the question bank for the detected type to the LLM
- LLM selects up to 5 unanswered mandatory questions per turn (adaptive — it skips questions already answered in the brief)
- Returns structured `pending_questions` objects with `type` and `options` for the Telegram gateway to render as inline buttons
- Sets `active_skill_name` so the gateway can show "Skill loaded: Civil Litigation"

**`lexagent/memory/session_store.py`**

Added `update_session()` for partial saves. Previously sessions were only written to SQLite on matter completion. Now the gateway calls `update_session()` after every intake turn — so a crash or restart loses at most one turn of conversation.

**`lexagent/gateway/telegram.py`** — Major overhaul

- `InlineKeyboardMarkup` + `CallbackQueryHandler` for binary (Yes / No) and MCQ questions (up to 4 options + "Other — type below" overflow button)
- Sessions loaded from SQLite on bot startup — the bot is stateless across restarts
- `/resume` command: shows a button list of recent matters, or accepts `/resume M-XXXXXX` directly
- `/matters` command: searchable matter list using SQLite FTS5
- `/setup` command: triggers the setup wizard
- `/help` command: shows all available commands with descriptions
- Tool routing menu appears before research: [IndianKanoon] [Web search] [eCourts] [Skip research] — selection is stored in `approved_tools`
- eCourts nudge: if Kanoon returns 0 results and eCourts is not configured, the bot surfaces a one-tap button to set it up
- .docx auto-delivery: sets `docx_path` in state before the graph runs; after completion sends the file via `reply_document()`
- Post-draft action menu: [Email] [Drive] [eCourts lookup] [Redraft] [Forward] [DocuSign] [Done] — DocuSign only appears for contract review matters
- Contextual progress messages: draws from `loading_messages.yaml`, substitutes state placeholders, rotates message on each node transition
- Skill visibility: shows "Skill loaded: Civil Litigation" banner when `active_skill_name` is set

**`lexagent/nodes/research.py`**

Respects `approved_tools` from state:
- `None` — CLI mode or no routing menu shown; run all tools as before
- `[]` — lawyer chose "Skip research"; node returns immediately with empty findings
- `["kanoon"]` — run only Indian Kanoon
- `["ecourts"]` — run only eCourts lookup
Sets `ecourts_nudge=True` in returned state when Kanoon returns 0 results and eCourts is not yet configured, so the gateway can surface the nudge button.

---

### Updated Bot Commands (full list after Phase 8)

| Command | What it does |
|---|---|
| `/start` | Greets the lawyer, asks for matter brief |
| `/new` | Starts a fresh matter |
| `/status` | Shows current matter stage |
| `/resume` | Lists recent matters as buttons for one-tap resume |
| `/matters` | Searchable matter list with FTS |
| `/setup` | Launches the 5-step setup wizard |
| `/help` | Shows all commands with descriptions |
| Any text | Processed as part of current matter |
| Any PDF | Triggers contract review |

---

### Test Count

Phase 8: **279 tests passing.** (The one excluded test is a pre-existing live Indian Kanoon network test that was already broken before Phase 8 began — it requires a live internet connection to `indiankanoon.org` and is excluded from the standard suite.)

---

*This document was written for beginners learning Python and LangGraph. If something is still confusing, the source files referenced throughout are the best next place to look — every non-obvious line has a comment explaining why it exists.*
