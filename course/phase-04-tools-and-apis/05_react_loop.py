"""
05_react_loop.py — ReAct (Reason-Act-Observe) Research Loop
=============================================================
A single search query is rarely enough for real legal research.
The lawyer might say "right to life article 21" — but the agent needs
to chase follow-up threads: landmark cases, subsequent cases that followed
or distinguished them, and relevant statutes. ReAct structures this pursuit.
"""

# ── SECTION 1: THE PROBLEM WITH SINGLE-SHOT SEARCH ───────────────────────────
#
# Naive approach (what NOT to do):
#   results = search("article 21 writ petition")
#   draft(results)
#
# Problems:
#   • One query catches only top-level hits. Nuanced cases are missed.
#   • The agent can't adapt — if the first query returns nothing useful,
#     it has no way to try a different angle.
#   • Research depth is fixed regardless of how complex the matter is.
#
# ReAct fixes this by letting the agent *reason* about what to search next
# based on what it has already found.

# ── SECTION 2: THE REACT PATTERN ─────────────────────────────────────────────
#
# ReAct = Reason → Act → Observe → (loop back to Reason)
#
#   Reason:  "I've found Maneka Gandhi. What cases followed it?
#             I should search for 'Maneka Gandhi followed distinguished'."
#
#   Act:     call search_kanoon("Maneka Gandhi followed distinguished")
#
#   Observe: "Found 2 more cases: Francis Coralie 1981, Olga Tellis 1985."
#             Add them to findings.
#
#   Reason:  "Do I have enough? Three cases covering personal liberty.
#             The lawyer also asked about procedural fairness — one more search."
#
# This loop continues until:
#   (a) enough findings are accumulated, or
#   (b) max_iterations is reached (cost control)
#
# WHY max_iterations: each iteration = one LLM call + one API call.
# Without a ceiling, a complex matter could run 20 iterations.
# LexConfig exposes `react_max_iterations` (default: 4) so lawyers can tune it.

MAX_ITERATIONS = 3  # mirrors LexConfig.react_max_iterations default

# ── SECTION 3: SIMULATED SEARCH TOOL ─────────────────────────────────────────
#
# No LLM calls, no API calls — pure simulation so you can run this file
# anywhere with just Python stdlib.

STUB_CASES: dict[str, list[str]] = {
    "article 21": [
        "Maneka Gandhi v Union of India — AIR 1978 SC 597",
        "Kharak Singh v State of UP — AIR 1963 SC 1295",
    ],
    "maneka gandhi followed": [
        "Francis Coralie Mullin v Administrator Union Territory of Delhi — 1981 SC",
        "Olga Tellis v Bombay Municipal Corporation — AIR 1986 SC 180",
    ],
    "maneka gandhi distinguished": [
        "ADM Jabalpur v Shivkant Shukla — AIR 1976 SC 1207",
    ],
    "personal liberty procedural fairness": [
        "A.K. Gopalan v State of Madras — AIR 1950 SC 27",
    ],
    "right to life shelter": [
        "Olga Tellis v Bombay Municipal Corporation — AIR 1986 SC 180",
        "Chameli Singh v State of UP — AIR 1996 SC 1051",
    ],
}


def stub_search(query: str) -> list[str]:
    """Return stub results whose key appears in the query string."""
    for key, results in STUB_CASES.items():
        if key in query.lower():
            return results
    return []


# ── SECTION 4: THE REACT LOOP ─────────────────────────────────────────────────

def run_react_loop(initial_query: str, max_iterations: int = MAX_ITERATIONS) -> dict:
    """
    Run a multi-iteration ReAct research loop.

    In production, the 'Reason' step is an LLM call that decides the next
    query. Here we simulate it with a simple progression rule.

    Returns:
        {"findings": list[str], "queries_tried": list[str], "iterations": int}
    """
    all_findings: list[str] = []
    queries_tried: list[str] = []

    # Simulated reasoning strategy — in production an LLM generates these
    query_progression = [
        initial_query,
        initial_query.split()[0] + " followed distinguished",
        initial_query.split()[0] + " right to life shelter",
    ]

    for i in range(max_iterations):
        # ── REASON ────────────────────────────────────────────────────────────
        query = query_progression[i] if i < len(query_progression) else initial_query
        print(f"\n[Iteration {i + 1}/{max_iterations}]")
        print(f"  Reason  : searching for '{query}'")

        # ── ACT ───────────────────────────────────────────────────────────────
        queries_tried.append(query)
        results = stub_search(query)

        # ── OBSERVE ───────────────────────────────────────────────────────────
        new = [r for r in results if r not in all_findings]
        all_findings.extend(new)
        print(f"  Observe : found {len(results)} case(s), {len(new)} new")
        for r in new:
            print(f"            + {r}")

        # ── STOP CONDITION ────────────────────────────────────────────────────
        # WHY 3: a minimum viable citation set for most Indian court documents
        # is 3–5 cases. Stopping early saves tokens and API quota.
        if len(all_findings) >= 3:
            print(f"  Decision: {len(all_findings)} findings — sufficient, stopping early.")
            return {
                "findings": list(dict.fromkeys(all_findings)),  # preserve order, dedupe
                "queries_tried": queries_tried,
                "iterations": i + 1,
            }

    print(f"\n  Decision: reached max_iterations={max_iterations}, returning what we have.")
    return {
        "findings": list(dict.fromkeys(all_findings)),
        "queries_tried": queries_tried,
        "iterations": max_iterations,
    }


# ── SECTION 5: CITATION GATE ──────────────────────────────────────────────────
#
# After the loop, the agent drafts the document. Before sending it to the
# lawyer, the cite node verifies that every case cited in the draft actually
# appeared in the research findings. This prevents hallucinated citations.

def verify_citations(draft_text: str, findings: list[str]) -> dict:
    """
    Check that every case name in `draft_text` appears in `findings`.
    A citation is identified by the pattern 'X v Y' (contains ' v ').

    Returns:
        {"verified": bool, "unverified": list[str]}
    """
    # Extract candidate citations from draft text
    cited: list[str] = []
    for word_group in [draft_text[i:i+60] for i in range(0, len(draft_text), 20)]:
        if " v " in word_group or " v. " in word_group:
            # Grab a 50-char window around the 'v' as the citation name
            idx = word_group.find(" v ")
            snippet = word_group[max(0, idx - 15): idx + 20].strip()
            if snippet and snippet not in cited:
                cited.append(snippet)

    # Check each against the findings list (case-insensitive substring match)
    findings_lower = [f.lower() for f in findings]
    unverified = [
        c for c in cited
        if not any(c.lower()[:10] in f for f in findings_lower)
    ]

    return {
        "verified": len(unverified) == 0,
        "unverified": unverified,
    }


# ── LIVE DEMO ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("REACT LOOP DEMO: 'right to life article 21'")
    print("=" * 60)

    result = run_react_loop("article 21 right to life")

    print("\n── FINAL RESEARCH FINDINGS ──────────────────────────")
    for i, finding in enumerate(result["findings"], 1):
        print(f"  {i}. {finding}")
    print(f"\nQueries tried : {result['queries_tried']}")
    print(f"Iterations    : {result['iterations']}")

    # Demonstrate citation gate
    print("\n── CITATION GATE ────────────────────────────────────")
    sample_draft = (
        "As held in Maneka Gandhi v Union of India (AIR 1978 SC 597), "
        "Article 21 extends beyond mere physical existence. "
        "This was further elaborated in Phantom Case v Imaginary State, "
        "a case that does not exist and should be flagged."
    )
    gate = verify_citations(sample_draft, result["findings"])
    print(f"  Verified?   : {gate['verified']}")
    print(f"  Unverified  : {gate['unverified']}")


# ── PAUSE AND THINK ───────────────────────────────────────────────────────────
#
# 1. In `lexagent/nodes/react_research.py`, the 'Reason' step is a real LLM
#    call. What prompt do you give the LLM so it generates the *next* query
#    rather than hallucinating a full answer?
#
# 2. `lexagent/config.py` has a `react_max_iterations` field. If a lawyer sets
#    it to 1, they get a single-shot search. When would that be preferable?
#
# 3. The citation gate above uses a simple substring match. What are two ways
#    it could produce a false negative (missing a real hallucination)?
#
# 4. LangGraph can run nodes in parallel using `Send`. Could you parallelise
#    the three ReAct iterations to run simultaneously? What would break?
#
# 5. The loop stops when findings >= 3. Should the stopping condition be based
#    on *quantity* of findings or *quality* (e.g. relevance score)? How would
#    you implement a quality-based stop?
