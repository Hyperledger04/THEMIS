# LexAgent — Phase 2 Complete 🧠
### Memory & Identity — explained simply, no coding knowledge needed

---

## 🎯 What Did Phase 2 Add?

In Phase 1, LexAgent could ask questions and write a legal document. But it had a problem: **it forgot everything the moment you closed the terminal.**

Every time you ran it, it was like meeting a stranger. It did not know your name. It did not know you were a lawyer at Delhi High Court. It did not remember the property dispute matter you worked on last Tuesday. You had to explain everything from scratch every single time.

**Phase 2 gives LexAgent a memory.**

Now LexAgent:
1. **Knows who you are** — your name, your bar number, your courts, your drafting style
2. **Remembers every matter** — parties, jurisdiction, what was drafted, what was decided
3. **Can pick up where you left off** — continue a matter from days or weeks ago
4. **Lets you search your entire case history** — "show me all property dispute matters from Delhi"

Phase 2 is the difference between a smart stranger and a trusted colleague who knows your practice inside out.

---

## 🗺️ The Big Picture — What Phase 2 Added

Here is the Phase 1 picture, with the new Phase 2 parts highlighted:

```
┌─────────────────────────────────────────────────────────────────┐
│                         YOUR TERMINAL                           │
│                                                                 │
│   $ lex setup    ← NEW: Creates your lawyer profile            │
│   $ lex draft "I need an injunction..."                         │
│   $ lex matter list  ← NEW: See all your past matters          │
│   $ lex search "property dispute"  ← NEW: Search everything    │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                      cli.py  🖥️  (UPDATED)                       │
│                                                                 │
│  NEW in Phase 2:                                                │
│  • `lex setup` → runs the lawyer profile wizard                 │
│  • `lex matter list` → shows all saved matters in a table      │
│  • `lex matter show M-001` → shows a matter's memory log       │
│  • `lex search "keyword"` → full-text search                   │
│  • After every draft: saves to SQLite + MEMORY.md              │
│  • `lex draft --matter-id M-001` → continues a prior matter    │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│           nodes/intake.py  ❓  (UPDATED)                         │
│                                                                 │
│  NEW in Phase 2:                                                │
│  • First thing it does: loads your SOUL.md                     │
│  • Puts your lawyer profile into the shared state              │
│  • Draft node can then read it and personalise the output      │
└──────────────────────────────────┬──────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────┐
│           nodes/draft.py  📄  (UPDATED)                          │
│                                                                 │
│  NEW in Phase 2:                                                │
│  • Reads your SOUL.md from state and adds it to the AI prompt  │
│  • Every document now says "drafted for Arjun Mehta, Delhi HC" │
│  • Uses your preferred tone, citation style, document length   │
└──────────────────────────────────┬──────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────┐
│              memory/  📁  (ALL NEW IN PHASE 2)                   │
│                                                                 │
│  ┌──────────────────────┐  ┌──────────────────────────────────┐ │
│  │    soul.py  👤        │  │    matter_memory.py  📓          │ │
│  │  "The ID Card"       │  │    "The Case File Log"           │ │
│  │                      │  │                                  │ │
│  │  Reads/writes        │  │  Writes a timestamped summary    │ │
│  │  ~/.lexagent/SOUL.md │  │  after each session              │ │
│  │                      │  │  ~/.lexagent/matters/M-001/      │ │
│  │  Runs the setup      │  │    MEMORY.md  ← human-readable   │ │
│  │  wizard questions    │  │    state.json ← machine-readable │ │
│  └──────────────────────┘  └──────────────────────────────────┘ │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              session_store.py  🗄️                          │   │
│  │           "The Searchable Archive"                        │   │
│  │                                                          │   │
│  │  SQLite database: ~/.lexagent/sessions.db                │   │
│  │  • Stores every session in a table                       │   │
│  │  • FTS5 full-text search: find matters by keyword        │   │
│  │  • Reload prior state to continue a matter               │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🌊 The Full Journey — Step By Step With Memory

Here is what happens now when you use LexAgent for the **first time** and then **come back a week later**:

```
FIRST TIME
━━━━━━━━━━
$ lex setup

  → Wizard asks 14 questions (name, bar number, courts, tone, etc.)
  → Saves your answers to ~/.lexagent/SOUL.md
  → Initialises the SQLite database at ~/.lexagent/sessions.db
  → Done. 2 minutes. Never asked again.

$ lex draft "I need an injunction for a property dispute in Delhi"

STEP 1: cli.py checks if SOUL.md exists.
  It does! No warning. (Without SOUL.md it would show a tip to run lex setup.)

STEP 2: cli.py creates a Matter ID: M-4F2A9C1B
  Builds blank state, starts the graph.

STEP 3: intake.py runs.
  NEW: First thing it does is call load_soul() → reads your SOUL.md
  Saves your lawyer profile into state["lawyer_soul"]
  Then does its normal job: asks clarifying questions.

STEP 4: Lawyer answers questions. intake_complete = True.

STEP 5: draft.py runs.
  NEW: Reads state["lawyer_soul"], finds your name "Arjun Mehta"
  Builds the system prompt: "You are drafting for Arjun Mehta,
    Delhi High Court, Senior formal tone, Always include citations."
  Tells the AI: "Please draft the legal document for Arjun Mehta:"
  AI produces a document that sounds like Arjun Mehta wrote it.

STEP 6: cli.py renders the draft on screen.

STEP 7: cli.py saves the session.
  NEW: Calls save_matter_memory() → writes MEMORY.md + state.json
  NEW: Calls save_session() → writes one row to sessions.db
  Shows: "✓ Session saved (ID: 1) | Matter memory: ~/.lexagent/matters/M-4F2A9C1B/MEMORY.md"


ONE WEEK LATER
━━━━━━━━━━━━━━
$ lex draft --matter-id M-4F2A9C1B "Add a prayer for damages"

  cli.py sees the --matter-id flag.
  Calls get_session_state("M-4F2A9C1B") → loads the saved state from SQLite.
  Sets intake_complete = False so the agent re-asks questions (the matter may have changed).
  Passes the prior state as the starting point — parties, jurisdiction, purpose already filled in.
  The agent now KNOWS this matter. It doesn't ask "who are the parties?" again.
  It just asks: "What specific damages are you seeking?"
  Draft is produced. Session saved again. MEMORY.md gets a second entry.


SEARCHING YOUR HISTORY
━━━━━━━━━━━━━━━━━━━━━━
$ lex search "property dispute Delhi"

  Searches sessions.db using FTS5 (the built-in search engine)
  Returns: all sessions where those words appear in matter type, parties, or summary
  Shows a table: Matter ID | Date | Type | Parties | Summary

$ lex matter list

  Lists all matter directories in ~/.lexagent/matters/
  Sorted newest first. Shows matter type and parties from state.json.

$ lex matter show M-4F2A9C1B

  Reads MEMORY.md for that matter and renders it as formatted markdown.
  Shows every session ever recorded for that matter, with timestamps.
```

---

## 📁 Every File We Created — What It Does In Simple English

---

### 📄 `lexagent/memory/__init__.py` — The Signpost

This is an empty file that tells Python: "the `memory` folder is a package — you can import things from it."

Think of it as a sign on a door that says "Memory Department. Enter here."

Without this file, Python would not know that `soul.py`, `matter_memory.py`, and `session_store.py` belong together as a group.

---

### 📄 `lexagent/memory/soul.py` — The ID Card

**What is a SOUL.md?**

Imagine your lawyer's business card, but much more detailed. It lives at `~/.lexagent/SOUL.md` (the `~` means "your home folder on your computer"). It looks like this:

```markdown
# Lawyer Identity

**Name:** Arjun Mehta
**Bar Enrollment:** D/456/2015, Delhi Bar Council
**Practice Since:** 2015

## Practice Profile
**Primary Courts:** Delhi High Court, Patiala House Courts
**Primary Practice Areas:** Civil Litigation, Arbitration

## Drafting Style
**Preferred Tone:** Senior formal
**Citation Preference:** Always include
...
```

Every time LexAgent writes a document, it reads this file and uses it to personalise the output. The document sounds like **you** wrote it — not a generic AI.

---

**The functions in `soul.py`:**

#### `soul_path(home_dir)` — The Address Finder
```
Input:  home_dir = "~/.lexagent"
Output: /Users/arjun/.lexagent/SOUL.md  (the exact path on disk)
```

This tiny function just computes where SOUL.md should be stored. It converts the shorthand `~` into the actual folder path on your computer. Used by every other function that needs to find the file.

---

#### `load_soul(home_dir)` — The File Reader
```
Input:  home_dir = "~/.lexagent"
Output: {"name": "Arjun Mehta", "bar_enrollment": "D/456/2015", "raw": "...", ...}
  OR    None  (if SOUL.md doesn't exist yet)
```

Opens SOUL.md and reads it into a Python dictionary (a lookup table of key-value pairs). If the file doesn't exist yet — first run — it returns `None` gracefully.

The dictionary has two types of entries:
- **Simple fields** like `name`, `bar_enrollment`, `tone` — one line each
- **`raw`** — the entire file text, so the AI can read the whole thing as a human would

---

#### `save_soul(soul_data, home_dir)` — The File Writer
```
Input:  {"name": "Arjun Mehta", "bar_enrollment": "D/456/2015", ...}
Output: Creates ~/.lexagent/SOUL.md  (returns the path where it was saved)
```

Takes a dictionary of answers from the setup wizard, fills them into the SOUL_TEMPLATE (a pre-made document outline), and writes the result to disk. Also creates the `~/.lexagent/` folder if it doesn't exist yet.

---

#### `append_soul_note(note, section, home_dir)` — The Learning Pen
```
Input:  note="Always verify limitation before filing", section="Custom Instructions"
Effect: Adds a new bullet point to the "Custom Instructions" section of SOUL.md
```

This function is built for **Phase 6 (self-learning)**. After LexAgent finishes a complex matter, it can suggest new things to remember — like "you always ask about limitation periods before injunctions." This function writes those learned preferences into SOUL.md so they stick forever. The hook is ready; it activates in Phase 6.

---

#### `run_setup_wizard(home_dir)` — The 2-Minute Interview
```
Input:  home_dir = "~/.lexagent"
Effect: Asks 14 questions in the terminal. Saves answers to SOUL.md.
Output: Returns the dictionary of answers.
```

This is the function called by `lex setup`. It uses a loop of `Prompt.ask()` calls (the Rich library's way of asking questions in the terminal) to collect: name, bar number, courts, practice areas, tone preference, firm details, and custom instructions.

Every question has a default answer — press Enter to skip. Once all answers are collected, it calls `save_soul()` to write them to disk.

---

#### `_parse_soul(content)` — The Decoder (internal helper)
```
Input:  "**Name:** Arjun Mehta\n**Bar Enrollment:** D/456/2015\n..."
Output: {"name": "Arjun Mehta", "bar_enrollment": "D/456/2015", "raw": "...", ...}
```

This is the private "workhorse" function inside `soul.py`. It takes the raw text of SOUL.md and turns it into a Python dictionary.

It uses **regex** (pattern matching) to find two types of content:
1. Lines like `**Name:** Arjun Mehta` → becomes `{"name": "Arjun Mehta"}`
2. Sections like `## Drafting Style\n...` → becomes `{"section_drafting_style": "..."}`

The function name starts with `_` (underscore) which is Python's way of saying "this is private — only call this from inside soul.py, not from outside."

---

### 📄 `lexagent/memory/matter_memory.py` — The Case File Log

When a doctor sees a patient, they write notes in a case file. When a lawyer works on a matter with LexAgent, this file records what happened — so the next session picks up exactly where the last one left off.

Every matter gets its own folder: `~/.lexagent/matters/M-4F2A9C1B/`

Inside that folder are two files:
- **`MEMORY.md`** — a human-readable log you can open in any text editor
- **`state.json`** — a machine-readable snapshot that LexAgent uses to reload the session

Here is what MEMORY.md looks like after two sessions:

```markdown
# Matter Memory — M-4F2A9C1B

Created: 2026-05-17 14:30

## Session — 2026-05-17 14:30
**Matter type:** Injunction application
**Parties:** plaintiff: ABC Ltd; defendant: XYZ Developers
**Jurisdiction:** Delhi High Court
**Purpose:** Stop construction on disputed property
**Summary:** ABC Ltd is seeking an injunction to stop XYZ from building on the land.

## Session — 2026-05-24 10:15
**Matter type:** Injunction application
**Parties:** plaintiff: ABC Ltd; defendant: XYZ Developers
**Jurisdiction:** Delhi High Court
**Purpose:** Add prayer for damages
**Summary:** Updated application adds Rs. 50 lakh damages claim.
```

---

**The functions in `matter_memory.py`:**

#### `matter_dir(matter_id, matters_dir)` — The Folder Finder
```
Input:  matter_id = "M-001",  matters_dir = "~/.lexagent/matters"
Output: Path to ~/.lexagent/matters/M-001/  (creates it if it doesn't exist)
```

Computes and creates the folder for one specific matter. Used by every other function that needs to read or write files for that matter.

---

#### `load_matter_memory(matter_id, matters_dir)` — The Log Reader
```
Input:  matter_id = "M-001"
Output: The full text of MEMORY.md as a string
  OR    None  (if this matter has no memory yet)
```

Reads the human-readable log for a matter. Used by `lex matter show M-001` to display the log on screen.

---

#### `save_matter_memory(matter_id, state, matters_dir)` — The Session Recorder
```
Input:  matter_id = "M-001",  state = (the full state after the graph ran)
Effect: Appends a new entry to MEMORY.md + overwrites state.json
Output: Path to the MEMORY.md file
```

This is the main function. It does two things at once:
1. **Appends** a new timestamped entry to MEMORY.md (never overwrites — always adds to the bottom)
2. **Overwrites** state.json with the latest state snapshot

The first session creates the file with a header. Every session after that just appends. This means you can see the full history of a matter by opening MEMORY.md in any text editor.

---

#### `load_state_snapshot(matter_id, matters_dir)` — The Session Reloader
```
Input:  matter_id = "M-001"
Output: A Python dictionary with all the state from the last session
  OR    None  (if no snapshot exists)
```

Reads `state.json` and returns it as a dictionary. Used by `lex draft --matter-id M-001` to restore the prior session — parties, jurisdiction, purpose — so the lawyer doesn't have to re-explain the matter from scratch.

---

#### `list_matters(matters_dir)` — The Table of Contents
```
Input:  matters_dir = "~/.lexagent/matters"
Output: [
    {"matter_id": "M-4F2A9C1B", "last_modified": "2026-05-24 10:15",
     "matter_type": "Injunction application", "parties": "ABC Ltd vs XYZ"},
    ...
  ]
```

Scans the matters folder, finds every matter directory, reads the state.json from each one, and returns a list sorted by most recently modified. Used by `lex matter list` to show the table on screen.

---

#### `_save_state_snapshot(matter_id, state, mdir)` — The Snapshot Saver (internal)
```
Input:  state = (the full LexState dict after the graph ran)
Effect: Writes state.json with all fields except messages
```

This private helper saves the state as JSON. One important decision: it **skips the `messages` field**. The messages list contains LangChain message objects that cannot be saved as JSON. We only need the text fields (matter type, parties, draft, etc.) for resuming a session anyway.

---

### 📄 `lexagent/memory/session_store.py` — The Searchable Archive

If `matter_memory.py` is the individual case file, then `session_store.py` is the **entire filing cabinet** — with a search engine built in.

It uses **SQLite** — a database that lives in a single file (`~/.lexagent/sessions.db`). SQLite is built into Python, needs no installation, works offline, and is fast enough for thousands of sessions.

**The magic feature: FTS5**

FTS5 stands for "Full Text Search, version 5." It's a special search engine built into SQLite. When you type `lex search "property dispute Delhi"`, FTS5 finds all sessions that contain those words in any of the stored fields (matter type, parties, jurisdiction, purpose, summary). This happens in milliseconds, even across thousands of sessions.

---

**The database table structure:**

```
sessions table:
┌────┬─────────────┬─────────────────────┬──────────────────────┬─────────┐
│ id │  matter_id  │     created_at      │     matter_type      │ parties │
├────┼─────────────┼─────────────────────┼──────────────────────┼─────────┤
│  1 │ M-4F2A9C1B  │ 2026-05-17T14:30:00 │ Injunction applicat. │ ABC Ltd │
│  2 │ M-7B3D1A2C  │ 2026-05-18T09:00:00 │ Legal notice         │ XYZ Ltd │
└────┴─────────────┴─────────────────────┴──────────────────────┴─────────┘
+ jurisdiction, purpose, summary, state_json columns (not shown for space)

sessions_fts (the search engine table):
Points at the sessions table. When you search "injunction", it finds row 1 instantly.
```

---

**The functions in `session_store.py`:**

#### `db_path(sessions_db)` — The Database Address
```
Input:  sessions_db = "~/.lexagent/sessions.db"
Output: /Users/arjun/.lexagent/sessions.db  (the actual path on disk)
```

Like `soul_path()` in soul.py — just converts the shorthand path into the real path.

---

#### `_connect(sessions_db)` — The Connection Manager (internal)
```
Effect: Opens the SQLite database file, keeps it open while you use it,
        automatically saves and closes when done.
```

This is a "context manager" — Python's way of saying "do something, then clean up automatically." You use it with the `with` keyword:

```python
with _connect() as conn:
    conn.execute("SELECT ...")
# Connection automatically closed and saved here
```

This pattern prevents the database from being left open (which can cause corruption) and ensures every write is saved. The underscore in `_connect` means it's private — only used inside session_store.py.

---

#### `init_db(sessions_db)` — The First-Time Setup
```
Input:  sessions_db = "~/.lexagent/sessions.db"
Effect: Creates the database file, the sessions table, the FTS5 search table,
        and the triggers that keep them in sync. Safe to call multiple times.
```

This function sets up the entire database structure. It uses `CREATE TABLE IF NOT EXISTS` — which means "create this table, but only if it doesn't already exist." This makes it **idempotent** — you can call it 100 times and the result is always the same, no errors.

It also creates two **triggers**. A trigger is like a robot that watches the table. When a new session is inserted, the trigger automatically adds it to the FTS5 search index. When a session is deleted, the trigger removes it from the search index. You never have to manually manage the search index.

---

#### `save_session(state, sessions_db)` — The Session Writer
```
Input:  state = (the full LexState after the graph ran)
Output: The row ID (an integer) of the newly saved session
```

Writes one row to the sessions table. The state has a `messages` field that contains LangChain message objects (not saveable as text), so those are excluded. Everything else — matter type, parties, jurisdiction, the full draft, the summary — goes into the row.

After writing the row, the trigger automatically adds it to the FTS5 search index. Next time you search, this session will appear in results.

---

#### `search_sessions(query, limit, sessions_db)` — The Search Engine
```
Input:  query = "property dispute Delhi",  limit = 10
Output: [
    {"matter_id": "M-4F2A9C1B", "matter_type": "Injunction application",
     "parties": "ABC Ltd; XYZ Developers", "jurisdiction": "Delhi HC", ...},
    ...
  ]
```

Runs a full-text search using FTS5. The SQL query does a `JOIN` between the `sessions` table (which has all the data) and the `sessions_fts` table (which does the keyword matching). Results come back sorted by relevance.

Used by `lex search "your query"`.

---

#### `list_sessions(limit, sessions_db)` — The Recent History
```
Input:  limit = 20
Output: The 20 most recent sessions, newest first
```

A simple database query: "give me the last 20 sessions, ordered by date."

---

#### `get_session_state(matter_id, sessions_db)` — The Matter Loader
```
Input:  matter_id = "M-4F2A9C1B"
Output: The state dictionary from the last session for that matter
  OR    None  (if no sessions exist)
```

Looks up the most recent session for a specific matter ID and returns the saved state as a dictionary. Used by `lex draft --matter-id` to continue a prior matter.

The `ORDER BY created_at DESC LIMIT 1` in the SQL query means "get the most recent one" — so if a matter has 10 sessions, you always get the latest.

---

## 🔄 How The Updated Nodes Work

### `nodes/intake.py` — Updated

**One new addition:** at the start of every intake run, before asking any questions, the intake node now calls `load_soul()`.

```
Before Phase 2:
  intake runs → asks questions → returns

After Phase 2:
  intake runs → loads SOUL.md → saves to state → asks questions → returns
```

If SOUL.md doesn't exist (first run before setup), `load_soul()` returns `None`. The intake node stores `None` into `state["lawyer_soul"]`. The draft node handles `None` gracefully by showing a tip to run `lex setup`.

If SOUL.md exists, the full parsed dictionary goes into `state["lawyer_soul"]`. Every node that runs after intake — including draft — can read it.

---

### `nodes/draft.py` — Updated

**Two new additions:**

**Addition 1 — SOUL.md in the system prompt:**

The system prompt is the "instruction manual" given to the AI at the start of every draft request. Before Phase 2, it had a placeholder for the lawyer profile. Now it fills in the actual SOUL.md text:

```
Before Phase 2:
  System prompt → "No profile loaded. Run lex setup."

After Phase 2 (with SOUL.md):
  System prompt → "## Your Lawyer Profile
                   # Lawyer Identity
                   **Name:** Arjun Mehta
                   **Bar Enrollment:** D/456/2015, Delhi Bar Council
                   ...
                   **Preferred Tone:** Senior formal
                   **Citation Preference:** Always include"
```

The AI reads this and immediately adjusts. It knows whose document it is writing. It knows the tone. It knows the citation preference. Without any extra instructions, every document becomes personalised.

**Addition 2 — Name in the drafting instruction:**

The instruction to the AI also now includes the lawyer's name:

```
Before Phase 2:
  "Please draft the legal document for the following matter:"

After Phase 2 (with name):
  "Please draft the legal document for Arjun Mehta:"
```

A small change, but it anchors every document to a specific practitioner.

---

## 🖥️ The Updated CLI — New Commands

### `lex setup` — The Profile Wizard

Before Phase 2, `lex setup` just showed a message: "coming in Phase 2." Now it does the real thing:

```
$ lex setup

┌─────────────────────────────────────────────────┐
│  ⚖ LexAgent Setup — Lawyer Profile              │
│                                                 │
│  Welcome to LexAgent. This 2-minute wizard     │
│  creates your lawyer profile at                 │
│  ~/.lexagent/SOUL.md.                           │
└─────────────────────────────────────────────────┘

Your full name: Arjun Mehta
Bar enrollment number: D/456/2015, Delhi Bar Council
Year called to the Bar: 2015
Primary courts: Delhi High Court, Saket District Court
...
(14 questions total, all skippable with Enter)
...
┌─────────────────────────────────────┐
│  ✓ Setup Complete                   │
│  Profile saved to ~/.lexagent/SOUL.md│
└─────────────────────────────────────┘
Sessions database ready at ~/.lexagent/sessions.db
```

After setup, `lex draft` will immediately personalise every output with your name and style.

If you run `lex setup` again, it asks "Overwrite?" before replacing your existing profile.

---

### `lex matter list` — The Case Table

```
$ lex matter list

┌────────────────────────────────────────────────────────────────────┐
│                         Saved Matters                              │
├─────────────┬──────────────────┬──────────────────┬───────────────┤
│ Matter ID   │ Last Modified    │ Type             │ Parties       │
├─────────────┼──────────────────┼──────────────────┼───────────────┤
│ M-4F2A9C1B  │ 2026-05-24 10:15 │ Injunction appl. │ ABC vs XYZ   │
│ M-7B3D1A2C  │ 2026-05-18 09:00 │ Legal notice     │ PQR vs ABC   │
└─────────────┴──────────────────┴──────────────────┴───────────────┘

Run `lex matter show <MATTER-ID>` to view details.
```

---

### `lex matter show M-4F2A9C1B` — The Case Log

```
$ lex matter show M-4F2A9C1B

┌──────────────────────────────────────────────────────────┐
│  Matter Memory — M-4F2A9C1B                              │
│                                                          │
│  ## Session — 2026-05-17 14:30                           │
│  Matter type: Injunction application                     │
│  Parties: plaintiff: ABC Ltd; defendant: XYZ Developers  │
│  Jurisdiction: Delhi High Court                          │
│  ...                                                     │
└──────────────────────────────────────────────────────────┘
```

---

### `lex search "property dispute"` — The Archive Search

```
$ lex search "property dispute"

┌──────────────────────────────────────────────────────────────────┐
│           Search results for: property dispute                    │
├─────────────┬────────────┬───────────────────┬──────────────────┤
│ Matter ID   │ Date       │ Type              │ Summary          │
├─────────────┼────────────┼───────────────────┼──────────────────┤
│ M-4F2A9C1B  │ 2026-05-17 │ Injunction appl.  │ ABC Ltd seeking  │
│ M-9C1E4D7F  │ 2026-04-02 │ Plaint            │ Property title   │
└─────────────┴────────────┴───────────────────┴──────────────────┘
```

---

### `lex draft --matter-id M-4F2A9C1B "Add damages prayer"` — Continue A Matter

```
$ lex draft --matter-id M-4F2A9C1B "Add damages prayer"

Resuming matter M-4F2A9C1B...

┌──────────────────────────────────────────┐
│  ⚖ LexAgent                              │
│  Matter ID: M-4F2A9C1B                   │
│  Brief: Add damages prayer               │
└──────────────────────────────────────────┘

Thinking...
(Agent already knows: ABC Ltd vs XYZ, Delhi HC, injunction matter)
(Only asks: "What specific damages? What amount?")
(Does NOT ask: "Who are the parties?" — it already knows)
```

---

## 📊 Code Review — What's Done, What's Planned

```
COMPONENT               STATUS    NOTES
─────────────────────────────────────────────────────────────────
memory/soul.py          ✅ Done   SOUL.md read/write + wizard.
                                  append_soul_note() hook ready
                                  for Phase 6 self-learning.

memory/matter_memory.py ✅ Done   MEMORY.md append-only log.
                                  state.json for session reload.
                                  Phase 5 RAG hook ready.

memory/session_store.py ✅ Done   SQLite + FTS5 search.
                                  Schema versioning built in
                                  for future migrations.

nodes/intake.py         ✅ Done   Now loads SOUL.md on every
(updated)                         pass. Graceful if not found.

nodes/draft.py          ✅ Done   SOUL.md injected into system
(updated)                         prompt. Lawyer name in draft
                                  instruction.

cli.py                  ✅ Done   lex setup (real wizard),
(updated)                         lex matter list/show,
                                  lex search, --matter-id,
                                  auto-save after every draft.

tests/test_memory.py    ✅ Done   42 tests. Covers all 3 memory
                                  modules, all edge cases
                                  (no file, first run, append,
                                  FTS search, snapshot reload).

─────────────────────────────────────────────────────────────────
PHASE 2 COMPLETENESS: 100% ██████████
─────────────────────────────────────────────────────────────────

WHAT PHASE 2 CANNOT DO YET:
  ✗ Auto-select the right skill template (injunction vs plaint vs notice) — Phase 3
  ✗ Real Indian Kanoon citations — Phase 4
  ✗ Word document export — Phase 5
  ✗ SOUL.md self-updates after matters (self-learning) — Phase 6
  ✗ Telegram access from phone — Phase 7
```

---

## 🗓️ What We Decided In This Session

### 1. Files over databases for human-readable memory
**What:** MEMORY.md is a plain text file, not a database row.  
**Why:** A lawyer should be able to open it in Notepad, read it, edit it, or email it. Databases require tools to read. Markdown needs nothing.

### 2. Both formats for every matter
**What:** Every matter gets both `MEMORY.md` (human-readable) AND `state.json` (machine-readable).  
**Why:** MEMORY.md is for the lawyer. state.json is for LexAgent to reload. Neither format is "better" — they serve different audiences.

### 3. FTS5 over a vector database
**What:** We use SQLite FTS5 for search, not a vector store like Pinecone or Chroma.  
**Why:** FTS5 is zero-dependency, zero-cost, works offline, and is fast enough for any individual lawyer's case history (thousands of matters, not millions). Phase 5 will add embeddings on top for semantic search ("find matters similar to this one, not just keyword matches").

### 4. Save-after-draft, not save-during
**What:** Sessions are saved to SQLite and MEMORY.md after the draft completes, not during.  
**Why:** If something goes wrong mid-session (network error, the AI fails), you don't want a half-finished session in your database. Save only when there's something worth saving.

### 5. Failure to save never crashes the CLI
**What:** The save functions (`_save_session_and_memory`) are wrapped in `try/except`. If saving fails, the CLI shows a gentle warning but continues.  
**Why:** The lawyer already has their draft on screen. A failed database write should never take away what they already got.

---

## 🚦 The 8-Phase Roadmap

```
PHASE 1 ████████████ DONE
Foundation. Get something running.
lex draft works end-to-end.

PHASE 2 ████████████ DONE (this phase)
Memory & Identity.
SOUL.md, matter memory, SQLite sessions.
"Output references lawyer's name and style. Matters are remembered."

PHASE 3 ░░░░░░░░░░░░ Next
Skills System.
Auto-select skill by matter type.
"Injunction draft follows civil_litigation.md structure."

PHASE 4 ░░░░░░░░░░░░
Tools: Real Legal Data.
Indian Kanoon, eCourts, CourtListener — all BYOK/BYO-MCP.
Multi-agent: Research + Drafting + Citation as separate AI workers.
This is the "Openclaw" layer — open connections to legal databases.

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
# 1. First time only — create your lawyer profile
uv run lex setup

# 2. Draft a document (now personalised to you)
uv run lex draft "I need an injunction for a property dispute in Delhi"

# 3. See your saved matters
uv run lex matter list

# 4. Read the memory log for a specific matter
uv run lex matter show M-XXXXXXXX

# 5. Search all your past matters
uv run lex search "property dispute"

# 6. Continue a prior matter
uv run lex draft --matter-id M-XXXXXXXX "Add a prayer for damages"

# 7. Run all tests (should say 56 passed)
uv run pytest tests/ -v

# 8. See current settings
uv run lex config
```

---

## 🗂️ Where Files Live After Phase 2

```
~/.lexagent/
├── SOUL.md                    ← Your lawyer identity (created by lex setup)
├── sessions.db                ← SQLite database (all sessions, searchable)
└── matters/
    ├── M-4F2A9C1B/
    │   ├── MEMORY.md          ← Human-readable log of all sessions for this matter
    │   └── state.json         ← Machine-readable snapshot (for lex draft --matter-id)
    ├── M-7B3D1A2C/
    │   ├── MEMORY.md
    │   └── state.json
    └── ...

~/Lexagent/                    ← The project code (separate from your data)
├── lexagent/
│   ├── memory/
│   │   ├── __init__.py
│   │   ├── soul.py
│   │   ├── matter_memory.py
│   │   └── session_store.py
│   ├── nodes/
│   │   ├── intake.py  (updated)
│   │   └── draft.py   (updated)
│   └── cli.py         (updated)
└── tests/
    ├── test_state.py   (14 tests, Phase 1)
    └── test_memory.py  (42 tests, Phase 2)
```

**The key insight:** Your data (`~/.lexagent/`) is completely separate from the code (`~/Lexagent/`). You can update LexAgent, delete the code folder, even reinstall everything — and your SOUL.md, your matter memory, and your session history are untouched. They live in your home directory, not in the project.

---

*Phase 2 completed — May 2026*  
*Author: Brahm (brahmsareen04@gmail.com)*  
*Next: Phase 3 — Skills System (auto-select civil litigation / legal notice / writ skill)*
