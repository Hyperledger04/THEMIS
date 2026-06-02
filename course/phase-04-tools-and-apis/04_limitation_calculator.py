"""
04_limitation_calculator.py — Limitation Period Calculator
===========================================================
Every legal claim in India has a filing deadline. Miss it and the court bars
your suit — regardless of how strong your case is. This tool automates the
calculation so the agent can warn the lawyer *before* a deadline is missed.
"""

from datetime import date, timedelta

# ── SECTION 1: WHAT LIMITATION IS ────────────────────────────────────────────
#
# The Limitation Act, 1963 sets the maximum time within which a legal action
# must be filed. After that time, the claim is "time-barred" and courts will
# reject it at the threshold, even without examining the merits.
#
# Key terminology:
#   Cause of action (COA) — the date the legal right to sue arose.
#                           For a bounced cheque: the date of dishonour.
#                           For a contract breach: the date the breach occurred.
#
#   Limitation period — the window (in days/years) counting from the COA.
#
#   Condonation of delay — courts *can* extend the deadline under Section 5
#                          of the Limitation Act if "sufficient cause" is shown,
#                          but this is discretionary and not guaranteed.
#
# WHY this matters for the agent: a lawyer typing "file a money suit — client
# paid nothing after 2019 contract" needs to know immediately if the 3-year
# window has already closed before drafting anything.

# ── SECTION 2: LIMITATION PERIODS ────────────────────────────────────────────
#
# Source: First Schedule to the Limitation Act 1963, plus special acts.
# Days are used throughout so arithmetic stays uniform.

LIMITATION_PERIODS: dict[str, int | None] = {
    # Civil suits (First Schedule, Articles 36–137)
    "money_suit": 3 * 365,            # Art. 113 — 3 years from date money due
    "contract_breach": 3 * 365,       # Art. 55 — 3 years from date of breach
    "recovery_of_land": 12 * 365,     # Art. 65 — 12 years for immovable property
    "specific_performance": 3 * 365,  # Art. 54 — 3 years from date fixed for performance

    # Criminal / quasi-criminal
    "cheque_bounce_complaint": 30,    # S.138 NI Act — 30 days from knowledge of dishonour
                                      # WHY so short: the notice period + complaint window
                                      # is prescribed strictly in the NI Act, not Limitation Act

    # Consumer disputes
    "consumer_complaint": 2 * 365,   # Consumer Protection Act 2019, S.69 — 2 years

    # Motor accident claims
    "motor_accident_claim": 3 * 365, # Motor Vehicles Act 1988, S.166(3)

    # Writs and petitions — no fixed period
    "writ_petition": None,           # No statutory limit — courts apply *laches*
    "affidavit": None,               # Not a time-bound proceeding
    "pil": None,                     # Public Interest Litigation — court's discretion
}

# ── SECTION 3: calculate_limitation ──────────────────────────────────────────

def calculate_limitation(matter_type: str, cause_of_action: str) -> dict:
    """
    Calculate whether a claim is within its limitation period.

    Args:
        matter_type        — key from LIMITATION_PERIODS (e.g. "money_suit")
        cause_of_action    — ISO date string when the right to sue arose
                             (e.g. "2022-03-15")

    Returns:
        A dict with keys: deadline, days_remaining, is_expired,
                          period_days, note
    """
    # Parse the cause-of-action date
    coa_date = date.fromisoformat(cause_of_action)
    today = date.today()

    # Look up the limitation period (None means no fixed statutory period)
    period = LIMITATION_PERIODS.get(matter_type)

    if period is None:
        return {
            "deadline": None,
            "days_remaining": None,
            "is_expired": False,
            "period_days": None,
            "note": (
                "No fixed limitation period — courts apply the doctrine of laches. "
                "File as promptly as possible; unexplained delay weakens the petition."
            ),
        }

    # Calculate deadline and days remaining
    deadline = coa_date + timedelta(days=period)
    days_remaining = (deadline - today).days

    if days_remaining >= 0:
        note = (
            f"Must file by {deadline.isoformat()} "
            f"({days_remaining} day(s) remaining)."
        )
    else:
        note = (
            f"EXPIRED {abs(days_remaining)} day(s) ago "
            f"(deadline was {deadline.isoformat()}). "
            "Consider applying for condonation of delay under Section 5."
        )

    return {
        "deadline": deadline.isoformat(),
        "days_remaining": days_remaining,
        "is_expired": days_remaining < 0,
        "period_days": period,
        "note": note,
    }

# ── SECTION 4: RETURN STRUCTURE ───────────────────────────────────────────────
#
# Every call returns the same shape so the research node can pattern-match:
#
#   deadline       — ISO date string, or None if no fixed period
#   days_remaining — integer (negative = already expired), or None
#   is_expired     — bool; True if the deadline has already passed
#   period_days    — the statutory limit in days, or None
#   note           — human-readable sentence for the draft / lawyer output

# ── SECTION 5: LIVE DEMO ──────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("LIMITATION CALCULATOR — THREE EXAMPLES")
    print("=" * 60)

    examples = [
        ("money_suit",             "2022-01-10",  "Money suit — COA 3+ years ago"),
        ("cheque_bounce_complaint","2024-12-01",  "Cheque bounce — 15 days after dishonour"),
        ("writ_petition",          "2020-06-01",  "Writ petition — no fixed period"),
    ]

    for matter_type, coa, label in examples:
        print(f"\n[{label}]")
        print(f"  Matter type : {matter_type}")
        print(f"  COA date    : {coa}")
        result = calculate_limitation(matter_type, coa)
        print(f"  Deadline    : {result['deadline']}")
        print(f"  Days left   : {result['days_remaining']}")
        print(f"  Expired?    : {result['is_expired']}")
        print(f"  Note        : {result['note']}")


# ── PAUSE AND THINK ───────────────────────────────────────────────────────────
#
# 1. In `lexagent/tools/limitation.py`, how does the research node pass the
#    cause_of_action date? Where does it get that date from (hint: LexState)?
#
# 2. Cheque bounce has a 30-day window for filing the complaint — but there is
#    also a 15-day notice period first. How would you model that two-step
#    deadline in LIMITATION_PERIODS?
#
# 3. `is_expired=True` doesn't mean the lawyer can't file — condonation of
#    delay under Section 5 may apply. How should the draft node use this flag?
#    Should it block drafting or add a warning paragraph?
#
# 4. The Limitation Act uses calendar days, not working days. Does your
#    calculation handle public holidays? What would break if a deadline fell
#    on a Sunday (courts are closed)?
#
# 5. `lexagent/nodes/research.py` calls this tool and stores the result in
#    `state["limitation_analysis"]`. Which part of the draft prompt reads
#    that field and decides whether to include a limitation warning section?
