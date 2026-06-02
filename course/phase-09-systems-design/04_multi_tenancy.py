"""
Phase 9 — 04: Multi-Tenancy Patterns
======================================
Run:  python 04_multi_tenancy.py
      (no external deps — pure stdlib)

Multi-tenancy: one LexAgent deployment serves many law firms.
Each firm's data must be invisible to every other firm.
"""

import json
import pathlib
import sqlite3
import tempfile
import uuid
from dataclasses import dataclass, field
from typing import Any

# ── SECTION 1: THE DATA BREACH SCENARIO ─────────────────────────────────────
#
# Without tenant isolation, a single bug can expose Client A's matter to Client B.
#
# Bug scenario (no firm_id in query):
#
#   ❌ WRONG — Firm B can request matter_id from Firm A
#   SELECT * FROM matters WHERE matter_id = $1
#
# With firm_id enforcement:
#
#   ✓ CORRECT — Firm B gets nothing even if they know Firm A's matter_id
#   SELECT * FROM matters WHERE matter_id = $1 AND firm_id = $2
#
# The firm_id comes from the JWT (verified by Depends(verify_jwt)) — not from
# the request body.  Clients cannot forge their own firm_id.
#
# WHY JWT-sourced firm_id?
#   If firm_id were in the request body, a malicious client could set
#   firm_id="competitor_firm" and read their data.

# ── SECTION 2: FIRM_ID IN LEXSTATE ──────────────────────────────────────────
#
# Every field in LexState that is firm-sensitive carries firm_id.
# In lexagent/state.py, LexState includes:
#
#   firm_id: str          # "personal" for solo use, "acme_law" for firms
#   user_id: str          # individual user within the firm
#   matter_id: str        # unique per matter, NOT per firm (we add firm_id to queries)
#
# "personal" mode:
#   A solo lawyer can use LexAgent without setting up any firm infrastructure.
#   firm_id = "personal" — all isolation patterns still apply, just scoped to them.

@dataclass
class LexStateMini:
    """
    Minimal slice of LexState showing tenant fields.
    Full definition: lexagent/state.py
    """
    firm_id: str = "personal"
    user_id: str = "u1"
    matter_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    matter: str = ""
    draft_output: str = ""


# ── SECTION 3: FILE-SYSTEM ISOLATION ─────────────────────────────────────────
#
# SOUL.md and MEMORY.md are stored per-firm:
#
#   ~/.lexagent/personal/SOUL.md          ← solo lawyer
#   ~/.lexagent/acme_law/SOUL.md          ← Acme Law firm
#   ~/.lexagent/acme_law/matters/m001/MEMORY.md
#   ~/.lexagent/rival_firm/matters/m002/MEMORY.md   ← completely separate subtree
#
# No firm can traverse another firm's directory because:
#   a) The API only ever constructs paths using the JWT-sourced firm_id.
#   b) The path is always rooted at ~/.lexagent/{firm_id}/...

def firm_base_path(root: pathlib.Path, firm_id: str) -> pathlib.Path:
    """
    Returns the base directory for a firm.
    WHY: centralise path construction so every code path uses the same formula.
    """
    # Sanitise firm_id — prevent path traversal attacks like firm_id="../../etc"
    safe = firm_id.replace("/", "_").replace("..", "_")
    return root / safe


def matter_path(root: pathlib.Path, firm_id: str, matter_id: str) -> pathlib.Path:
    return firm_base_path(root, firm_id) / "matters" / matter_id


def demo_filesystem_isolation(root: pathlib.Path) -> None:
    """Create two firms' matter directories and verify they're separate."""
    firms = [
        ("firm_a", "m001"),
        ("firm_a", "m002"),
        ("firm_b", "m001"),   # same matter_id as firm_a — different directory
    ]

    print("── File-system isolation demo ──")
    for firm_id, mid in firms:
        path = matter_path(root, firm_id, mid)
        path.mkdir(parents=True, exist_ok=True)
        memory_file = path / "MEMORY.md"
        memory_file.write_text(f"# Memory for {firm_id}/{mid}\n")
        print(f"   Created: {path.relative_to(root)}")

    # Verify firm_a cannot see firm_b's directories by listing only firm_a subtree
    firm_a_root = firm_base_path(root, "firm_a")
    firm_a_matters = list(firm_a_root.glob("matters/*"))
    firm_b_root = firm_base_path(root, "firm_b")
    firm_b_matters = list(firm_b_root.glob("matters/*"))

    print(f"\n   firm_a matters: {[p.name for p in firm_a_matters]}")
    print(f"   firm_b matters: {[p.name for p in firm_b_matters]}")

    # firm_a/matters/m001 and firm_b/matters/m001 are different inodes
    a_inode = (firm_a_root / "matters" / "m001").stat().st_ino
    b_inode = (firm_b_root / "matters" / "m001").stat().st_ino
    assert a_inode != b_inode, "Inodes should differ — separate directories"
    print(f"\n   ✓ firm_a/m001 inode={a_inode} ≠ firm_b/m001 inode={b_inode}")
    print("   ✓ File-system isolation confirmed\n")


# ── SECTION 4: QDRANT ISOLATION ───────────────────────────────────────────────
#
# Each matter gets its own Qdrant collection:
#
#   firm_a_m001   ← Firm A, Matter 1
#   firm_b_m001   ← Firm B, Matter 1 (different collection despite same matter_id)
#
# At search time:
#   collection_name = f"{state['firm_id']}_{state['matter_id']}"
#   results = qdrant_client.search(collection_name, query_vector, limit=5)
#
# Even if a bug passes the wrong matter_id, the wrong firm_id in the collection
# name means zero results — not a data leak.

def qdrant_collection_name(firm_id: str, matter_id: str) -> str:
    """
    Canonical naming function — used by retriever.py and any code that
    creates / searches Qdrant collections.

    WHY a function instead of an f-string inline?
      Single definition → rename once if the convention changes.
    """
    return f"{firm_id}_{matter_id}"


# ── SECTION 5: SQL ISOLATION ──────────────────────────────────────────────────
#
# Every table that holds tenant data has a `firm_id` column.
# Every SELECT includes `AND firm_id = ?` (Postgres: `AND firm_id = $2`).
#
# We use SQLite here so this file runs without a server.
# The pattern is identical for Postgres — only the placeholder changes.

def demo_sql_isolation(db_path: str) -> None:
    """
    Demonstrate that firm_id enforcement prevents cross-tenant reads.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Create a simple matters table with firm_id column
    cur.execute("""
        CREATE TABLE IF NOT EXISTS matters (
            matter_id TEXT NOT NULL,
            firm_id   TEXT NOT NULL,
            brief     TEXT,
            PRIMARY KEY (matter_id, firm_id)
        )
    """)

    # Insert matters for two firms
    cur.executemany(
        "INSERT OR REPLACE INTO matters VALUES (?, ?, ?)",
        [
            ("m001", "firm_a", "Bail petition — Delhi HC"),
            ("m002", "firm_a", "Property dispute — Bombay HC"),
            ("m001", "firm_b", "Trade mark infringement"),
        ],
    )
    conn.commit()

    print("── SQL isolation demo ──")

    # ✓ Correct: firm_a fetches their own matter m001
    row = cur.execute(
        "SELECT * FROM matters WHERE matter_id = ? AND firm_id = ?",
        ("m001", "firm_a"),
    ).fetchone()
    print(f"   firm_a fetches m001: '{row['brief']}'")

    # ✓ Correct: firm_b fetches their own matter m001
    row = cur.execute(
        "SELECT * FROM matters WHERE matter_id = ? AND firm_id = ?",
        ("m001", "firm_b"),
    ).fetchone()
    print(f"   firm_b fetches m001: '{row['brief']}'")

    # ✓ Security: firm_b tries to read firm_a's matter — gets nothing
    row = cur.execute(
        "SELECT * FROM matters WHERE matter_id = ? AND firm_id = ?",
        ("m002", "firm_b"),                    # ← firm_b asking for firm_a's m002
    ).fetchone()
    print(f"   firm_b tries to read firm_a/m002: {row} (expected None)")
    assert row is None, "Isolation broken — firm_b can read firm_a's matter!"
    print("   ✓ SQL isolation confirmed\n")

    conn.close()


# ── SECTION 6: PERSONAL MODE ─────────────────────────────────────────────────
#
# Solo lawyers don't need firm infrastructure.
# firm_id = "personal" flows through every isolation layer unchanged:
#
#   File path:    ~/.lexagent/personal/SOUL.md
#   Qdrant:       personal_m001
#   SQL:          WHERE firm_id = 'personal'
#
# The code path is identical — no special-casing needed.
# This is by design: if a solo lawyer later joins a firm, they change firm_id
# and everything "just works".

def personal_mode_example() -> None:
    state = LexStateMini(
        firm_id="personal",
        user_id="brahm_sareen",
        matter_id="bail_001",
        matter="Bail petition for accused in NDPS case",
    )
    print("── Personal mode demo ──")
    print(f"   firm_id     : {state.firm_id}")
    print(f"   user_id     : {state.user_id}")
    print(f"   matter_id   : {state.matter_id}")
    print(f"   Qdrant coll : {qdrant_collection_name(state.firm_id, state.matter_id)}")
    print(f"   SOUL.md path: ~/.lexagent/{state.firm_id}/SOUL.md")
    print()


# ── SECTION 7: FULL DEMO ─────────────────────────────────────────────────────

def run_demo() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = pathlib.Path(tmpdir)

        personal_mode_example()
        demo_filesystem_isolation(root)

        db_path = str(root / "lexagent_test.db")
        demo_sql_isolation(db_path)

    print("── Qdrant collection names ──")
    for firm, matter in [("firm_a", "m001"), ("firm_b", "m001"), ("personal", "bail_001")]:
        name = qdrant_collection_name(firm, matter)
        print(f"   {firm:12s}  {matter:10s}  →  '{name}'")
    print()
    print("── All isolation checks passed ──")


if __name__ == "__main__":
    run_demo()


# ── PAUSE AND THINK ──────────────────────────────────────────────────────────
#
# 1. Open lexagent/state.py.
#    Does LexState currently have a `firm_id` field?
#    If not, what would you need to change to add it, and which nodes
#    would need updating to propagate it?
#
# 2. Open lexagent/security/ (if it exists).
#    Is `firm_id` extracted from the JWT or from the request body?
#    What attack does JWT-sourced firm_id prevent?
#
# 3. The `firm_base_path()` function sanitises firm_id with `.replace("..", "_")`.
#    Name one other character that could be dangerous in a file path
#    and should also be sanitised.
#
# 4. `personal` mode uses firm_id="personal" — but two solo lawyers both use
#    firm_id="personal".  Is this a problem?  How does the user_id field
#    provide the second layer of isolation for file paths vs. SQL?
#
# 5. A Qdrant collection named `firm_a_m001` can't be "shared" with firm_b.
#    But what if a partner at firm_a wants to share a matter with an associate
#    at firm_a?  How would you implement intra-firm access control?
