# LexAgent — Phase 1 Complete 🏗️
### Everything we built, explained simply — no coding knowledge needed

---

## 🎯 What Are We Building?

Imagine you are a lawyer. You have a client with a property dispute in Delhi. You need to write a formal legal document called an "injunction application" — a document that asks the court to immediately stop something from happening.

Writing this takes hours. You need to know the exact legal structure, which court cases to cite, the correct prayer format, the verification clause — it's complex.

**LexAgent is your AI robot lawyer-assistant.** You type one sentence about your problem. It asks you a few smart questions. Then it types the whole document for you — correctly, professionally, and fast.

That is the product. Phase 1 is the foundation that makes this possible.

---

## 🗺️ The Big Picture — How The Files Talk To Each Other

```
┌─────────────────────────────────────────────────────────────────┐
│                         YOUR TERMINAL                           │
│                                                                 │
│   $ lex draft "I need an injunction for a property dispute"     │
└────────────────────────┬────────────────────────────────────────┘
                         │ You type this command
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                      cli.py  🖥️                                  │
│                   "The Front Door"                              │
│                                                                 │
│  • Receives your message                                        │
│  • Shows you a nice panel with a Matter ID                      │
│  • Hands everything to the Graph                                │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                     graph.py  🗺️                                 │
│                   "The Traffic Controller"                      │
│                                                                 │
│  • Knows the route: INTAKE → DRAFT → DONE                       │
│  • Makes decisions: "Did the lawyer answer everything?          │
│    Yes? → Go to Draft. No? → Ask more questions."              │
└──────────────┬──────────────────────────┬───────────────────────┘
               │                          │
               ▼                          ▼
┌──────────────────────────┐  ┌──────────────────────────────────┐
│    nodes/intake.py  ❓   │  │      nodes/draft.py  📄          │
│    "The Receptionist"    │  │      "The Writer"                │
│                          │  │                                  │
│  • Reads your brief      │  │  • Gets all the info from        │
│  • Figures out what's    │  │    intake                        │
│    missing               │  │  • Loads the prompt template     │
│  • Asks smart questions  │  │  • Calls the AI to write         │
│  • Loops until it has    │  │    the full legal document       │
│    everything it needs   │  │  • Pulls out the plain           │
│                          │  │    English summary               │
└──────────────────────────┘  └──────────────────────────────────┘
               │                          │
               └──────────┬───────────────┘
                          │ Both nodes read & write to:
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                     state.py  📋                                 │
│                   "The Shared File"                             │
│                                                                 │
│  This is like a Google Doc that every part of the system       │
│  can read and write to. It holds everything:                    │
│  • What the lawyer said                                         │
│  • What the AI figured out (matter type, parties, court...)    │
│  • The finished draft                                           │
│  • Any errors that happened                                     │
└─────────────────────────────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────────────┐
│                    config.py  ⚙️                                  │
│                   "The Settings Panel"                          │
│                                                                 │
│  • Which AI model to use? (Claude / GPT / Gemini / Ollama)     │
│  • Where to save files?                                         │
│  • Which legal databases are connected?                         │
│  • Read from the .env file so lawyers never touch code         │
└─────────────────────────────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────────────┐
│                  nodes/_llm.py  🧠                               │
│               "The Brain Connector"                             │
│                                                                 │
│  • Connects to whichever AI the lawyer has chosen               │
│  • Uses LiteLLM — one piece of code that speaks to             │
│    Claude, GPT, Gemini, local AI, OpenRouter, all of them      │
│  • Lawyer just sets their API key in .env — done               │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🌊 The Full Journey — Step By Step

Here is exactly what happens when you type `lex draft "I need an injunction"`:

```
STEP 1: You type the command
━━━━━━━━━━━━━━━━━━━━━━━━━━━
$ lex draft "I need an injunction for a property dispute in Delhi"
                    │
                    ▼
STEP 2: cli.py wakes up
━━━━━━━━━━━━━━━━━━━━━━━
• Shows you a nice box: "⚖ LexAgent | Matter ID: M-4F2A9C1B"
• Creates a blank "file on the table" (state) with just your brief
• Hands it to the graph
                    │
                    ▼
STEP 3: Graph sends to Intake first
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                    │
                    ▼
STEP 4: intake.py checks what we know
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• We know: "property dispute, Delhi" (some info)
• We DON'T know yet: exact parties? which court? what document?
• AI thinks: "I need to ask questions"
• Returns: ["Who are the parties?", "Which Delhi court?"]
                    │
                    ▼
STEP 5: cli.py shows the questions to the lawyer
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
┌─────────────────────────────────────────────────┐
│      LexAgent needs a few more details          │
│  1. Who are the parties and their relationship? │
│  2. Which specific court in Delhi?              │
└─────────────────────────────────────────────────┘
Lawyer types: "ABC Ltd vs XYZ Developers, Delhi HC"
                    │
                    ▼
STEP 6: Graph loops back to Intake
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• Now checks: do we have matter_type? parties? jurisdiction? purpose?
• Yes! All four present → sets intake_complete = True
• Graph routes to DRAFT
                    │
                    ▼
STEP 7: draft.py writes the document
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• Loads the instructions from prompts/base_system.md
• Fills in: matter type, parties, court, purpose
• Calls the AI: "Write a formal injunction application with these details"
• AI produces a full document with numbered paragraphs and a prayer
• Also produces a 2-3 line plain English summary for the client
                    │
                    ▼
STEP 8: cli.py shows the result
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
┌──────────────────────────────────────┐
│          ⚖ Draft Complete            │
│                                      │
│  IN THE HIGH COURT OF DELHI          │
│  I.A. No. ___ of 2026               │
│                                      │
│  BETWEEN:                            │
│  ABC Ltd             ... Plaintiff   │
│  XYZ Developers      ... Defendant   │
│  ...                                 │
└──────────────────────────────────────┘
┌──────────────────────────────────────┐
│       Plain English Summary          │
│  ABC Ltd is asking the Delhi HC to   │
│  stop XYZ from building on the       │
│  disputed property until the case    │
│  is decided.                         │
└──────────────────────────────────────┘
```

---

## 📁 Every File We Created — What It Does In Simple English

---

### 📄 `pyproject.toml` — The Shopping List

Before you cook a meal, you make a shopping list. This file is LexAgent's shopping list.

It tells the computer:
- "This project is called `lexagent`, version 0.1.0"
- "It needs Python 3.11 or newer to run"
- "It needs these tools: LangGraph (the agent brain), LiteLLM (the AI connector), Rich (the pretty terminal), Typer (the command-line handler)..."
- "When someone types `lex` in the terminal, run this file: `lexagent/cli.py`"

**Why it matters:** Without this file, nobody can install LexAgent. It is the recipe card for the whole project.

---

### 📄 `.env.example` — The Key Holder

Every AI model (Claude, GPT, Gemini) requires a secret password called an **API key**. You get this from the AI company's website.

This file is a template that shows lawyers exactly where to paste their keys:

```
ANTHROPIC_API_KEY=sk-ant-...     ← paste your Claude key here
OPENAI_API_KEY=sk-...            ← or paste your GPT key here
LEX_MODEL=claude-sonnet-4-6      ← which model to use
LEX_KANOON_BACKEND=stub          ← which legal database to use
```

Lawyers copy this file, rename it to `.env`, fill in their keys, and LexAgent is ready to go. **No code editing. Ever.**

This is the BYOK system — **Bring Your Own Key.** LexAgent does not lock you into one AI company. You bring your own.

---

### 📄 `lexagent/state.py` — The Shared Notebook

Imagine a case file folder sitting on a table. Every worker who touches the case picks up that folder, reads what's in it, adds their notes, and puts it back.

`state.py` defines what is inside that folder. It is a list of every piece of information LexAgent tracks for a single matter:

| Field | What it holds | Ready? |
|---|---|---|
| `user_input` | The lawyer's original message | ✅ Phase 1 |
| `matter_type` | "injunction", "plaint", "notice"... | ✅ Phase 1 |
| `parties` | Who is suing whom | ✅ Phase 1 |
| `jurisdiction` | Which court, which country | ✅ Phase 1 |
| `purpose` | What the lawyer wants to achieve | ✅ Phase 1 |
| `intake_complete` | Is the intake finished? (True/False) | ✅ Phase 1 |
| `draft_output` | The finished legal document | ✅ Phase 1 |
| `messages` | The full conversation history | ✅ Phase 1 |
| `research_findings` | Real court cases found online | ⏳ Phase 4 |
| `lawyer_soul` | The lawyer's personal style profile | ⏳ Phase 2 |
| `active_skill` | Which skill set the agent is using | ⏳ Phase 3 |

**The key rule:** No worker changes the whole folder — they only write on their specific page. This is why nodes return only the keys they changed.

---

### 📄 `lexagent/config.py` — The Control Panel

Every setting that a lawyer might want to change lives here. Things like:

- Which AI model to use (Claude, GPT, Gemini, Ollama, OpenRouter)
- Where to save matter files on the computer
- Which legal databases are connected (Indian Kanoon, eCourts, CourtListener)
- Whether to automatically verify citations

**Why this matters:** In Phase 8, we will build a web interface with buttons and dropdowns. Every button on that interface will just change a value in this file. The code never needs to be touched.

The three modes for legal databases:
- `stub` — pretend mode, returns fake data (good for testing)
- `api` — connects directly using the lawyer's own API key
- `mcp` — connects using an MCP server the lawyer has set up themselves

---

### 📄 `lexagent/prompts/base_system.md` — The Instructions Card

When you hire a new employee, you give them an instruction manual. This file is the instruction manual for LexAgent's AI brain.

It tells the AI:
- "You are a professional legal AI assistant"
- "Never make up court cases — if you're not sure a case exists, flag it as [UNVERIFIED]"
- "Always number your paragraphs"
- "Always bold the prayer section"
- "After the document, write a 2-3 sentence plain English summary"

**Why it's a separate file (not inside the code):** A lawyer can edit this file in Notepad without touching any Python. In Phase 8, the web interface will have a text editor that writes to this file directly.

---

### 📄 `lexagent/nodes/_llm.py` — The Brain Connector

This tiny file does one very important thing: it connects LexAgent to whichever AI model the lawyer has chosen.

It uses a library called **LiteLLM** — think of it as a universal adapter plug. Whether the lawyer uses Claude, GPT-4, Gemini, or a local AI running on their own computer — LiteLLM makes them all look the same to LexAgent.

The lawyer just sets two lines in their `.env` file:
```
LEX_MODEL=claude-sonnet-4-6
LEX_MODEL_PROVIDER=anthropic
```

And `_llm.py` builds the correct connection automatically. Zero code changes needed to switch AI providers.

**This is exactly how Hermes Agent (the developer tool that inspired LexAgent) works.**

---

### 📄 `lexagent/nodes/intake.py` — The Receptionist

Think of a receptionist at a law firm. When a new client walks in, they don't just immediately start on the case. They ask:

1. What is your matter about?
2. Who are the parties?
3. Which court is handling this?
4. What do you need us to draft?

That is exactly what `intake.py` does, except it's smarter:

- If you already told it some information (like "Delhi HC"), it doesn't ask again
- It asks maximum 4 questions at once — never more
- It loops (asks → gets answer → checks → asks again if needed) until it has everything
- Once it has all 4 required fields, it sets `intake_complete = True` and stops

**The loop mechanism is key.** The intake node can run multiple times in a row. This is LangGraph's superpower — nodes can loop until a condition is met.

---

### 📄 `lexagent/nodes/draft.py` — The Writer

Once intake is done, the writer takes over. It:

1. **Loads the instruction manual** (`prompts/base_system.md`) — tells the AI who it is and how to behave
2. **Fills in the details** — replaces placeholders like `{parties}` with "ABC Ltd vs XYZ Developers"
3. **Gives the AI a warning** — "No verified research yet. Only cite cases you're very confident about. Flag any citations as [UNVERIFIED]."
4. **Calls the AI** — sends the instruction + the matter details + the warning
5. **Receives the document** — the full legal draft
6. **Pulls out the summary** — finds the "Plain English Summary" section and saves it separately

**Phase 4 upgrade (coming later):** In Phase 4, step 3 will change. Instead of a warning about unverified citations, it will provide a list of *real, verified* court cases found by the research node. The draft will then include those real citations.

---

### 📄 `lexagent/graph.py` — The Traffic Controller

This is the brain of LangGraph itself. It defines the map:

```
START
  │
  ▼
INTAKE ──── Did we get everything? ──── NO ──→ (back to INTAKE)
  │
  YES
  │
  ▼
DRAFT
  │
  ▼
END
```

The technical term for this map is a **StateGraph**. It:
- Knows the name of every worker (node)
- Knows all the roads between them (edges)
- Makes decisions at forks in the road (conditional edges)
- Gets compiled once at the start — then it runs forever

**The conditional edge is the most important line:**
```
"After intake runs, if intake_complete is True → go to draft.
 If intake_complete is False → go back to intake."
```

This is how LexAgent loops and asks follow-up questions instead of giving up.

---

### 📄 `lexagent/cli.py` — The Front Door

This is what the lawyer actually sees. When they type `lex draft "..."`, this file:

1. Receives the message
2. Shows a beautiful coloured panel with the Matter ID
3. Starts the graph
4. Shows a spinner while thinking ("⠿ Thinking...")
5. When intake asks questions → shows them in a yellow box and waits for answers
6. When the draft is ready → shows it in a green box
7. Shows the plain English summary in a blue box
8. Flags any unverified citations in a red box

**Available commands:**
- `lex draft "brief"` — the main command
- `lex setup` — will create your lawyer profile (Phase 2)
- `lex config` — shows current settings

All output uses a library called **Rich** which makes terminal text look beautiful — coloured panels, spinners, styled text. This is a design decision: it signals "professional tool" from the very first run.

---

### 📄 `tests/test_state.py` — The Safety Net

Before building a bridge, engineers test the steel. Before trusting LexAgent's foundation, we test it.

This file contains 14 automatic tests that verify:
- The state (the shared notebook) has all the right fields
- Fields that should start empty actually start empty
- `intake_complete` starts as `False`
- The message history can hold conversation messages
- The node return pattern (partial dict) works correctly

**Run them with:** `uv run pytest tests/ -v`

**Result:** 14/14 PASSED ✅

---

## 📊 Code Review — What's Good, What's Planned

```
COMPONENT          STATUS    QUALITY NOTES
─────────────────────────────────────────────────────────────────
state.py           ✅ Done   Covers all 8 phases already.
                             jurisdiction_country added for
                             global scope (not in original brief)

config.py          ✅ Done   BYOK + BYO-MCP pattern solid.
                             3 backends per source: stub/api/mcp
                             Maps 1:1 to future web UI controls

_llm.py            ✅ Done   LiteLLM pattern identical to Hermes.
                             Single change in .env switches all nodes.

intake.py          ✅ Done   Loops correctly. JSON parsing has
                             fallback for malformed LLM responses.
                             Max 4 questions per round enforced.

draft.py           ✅ Done   Phase 4 hook already in place
                             (research_findings check). Prompts
                             loaded from .md files — not hardcoded.

graph.py           ✅ Done   LANGGRAPH comments on every concept.
                             Conditional edges on draft already
                             in place for Phase 4/5 additions.

cli.py             ✅ Done   Interactive loop handles multiple
                             intake rounds. Rich panels throughout.
                             Matter ID generated per session.

prompts/           ✅ Done   Global identity (not India-specific).
                             Placeholder slots for SOUL.md (Ph.2)
                             and skills (Ph.3).

tests/test_state   ✅ Done   14 tests, all passing.
                             Covers state structure, node contract,
                             and global jurisdiction field.

─────────────────────────────────────────────────────────────────
PHASE 1 COMPLETENESS: 100% ██████████
─────────────────────────────────────────────────────────────────

WHAT PHASE 1 CANNOT DO YET:
  ✗ Real court case citations (comes in Phase 4)
  ✗ Lawyer profile / drafting style (comes in Phase 2)
  ✗ Skill templates for injunction vs plaint vs notice (Phase 3)
  ✗ Save matters to memory (Phase 2)
  ✗ Word document export (Phase 5)
  ✗ Telegram access from phone (Phase 7)
  ✗ Self-learning / skills that write themselves (Phase 6)
```

---

## 🗓️ What We Decided In This Session (The Big Choices)

Before writing a single line of code, we spent time answering hard questions. Here are the decisions we made and why:

### 1. LiteLLM for AI model switching
**What:** One library that speaks to all AI providers.
**Why:** Hermes Agent (the product that inspired LexAgent) uses LiteLLM. We matched that choice. Lawyers change one line in `.env` to switch from Claude to GPT to a local AI.

### 2. Global jurisdiction from day one
**What:** The intake node asks "which court, which country?" as free-form text.
**Why:** LexAgent is not just for Indian lawyers. Indian-specific rules (CPC, Limitation Act) will live in skill files (Phase 3), not in the core code. UK, US, Singapore lawyers can use LexAgent too.

### 3. Three backends for every legal database
**What:** Each database (Indian Kanoon, eCourts, CourtListener) has three modes: stub, api, mcp.
**Why:** A lawyer might use their own Indian Kanoon API key. Another might use an MCP server. A developer might want mock data for testing. All three cases are handled by one config setting.

### 4. Prompts in `.md` files, not in code
**What:** The AI's instructions live in `prompts/base_system.md`.
**Why:** Lawyers can edit a text file. They cannot edit Python. The future web interface will have a live editor for these files.

### 5. Multi-agent in Phase 4-5
**What:** Phase 4-5 will have a Research Agent, a Drafting Agent, and a Citation Agent — three separate AI workers, each an expert in one thing.
**Why:** One AI doing everything is less reliable than three AIs each doing their specialty. The supervisor pattern (one AI directing the others) is how advanced LangGraph systems work.

### 6. Self-learning (Phase 6) has three parts
- SOUL.md auto-updates: After each matter, the AI proposes additions to the lawyer's style profile. Lawyer approves or rejects.
- Skills that write themselves: After complex work, the AI generates a new skill template for that type of matter.
- RAG on past matters: The AI remembers what you drafted last time and uses it to inform the current draft.

---

## 🚦 The 8-Phase Roadmap

```
PHASE 1 ████████████ DONE
Foundation. Get something running.
lex draft works end-to-end.

PHASE 2 ░░░░░░░░░░░░ Next
Memory & Identity.
Lawyer profile (SOUL.md). Matter memory. SQLite sessions.
"Output references lawyer's name and bar number."

PHASE 3 ░░░░░░░░░░░░
Skills System.
Auto-select skill by matter type.
"Injunction draft follows civil_litigation.md structure."

PHASE 4 ░░░░░░░░░░░░
Tools: Real Legal Data.
Indian Kanoon, eCourts, CourtListener — all BYOK/BYO-MCP.
Multi-agent: Research + Drafting + Citation as separate AI workers.

PHASE 5 ░░░░░░░░░░░░
RAG on Past Matters + Review Node + .docx Output.
"Draft cites your own past matters. Export to Word."

PHASE 6 ░░░░░░░░░░░░
Self-Learning Loop.
SOUL.md auto-updates. Skills that write themselves.
"After 5 matters, a new skill was auto-generated."

PHASE 7 ░░░░░░░░░░░░
Telegram Gateway + .docx + Polish.
"Send brief from phone, receive formatted draft."

PHASE 8 ░░░░░░░░░░░░
FastAPI Layer + PyPI Launch.
REST API for future web UI. pip install lexagent works.
```

---

## ✅ How To Run What We Built

```bash
# 1. Go to the project folder
cd /Users/anshoosareen/Lexagent

# 2. Copy the settings template
cp .env.example .env

# 3. Open .env in any text editor and paste your Anthropic API key
# (Get one from: console.anthropic.com)
# ANTHROPIC_API_KEY=sk-ant-your-key-here

# 4. Run LexAgent
uv run lex draft "I need an injunction application for a property dispute in Delhi"

# 5. Run the tests (should say 14 passed)
uv run pytest tests/ -v

# 6. See current settings
uv run lex config
```

---

*Phase 1 completed — May 2026*
*Author: Brahm (brahmsareen04@gmail.com)*
*Next: Phase 2 — Memory & Identity*
