# Court fee calculator for Indian courts.
#
# WHY YAML-backed: Court fee schedules change every few years (state budgets, Finance Acts).
# Keeping the fee table in lexagent/data/court_fees.yaml means a lawyer can update the
# numbers without touching Python. The tool reads the YAML on every call so edits are
# live immediately.
#
# Data sources: Court Fees Act 1870 (central), Delhi Court Fees Act, and per-state schedules.
# Values are approximate — always verify with the specific court's fee schedule.

from pathlib import Path

from lexagent.tools.registry import ToolRegistry

_DATA_FILE = Path(__file__).parent.parent / "data" / "court_fees.yaml"

_FALLBACK_FEES: dict = {
    "civil suit (district court)": {
        "base": "Ad valorem — 10% of suit valuation (max ₹75,000 under Delhi Court Fees Act).",
        "note": "Check Schedule I of the Court Fees Act 1870 and applicable state schedule.",
    },
    "writ petition (high court)": {
        "base": "Fixed — ₹500 (Delhi HC) to ₹2,000 (Bombay HC). Varies by state.",
        "note": "No ad valorem element for writs challenging state action.",
    },
    "bail application": {
        "base": "Fixed — ₹10 to ₹50 (nominal; varies by court).",
        "note": "Most criminal applications attract nominal fees under Schedule II.",
    },
    "injunction application": {
        "base": "Fixed — ₹50 to ₹200 (interlocutory application fee).",
        "note": "Filed along with the main suit; separate fee for I.A.",
    },
    "execution petition": {
        "base": "Ad valorem — typically 50% of the decree amount (max caps apply).",
        "note": "Subject to Order XXI CPC and state Court Fees schedule.",
    },
    "appeal (first appeal)": {
        "base": "Same as original suit fee in most states.",
        "note": "Verify: some HCs charge ₹500 flat for first appeals.",
    },
    "legal notice": {
        "base": "No court fee — pre-litigation notice.",
        "note": "Advocate fees and postal charges apply; no stamp duty unless notarised.",
    },
    "consumer complaint": {
        "base": "₹200 (up to ₹5 lakh) to ₹7,500 (National Commission) — see Consumer Protection Act 2019 Schedule.",
        "note": "Fee is fixed by forum (district/state/national) based on claim value.",
    },
    "cheque dishonour (NI Act 138)": {
        "base": "Fixed — ₹200 (magistrate complaint).",
        "note": "File as a criminal complaint; no ad valorem element.",
    },
}


def _load_fees() -> dict:
    """Load fee table from YAML, falling back to hardcoded table if file absent."""
    try:
        import yaml
        if _DATA_FILE.exists():
            data = yaml.safe_load(_DATA_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return _FALLBACK_FEES


@ToolRegistry.register(
    name="calculate_court_fee",
    description=(
        "Estimate the court fee payable for an Indian litigation matter. "
        "Returns a human-readable fee description, statutory basis, and notes. "
        "Provide matter_type (e.g. 'writ petition', 'civil suit') and optionally "
        "suit_value (numeric, in rupees) for ad valorem calculations."
    ),
)
def calculate_court_fee(matter_type: str, suit_value: float = 0.0, state: str = "") -> dict:
    """
    Args:
        matter_type: e.g. "civil suit", "bail application", "writ petition"
        suit_value:  Numeric value in rupees for ad valorem fee computation.
        state:       State/jurisdiction name for state-specific schedules (optional).

    Returns dict with: matter_type, fee_description, statutory_basis, notes, suit_value.
    """
    fees = _load_fees()

    # Normalise lookup key
    key = matter_type.lower().strip()
    row = fees.get(key)

    # Fuzzy fallback: check if any key contains the input
    if not row:
        for k, v in fees.items():
            if key in k or k in key:
                row = v
                key = k
                break

    if not row:
        row = {
            "base": "Fee not found in table — check the applicable Court Fees Act schedule.",
            "note": "Add this matter type to lexagent/data/court_fees.yaml for future lookups.",
        }

    # Ad valorem estimate when suit_value is provided and row references "ad valorem"
    ad_valorem_note = ""
    if suit_value > 0 and "ad valorem" in str(row.get("base", "")).lower():
        # Simple 10% Delhi HC estimate — correct for most civil suits
        estimated_fee = min(suit_value * 0.10, 75_000)
        ad_valorem_note = (
            f" For suit value ₹{suit_value:,.0f}: estimated fee ≈ ₹{estimated_fee:,.0f} "
            "(10% up to ₹75,000 cap — verify against current state schedule)."
        )

    state_note = f" State: {state}." if state else ""

    return {
        "matter_type": matter_type,
        "fee_description": str(row.get("base", "")) + ad_valorem_note,
        "statutory_basis": "Court Fees Act 1870 + applicable state schedule.",
        "notes": str(row.get("note", "")) + state_note,
        "suit_value": suit_value,
        "disclaimer": "Approximate only. Always verify with the specific court's fee schedule before filing.",
    }
