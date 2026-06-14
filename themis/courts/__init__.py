"""
Court DraftSpec — data-driven formatting and compliance rules per court x matter type.

Each YAML file in this directory encodes one court's rules:
  - margins, font, spacing (formatting)
  - required and recommended sections (for review.py compliance)
  - section output order (for docx_writer.py)
  - annexure label format (e.g. ANNEXURE P-1 vs EX-CW1/A)
  - party labels (overrides docx_writer.PARTY_LABELS for court-aware filers)

Loader: load_spec(jurisdiction, matter_type, soul=None) -> CourtDraftSpec
  Matches on jurisdiction_keywords + matter_types in each YAML.
  Falls back to generic_indian_court if no match found.
  If soul dict has "formatting_style", that named preset overrides the spec's formatting block.

Named formatting presets (lawyer selects at setup; stored in SOUL.md):
  "district_court"  -- Bookman Old Style 14pt, 1" margins, legal paper, single-spaced
                       Matches standard Indian district/magistrate court filings.
  "high_court"      -- Times New Roman 12pt, 1.5" left margin, A4, double-spaced
  "supreme_court"   -- Times New Roman 12pt, 1.5" left margin, A4, double-spaced
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from pathlib import Path

import yaml  # type: ignore[import]

_COURTS_DIR = Path(__file__).parent
_FALLBACK_SPEC_ID = "generic_indian_court"


# ---------------------------------------------------------------------------
# Spec dataclasses — frozen so nodes cannot mutate them accidentally
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FormattingSpec:
    paper: str = "Legal"  # Legal (8.5x14") | A4
    left_margin_inches: float = 1.0
    right_margin_inches: float = 1.0
    top_margin_inches: float = 1.0
    bottom_margin_inches: float = 1.0
    font_name: str = "Bookman Old Style"
    font_size_pt: int = 14
    # WHY: named rule, not raw pt value — python-docx handles "single" and
    # "double" differently from Pt() values. Values: single | 1.5x | double
    line_spacing: str = "single"
    para_numbering: str = "arabic"        # arabic | roman | alpha | none
    heading_style: str = "bold_centered"  # bold_centered | bold_left | uppercase_centered


@dataclass(frozen=True)
class AnnexureSpec:
    # {n} replaced with sequential number; {alpha} with A, B, C...
    format: str = "ANNEXURE {n}"


@dataclass(frozen=True)
class CourtDraftSpec:
    court_id: str
    display_name: str

    # Matching criteria — used by load_spec() to pick the right YAML
    jurisdiction_keywords: tuple[str, ...]  # e.g. ("delhi hc", "high court of delhi")
    matter_types: tuple[str, ...]           # e.g. ("writ_petition", "writ")

    formatting: FormattingSpec
    mandatory_sections: tuple[str, ...]     # P0 — blocks filing if missing
    recommended_sections: tuple[str, ...]   # P1 — warns but does not block
    section_order: tuple[str, ...]          # expected output sequence

    annexures: AnnexureSpec

    # (filer_label, opposing_label) — overrides docx_writer.PARTY_LABELS
    party_labels: tuple[str, str]

    stamp_paper: bool = False
    filing_fee_note: bool = False


# ---------------------------------------------------------------------------
# Named formatting presets
# Lawyer picks one at setup; stored in SOUL.md as:
#   formatting_style: district_court
# Overrides only the formatting block of whatever court spec is matched.
# Structure rules (sections, ordering, party labels) come from the court YAML.
# ---------------------------------------------------------------------------

FORMATTING_PRESETS: dict[str, FormattingSpec] = {
    # Standard Indian district / magistrate court filing.
    # Based on actual filed COMPLAINT-138 NI ACT reference document:
    #   Bookman Old Style 14pt, 1" all margins, legal paper (8.5x14"), single-spaced.
    "district_court": FormattingSpec(
        paper="Legal",
        left_margin_inches=1.0,
        right_margin_inches=1.0,
        top_margin_inches=1.0,
        bottom_margin_inches=1.0,
        font_name="Bookman Old Style",
        font_size_pt=14,
        line_spacing="single",
    ),
    # High Court petition format (Delhi HC, Bombay HC, etc.)
    # Times New Roman 12pt, 1.5" left margin (binding side), A4, double-spaced.
    "high_court": FormattingSpec(
        paper="A4",
        left_margin_inches=1.5,
        right_margin_inches=1.0,
        top_margin_inches=1.0,
        bottom_margin_inches=1.0,
        font_name="Times New Roman",
        font_size_pt=12,
        line_spacing="double",
    ),
    # Supreme Court — same base as high_court; SC-specific sections via sc_slp.yaml
    "supreme_court": FormattingSpec(
        paper="A4",
        left_margin_inches=1.5,
        right_margin_inches=1.0,
        top_margin_inches=1.0,
        bottom_margin_inches=1.0,
        font_name="Times New Roman",
        font_size_pt=12,
        line_spacing="double",
    ),
}

# Human-readable labels shown in the setup wizard
FORMATTING_PRESET_LABELS: dict[str, str] = {
    "district_court": "District / Magistrate Court  (Bookman Old Style 14pt, legal paper, single-spaced)",
    "high_court":     "High Court  (Times New Roman 12pt, A4, double-spaced)",
    "supreme_court":  "Supreme Court  (Times New Roman 12pt, A4, double-spaced)",
}


# ---------------------------------------------------------------------------
# YAML -> dataclass parser
# ---------------------------------------------------------------------------


def _parse_spec(data: dict) -> CourtDraftSpec:
    fmt_data = data.get("formatting", {})
    margin = fmt_data.get("margins", {})

    formatting = FormattingSpec(
        paper=fmt_data.get("paper", "Legal"),
        left_margin_inches=float(margin.get("left_inches", 1.0)),
        right_margin_inches=float(margin.get("right_inches", 1.0)),
        top_margin_inches=float(margin.get("top_inches", 1.0)),
        bottom_margin_inches=float(margin.get("bottom_inches", 1.0)),
        font_name=fmt_data.get("font_name", "Bookman Old Style"),
        font_size_pt=int(fmt_data.get("font_size_pt", 14)),
        line_spacing=fmt_data.get("line_spacing", "single"),
        para_numbering=fmt_data.get("para_numbering", "arabic"),
        heading_style=fmt_data.get("heading_style", "bold_centered"),
    )

    annex_data = data.get("annexures", {})
    annexures = AnnexureSpec(
        format=annex_data.get("format", "ANNEXURE {n}"),
    )

    party = data.get("party_labels", {})
    party_labels: tuple[str, str] = (
        party.get("filer", "Petitioner"),
        party.get("opposing", "Respondent"),
    )

    return CourtDraftSpec(
        court_id=data["court_id"],
        display_name=data.get("display_name", data["court_id"]),
        jurisdiction_keywords=tuple(kw.lower() for kw in data.get("jurisdiction_keywords", [])),
        matter_types=tuple(mt.lower() for mt in data.get("matter_types", [])),
        formatting=formatting,
        mandatory_sections=tuple(data.get("mandatory_sections", [])),
        recommended_sections=tuple(data.get("recommended_sections", [])),
        section_order=tuple(data.get("section_order", [])),
        annexures=annexures,
        party_labels=party_labels,
        stamp_paper=bool(data.get("stamp_paper", False)),
        filing_fee_note=bool(data.get("filing_fee_note", False)),
    )


def _apply_soul_formatting_override(spec: CourtDraftSpec, soul: dict) -> CourtDraftSpec:
    """Return a new spec with formatting replaced by the soul's named preset.

    If SOUL.md has  formatting_style: high_court  this overrides the matched
    spec's formatting block while keeping all structural rules (sections,
    ordering, party labels) from the court YAML.
    """
    preset_key = soul.get("formatting_style", "").strip().lower().replace(" ", "_")
    preset = FORMATTING_PRESETS.get(preset_key)
    if not preset:
        return spec
    # WHY: dataclasses are frozen so we rebuild rather than mutate.
    return CourtDraftSpec(
        court_id=spec.court_id,
        display_name=spec.display_name,
        jurisdiction_keywords=spec.jurisdiction_keywords,
        matter_types=spec.matter_types,
        formatting=preset,               # <- lawyer's choice wins
        mandatory_sections=spec.mandatory_sections,
        recommended_sections=spec.recommended_sections,
        section_order=spec.section_order,
        annexures=spec.annexures,
        party_labels=spec.party_labels,
        stamp_paper=spec.stamp_paper,
        filing_fee_note=spec.filing_fee_note,
    )


# ---------------------------------------------------------------------------
# In-process cache — YAMLs are small; load once per process
# ---------------------------------------------------------------------------
_cache: dict[str, CourtDraftSpec] = {}


def _clear_cache() -> None:
    """Clear the in-process spec cache. Useful in tests."""
    _cache.clear()


def _load_all() -> dict[str, CourtDraftSpec]:
    """Load every YAML in the courts/ directory into _cache. Called once."""
    if _cache:
        return _cache
    for path in _COURTS_DIR.glob("*.yaml"):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            spec = _parse_spec(data)
            _cache[spec.court_id] = spec
        except Exception as exc:  # noqa: BLE001
            # WHY: a malformed YAML must not crash the entire agent —
            # warn and skip so the fallback still works.
            warnings.warn(f"CourtDraftSpec: failed to load {path.name}: {exc}", stacklevel=2)
    return _cache


def load_spec(
    jurisdiction: str,
    matter_type: str,
    soul: dict | None = None,
) -> CourtDraftSpec:
    """Return the best-matching CourtDraftSpec for this matter.

    Matching logic (first match wins):
      1. Both jurisdiction keyword AND matter_type match a spec.
      2. Only matter_type matches (jurisdiction-agnostic spec).
      3. Fallback: generic_indian_court.

    If soul dict contains "formatting_style", its named preset overrides
    the matched spec's formatting block (structure rules unchanged).

    Args:
        jurisdiction:  Free-text from LexState e.g. "GBN CJM", "Delhi HC".
        matter_type:   Normalised matter type e.g. "s138_complaint".
        soul:          Parsed SOUL.md dict. Optional. Supplies formatting override.
    """
    specs = _load_all()

    jur = (jurisdiction or "").lower()
    mt = (matter_type or "").lower().replace(" ", "_")

    matched: CourtDraftSpec | None = None

    # Pass 1: both jurisdiction and matter_type match
    for spec in specs.values():
        jur_hit = any(kw in jur for kw in spec.jurisdiction_keywords)
        mt_hit = mt in spec.matter_types or any(mt in m or m in mt for m in spec.matter_types)
        if jur_hit and mt_hit:
            matched = spec
            break

    # Pass 2: matter_type match only
    if matched is None:
        for spec in specs.values():
            mt_hit = mt in spec.matter_types or any(mt in m or m in mt for m in spec.matter_types)
            if mt_hit:
                matched = spec
                break

    if matched is None:
        matched = specs.get(_FALLBACK_SPEC_ID) or _make_generic_fallback()

    if soul:
        matched = _apply_soul_formatting_override(matched, soul)

    return matched


def _make_generic_fallback() -> CourtDraftSpec:
    """Hard-coded fallback in case even generic_indian_court.yaml is missing."""
    return CourtDraftSpec(
        court_id="generic_indian_court",
        display_name="Indian Court (Generic)",
        jurisdiction_keywords=(),
        matter_types=(),
        formatting=FORMATTING_PRESETS["district_court"],
        mandatory_sections=(),
        recommended_sections=(),
        section_order=("TITLE_BLOCK", "PARTIES", "FACTS_IN_BRIEF", "PRAYER", "VERIFICATION"),
        annexures=AnnexureSpec(),
        party_labels=("Petitioner", "Respondent"),
    )
