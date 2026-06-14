"""
LLM-based extraction of legal entities from document text.

Given a list of page texts from an ingested document, calls the LLM to extract:
  - Parties (names, roles)
  - Facts (key events, admissions, claims)
  - Dates (events tied to specific dates → ChronologyItems)
  - Issues (legal questions raised by the document)
  - Deadlines (limitation dates, hearing dates, notice deadlines)

All extracted objects carry source_anchor_ids for provenance — the anchor IDs
come from the SourceAnchors already persisted for the document.

Provenance rule (§6 Matter Workspace update rules):
  Agent-generated facts are 'extracted' status. Only lawyer confirmation or
  matching document provenance may change them to 'confirmed'.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Optional

from themis.workspace.models import (
    ChronologyItem,
    Deadline,
    ExtractedFact,
    Issue,
    Party,
    SourceAnchor,
)

logger = logging.getLogger(__name__)

_EXTRACTION_SYSTEM = """You are a legal document analyst extracting structured information
from Indian legal documents for a lawyer's matter workspace.

Extract ALL of the following from the provided text:
1. PARTIES — names of people, companies, or entities and their roles
   (complainant/respondent/applicant/opponent/witness/other)
2. FACTS — specific events, actions, or admissions stated in the document
3. DATES — events tied to a specific date or date range (for chronology)
4. ISSUES — legal questions or disputes raised by the document
5. DEADLINES — any limitation periods, hearing dates, notice deadlines,
   or filing deadlines mentioned

Return ONLY valid JSON in this exact structure:
{
  "parties": [
    {"name": "...", "role": "complainant|respondent|applicant|opponent|witness|other"}
  ],
  "facts": [
    {"text": "...", "confidence": 0.0-1.0, "excerpt": "...verbatim quote from source..."}
  ],
  "dates": [
    {"date_text": "...", "event": "...", "normalized_date": "YYYY-MM-DD or null",
     "confidence": 0.0-1.0, "excerpt": "...verbatim quote..."}
  ],
  "issues": [
    {"text": "...", "category": "limitation|jurisdiction|liability|evidence|procedure|other"}
  ],
  "deadlines": [
    {"title": "...", "due_date": "YYYY-MM-DD", "deadline_type":
     "limitation|filing|hearing|notice|other"}
  ]
}

Rules:
- Only extract what is explicitly stated. Do not infer or hallucinate.
- For each fact and date, include a short verbatim excerpt from the source text.
- confidence reflects how clearly the item is stated (1.0 = explicit, 0.5 = implied).
- normalized_date must be YYYY-MM-DD if derivable, otherwise null.
- due_date for deadlines must be YYYY-MM-DD; omit the deadline if date is unclear.
"""


@dataclass
class ExtractionResult:
    """Structured output from extracting a single page/chunk."""
    parties: list[Party]
    facts: list[ExtractedFact]
    chronology_items: list[ChronologyItem]
    issues: list[Issue]
    deadlines: list[Deadline]
    raw_response: str


async def extract_from_pages(
    matter_id: str,
    document_id: str,
    pages,                          # list[PageText] from ingestion/documents.py
    anchors: list[SourceAnchor],
    llm_callable,                   # awaitable async fn(system: str, user: str) -> str
    run_id: Optional[str] = None,
    extractor_agent: str = "extraction_worker",
) -> ExtractionResult:
    """
    Extract legal entities from all pages of a document.

    Each page is processed individually and results are merged. Anchor IDs
    are matched to extracted excerpts by substring search — not perfect but
    sufficient for MVP provenance without complex span alignment.

    Args:
        matter_id: Owning matter.
        document_id: Source document.
        pages: List of PageText from ingestion/documents.py.
        anchors: SourceAnchors already persisted for this document.
        llm_callable: sync fn(system_prompt: str, user_prompt: str) -> str.
        run_id: Extraction run ID for provenance.
        extractor_agent: Name tag stored on all produced objects.
    """
    # Build excerpt → anchor_id index for fast provenance lookup
    excerpt_index = _build_excerpt_index(anchors)

    all_parties: list[Party] = []
    all_facts: list[ExtractedFact] = []
    all_chronology: list[ChronologyItem] = []
    all_issues: list[Issue] = []
    all_deadlines: list[Deadline] = []
    last_raw = ""

    for page in pages:
        if not page.text.strip():
            continue
        try:
            raw = await llm_callable(_EXTRACTION_SYSTEM, _page_prompt(page))
            last_raw = raw
            parsed = _parse_json(raw)
        except Exception as exc:
            logger.warning("Extraction failed for page %d of %s: %s", page.page, document_id, exc)
            continue

        anchor_ids_for_page = [
            a.anchor_id for a in anchors if a.page == page.page
        ]

        for item in parsed.get("parties", []):
            all_parties.append(
                Party(
                    matter_id=matter_id,
                    name=item.get("name", "Unknown"),
                    role=_coerce_role(item.get("role", "other")),
                )
            )

        for item in parsed.get("facts", []):
            excerpt = item.get("excerpt", "")
            anchor_ids = _match_anchors(excerpt, excerpt_index) or anchor_ids_for_page[:3]
            all_facts.append(
                ExtractedFact(
                    matter_id=matter_id,
                    text=item.get("text", ""),
                    status="extracted",
                    confidence=float(item.get("confidence", 0.5)),
                    source_anchor_ids=anchor_ids,
                    extractor_agent=extractor_agent,
                    extraction_run_id=run_id,
                )
            )

        for item in parsed.get("dates", []):
            excerpt = item.get("excerpt", "")
            anchor_ids = _match_anchors(excerpt, excerpt_index) or anchor_ids_for_page[:3]
            all_chronology.append(
                ChronologyItem(
                    matter_id=matter_id,
                    date_text=item.get("date_text", ""),
                    event=item.get("event", ""),
                    normalized_date=item.get("normalized_date") or None,
                    confidence=float(item.get("confidence", 0.5)),
                    source_anchor_ids=anchor_ids,
                    extractor_agent=extractor_agent,
                    extraction_run_id=run_id,
                )
            )

        for item in parsed.get("issues", []):
            all_issues.append(
                Issue(
                    matter_id=matter_id,
                    text=item.get("text", ""),
                    category=item.get("category", "other"),
                    source_anchor_ids=anchor_ids_for_page[:2],
                )
            )

        for item in parsed.get("deadlines", []):
            due = item.get("due_date")
            if not due:
                continue
            all_deadlines.append(
                Deadline(
                    matter_id=matter_id,
                    title=item.get("title", "Unnamed deadline"),
                    due_date=due,
                    deadline_type=_coerce_deadline_type(item.get("deadline_type", "other")),
                    source_anchor_ids=anchor_ids_for_page[:2],
                )
            )

    return ExtractionResult(
        parties=_deduplicate_parties(all_parties),
        facts=all_facts,
        chronology_items=all_chronology,
        issues=all_issues,
        deadlines=all_deadlines,
        raw_response=last_raw,
    )


def persist_extraction(result: ExtractionResult, repo) -> None:
    """
    Persist all extracted objects to the workspace repository.
    Called after extract_from_pages succeeds. Kept separate so callers
    can inspect the result before committing.
    """
    seen_parties: set[str] = set()
    for party in result.parties:
        key = f"{party.matter_id}:{party.name.lower()}"
        if key not in seen_parties:
            seen_parties.add(key)
            try:
                repo.create_party(party)
            except Exception as exc:
                logger.debug("Party already exists or insert failed: %s", exc)

    repo.bulk_create_facts(result.facts)
    repo.bulk_create_chronology(result.chronology_items)

    for issue in result.issues:
        try:
            repo.create_issue(issue)
        except Exception as exc:
            logger.debug("Issue insert failed: %s", exc)

    for deadline in result.deadlines:
        try:
            repo.create_deadline(deadline)
        except Exception as exc:
            logger.debug("Deadline insert failed: %s", exc)


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _page_prompt(page) -> str:
    return (
        f"Document page {page.page}:\n\n"
        f"{page.text[:4000]}\n\n"
        "Extract all parties, facts, dates, issues, and deadlines from the text above."
    )


def _build_excerpt_index(anchors: list[SourceAnchor]) -> dict[str, str]:
    """Build a lower-cased excerpt → anchor_id map for fast lookup."""
    return {a.excerpt.lower().strip(): a.anchor_id for a in anchors if a.excerpt.strip()}


def _match_anchors(excerpt: str, index: dict[str, str]) -> list[str]:
    """Find anchor IDs whose excerpt appears in the extraction excerpt."""
    if not excerpt:
        return []
    excerpt_lower = excerpt.lower()
    return [
        anchor_id
        for anchor_text, anchor_id in index.items()
        if anchor_text and anchor_text in excerpt_lower
    ][:5]


def _parse_json(raw: str) -> dict[str, Any]:
    """Extract the first JSON object from an LLM response."""
    # Strip markdown code fences if present
    cleaned = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # Try to extract the first {...} block
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            return json.loads(match.group())
        return {}


_VALID_ROLES = {"complainant", "respondent", "applicant", "opponent", "witness", "other"}
_VALID_DEADLINE_TYPES = {"limitation", "filing", "hearing", "notice", "other"}


def _coerce_role(value: str) -> str:
    return value.lower() if value.lower() in _VALID_ROLES else "other"


def _coerce_deadline_type(value: str) -> str:
    return value.lower() if value.lower() in _VALID_DEADLINE_TYPES else "other"


def _deduplicate_parties(parties: list[Party]) -> list[Party]:
    """Deduplicate parties by lowercased name within the same matter."""
    seen: set[str] = set()
    out: list[Party] = []
    for p in parties:
        key = f"{p.matter_id}:{p.name.lower().strip()}"
        if key not in seen:
            seen.add(key)
            out.append(p)
    return out
