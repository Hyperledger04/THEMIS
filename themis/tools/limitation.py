# Indian Limitation Act 1963 — lookup table for common matter types.
# WHY: Limitation is a first-pass check, not legal advice. The research node
# injects this into the draft so the lawyer can verify and override.

from datetime import date, datetime, timedelta

from themis.tools.registry import ToolRegistry

# Key: lowercase matter_type string. years=None means no fixed statutory period.
_LIMITATION_TABLE: dict[str, dict] = {
    "civil suit": {
        "years": 3,
        "article": "Article 113, Limitation Act 1963",
        "note": "Residual 3-year period — applies where no specific article covers the cause.",
    },
    "money recovery": {
        "years": 3,
        "article": "Article 36, Limitation Act 1963",
        "note": "3 years from the date the money became due and payable.",
    },
    "injunction": {
        "years": 3,
        "article": "Article 58, Limitation Act 1963",
        "note": "3 years from when the right to seek the injunction first arose.",
    },
    "property suit": {
        "years": 12,
        "article": "Article 65, Limitation Act 1963",
        "note": "12 years for possession based on title; adverse possession starts when possession becomes adverse.",
    },
    "writ petition": {
        "years": None,
        "article": "No fixed statutory period — court discretion under laches doctrine",
        "note": "High Courts typically expect filing within ~3 years; delay requires explanation.",
    },
    "cheque dishonour": {
        "years": 1,
        "article": "Section 138, Negotiable Instruments Act 1881",
        "note": "File within 1 month of cause of action, which arises after the 15-day statutory notice period.",
    },
    "consumer complaint": {
        "years": 2,
        "article": "Section 69, Consumer Protection Act 2019",
        "note": "2 years from the date of cause of action; delay may be condoned for sufficient cause.",
    },
    "legal notice": {
        "years": None,
        "article": "N/A — notice is pre-litigation",
        "note": "The notice itself has no limitation period; the underlying cause of action governs.",
    },
}

_DEFAULT: dict = {
    "years": 3,
    "article": "Article 113, Limitation Act 1963",
    "note": "Residual 3-year period applies where no specific article is prescribed.",
}


@ToolRegistry.register(
    name="check_limitation",
    description=(
        "Calculate the limitation period under the Indian Limitation Act 1963 "
        "for a given matter type. Optionally compute the deadline and flag if "
        "the matter may be time-barred."
    ),
)
def check_limitation(matter_type: str, cause_of_action_date: str = "") -> dict:
    """
    Args:
        matter_type: e.g. "civil suit", "cheque dishonour", "writ petition"
        cause_of_action_date: ISO date string (YYYY-MM-DD). Empty = not provided.

    Returns dict with keys: matter_type, limitation_years, legal_basis, note,
    deadline, risk, analysis.
    """
    row = _LIMITATION_TABLE.get(matter_type.lower().strip(), _DEFAULT)
    years: int | None = row["years"]

    deadline: str | None = None
    risk = "unknown"

    if cause_of_action_date and years is not None:
        try:
            coa = datetime.fromisoformat(cause_of_action_date).date()
            # WHY: Add calendar years directly — Limitation Act counts years, not days.
            # Handles Feb 29 edge case: if coa is Feb 29, deadline becomes Feb 28.
            try:
                deadline_dt = coa.replace(year=coa.year + years)
            except ValueError:
                deadline_dt = coa.replace(year=coa.year + years, day=28)
            deadline = deadline_dt.isoformat()
            today = date.today()
            days_left = (deadline_dt - today).days
            if days_left < 0:
                risk = "expired"
            elif days_left < 180:
                risk = "within_6_months"
            else:
                risk = "clear"
        except ValueError:
            risk = "unknown"

    # Build human-readable analysis for injection into the draft system prompt
    if years is not None:
        analysis = f"Limitation: {years} year(s) under {row['article']}. {row['note']}."
    else:
        analysis = f"Limitation: {row['article']}. {row['note']}."

    if deadline:
        analysis += f" Deadline: {deadline}."
    if risk == "expired":
        analysis += " WARNING: limitation period appears EXPIRED — urgent condonation application required."
    elif risk == "within_6_months":
        analysis += " ALERT: fewer than 6 months remaining — file urgently."
    elif risk == "clear":
        analysis += " Status: well within limitation period."

    return {
        "matter_type": matter_type,
        "limitation_years": years,
        "legal_basis": row["article"],
        "note": row["note"],
        "deadline": deadline,
        "risk": risk,
        "analysis": analysis,
    }
