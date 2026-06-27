"""
Phase 10 — 07: Adversarial Multi-Agent Review Chamber
======================================================
Run:  pip install pydantic
      python 07_adversarial_chamber.py

The problem: every AI draft review tool today works the same way —
one LLM reads the draft and says what's wrong with it. That is the same
as asking a junior associate to proofread their own memo. The reviewer
and the writer share the same blind spots.

The insight: in a real law firm, a draft goes through multiple reviewers
who do not share the same goal:
  - A reviewer finds problems
  - A partner challenges whether those problems are real
  - An editor synthesises both into actionable instructions

This is the "adversarial chamber" pattern from doc-haus. Three sequential
LLM calls, each with a different role and access to different information.
The Challenger cannot do its job without the Reviewer's output.
The Summarizer cannot do its job without both.

This is a DAG dependency — lesson 5 (05_dynamic_planner.py) makes this
precise. Here we keep it simple.

Real code: themis/nodes/chamber.py
Activate: lex draft "review vendor agreement" --chamber
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Literal
import asyncio

print("=" * 60)
print("PART 1: Why one reviewer is not enough")
print("=" * 60)

# Simulate what a single-pass review produces
SAMPLE_DRAFT = """
IN THE COURT OF THE CHIEF JUDICIAL MAGISTRATE
GURUGRAM

Complaint Case No. ___ / 2026

COMPLAINT UNDER SECTION 138 OF THE NEGOTIABLE INSTRUMENTS ACT, 1881

The Complainant most respectfully submits as follows:

1. The accused issued a cheque bearing No. 001234 for Rs. 5,00,000/- (Five
   Lakhs only) drawn on XYZ Bank, Sector 14, Gurugram.

2. The cheque was presented for encashment on 10.01.2026 and was returned
   dishonoured with the memo "Insufficient Funds".

3. The Complainant sent a legal notice on 25.01.2026. The accused failed
   to pay the amount within 15 days.

PRAYER: The accused be convicted and sentenced under Section 138 NI Act.
"""

print("""
A single-pass reviewer will find:
  - Missing: date of cheque
  - Missing: cause of action date calculation
  - Prayer says "15 days" but the law requires 30 days
  - No section 141 block if accused is a company

But the same LLM that drafted this is now reviewing it.
It may miss errors that were systematic in the draft.
""")

# ---------------------------------------------------------------------------
# Section 2: The three-role architecture
# ---------------------------------------------------------------------------
print("=" * 60)
print("PART 2: Three roles, three different perspectives")
print("=" * 60)

print("""
Role 1 — REVIEWER
  Goal: find every material weakness
  Input: draft only
  Output: numbered issue list
  Constraint: be specific — not "improve the prayer", say
              "prayer cites 15-day period; S.138 mandates 30-day
               demand notice under proviso (b); this fails the
               limitation condition"

Role 2 — CHALLENGER
  Goal: push back on the reviewer's findings
  Input: issue list + draft
  Output: VALID / OVERSTATED / WRONG per item with reasoning
  Why: reviewers over-flag. A challenger who has seen both the
       issue and the draft can judge whether it is real.

Role 3 — SUMMARIZER (editorial counsel)
  Goal: produce actionable instructions for revision
  Input: issue list + challenger verdicts + draft
  Rules:
    VALID  → ACTION ITEM  (imperative, specific)
    OVERSTATED → ADVISORY item
    WRONG  → exclude entirely
  Output: final review with RISK LEVEL: LOW / MEDIUM / HIGH
""")

# ---------------------------------------------------------------------------
# Pause and think:
# ---------------------------------------------------------------------------
# Q: Why can't we do all three in a single prompt?
#
# A: The Challenger needs the Reviewer's numbered list to respond per-item.
#    If you give the LLM all three roles at once, it collapses them —
#    the Challenger cannot genuinely push back on findings it generated
#    itself. Role separation creates the adversarial tension that catches
#    more errors.
#
# Q: Isn't this three times the cost?
#
# A: Yes — roughly 3x tokens. For a legal document that will be filed
#    in court, that is the right trade-off. For first-pass research
#    or a simple summary, a single reviewer is fine. The --chamber flag
#    makes it opt-in.

# ---------------------------------------------------------------------------
# Section 3: Simulated chamber (no LLM needed to understand the pattern)
# ---------------------------------------------------------------------------
print("=" * 60)
print("PART 3: Simulated chamber run")
print("=" * 60)


@dataclass
class ChamberResult:
    issues: str
    pushback: str
    review: str
    risk_level: Literal["LOW", "MEDIUM", "HIGH"]


def simulated_reviewer(draft: str) -> str:
    """In production this is an LLM call with chamber_reviewer.txt prompt."""
    return (
        "1. Prayer cites 15-day repayment window; S.138 proviso (b) "
        "mandates 30 days from receipt of demand notice. Filing will fail "
        "the limitation condition.\n"
        "2. Cheque date not stated. Court requires the instrument date "
        "for the timeline of dishonour → notice → complaint.\n"
        "3. No S.141 block. If accused is a company, liability of directors "
        "must be separately pleaded under S.141 NI Act.\n"
        "4. Exhibit labels missing. Each document in the list must carry "
        "an EX-CW1/A style label for the court record."
    )


def simulated_challenger(issues: str, draft: str) -> str:
    """In production this is an LLM call with chamber_challenger.txt prompt."""
    return (
        "1. VALID — the 15-day figure is wrong; 30 days required. This "
        "will be caught by defence counsel and could cause dismissal.\n"
        "2. VALID — cheque date is essential; its absence is a pleading gap.\n"
        "3. OVERSTATED — whether accused is a company is not clear from the "
        "draft as given; this may not apply.\n"
        "4. VALID — exhibit labels are standard practice in this court and "
        "their absence will draw an objection at the first hearing."
    )


def simulated_summarizer(issues: str, pushback: str, draft: str) -> ChamberResult:
    """In production this is an LLM call with chamber_summarizer.txt prompt."""
    review = (
        "ACTION: Replace '15 days' in the prayer with '30 days' as required "
        "by S.138 proviso (b).\n"
        "ACTION: Add the cheque date in paragraph 1.\n"
        "ADVISORY: If the accused entity is a company or LLP, add a S.141 "
        "block pleading director/partner liability.\n"
        "ACTION: Add EX-CW1/A style exhibit labels to every document in the "
        "list of documents."
    )
    return ChamberResult(
        issues=issues,
        pushback=pushback,
        review=review,
        risk_level="MEDIUM",
    )


# Run the simulated chamber
print("\nRunning chamber on sample S.138 complaint draft...\n")
issues = simulated_reviewer(SAMPLE_DRAFT)
print("─── REVIEWER ────────────────────────────────────────")
print(issues)

pushback = simulated_challenger(issues, SAMPLE_DRAFT)
print("\n─── CHALLENGER ──────────────────────────────────────")
print(pushback)

result = simulated_summarizer(issues, pushback, SAMPLE_DRAFT)
print("\n─── FINAL REVIEW ────────────────────────────────────")
print(result.review)
print(f"\nRISK LEVEL: {result.risk_level}")

# ---------------------------------------------------------------------------
# Section 4: How the real node works
# ---------------------------------------------------------------------------
print("\n" + "=" * 60)
print("PART 4: The real implementation (themis/nodes/chamber.py)")
print("=" * 60)

print("""
The real node follows the same structure:

async def run(state: LexState) -> dict:
    if not state.get("chamber_enabled"):
        return {}                          # opt-in only
    try:
        llm = _get_llm()
        issues   = await llm.ainvoke(reviewer_prompt)
        pushback = await llm.ainvoke(challenger_prompt)   # sees issues
        review   = await llm.ainvoke(summarizer_prompt)   # sees both
        return {"chamber_issues": issues, "chamber_pushback": pushback,
                "chamber_review": review}
    except Exception as exc:
        return {"error": f"chamber: {exc}"}   # never raise from a node

Graph wiring (themis/graph.py):
    graph.add_conditional_edges(
        "draft",
        lambda state: "chamber" if state.get("chamber_enabled") else "review",
        {"chamber": "chamber", "review": "review"},
    )
    graph.add_edge("chamber", "review")

Prompt files:
    themis/prompts/chamber_reviewer.txt
    themis/prompts/chamber_challenger.txt
    themis/prompts/chamber_summarizer.txt
""")

# ---------------------------------------------------------------------------
# Section 5: V3 future — specialist subagents
# ---------------------------------------------------------------------------
print("=" * 60)
print("PART 5: V3 path — from one node to a specialist chamber")
print("=" * 60)

print("""
The chamber node (three sequential LLM calls) is a bridge.
V3 Phase 11 replaces it with 10 isolated specialist subagents:

  Senior Counsel    — owns the final answer, delegates, resolves conflicts
  Planner Counsel   — converts goal into execution DAG
  Research Counsel  — case law, precedents, treatment
  Statutory Counsel — acts, rules, notifications
  Procedure Counsel — jurisdiction, limitation, maintainability
  Evidence Counsel  — documents, chronology, admissions
  Drafting Counsel  — pleadings, notices, contracts
  Citation Counsel  — verifies citations, source text, treatment
  Risk Counsel      — attacks the draft, finds weak facts
  Client Counsel    — fact gathering, client-friendly summaries

The external interface is the same: `chamber_review` in LexState.
The node boundary is the same: `draft → chamber → review`.

This is the key design principle in LexAgent:
  Ship the interface first. Replace the internals later.
  The graph topology does not change. Only the node internals evolve.
""")

print("\n✅ Run: lex draft 'review vendor agreement' --chamber")
