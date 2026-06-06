"""
Chronology builder — assembles a sorted, deduplicated chronology for a matter.

Reads ChronologyItems already persisted in the workspace, sorts them by
normalized_date (ASC, nulls last), and returns a formatted chronology string
suitable for injection into drafting or research prompts.

Also exposes build_chronology_for_matter() which returns the raw sorted list
for structured use by the morning brief and research jobs.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Optional

from lexagent.workspace.models import ChronologyItem

logger = logging.getLogger(__name__)


@dataclass
class ChronologyEntry:
    """Single chronology entry enriched with sort key and display string."""
    item: ChronologyItem
    sort_key: Optional[date]          # None for undated entries (sorted last)
    display_date: str                  # Human-readable date string for output


def build_chronology_for_matter(
    matter_id: str,
    firm_id: str,
    repo,
) -> list[ChronologyEntry]:
    """
    Fetch all ChronologyItems for a matter, sort by date, and return as
    ChronologyEntry list. The repo query already sorts by normalized_date ASC;
    this function adds the sort_key and display_date enrichment.

    Args:
        matter_id: Target matter.
        firm_id: Owning firm (tenant scope).
        repo: PostgresWorkspaceRepository.
    """
    items = repo.list_chronology(matter_id=matter_id, firm_id=firm_id)
    entries = [_to_entry(item) for item in items]
    # Secondary sort: dated entries first, undated last; ties by creation order
    entries.sort(key=lambda e: (e.sort_key is None, e.sort_key or date.min))
    return entries


def format_chronology(entries: list[ChronologyEntry], max_entries: int = 100) -> str:
    """
    Return a markdown-formatted chronology string for prompt injection.
    Suitable for use in drafting, research, and morning-brief prompts.
    """
    if not entries:
        return "No chronology items found for this matter."

    lines = ["## Matter Chronology\n"]
    for entry in entries[:max_entries]:
        anchor_refs = (
            " " + " ".join(f"[{a}]" for a in entry.item.source_anchor_ids[:3])
            if entry.item.source_anchor_ids
            else ""
        )
        confidence_flag = " [unverified]" if entry.item.confidence < 0.7 else ""
        lines.append(
            f"- **{entry.display_date}** — {entry.item.event}{anchor_refs}{confidence_flag}"
        )

    if len(entries) > max_entries:
        lines.append(f"\n_...and {len(entries) - max_entries} more items._")

    return "\n".join(lines)


def build_and_format_chronology(
    matter_id: str,
    firm_id: str,
    repo,
    max_entries: int = 100,
) -> tuple[list[ChronologyEntry], str]:
    """
    Convenience wrapper: build + format in one call.
    Returns (entries, formatted_markdown).
    """
    entries = build_chronology_for_matter(matter_id, firm_id, repo)
    text = format_chronology(entries, max_entries=max_entries)
    return entries, text


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _to_entry(item: ChronologyItem) -> ChronologyEntry:
    sort_key: Optional[date] = None
    display_date = item.date_text or "Undated"

    if item.normalized_date:
        try:
            sort_key = date.fromisoformat(item.normalized_date[:10])
            display_date = sort_key.strftime("%-d %B %Y")
        except ValueError:
            logger.debug("Could not parse normalized_date: %s", item.normalized_date)

    return ChronologyEntry(item=item, sort_key=sort_key, display_date=display_date)
