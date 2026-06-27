# Wisdom accumulation: extract durable insights from completed drafts and append
# to ~/.themis/wisdom.md. Each matter contributes a few lines — over time the
# file becomes a personalised legal knowledge base specific to the lawyer's practice.
#
# WHY: The agent should improve the more it is used. Wisdom is kept in a flat
# Markdown file (not SQLite) so lawyers can read, edit, and version-control it.
# The extraction uses claude-haiku for speed — it only needs to pull structured
# facts, not reason deeply.

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional

from themis.config import LexConfig
from themis.state import SeniorCounselState

_WISDOM_FILENAME = "wisdom.md"

_EXTRACTION_PROMPT = """\
You are extracting durable legal practice wisdom from a completed matter.

Matter summary:
  Type: {matter_type}
  Jurisdiction: {jurisdiction}
  Purpose: {purpose}
  Limitation analysis: {limitation_analysis}
  Statutes cited: {statutes}
  Draft excerpt (first 600 chars): {draft_excerpt}

Extract 2-4 short, reusable insights that a lawyer would want to remember for
FUTURE similar matters. Focus on:
  - Effective legal arguments or framings that worked
  - Statutes and precedents relevant to this matter type + jurisdiction combo
  - Court-specific or judge-specific notes (if jurisdiction is specific)
  - Recurring patterns or risks for this matter type

Format as a YAML block (no markdown fences), one item per line:
- matter_type: "{matter_type}"
  jurisdiction: "{jurisdiction}"
  note: "Concise insight here (max 120 chars)"
  date: "{date}"

Emit ONLY the YAML lines. No preamble, no explanation."""


def wisdom_path(home_dir: str = "~/.themis") -> Path:
    return Path(home_dir).expanduser() / _WISDOM_FILENAME


def load_wisdom(home_dir: str = "~/.themis") -> str:
    """Return wisdom file contents, or empty string if it doesn't exist."""
    p = wisdom_path(home_dir)
    if not p.exists():
        return ""
    return p.read_text(encoding="utf-8")


def _append_wisdom(new_yaml: str, home_dir: str = "~/.themis") -> None:
    p = wisdom_path(home_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(new_yaml.strip() + "\n")


async def extract_and_save_wisdom(state: SeniorCounselState, cfg: LexConfig) -> None:
    """
    Background Haiku call: extract 2-4 insights from a completed draft and
    append them to wisdom.md. Runs fire-and-forget after draft delivery.
    Errors are silently swallowed — wisdom extraction must never block the user.
    """
    try:
        draft = state.get("draft_output") or ""
        if not draft or not state.get("matter_type"):
            return

        from themis.nodes._llm import call_llm

        # WHY: Use haiku-class model for extraction — cheap, fast, sufficient for
        # structured fact pulling. The expensive model is reserved for drafting.
        haiku_cfg = LexConfig(
            default_model="claude-haiku-4-5-20251001",
            model_provider="anthropic",
        )

        prompt = _EXTRACTION_PROMPT.format(
            matter_type=state.get("matter_type") or "",
            jurisdiction=state.get("jurisdiction") or "",
            purpose=(state.get("purpose") or "")[:200],
            limitation_analysis=(state.get("limitation_analysis") or "")[:300],
            statutes=", ".join((state.get("statutes_cited") or [])[:6]),
            draft_excerpt=draft[:600],
            date=datetime.now().strftime("%Y-%m-%d"),
        )

        result = await call_llm(
            [
                {"role": "system", "content": "You extract structured legal practice insights. Return only YAML lines."},
                {"role": "user", "content": prompt},
            ],
            haiku_cfg,
        )
        raw = result["content"].strip()
        if raw:
            _append_wisdom(raw, cfg.home_dir)

    except Exception:
        pass  # wisdom extraction must never fail the main flow


def get_relevant_wisdom(
    matter_type: Optional[str],
    jurisdiction: Optional[str],
    home_dir: str = "~/.themis",
    max_entries: int = 5,
) -> str:
    """
    Load wisdom entries relevant to the current matter type and jurisdiction.
    Returns a formatted string ready for injection into a system prompt.
    Returns empty string if wisdom file is absent or no matches found.
    """
    import yaml  # standard library available via PyYAML

    raw = load_wisdom(home_dir)
    if not raw:
        return ""

    try:
        entries = yaml.safe_load(raw)
        if not isinstance(entries, list):
            return ""
    except Exception:
        return ""

    mt_lower = (matter_type or "").lower()
    jur_lower = (jurisdiction or "").lower()

    scored: list[tuple[int, dict]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        score = 0
        if mt_lower and mt_lower in (entry.get("matter_type") or "").lower():
            score += 2
        if jur_lower and jur_lower in (entry.get("jurisdiction") or "").lower():
            score += 1
        if score > 0:
            scored.append((score, entry))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = [e for _, e in scored[:max_entries]]

    if not top:
        return ""

    lines = ["Relevant practice wisdom from past matters:"]
    for e in top:
        note = e.get("note", "")
        mt = e.get("matter_type", "")
        jur = e.get("jurisdiction", "")
        date = e.get("date", "")
        lines.append(f"  • [{mt}, {jur}, {date}] {note}")
    return "\n".join(lines)
