"""
Phase 4 — Exercise 2: Build a ReAct Research Loop

Implement a 3-iteration Reason-Act-Observe loop using the stub search tool.
"""


# ── STUB TOOL (already implemented — use this) ────────────────────────────────

STUB_CASES = {
    "article 21": ["Maneka Gandhi AIR 1978 SC 597", "Kharak Singh AIR 1963 SC 1295"],
    "maneka gandhi": ["Francis Coralie 1981 SC 746", "Olga Tellis 1985 SCC 545"],
    "personal liberty": ["A.K. Gopalan AIR 1950 SC 27", "Rustom Cavasjee Cooper 1970 SC"],
    "writ petition": ["Bandhua Mukti Morcha AIR 1984 SC 802"],
}

def stub_search(query: str) -> list[str]:
    """Simulates Indian Kanoon search with hardcoded results."""
    results = []
    query_lower = query.lower()
    for key, cases in STUB_CASES.items():
        if key in query_lower:
            results.extend(cases)
    return list(set(results))  # deduplicate


# ── IMPLEMENT THESE ───────────────────────────────────────────────────────────

def decide_next_query(goal: str, iteration: int, previous_findings: list[str]) -> str:
    """
    Simulate the 'Reason' step — decide what to search next.
    Simple rules (no LLM needed):
      - iteration 0: search the goal directly
      - iteration 1: if findings mention "Maneka Gandhi", search "maneka gandhi"
      - iteration 2: search for "personal liberty" (always useful)
    """
    # TODO: implement the 3-iteration logic described above
    pass


def run_react_loop(goal: str, max_iterations: int = 3) -> dict:
    """
    Run a ReAct research loop.
    Returns: {"findings": list[str], "iterations_used": int, "queries_tried": list[str]}

    Each iteration should:
      1. Print f"[Iteration {i+1}] Reason: {reasoning}"
      2. Call stub_search with the query
      3. Print f"[Iteration {i+1}] Observe: found {n} cases: {results}"
      4. Add results to all_findings
      5. Stop early if len(all_findings) >= 4
    """
    # TODO: implement the loop
    pass


def verify_citations(draft_text: str, findings: list[str]) -> dict:
    """
    Check that every case name in the draft appears in findings.
    A simple check: look for 'v.' patterns in draft, verify each appears in findings.
    Returns: {"verified": bool, "unverified": list[str], "verified_count": int}
    """
    import re
    # Extract case names: patterns like "Maneka Gandhi" before "v." or "AIR YYYY"
    cited = re.findall(r'([A-Z][a-zA-Z\s]+(?:v\.|AIR)\s*\d*)', draft_text)
    cited = [c.strip() for c in cited if len(c.strip()) > 5]

    # TODO: for each cited case, check if any finding contains it
    # Return {"verified": all_found, "unverified": [...], "verified_count": n}
    pass


# ── TESTS ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("ReAct Research Loop Demo")
    print("Goal: research 'article 21 right to life writ petition'")
    print("=" * 60)

    result = run_react_loop("article 21 right to life writ petition")
    print(f"\nFinal findings ({len(result['findings'])} cases):")
    for case in result["findings"]:
        print(f"  - {case}")
    print(f"Iterations used: {result['iterations_used']}")
    print(f"Queries tried: {result['queries_tried']}")

    # Citation verification test
    print("\n" + "=" * 60)
    print("Citation Verification")
    sample_draft = "As held in Maneka Gandhi AIR 1978 SC 597, Article 21 is expansive."
    verification = verify_citations(sample_draft, result["findings"])
    if verification:
        print(f"Verified: {verification['verified']}")
        print(f"Unverified citations: {verification['unverified']}")

# ── PAUSE AND THINK ───────────────────────────────────────────────────────────
# 1. Open lexagent/nodes/react_research.py — how does the real loop differ?
#    Does it use actual LLM reasoning or a rule-based approach like yours?
# 2. What is cfg.react_max_iterations for? Open lexagent/config.py to find it.
# 3. The citation gate blocks output if too many citations are unverified.
#    Open lexagent/nodes/cite.py — what is the threshold config field?
