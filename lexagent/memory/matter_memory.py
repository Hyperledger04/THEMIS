# WHY: Per-matter memory allows LexAgent to remember what happened in previous sessions
# for the same matter. A lawyer working on a complex case over several weeks can continue
# from where they left off — the agent already knows the parties, the court, past decisions.
#
# Storage: ~/.lexagent/matters/{matter_id}/MEMORY.md
# Format: append-only markdown log with timestamped entries.
# Phase 5 will add RAG (retrieval-augmented generation) over past matter memory.

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from lexagent.state import LexState

MEMORY_FILENAME = "MEMORY.md"
STATE_FILENAME = "state.json"


def matter_dir(matter_id: str, matters_dir: str = "~/.lexagent/matters") -> Path:
    """Returns the Path for a specific matter's directory. Creates it if needed."""
    path = Path(matters_dir).expanduser() / matter_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_matter_memory(matter_id: str, matters_dir: str = "~/.lexagent/matters") -> Optional[str]:
    """
    Load the MEMORY.md for a matter.
    Returns None if no memory exists yet (first session for this matter).
    """
    mem_path = matter_dir(matter_id, matters_dir) / MEMORY_FILENAME
    if not mem_path.exists():
        return None
    return mem_path.read_text(encoding="utf-8")


def save_matter_memory(matter_id: str, state: LexState, matters_dir: str = "~/.lexagent/matters") -> Path:
    """
    Append a session summary to MEMORY.md for the given matter.
    Called at the end of each session so context is available next time.
    Returns the path where memory was saved.
    """
    mdir = matter_dir(matter_id, matters_dir)
    mem_path = mdir / MEMORY_FILENAME
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Build the session summary block
    parties = state.get("parties") or {}
    if isinstance(parties, dict):
        parties_str = "; ".join(f"{k}: {v}" for k, v in parties.items() if v)
    else:
        parties_str = str(parties)

    entry_lines = [
        f"\n## Session — {timestamp}",
        f"**Matter type:** {state.get('matter_type') or 'Unknown'}",
        f"**Parties:** {parties_str or 'Unknown'}",
        f"**Jurisdiction:** {state.get('jurisdiction') or 'Unknown'}",
        f"**Purpose:** {state.get('purpose') or 'Unknown'}",
    ]

    if state.get("plain_english_summary"):
        entry_lines.append(f"\n**Summary:** {state['plain_english_summary']}")

    if state.get("statutes_cited"):
        entry_lines.append(f"\n**Statutes cited:** {', '.join(state['statutes_cited'])}")

    if state.get("research_findings"):
        cases = [f"{r.get('case_name', '')} ({r.get('citation', '')})" for r in state["research_findings"]]
        entry_lines.append(f"\n**Cases researched:** {', '.join(cases)}")

    if state.get("unverified_citations"):
        entry_lines.append(f"\n**⚠ Unverified citations:** {', '.join(state['unverified_citations'])}")

    if state.get("error"):
        entry_lines.append(f"\n**Error recorded:** {state['error']}")

    entry = "\n".join(entry_lines) + "\n"

    # Initialise the file with a header if this is the first session
    if not mem_path.exists():
        header = f"# Matter Memory — {matter_id}\n\nCreated: {timestamp}\n"
        mem_path.write_text(header, encoding="utf-8")

    with mem_path.open("a", encoding="utf-8") as f:
        f.write(entry)

    # Also persist the full state as JSON so future sessions can reload it
    _save_state_snapshot(matter_id, state, mdir)

    return mem_path


def load_state_snapshot(matter_id: str, matters_dir: str = "~/.lexagent/matters") -> Optional[dict]:
    """
    Load the last saved state snapshot for a matter.
    Used when --matter-id is passed to `lex draft` to continue a matter.
    Returns None if no snapshot exists.
    """
    snap_path = matter_dir(matter_id, matters_dir) / STATE_FILENAME
    if not snap_path.exists():
        return None
    with snap_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def list_matters(matters_dir: str = "~/.lexagent/matters") -> list[dict]:
    """
    List all saved matters, sorted by most recently modified.
    Returns a list of dicts: [{matter_id, created, last_modified, matter_type, parties}]
    """
    base = Path(matters_dir).expanduser()
    if not base.exists():
        return []

    matters = []
    for d in sorted(base.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if not d.is_dir():
            continue

        mem_path = d / MEMORY_FILENAME
        snap_path = d / STATE_FILENAME

        # Skip ghost directories that were created but never saved — no content at all.
        if not mem_path.exists() and not snap_path.exists():
            continue

        entry: dict = {
            "matter_id": d.name,
            "last_modified": datetime.fromtimestamp(d.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
            "matter_type": "",
            "parties": "",
        }

        if snap_path.exists():
            try:
                with snap_path.open("r", encoding="utf-8") as f:
                    snap = json.load(f)
                entry["matter_type"] = snap.get("matter_type") or ""
                parties = snap.get("parties") or {}
                if isinstance(parties, dict):
                    entry["parties"] = "; ".join(f"{k}: {v}" for k, v in parties.items() if v)
                else:
                    entry["parties"] = str(parties)
            except (json.JSONDecodeError, OSError):
                pass

        matters.append(entry)

    return matters


# -----------------------------------------------------------------------
# Internal helpers
# -----------------------------------------------------------------------

def _save_state_snapshot(matter_id: str, state: LexState, mdir: Path) -> None:
    """
    Save a JSON snapshot of the state (serialisable fields only).
    The messages list contains LangChain message objects which are not JSON-serialisable,
    so we exclude them and store just the text fields.
    """
    # Only snapshot the fields that are plain Python types (str, dict, list of str, bool)
    serialisable = {
        k: v for k, v in state.items()
        if k != "messages" and isinstance(v, (str, dict, list, bool, int, float, type(None)))
    }
    snap_path = mdir / STATE_FILENAME
    with snap_path.open("w", encoding="utf-8") as f:
        json.dump(serialisable, f, indent=2, ensure_ascii=False)
