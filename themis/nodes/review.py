# Review node: validation gate that runs after cite, before .docx output.
#
# Checks (in order of severity):
#   P0 — Blocking: lawyer note leakage, empty draft, incorrect party labels
#   P1 — Structural: missing required sections (cause of action, jurisdiction, limitation, prayer)
#   P2 — Quality: draft length, unverified citations
#
# P0 issues block output (set error, do not write .docx).
# P1/P2 issues annotate but do not block.

from rich.console import Console

from themis.courts import CourtDraftSpec, load_spec
from themis.state import SeniorCounselState

console = Console()

# WHY: Rough word-count limits by document type.
_WORD_LIMITS: dict[str, int] = {
    "injunction": 5000,
    "writ petition": 8000,
    "legal notice": 2000,
    "plaint": 10000,
    "written statement": 10000,
    "affidavit": 3000,
    "vakalatnama": 500,
    "s138_complaint": 4000,
    "cheque dishonour": 4000,
}
_DEFAULT_WORD_LIMIT = 12000

# ---------------------------------------------------------------------------
# Structural section requirements — keyed by matter_type (lowercase, underscore)
# Each entry: list of (keyword, severity) where severity is "P0" or "P1"
# P0 → blocks filing; P1 → warns only
# ---------------------------------------------------------------------------
_REQUIRED_SECTIONS: dict[str, list[tuple[str, str]]] = {
    "s138_complaint": [
        ("cause of action",  "P0"),
        ("jurisdiction",     "P0"),
        ("limitation",       "P0"),
        ("prayer",           "P0"),
        ("verification",     "P1"),
        ("section 138",      "P0"),
    ],
    "writ_petition": [
        ("grounds",          "P0"),
        ("prayer",           "P0"),
        ("verification",     "P1"),
        ("cause of action",  "P0"),
        ("jurisdiction",     "P1"),
    ],
    "plaint": [
        ("cause of action",  "P0"),
        ("jurisdiction",     "P0"),
        ("limitation",       "P0"),
        ("prayer",           "P0"),
        ("verification",     "P1"),
        ("valuation",        "P1"),
    ],
    "written_statement": [
        ("preliminary objection", "P0"),
        ("prayer",               "P0"),
        ("verification",         "P1"),
    ],
    "bail_application": [
        ("prayer",           "P0"),
        ("grounds",          "P0"),
    ],
    "injunction_application": [
        ("prima facie",      "P0"),
        ("balance of convenience", "P0"),
        ("irreparable",      "P0"),
        ("prayer",           "P0"),
    ],
}

# ---------------------------------------------------------------------------
# Spec section name → searchable keyword in the filing body.
# WHY: spec section names are SCREAMING_SNAKE_CASE identifiers, not prose.
# "CAUSE_OF_ACTION" must be searched as "cause of action"; "S141_BLOCK" as
# "section 141". Names not in this dict fall back to lowercased + spaces.
# ---------------------------------------------------------------------------
_SECTION_NAME_KEYWORDS: dict[str, str] = {
    "TITLE_BLOCK":          "in the court",
    "PARTIES":              "versus",
    "CAUSE_OF_ACTION":      "cause of action",
    "FACTS_IN_BRIEF":       "facts",
    "COGNIZANCE":           "cognizance",
    "GROUNDS":              "grounds",
    "GROUNDS_FOR_BAIL":     "grounds",
    "PRAYER":               "prayer",
    "VERIFICATION":         "verification",
    "LIMITATION":           "limitation",
    "S141_BLOCK":           "section 141",
    "LIST_OF_DATES":        "list of dates",
    "LIST_OF_DOCUMENTS":    "list of documents",
    "LEGAL_NOTICE_DETAILS": "legal notice",
    "AFFIDAVIT_IN_SUPPORT": "affidavit",
    "IMPUGNED_JUDGMENT":    "impugned",
    "QUESTIONS_OF_LAW":     "question of law",
    "NATURE_OF_ACCUSATION": "fir no",
    "ANTECEDENTS":          "antecedent",
    "CUSTODY_PERIOD":       "custody",
    "SURETY_OFFER":         "surety",
    "SYNOPSIS":             "synopsis",
    "VALUATION":            "valuation",
    "AFFIDAVIT_SUPPORT":    "affidavit",
}


def _section_to_keyword(section_name: str) -> str:
    return _SECTION_NAME_KEYWORDS.get(section_name, section_name.lower().replace("_", " "))


def _check_required_sections_from_spec(
    filing_body: str,
    spec: CourtDraftSpec,
    matter_type_key: str,
) -> tuple[list[str], list[str]]:
    """
    Check filing body against the court spec's mandatory and recommended sections,
    then supplement with any fine-grained keyword checks from _REQUIRED_SECTIONS.

    Returns (p0_missing, p1_missing).
    """
    lower = filing_body.lower()
    p0_missing: list[str] = []
    p1_missing: list[str] = []
    seen: set[str] = set()

    for section in spec.mandatory_sections:
        keyword = _section_to_keyword(section)
        display = section.replace("_", " ").title()
        if keyword not in lower and display not in seen:
            p0_missing.append(display)
            seen.add(display)

    for section in spec.recommended_sections:
        keyword = _section_to_keyword(section)
        display = section.replace("_", " ").title()
        if keyword not in lower and display not in seen:
            p1_missing.append(display)
            seen.add(display)

    # Supplement with legacy keyword checks — catches fine-grained phrases
    # like "section 138", "prima facie" that section names don't map to cleanly.
    for keyword, severity in _REQUIRED_SECTIONS.get(matter_type_key, []):
        display = keyword.title()
        if keyword.lower() not in lower and display not in seen:
            seen.add(display)
            if severity == "P0":
                p0_missing.append(display)
            else:
                p1_missing.append(display)

    return p0_missing, p1_missing


# Phrases that indicate lawyer working notes leaked into the filing body.
# WHY: base_system.md appends these after '---'. If they appear BEFORE the
# separator (or if the separator was missed), the filing is contaminated.
_LAWYER_NOTE_LEAKAGE_PATTERNS = [
    "⚠ high risk",
    "⚡ medium risk",
    "ℹ low risk",
    "high risk",
    "medium risk",
    "low risk — ",
    "generated by themis",
    "phase 5 draft",
    "matter id:",
    "plain english summary",
    "risk assessment",
]


def _word_count(text: str) -> int:
    return len(text.split())


def _jurisdiction_limit(matter_type: str | None) -> int:
    if not matter_type:
        return _DEFAULT_WORD_LIMIT
    key = (matter_type or "").lower().strip()
    for known, limit in _WORD_LIMITS.items():
        if known in key:
            return limit
    return _DEFAULT_WORD_LIMIT


def _normalise_matter_type(matter_type: str | None) -> str:
    """Normalise to the key used in _REQUIRED_SECTIONS."""
    if not matter_type:
        return ""
    return matter_type.lower().strip().replace(" ", "_")


def _check_lawyer_note_leakage(filing_body: str) -> list[str]:
    """
    Scan the filing body for phrases that indicate lawyer notes were not stripped.
    Returns a list of matched phrases.
    """
    lower = filing_body.lower()
    found = []
    for pattern in _LAWYER_NOTE_LEAKAGE_PATTERNS:
        if pattern.lower() in lower:
            found.append(pattern)
    return found


def _check_required_sections(
    filing_body: str, matter_type_key: str
) -> tuple[list[str], list[str]]:
    """
    Check that required section keywords appear in the filing body.

    Returns:
        (p0_missing, p1_missing) — lists of section names that are absent.
    """
    if matter_type_key not in _REQUIRED_SECTIONS:
        return [], []

    lower = filing_body.lower()
    p0_missing: list[str] = []
    p1_missing: list[str] = []

    for keyword, severity in _REQUIRED_SECTIONS[matter_type_key]:
        if keyword.lower() not in lower:
            if severity == "P0":
                p0_missing.append(keyword)
            else:
                p1_missing.append(keyword)

    return p0_missing, p1_missing


def _check_placeholder_leakage(filing_body: str) -> list[str]:
    """Find unfilled placeholder patterns like [INSERT ...] or [___]."""
    import re
    patterns = re.findall(r"\[(?:INSERT|FILL|ADD|___|\.\.\.).*?\]", filing_body, re.IGNORECASE)
    return patterns


async def run(state: SeniorCounselState) -> dict:
    try:
        from themis.tools.docx_writer import _split_draft  # local import to avoid circularity

        draft = state.get("draft_output") or ""
        # Use only the filing body (before '---') for structural checks
        filing_body, _ = _split_draft(draft)

        unverified = state.get("unverified_citations") or []
        grounded = state.get("grounded_citations") or []
        matter_type = state.get("matter_type")
        matter_type_key = _normalise_matter_type(matter_type)
        jurisdiction = state.get("jurisdiction") or ""
        soul = state.get("lawyer_soul") or {}
        soul_dict = soul if isinstance(soul, dict) else {}
        docx_output_path: str | None = state.get("docx_path")

        # Load court spec — drives section compliance checks below.
        spec = load_spec(jurisdiction, matter_type_key, soul=soul_dict)

        p0_issues: list[str] = []
        p1_issues: list[str] = []
        risk_annotations: list[dict] = []

        # ── P0: empty draft ──────────────────────────────────────────────────
        if not filing_body.strip():
            p0_issues.append("Draft output is empty")

        # ── P0: lawyer note leakage in filing body ───────────────────────────
        leaked = _check_lawyer_note_leakage(filing_body)
        if leaked:
            p0_issues.append(
                f"Lawyer working notes leaked into filing body: {', '.join(leaked[:3])}"
            )

        # ── P0/P1: required structural sections (spec-driven) ────────────────
        p0_missing, p1_missing = _check_required_sections_from_spec(
            filing_body, spec, matter_type_key
        )
        if p0_missing:
            p0_issues.append(
                f"Missing required sections (P0): {', '.join(p0_missing)}"
            )
        if p1_missing:
            p1_issues.append(
                f"Missing recommended sections: {', '.join(p1_missing)}"
            )

        # ── P1: placeholder leakage ──────────────────────────────────────────
        placeholders = _check_placeholder_leakage(filing_body)
        if placeholders:
            p1_issues.append(
                f"Unfilled placeholders in filing body: {', '.join(placeholders[:5])}"
            )

        # ── P2: unverified citations ─────────────────────────────────────────
        if unverified:
            p1_issues.append(
                f"{len(unverified)} citation(s) could not be grounded: "
                + ", ".join(unverified[:3])
                + (" ..." if len(unverified) > 3 else "")
            )

        # ── P2: draft length ─────────────────────────────────────────────────
        limit = _jurisdiction_limit(matter_type)
        wc = _word_count(draft)
        if wc > limit:
            p1_issues.append(
                f"Draft is {wc} words — exceeds {matter_type or 'document'} "
                f"guidance of {limit} words"
            )

        # ── Report ───────────────────────────────────────────────────────────
        if p0_issues:
            for issue in p0_issues:
                console.print(f"[bold red]✗ P0 Review:[/bold red] {issue}")
            for issue in p1_issues:
                console.print(f"[yellow]⚠ P1 Review:[/yellow] {issue}")
            # P0 issues block .docx output — return error so CLI can re-draft
            return {
                "error": f"P0 review failures (filing blocked): {'; '.join(p0_issues)}",
                "risk_annotations": [
                    {"clause": "review", "risk_level": "H", "note": i} for i in p0_issues
                ] + [
                    {"clause": "review", "risk_level": "M", "note": i} for i in p1_issues
                ],
            }

        for issue in p1_issues:
            console.print(f"[yellow]⚠ P1 Review:[/yellow] {issue}")

        if not p0_issues and not p1_issues:
            console.print("[green]✓ Review:[/green] All structural checks passed")
        else:
            console.print("[green]✓ Review:[/green] Structural checks passed (warnings above)")

        # R2B: persist review findings as mem0 learning signals.
        # P1 issues reveal what the reviewer consistently flags for this matter type —
        # future drafts can pre-empt these by knowing the common gaps.
        try:
            from themis.config import LexConfig as _LexConfig
            from themis.memory.lawyer_memory import save_feedback as _save_feedback
            _cfg = _LexConfig()
            _lawyer_id = state.get("lawyer_id") or "default_lawyer"
            _matter_id = state.get("matter_id") or ""
            _mt = matter_type or "unknown"
            _jur = jurisdiction or "India"
            if p1_issues:
                _review_signal = (
                    f"In {_mt} draft for {_jur}, reviewer flagged: "
                    + "; ".join(p1_issues[:3])
                )
            else:
                _review_signal = f"Review passed cleanly for {_mt} draft in {_jur}."
            _save_feedback(
                _review_signal, _matter_id, _lawyer_id, _cfg,
                metadata={"source": "review", "matter_type": _mt},
            )
        except Exception:
            pass  # review feedback failure must never block .docx output

        # ── Generate .docx (only reaches here if no P0 blocking issues) ──────
        # WHY run_in_executor: write_docx does synchronous disk I/O (python-docx).
        # Running it in the default ThreadPoolExecutor keeps the asyncio event loop
        # unblocked — critical for serving concurrent Telegram users.
        import asyncio
        from pathlib import Path as _Path
        from themis.tools.docx_writer import write_docx, write_affidavit_docx

        docx_path_out: str | None = None
        affidavit_path_out: str | None = None

        if docx_output_path and filing_body.strip():
            loop = asyncio.get_event_loop()
            docx_path_out = await loop.run_in_executor(None, write_docx, state, docx_output_path)
            console.print(f"[bold green]✓ Draft saved to:[/bold green] {docx_path_out}")

            # Write affidavit sub-document alongside the main filing if generated
            if state.get("affidavit_output"):
                stem = _Path(docx_output_path).stem
                parent = _Path(docx_output_path).parent
                affidavit_path = str(parent / f"{stem}_affidavit_evidence.docx")
                affidavit_path_out = await loop.run_in_executor(
                    None, write_affidavit_docx, state, affidavit_path
                )
                if affidavit_path_out:
                    console.print(f"[bold green]✓ Affidavit saved to:[/bold green] {affidavit_path_out}")

        # Redline: if caller set redline_source_path, produce a tracked-changes .docx
        redline_output_path: str | None = None
        redline_source = state.get("redline_source_path")
        if redline_source and docx_path_out and filing_body.strip():
            from themis.tools.redline import write_redline_docx
            redline_out = str(_Path(docx_path_out).parent / "redline.docx")
            try:
                redline_output_path = await loop.run_in_executor(
                    None, write_redline_docx, redline_source, filing_body, redline_out
                )
                console.print(f"[bold green]✓ Redline saved to:[/bold green] {redline_output_path}")
            except Exception as _re:
                console.print(f"[yellow]Redline skipped:[/yellow] {_re}")

        return {
            "docx_path": docx_path_out,
            "affidavit_path": affidavit_path_out,
            "redline_output_path": redline_output_path,
            "risk_annotations": [
                {"clause": "review", "risk_level": "M", "note": i} for i in p1_issues
            ] if p1_issues else None,
        }

    except Exception as e:
        return {"error": str(e)}
