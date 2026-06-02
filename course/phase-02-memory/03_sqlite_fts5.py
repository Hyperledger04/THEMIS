"""
03 — SQLite from Scratch, Then FTS5 for Legal Text
====================================================
The two file-based stores (SOUL.md, MEMORY.md) are great for human reading.
But how do you search across ALL matters? How do you find "every matter where
I cited Maneka Gandhi" without opening 50 MEMORY.md files?

Answer: SQLite with FTS5 (Full-Text Search, version 5).

This lesson builds from zero:
  1. What SQLite is and why it needs no server
  2. Creating tables and inserting data
  3. Why LIKE is not good enough for legal text
  4. FTS5: creating a virtual table and running full-text queries
  5. Keeping FTS5 in sync with the main table

python 03_sqlite_fts5.py
"""

import sqlite3
import tempfile
from pathlib import Path

# Use a temp file so this lesson is safe and repeatable
DB_PATH = Path(tempfile.mkdtemp()) / "sessions.db"

print(f"Working with database at: {DB_PATH}")
print()

# ── SECTION 1: SQLITE — NO SERVER NEEDED ────────────────────────────────────
#
# Most databases need a server process: PostgreSQL, MySQL, MongoDB.
# You start the server, connect to it over TCP, it manages memory.
#
# SQLite is different:
#   - The entire database is ONE FILE on disk (sessions.db)
#   - Your Python process reads/writes it directly (no TCP, no server)
#   - sqlite3 is built into Python — zero extra dependencies
#   - Handles gigabytes of data comfortably
#
# WHY SQLite for LexAgent?
#   - Lawyers run LexAgent locally (not on a shared server)
#   - No Docker, no Postgres, no config required
#   - The DB file can be backed up with a simple `cp sessions.db backup.db`
#   - It is the right tool for a single-user CLI application

print("── SECTION 1: Connecting to SQLite ─────────────────────────────────────")
print()

# sqlite3.connect() creates the file if it doesn't exist.
# WHY check_same_thread=False?
# SQLite's Python binding by default refuses to share a connection across
# threads. We set this to False because our async code may hop between
# asyncio event loop threads. We handle safety ourselves (see lesson 04).
conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)

# Return rows as sqlite3.Row objects (access columns by name, not index)
# WHY row_factory? conn.execute("SELECT id, summary FROM sessions").fetchone()[1]
# is fragile. Row objects let you do row["summary"] — much safer.
conn.row_factory = sqlite3.Row

print(f"  Connected. DB file size: {DB_PATH.stat().st_size} bytes (empty)")
print()

# ── SECTION 2: CREATING THE SESSIONS TABLE ───────────────────────────────────
#
# Design decisions for each column:
#   id         TEXT PRIMARY KEY  — matter_id slug, e.g. "sharma-v-state-2024"
#   matter_id  TEXT              — same as id here; useful for joins in future
#   created_at TEXT              — ISO 8601 string; SQLite has no native datetime
#   updated_at TEXT              — last time a session was modified
#   summary    TEXT              — one-paragraph human summary of the session
#   state_json TEXT              — full LexState serialised as JSON
#
# WHY TEXT for everything? SQLite is "type-flexible" — TEXT, INTEGER, REAL, BLOB
# are type affinities, not strict types. Storing timestamps as TEXT ISO strings
# is idiomatic SQLite: they sort correctly because ISO 8601 is lexicographic.

print("── SECTION 2: Creating tables ───────────────────────────────────────────")
print()

CREATE_SESSIONS = """
CREATE TABLE IF NOT EXISTS sessions (
    id          TEXT PRIMARY KEY,
    matter_id   TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    summary     TEXT,
    state_json  TEXT
)
"""

conn.execute(CREATE_SESSIONS)
conn.commit()
print("  sessions table created.")

# ── SECTION 3: WHY LIKE IS NOT ENOUGH FOR LEGAL TEXT ────────────────────────
#
# Suppose you want to find all sessions mentioning "writ petition":
#
#   SELECT * FROM sessions WHERE summary LIKE '%writ petition%'
#
# Problems with LIKE:
#
#   1. PERFORMANCE: LIKE with a leading wildcard ('%...') scans EVERY ROW.
#      For 10,000 sessions: 10,000 string comparisons per query. O(n).
#
#   2. TOKENIZATION: LIKE is byte-comparison. It doesn't understand that
#      "petition" and "Petition" and "PETITION" are the same word.
#      You need LIKE '%writ petition%' AND LIKE '%Writ Petition%' etc.
#
#   3. MULTI-WORD: "writ petition filed under article 226" — LIKE can't
#      rank results by relevance. All matches are equal.
#
#   4. LEGAL CITATIONS: "AIR 1978 SC 597" must be found as a unit, not
#      decomposed. FTS5's phrase search handles this: MATCH '"AIR 1978 SC 597"'
#
# FTS5 solves all of this.

print()
print("── SECTION 3: Why LIKE fails for legal text ─────────────────────────────")
print()
print("  LIKE '%writ petition%'  → full table scan, O(n), case-sensitive chaos")
print("  FTS5 MATCH 'writ petition' → indexed, O(log n), tokenised, ranked")
print()

# ── SECTION 4: CREATING THE FTS5 VIRTUAL TABLE ──────────────────────────────
#
# FTS5 is a SQLite "virtual table" — it looks like a table but is actually
# an inverted index (like the index at the back of a law textbook).
#
# content='sessions'       — this FTS5 table mirrors the content of `sessions`
# content_rowid='rowid'    — links FTS5 rows to sessions rows via rowid
#
# WHY content table (not regular FTS5)?
# A "content table" means FTS5 stores ONLY the index, not the actual text.
# Actual text stays in `sessions`. This saves disk space.
# Tradeoff: you must keep the FTS index in sync manually (see Section 5).

CREATE_FTS = """
CREATE VIRTUAL TABLE IF NOT EXISTS sessions_fts
USING fts5(
    summary,
    state_json,
    content='sessions',
    content_rowid='rowid'
)
"""

conn.execute(CREATE_FTS)
conn.commit()
print("── SECTION 4: FTS5 virtual table created ───────────────────────────────")
print()

# ── SECTION 5: INSERTING DATA AND KEEPING FTS5 IN SYNC ──────────────────────
#
# FTS5 content tables do NOT auto-update when you INSERT into `sessions`.
# After every INSERT, you must also INSERT into the FTS5 table.
# WHY? FTS5 content tables trade automation for disk efficiency.
#
# The rebuild command:
#   INSERT INTO sessions_fts(sessions_fts) VALUES('rebuild')
# reindexes everything in `sessions` from scratch.
# Use 'rebuild' after bulk inserts; use per-row insert for single rows.

print("── SECTION 5: Inserting sessions and syncing FTS5 ──────────────────────")
print()

# Three realistic LexAgent sessions
sessions = [
    {
        "id": "sharma-v-state-2024",
        "matter_id": "sharma-v-state-2024",
        "created_at": "2024-03-10T09:15:00",
        "updated_at": "2024-03-10T11:42:00",
        "summary": "Writ petition under Article 226 challenging eviction notice. "
                   "Cited Maneka Gandhi v. Union of India AIR 1978 SC 597 and "
                   "Olga Tellis v. Bombay Municipal Corporation AIR 1986 SC 180. "
                   "Bombay High Court jurisdiction. Petitioner: SHARMA.",
        "state_json": '{"matter_type": "writ petition", "jurisdiction": "Bombay HC"}',
    },
    {
        "id": "ibc-abc-corp-2025",
        "matter_id": "ibc-abc-corp-2025",
        "created_at": "2025-01-20T14:00:00",
        "updated_at": "2025-01-20T16:30:00",
        "summary": "Section 7 IBC petition against ABC Corp for default on term loan. "
                   "Financial creditor is Punjab National Bank. Outstanding: INR 4.2 Cr. "
                   "NCLT Mumbai bench. Limitation within three years of NPA declaration.",
        "state_json": '{"matter_type": "ibc section 7", "jurisdiction": "NCLT Mumbai"}',
    },
    {
        "id": "section-138-ni-act-2024",
        "matter_id": "section-138-ni-act-2024",
        "created_at": "2024-11-05T10:00:00",
        "updated_at": "2024-11-05T10:45:00",
        "summary": "Criminal complaint under Section 138 Negotiable Instruments Act "
                   "for cheque dishonour. Drawer: XYZ Enterprises. Amount: INR 8 lakhs. "
                   "Metropolitan Magistrate, Esplanade Court, Mumbai.",
        "state_json": '{"matter_type": "section 138 ni act", "jurisdiction": "Mumbai"}',
    },
]

for s in sessions:
    # Step 1: INSERT into main table
    conn.execute(
        """
        INSERT OR REPLACE INTO sessions
            (id, matter_id, created_at, updated_at, summary, state_json)
        VALUES
            (:id, :matter_id, :created_at, :updated_at, :summary, :state_json)
        """,
        s,
    )

conn.commit()

# Step 2: Rebuild FTS5 index after bulk insert
# WHY 'rebuild' not per-row? We just inserted 3 rows at once.
# For single-row inserts inside a class, use per-row approach (see lesson 04).
conn.execute("INSERT INTO sessions_fts(sessions_fts) VALUES('rebuild')")
conn.commit()

print(f"  Inserted {len(sessions)} sessions. FTS5 index rebuilt.")
print()

# ── SECTION 6: QUERYING WITH FTS5 ───────────────────────────────────────────
#
# FTS5 MATCH syntax:
#   'writ petition'          — both words must appear (implicit AND)
#   '"AIR 1978 SC 597"'      — exact phrase (quoted)
#   'writ OR ibc'            — either word
#   'section 138 -petition'  — must have "section 138", must NOT have "petition"
#
# We join sessions_fts back to sessions to get the full row content.
# WHY JOIN? FTS5 content table only stores the index, not the text.
# The text is in sessions; we retrieve it via rowid join.

print("── SECTION 6: FTS5 search queries ──────────────────────────────────────")
print()

def search_sessions(conn: sqlite3.Connection, query: str) -> list[dict]:
    """
    Search sessions using FTS5.
    Returns a list of result dicts with id, matter_id, summary.

    The JOIN pattern:
      sessions_fts.rowid = sessions.rowid
    This maps FTS5 index rows back to main table rows.
    """
    results = conn.execute(
        """
        SELECT s.id, s.matter_id, s.created_at, s.summary
        FROM sessions s
        WHERE s.rowid IN (
            SELECT rowid FROM sessions_fts
            WHERE sessions_fts MATCH ?
            ORDER BY rank           -- FTS5 built-in relevance ranking
        )
        """,
        (query,),
    ).fetchall()
    return [dict(r) for r in results]


# Test queries — all using real Indian legal terminology
queries = [
    "writ petition",                    # should match sharma-v-state-2024
    '"Article 226"',                    # exact phrase match
    "section 138",                      # NI Act matter
    "IBC OR insolvency",               # OR query
    '"Maneka Gandhi"',                  # case name as phrase
    "NCLT Mumbai",                      # tribunal + city
]

for q in queries:
    results = search_sessions(conn, q)
    matter_ids = [r["matter_id"] for r in results]
    print(f"  MATCH {q!r}")
    print(f"    → {matter_ids if matter_ids else '(no results)'}")
    print()

# ── SECTION 7: FTS5 vs LIKE — PERFORMANCE COMPARISON ────────────────────────
#
# With 3 rows we can't measure real performance.
# But let's demonstrate the CORRECTNESS difference:

print("── SECTION 7: FTS5 vs LIKE — correctness ────────────────────────────────")
print()

# LIKE: case-sensitive on text columns (depends on collation)
like_results = conn.execute(
    "SELECT id FROM sessions WHERE summary LIKE ?",
    ("%writ petition%",)
).fetchall()
print(f"  LIKE '%writ petition%' : {[r[0] for r in like_results]}")

# FTS5: case-insensitive, tokenised
fts_results = search_sessions(conn, "Writ Petition")  # capitalised — still works
print(f"  FTS5 MATCH 'Writ Petition': {[r['matter_id'] for r in fts_results]}")
print()
print("  FTS5 is case-insensitive by default. LIKE is not (without COLLATE).")
print()

conn.close()
print(f"  DB file final size: {DB_PATH.stat().st_size} bytes")
print()

# ── PAUSE AND THINK ──────────────────────────────────────────────────────────

print("""
── PAUSE AND THINK ─────────────────────────────────────────────────────────

Open lexagent/memory/session_store.py in your editor and answer these:

1. The real sessions table has a column called `lawyer_id`.
   Why? LexAgent is designed to eventually support multiple lawyers on one
   machine (e.g., a chambers with 3 junior advocates). How does lawyer_id
   enable that?

2. FTS5 content tables require manual sync. The real SessionStore uses
   per-row INSERT into sessions_fts rather than 'rebuild'.
   What is the per-row INSERT SQL for FTS5? Write it out.
   (Hint: look for "INSERT INTO sessions_fts" in session_store.py.)

3. FTS5 MATCH raises an exception if the query string is malformed.
   For example: MATCH 'AND OR' is invalid FTS5 syntax.
   How should search_sessions() handle malformed queries from a lawyer?

4. We stored state_json as TEXT. The real state can be 50KB+ (draft output,
   research findings, full message history).
   Should state_json be in the sessions table or a separate blobs table?
   What are the tradeoffs for each approach?

5. Run this in a Python shell:
   import sqlite3; conn = sqlite3.connect(":memory:")
   conn.execute("CREATE VIRTUAL TABLE t USING fts5(body)")
   conn.execute("INSERT INTO t VALUES ('AIR 1978 SC 597')")
   print(conn.execute("SELECT * FROM t WHERE t MATCH '1978'").fetchall())
   What does this tell you about how FTS5 tokenises citation strings?
""")
