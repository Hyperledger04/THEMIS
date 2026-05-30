# LexAgent — Phase 3 Complete 🎓
### Skills System + Prompt Caching — explained simply, no coding knowledge needed

---

## 🎯 What Did Phase 3 Add?

After Phase 2, LexAgent knew WHO you were (your name, your courts, your drafting style) and it remembered every matter you worked on. But it still had a problem: **it treated every document the same way.**

Whether you asked for an injunction, a legal notice, or a contract — the AI would write something reasonable, but it wouldn't know:
- That an injunction must have three specific legal elements (prima facie case, balance of convenience, irreparable harm)
- That a legal notice must state a specific deadline in digits AND words
- That a contract must have numbered clauses — never bullet points in the operative sections

**Phase 3 gives LexAgent professional expertise by document type.**

Now LexAgent:
1. **Automatically identifies what kind of document you need** — injunction? notice? contract?
2. **Pulls up the right "skill" for that document type** — a detailed instruction sheet
3. **Injects that skill into the AI's instructions** before drafting begins
4. **Caches the instructions to save money** — so you're not paying full price every time

Phase 3 is the difference between a smart generalist and a trained specialist.

---

## 🌊 The Big Picture — What Phase 3 Added

```
┌─────────────────────────────────────────────────────────────────────┐
│                         YOUR TERMINAL                               │
│                                                                     │
│   $ lex draft "I need an injunction for a property dispute"         │
│                                                                     │
│   [Phase 3] LexAgent says to itself:                               │
│   "injunction" → matches civil_litigation.md skill                 │
│   → loads the skill → injects it → drafts with expert knowledge    │
│                                                                     │
│   Result: Draft includes prayer, verification, balance of          │
│   convenience argument, mandatory citations — automatically.        │
└─────────────────────────────────┬──────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│           nodes/intake.py  ❓  (UPDATED)                              │
│                                                                     │
│  After detecting matter_type:                                       │
│  → Calls skill loader: "which skill matches injunction?"            │
│  → Gets civil_litigation.md content                                 │
│  → Saves it to state["active_skill"]                               │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│           nodes/draft.py  📄  (UPDATED)                               │
│                                                                     │
│  Reads state["active_skill"]                                       │
│  Builds system prompt: SOUL.md + skill content                      │
│  (Cached — so next turn this same block costs almost nothing)       │
│                                                                     │
│  Injects matter memory into the USER turn (not the system prompt)  │
│  (This keeps the system prompt identical → cache hits every turn)   │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│              skills/  📁  (ALL NEW IN PHASE 3)                        │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ loader.py 🔍                                                  │  │
│  │ The skill-picker. Scans all .md files in skills/             │  │
│  │ Matches by matter_type or keyword → returns skill content    │  │
│  │ User skills override bundled skills if same name             │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌─────────────────┐  ┌──────────────────┐  ┌──────────────────┐  │
│  │civil_litigation │  │  legal_notice.md │  │legal_contract.md │  │
│  │     .md         │  │                  │  │                  │  │
│  │Injunctions      │  │ Demand notices   │  │ Agreements, MOUs │  │
│  │Plaints, CPC     │  │ S.80 CPC notices │  │ NDAs, Deeds      │  │
│  │Structure + Risk │  │ Structure + Risk │  │ Structure + Risk │  │
│  └─────────────────┘  └──────────────────┘  └──────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 💡 What Is A Skill File? (Explained Simply)

Think of a skill file like a **recipe card for a professional dish**.

A chef who knows 100 recipes is more useful than a chef who only knows how to cook "food in general." LexAgent's skills work the same way.

Each skill file is a plain text document (`.md` format) that answers:
- **When do you use this skill?** (keywords: "injunction", "plaint", "CPC"…)
- **What types of matter does this cover?** (civil suit, execution petition…)
- **What must be confirmed before drafting?** (limitation period, jurisdiction, all parties impleaded…)
- **What is the exact structure?** (numbered sections, prayer format, verification clause…)
- **What are the risk flags?** (HIGH/MEDIUM/LOW — what can make this document fail?)
- **Which statutes always apply?** (CPC, Limitation Act, Specific Relief Act…)
- **Which cases should always be cited?** (for injunctions: Dalpat Kumar, Gujarat Bottling…)

A lawyer could write a skill file in any text editor. No code needed.

---

## 🗂️ The Three Bundled Skills

### 1. `civil_litigation.md` — The Civil Court Expert

**Triggered by:** injunction, plaint, civil suit, CPC, specific performance, recovery, execution, decree

**Covers:**
- Interim Injunction Applications (Order XXXIX Rules 1 & 2 CPC)
- Plaints (Order VII CPC)
- Written Statements (Order VIII CPC)
- Execution Petitions (Order XXI CPC)

**Key things it teaches the AI:**
- The three-pronged injunction test: prima facie case + balance of convenience + irreparable harm
- Limitation must be checked before drafting (and specifically pleaded)
- Jurisdiction needs three heads: territorial, pecuniary, subject matter
- The mandatory citations (Dalpat Kumar 1991, Gujarat Bottling 1995, Morgan Stanley 1994)
- Every paragraph of facts must be numbered
- Bold the prayer. Include the verification clause. Always.

---

### 2. `legal_notice.md` — The Notice Expert

**Triggered by:** legal notice, demand notice, notice to pay, notice before suit, S.80 notice

**Covers:**
- Demand notices (money, property, breach of contract)
- S.80 CPC statutory notices (mandatory before suing government — 2-month wait)
- S.138 Negotiable Instruments Act notices (cheque dishonour — 30-day deadline)
- Notices to vacate premises

**Key things it teaches the AI:**
- S.80 CPC: if you're suing government, this notice is mandatory AND you must wait 2 months
- S.138 NI Act: send this within 30 days of bank's dishonour memo or you lose the remedy
- State the demand precisely: exact amount in digits AND words
- Serve by registered post AND at least one other mode
- Include the advocate's enrollment number — required for a valid legal notice

---

### 3. `legal_contract.md` — The Contract Expert

**Triggered by:** contract, agreement, MOU, NDA, deed, lease, service agreement

**Covers:**
- NDAs / Confidentiality Agreements
- Service Agreements
- Employment Contracts
- Lease Agreements
- MOUs, Partnership Deeds, Shareholder Agreements

**Key things it teaches the AI:**
- Stamp duty: contracts not stamped per the State Stamp Act are inadmissible in court
- Arbitration clauses must use mandatory language ("shall", not "may")
- Post-termination non-competes are generally void in India (S.27 Indian Contract Act)
- IP assignment vs. licence — ownership requires written assignment, not just a licence
- Numbered clauses in the body, Schedules for commercial terms, Definitions first
- Always flag HIGH-risk items inline with [FLAG: ...]

---

## 🔍 How The Skill Loader Works (Step By Step)

The loader is like a smart librarian. You give it a matter type, it finds the right book.

```
You type: lex draft "I need an injunction for a property dispute in Delhi"

STEP 1: intake.py asks the AI: "what kind of matter is this?"
  AI responds: { "matter_type": "injunction application" }

STEP 2: intake.py calls load_skill("injunction application", ...)
  Loader scans: lexagent/skills/  (bundled)  → finds 3 .md files
  Loader scans: ~/.lexagent/skills/  (user)  → finds 0 files (no user skills yet)

  Pass 1 — Exact match on matter_types list:
    civil_litigation has: [civil_suit, injunction_application, execution_petition]
    "injunction_application" → matches "injunction application" (normalised) ✓
    → Return civil_litigation.md content

STEP 3: intake.py saves skill content to state["active_skill"]

STEP 4: draft.py reads state["active_skill"]
  Builds the system prompt: SOUL.md + civil_litigation.md content
  Now the AI knows the mandatory structure, the risk flags, and the citations.

STEP 5: AI drafts the document following the skill's structure.
  Result: prayer clause present, verification clause present, Dalpat Kumar cited.
```

If no skill matches (e.g., "tax advisory") → `load_skill()` returns `None` → draft still works, just without skill guidance. No crash, no error.

---

## 💾 How Caching Works — Two Layers

Every time you use LexAgent, it sends a message to the AI. That message costs money (API tokens). The system prompt — your SOUL.md + the skill content — can be several thousand words. Without caching, you pay full price for those words on every single call.

**Phase 3 adds two layers of caching:**

---

### Layer 1 — LiteLLM Disk Cache (All Providers)

Think of this as a **photocopy machine that remembers every document it has ever copied**.

LiteLLM (the routing layer under LangGraph) stores every prompt+response pair on your disk at `~/.lexagent/llm_cache/`. If the exact same prompt is sent again:
- No API call is made
- The stored response is returned instantly
- Zero cost

This is most useful during development (re-running the same test matter) and for repeated administrative queries. It works for **every model provider** — OpenAI, Gemini, Ollama, Claude, everything.

---

### Layer 2 — Anthropic Server-Side Prompt Caching (Claude Only, Bonus)

Think of this as **Anthropic remembering your letterhead**.

When you use Claude, the system prompt (SOUL.md + skill) can be marked with `cache_control: {"type": "ephemeral"}`. Anthropic's servers cache that block. The next time you send a different question but the same system prompt:
- Anthropic does NOT re-process the system prompt
- You're charged only ~10% of normal input token cost for that block
- The response is faster too (less to process)

For a typical session:
- Without caching: 2,000 tokens × 10 turns = 20,000 tokens billed at full price
- With caching: 2,000 tokens billed once + 200 tokens × 9 turns = 3,800 tokens billed

**That's an ~81% cost reduction on a 10-turn session.**

---

### The Rule That Makes Both Layers Work

```
System prompt = SOUL.md + skill content  ← STABLE, never changes mid-session → CACHED
User turn     = matter memory + question ← DYNAMIC, changes every turn → NEVER cached
```

If matter memory went into the system prompt, it would be different on every turn. The cache would miss every time. By keeping memory in the user turn, the system prompt is identical across all turns of a session — and the cache hits every time.

This is implemented in:
```
inject_memory_into_user_turn(user_input, matter_memory)
→ "<memory-context>\n...\n</memory-context>\n\nYour question here"
```

The `<memory-context>` XML tag tells the AI: "this is background, not a new instruction."

---

## 📁 Every File We Created — What It Does In Simple English

---

### `lexagent/skills/__init__.py` — The Door Sign

An empty file. Its only job is to tell Python: "the `skills/` folder is a package — you can import things from it." Without this file, Python would not know that `loader.py` and the `.md` files belong together.

---

### `lexagent/skills/loader.py` — The Librarian

This is the skill-picker. It has four functions:

**`load_skill(matter_type, bundled_dir, user_dir)`** — The Main Function
```
Input:  "injunction application"
Output: Full text of civil_litigation.md
  OR    None  (if no skill matches)
```
Looks in both skills directories (bundled + user), builds a merged list, and runs two matching passes: exact matter_type match first, then keyword substring match.

**`_skills_from_dir(directory)`** — The Scanner
```
Input:  /path/to/skills/
Output: List of parsed skill dicts [{name, trigger_keywords, matter_types, body}, ...]
```
Reads every `.md` file in a directory, parses each one, returns the list.

**`_parse_frontmatter(content)`** — The Reader
```
Input:  "---\nname: civil_litigation\n...\n---\n# Civil Litigation..."
Output: {name: "civil_litigation", trigger_keywords: [...], matter_types: [...], body: "..."}
```
Separates the YAML header (between the `---` lines) from the body. Uses Python's `yaml.safe_load()` to parse the header into a dictionary.

**`_normalise(text)`** — The Standardiser
```
Input:  "Injunction Application"  or  "injunction_application"
Output: "injunction_application"   (always the same)
```
Converts to lowercase, replaces spaces/hyphens with underscores. Used so "Injunction Application" and "injunction_application" match each other.

---

### `lexagent/nodes/draft.py` — Updated With Two New Functions

**`inject_memory_into_user_turn(user_input, matter_memory)`** — The Memory Wrapper
```
Input:  user_input  = "Please draft an injunction for ABC vs XYZ"
        matter_memory = "Prior session: matter type injunction, parties ABC vs XYZ, Delhi HC"
Output: "<memory-context>
         Prior session: matter type injunction, parties ABC vs XYZ, Delhi HC
         </memory-context>

         Please draft an injunction for ABC vs XYZ"
```
Always goes in the **user turn**, not the system prompt. Works for every provider. If memory is empty, returns the user_input unchanged.

**`build_system_prompt_blocks(soul, skill_content, use_cache_control)`** — The Prompt Builder
```
Input:  soul = {raw: "# Lawyer Identity\n**Name:** Arjun..."}, skill_content = "# Civil Litigation...", use_cache_control = True
Output: [{"type": "text", "text": "# Lawyer Identity...\n---\n# Civil Litigation...", "cache_control": {"type": "ephemeral"}}]
  OR (when use_cache_control=False):
        "# Lawyer Identity...\n---\n# Civil Litigation..."   (a plain string)
```
When Anthropic + caching: returns a list of content blocks (native LiteLLM/Anthropic format).
When other providers: returns a plain string.

---

### `lexagent/nodes/_llm.py` — Updated With Cache Setup

**`setup_litellm_cache(config)`** — The Cache Switch
```
Effect: litellm.cache = litellm.Cache(type="disk", disk_cache_dir="~/.lexagent/llm_cache")
```
Flips on LiteLLM's disk cache for the process. Called once at startup in `cli.py`. If `enable_prompt_caching=False` in config (or `.env`), does nothing.

---

## 🔄 The Updated Flow — Step By Step

```
$ lex draft "I need an injunction for a property dispute in Delhi"

STEP 1: cli.py starts
  → Calls setup_litellm_cache() ← NEW: disk cache is now active

STEP 2: cli.py calls graph.invoke()

STEP 3: intake.py runs
  → Loads SOUL.md (Phase 2, unchanged)
  → Calls AI: "what kind of matter is this?"
  → AI extracts: matter_type = "injunction application"
  → NEW: Calls load_skill("injunction application") → gets civil_litigation.md
  → Saves skill content to state["active_skill"]
  → Asks clarifying questions if needed

STEP 4: draft.py runs
  → Reads state["lawyer_soul"] (SOUL.md content)
  → Reads state["active_skill"] (civil_litigation.md content)
  → NEW: Builds system prompt: SOUL.md + civil litigation skill
  → NEW: Injects matter memory into user turn (not system prompt)
  → If Anthropic + caching: sends with cache_control → Layer 2 cache hit from turn 2
  → Else: sends as string → Layer 1 disk cache if identical
  → AI drafts with civil litigation expertise
    ✓ Numbered paragraphs
    ✓ Three-pronged injunction test argued
    ✓ Mandatory citations: Dalpat Kumar, Gujarat Bottling
    ✓ Prayer in bold
    ✓ Verification clause

STEP 5: cli.py shows draft on screen (Phase 1, unchanged)
STEP 6: cli.py saves to memory and SQLite (Phase 2, unchanged)
```

---

## 📊 Everything Built — Status

```
COMPONENT                  STATUS    NOTES
──────────────────────────────────────────────────────────────────────
skills/loader.py           ✅ Done   Exact + keyword matching.
                                     User skills override bundled.
                                     Graceful on empty/missing dirs.

skills/civil_litigation.md ✅ Done   Injunctions, plaints, CPC apps.
                                     Full structure + 3 risk levels
                                     + mandatory citations.

skills/legal_notice.md     ✅ Done   Demand notices, S.80 CPC, S.138 NI.
                                     Deadline rules, service modes.

skills/legal_contract.md   ✅ Done   Agreements, MOUs, NDAs, leases.
                                     Stamp duty, IP, arbitration, GST.

nodes/_llm.py              ✅ Done   setup_litellm_cache() added.
(updated)                            Disk cache at ~/.lexagent/llm_cache
                                     Works for ALL providers.

nodes/intake.py            ✅ Done   Auto-selects skill after matter_type
(updated)                            extracted. Saves to active_skill.

nodes/draft.py             ✅ Done   inject_memory_into_user_turn() —
(updated)                            memory in user turn, not system prompt.
                                     build_system_prompt_blocks() —
                                     cache_control for Anthropic Layer 2.
                                     Falls back to string for other providers.

config.py                  ✅ Done   enable_prompt_caching field added.
(updated)                            LEX_ENABLE_CACHING env var.

cli.py                     ✅ Done   setup_litellm_cache() called at startup.
(updated)

tests/test_skills.py       ✅ Done   17 tests. Covers frontmatter parsing,
                                     dir scanning, all match modes,
                                     user override, edge cases.

tests/test_caching.py      ✅ Done   15 tests. Covers memory injection
                                     (empty/None/real), cached prompt
                                     structure, string fallback.

──────────────────────────────────────────────────────────────────────
PHASE 3 COMPLETENESS: 100% ██████████
Test count: 90 passing (1 pre-existing kanoon scraper test failing on live site)
──────────────────────────────────────────────────────────────────────

WHAT PHASE 3 CANNOT DO YET:
  ✗ Real Indian Kanoon citations — Phase 4
  ✗ Research node + citation verification — Phase 4
  ✗ RAG on past matters — Phase 5
  ✗ Word document export — Phase 5
  ✗ SOUL.md self-updates — Phase 6
  ✗ Telegram gateway — Phase 7
```

---

## 🗓️ What We Decided In This Phase

### 1. User skills override bundled skills by name
**What:** If a lawyer creates `~/.lexagent/skills/civil_litigation.md`, it replaces the bundled version.
**Why:** Every lawyer's practice is different. A commercial litigation specialist in Mumbai may want a different injunction structure than the default. The user's expertise always wins.

### 2. Two-pass matching: exact first, then keywords
**What:** Exact `matter_types` match wins. Keyword substring match is the fallback.
**Why:** Exact match gives deterministic results for well-structured matter types. Keywords are the safety net for free-text input where the AI might say "injunction application" or "application for injunction" — both should match.

### 3. LiteLLM for caching (not the raw Anthropic SDK)
**What:** We use LiteLLM's disk cache (`litellm.Cache`) + LiteLLM's native `cache_control` support.
**Why:** LexAgent is built on LiteLLM for model routing. All providers (OpenAI, Gemini, Ollama, Claude) flow through LiteLLM. Adding a raw Anthropic SDK would create a parallel code path. LiteLLM supports Anthropic's `cache_control` format natively when calling `litellm.acompletion()` directly.

### 4. Memory in the user turn — for all providers
**What:** `inject_memory_into_user_turn()` wraps matter memory in `<memory-context>` tags and prepends it to the user message. Never touches the system prompt.
**Why:** The system prompt must be identical across all turns to get cache hits. If memory went in the system prompt, it would differ every turn → cache miss every turn. This applies to all providers, not just Anthropic.

### 5. Skill is loaded in intake, not draft
**What:** The skill is set in `state["active_skill"]` by the intake node, the moment `matter_type` is known.
**Why:** Loading skills at draft time would be too late — the system prompt must be fully built before the LLM call. Doing it in intake keeps the skill available for any future node (research, review, cite) that needs it, not just draft.

---

## ✅ How To Run What We Built

```bash
# 1. Draft an injunction — should use civil litigation skill automatically
uv run lex draft "I need an injunction application for a property dispute in Delhi High Court"

# 2. Draft a legal notice
uv run lex draft "Send a legal notice to recover unpaid rent of Rs. 2 lakh"

# 3. Draft a contract
uv run lex draft "Draft a service agreement for a software development project"

# 4. Run all Phase 3 tests
uv run pytest tests/test_skills.py tests/test_caching.py -v

# 5. Run the full test suite (90 should pass)
uv run pytest tests/ -v

# 6. Add your own skill (no code needed — just a .md file)
mkdir -p ~/.lexagent/skills
# Write your skill file to ~/.lexagent/skills/writ_petition.md
# LexAgent will pick it up automatically next time you run
```

---

## 🗂️ Where Files Live After Phase 3

```
~/Lexagent/                        ← The project code
├── lexagent/
│   ├── skills/                    ← NEW in Phase 3
│   │   ├── __init__.py
│   │   ├── loader.py              ← The skill picker
│   │   ├── civil_litigation.md    ← Injunctions, plaints, CPC
│   │   ├── legal_notice.md        ← Demand notices, S.80, S.138
│   │   └── legal_contract.md      ← Agreements, NDAs, MOUs
│   ├── nodes/
│   │   ├── _llm.py    (updated)   ← setup_litellm_cache() added
│   │   ├── intake.py  (updated)   ← loads skill after matter_type
│   │   └── draft.py   (updated)   ← cached prompt, memory injection
│   └── config.py      (updated)   ← enable_prompt_caching field
└── tests/
    ├── test_state.py   (14 tests, Phase 1, unchanged)
    ├── test_memory.py  (42 tests, Phase 2, unchanged)
    ├── test_kanoon.py  (Phase 4 — 1 test depends on live website)
    ├── test_skills.py  (17 tests, Phase 3) ← NEW
    └── test_caching.py (15 tests, Phase 3) ← NEW

~/.lexagent/                       ← Your data (separate from code)
├── SOUL.md
├── sessions.db
├── llm_cache/                     ← NEW: LiteLLM disk cache
├── skills/                        ← NEW: Your custom skills (override bundled)
│   └── (empty until you add one)
└── matters/
    └── ...
```

---

## 🚦 The 8-Phase Roadmap

```
PHASE 1 ████████████ DONE
Foundation. lex draft works end-to-end.

PHASE 2 ████████████ DONE
Memory & Identity.
SOUL.md, matter memory, SQLite sessions.

PHASE 3 ████████████ DONE (this phase)
Skills System + Prompt Caching.
Auto-select skill by matter type.
Two-layer caching: LiteLLM disk + Anthropic server-side.
"Injunction draft follows civil_litigation.md structure."

PHASE 4 ░░░░░░░░░░░░ Next
Tools: Real Legal Data.
Indian Kanoon, eCourts — research + citation verification nodes.
"Citations are verified against Indian Kanoon before the draft is shown."

PHASE 5 ░░░░░░░░░░░░
RAG on Past Matters + Review Node + .docx Output.
"Draft cites your own past matters. Export to Word."

PHASE 6 ░░░░░░░░░░░░
Self-Learning Loop.
SOUL.md auto-updates. Skills that write themselves.

PHASE 7 ░░░░░░░░░░░░
Telegram Gateway + Polish.

PHASE 8 ░░░░░░░░░░░░
FastAPI Layer + PyPI Launch.
```

---

*Phase 3 completed — May 2026*
*Author: Brahm (brahmsareen04@gmail.com)*
*Next: Phase 4 — Real Legal Data (Indian Kanoon citations, eCourts, research + cite nodes)*
