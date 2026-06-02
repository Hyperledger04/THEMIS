"""
Phase 10, Lesson 4: The Legal Chamber — Specialist Subagents

Today: one graph node does research, drafting, citation, AND review.
V3: 10 specialist counsel agents, coordinated by Senior Counsel.
"""
import asyncio
from typing import Optional
from pydantic import BaseModel

print("=" * 60)
print("The Legal Chamber — Division of Labor")
print("=" * 60)

# ── SECTION 1: Why specialists? ───────────────────────────────────────────────
print("""
  A real law firm has:
    Partners   → review and sign off (Senior Counsel)
    Researchers → case law and precedents (Research Counsel)
    Draftsmen  → pleadings and notices (Drafting Counsel)
    Juniors    → procedural checks (Procedure Counsel)

  Today's LexAgent draft node does all of this in one LLM call.
  Problems:
    - The LLM can't be simultaneously a neutral researcher AND an adversarial critic
    - One prompt can't carry enough context for both research AND drafting
    - No division of expertise → generic output for all matter types

  V3 Legal Chamber: 10 specialists with separate tools, prompts, and scope.
""")

# ── SECTION 2: The 10 specialists ─────────────────────────────────────────────
SPECIALISTS = {
    "senior_counsel": {
        "role": "Coordinator and final approver. Delegates to specialists, resolves conflicts.",
        "tools": [],
        "system_prompt_theme": "You are the lead advocate. Delegate work, ensure quality."
    },
    "planner_counsel": {
        "role": "Converts goal into an execution DAG with required inputs.",
        "tools": ["get_matter_type_template"],
        "system_prompt_theme": "You plan. Given a goal, define the tasks and order."
    },
    "research_counsel": {
        "role": "Case law, precedents, negative authorities, treatment history.",
        "tools": ["search_kanoon", "fetch_judgment", "expand_query"],
        "system_prompt_theme": "You research. Find binding and persuasive authorities."
    },
    "statutory_counsel": {
        "role": "Acts, rules, regulations, notifications, circulars.",
        "tools": ["search_gazette", "search_mca", "search_sebi"],
        "system_prompt_theme": "You find the applicable statute and current amendments."
    },
    "procedure_counsel": {
        "role": "Jurisdiction, limitation, maintainability, forum, court fees.",
        "tools": ["calculate_limitation", "court_fees_calc", "check_maintainability"],
        "system_prompt_theme": "You check if the case can be filed and where."
    },
    "evidence_counsel": {
        "role": "Documents, chronology, admissions, gaps, exhibit mapping.",
        "tools": ["extract_dates", "build_chronology", "identify_gaps"],
        "system_prompt_theme": "You analyze the facts and documents, build the timeline."
    },
    "drafting_counsel": {
        "role": "Pleadings, notices, contracts, affidavits, applications.",
        "tools": ["write_docx", "load_skill", "get_template"],
        "system_prompt_theme": "You draft. Use the research and facts provided."
    },
    "citation_counsel": {
        "role": "Verifies citations: source text, page, treatment history.",
        "tools": ["verify_citation", "fetch_judgment", "check_treatment"],
        "system_prompt_theme": "You verify. Every citation must be grounded in source text."
    },
    "risk_counsel": {
        "role": "Adversarial critique — attacks the draft, finds weak points.",
        "tools": ["search_adverse_law", "identify_gaps"],
        "system_prompt_theme": "You are opposing counsel. Find every weakness in this draft."
    },
    "client_counsel": {
        "role": "Fact gathering, clarifying questions, client-friendly summaries.",
        "tools": ["send_question", "summarize_for_client"],
        "system_prompt_theme": "You communicate with the client. Plain language only."
    },
}

print("── The 10 Legal Chamber Specialists ──")
for name, spec in SPECIALISTS.items():
    print(f"\n  {name.upper().replace('_', ' ')}")
    print(f"    Role:  {spec['role']}")
    print(f"    Tools: {spec['tools'] or ['(coordinator only)']}")

# ── SECTION 3: Subagent contract ──────────────────────────────────────────────
print("""
\n── Subagent Contract (same as LangGraph node contract) ──

  Every specialist must:
  1. Be async def — non-blocking
  2. Accept state dict (or specific fields) — no internal state
  3. Return partial dict — only changed keys
  4. Never raise — catch and return {"error": str(e)}
  5. Never store state internally — pure function behavior

  This is identical to the node contract from Phase 1.
  Each specialist IS a specialized node with its own tools and system prompt.
""")

# ── SECTION 4: Mock specialist implementations ────────────────────────────────
class SpecialistResult(BaseModel):
    specialist: str
    status: str
    output: dict
    error: Optional[str] = None


async def research_counsel_run(matter_brief: str, matter_type: str) -> SpecialistResult:
    """Research Counsel: find relevant case law."""
    await asyncio.sleep(0.05)  # simulate LLM + API calls
    return SpecialistResult(
        specialist="research_counsel",
        status="completed",
        output={
            "research_findings": [
                "Maneka Gandhi v. UOI, AIR 1978 SC 597: Article 21 personal liberty expanded.",
                "Olga Tellis v. BMC, 1985 SCC 545: Right to livelihood part of Article 21.",
            ],
            "key_authorities": ["AIR 1978 SC 597", "1985 SCC 545"],
        }
    )


async def procedure_counsel_run(matter_type: str, cause_of_action_date: str) -> SpecialistResult:
    """Procedure Counsel: check limitation and jurisdiction."""
    await asyncio.sleep(0.03)
    return SpecialistResult(
        specialist="procedure_counsel",
        status="completed",
        output={
            "limitation_status": "Within time — 287 days remaining",
            "forum": "High Court of Delhi",
            "alternative_remedy_exists": False,
            "maintainability_note": "Writ is maintainable — no statutory alternative remedy.",
        }
    )


async def drafting_counsel_run(research: dict, procedure: dict, brief: str) -> SpecialistResult:
    """Drafting Counsel: produce the draft using research and procedure outputs."""
    await asyncio.sleep(0.05)
    return SpecialistResult(
        specialist="drafting_counsel",
        status="completed",
        output={
            "draft_output": (
                f"IN THE HIGH COURT OF DELHI\n\n"
                f"WRIT PETITION (CIVIL) NO. ___/2024\n\n"
                f"MOST RESPECTFULLY SHOWETH:\n\n"
                f"1. That the petitioner is aggrieved by {brief[:40]}...\n\n"
                f"2. That as held in {research['key_authorities'][0]}, "
                f"the right to personal liberty cannot be curtailed without...\n\n"
                f"3. Forum: {procedure['forum']}. {procedure['maintainability_note']}"
            )
        }
    )


async def risk_counsel_run(draft: str) -> SpecialistResult:
    """Risk Counsel: adversarial critique of the draft."""
    await asyncio.sleep(0.03)
    return SpecialistResult(
        specialist="risk_counsel",
        status="completed",
        output={
            "risks": [
                "Citation AIR 1978 SC 597 must be verified against source text",
                "Prayer clause does not specify the exact relief sought",
                "No averment about exhaustion of alternative remedies",
            ],
            "risk_level": "medium",
        }
    )


# ── SECTION 5: Senior Counsel coordination ────────────────────────────────────
async def senior_counsel_run(matter_brief: str, matter_type: str) -> dict:
    """
    Senior Counsel: delegates to specialists, collects outputs, assembles final response.
    """
    print("\n[Senior Counsel] Delegating to specialists...")

    # Run specialists — some in parallel, some sequential (dependency-based)
    research_result, procedure_result = await asyncio.gather(
        research_counsel_run(matter_brief, matter_type),
        procedure_counsel_run(matter_type, "2024-01-15"),
    )
    print(f"  [Research Counsel] ✓ Found {len(research_result.output['research_findings'])} authorities")
    print(f"  [Procedure Counsel] ✓ Forum: {procedure_result.output['forum']}")

    # Drafting depends on research + procedure
    draft_result = await drafting_counsel_run(
        research_result.output, procedure_result.output, matter_brief
    )
    print(f"  [Drafting Counsel] ✓ Draft: {len(draft_result.output['draft_output'])} chars")

    # Risk runs on the draft
    risk_result = await risk_counsel_run(draft_result.output["draft_output"])
    print(f"  [Risk Counsel] ✓ {len(risk_result.output['risks'])} risks identified")

    print("\n[Senior Counsel] Final approval — assembling output...")
    return {
        "draft_output": draft_result.output["draft_output"],
        "research_findings": research_result.output["research_findings"],
        "risk_annotations": risk_result.output["risks"],
        "risk_level": risk_result.output["risk_level"],
        "forum": procedure_result.output["forum"],
    }


# ── SECTION 6: Demo ───────────────────────────────────────────────────────────
print("\n── Legal Chamber Demo ──")

async def demo():
    result = await senior_counsel_run(
        matter_brief="Writ petition challenging illegal demolition of shop without notice",
        matter_type="writ_petition"
    )
    print("\n── Final Output ──")
    print(f"Draft ({len(result['draft_output'])} chars):")
    print(result["draft_output"][:200] + "...")
    print(f"\nRisk annotations ({result['risk_level']} risk):")
    for r in result["risk_annotations"]:
        print(f"  ⚠ {r}")

asyncio.run(demo())

# ── PAUSE AND THINK ───────────────────────────────────────────────────────────
print("\n── PAUSE AND THINK ──")
print("""
  1. Read LEXAGENT_OS_V3_ARCHITECTURE_ROADMAP.md Section 5.
     The roadmap lists 10 specialists. Which ones does the current lexagent/agents/
     directory already have? Which are missing?

  2. Senior Counsel runs Research and Procedure in parallel (asyncio.gather).
     Drafting runs AFTER both complete. This is a dependency graph.
     Draw the dependency graph for NI Act Section 138 using the job types from Lesson 3.

  3. Each specialist has its own system_prompt_theme. Risk Counsel's prompt is
     explicitly adversarial ("you are opposing counsel"). Why is this necessary?
     What happens if you use the same prompt for both Drafting and Risk counsel?

  4. The specialists here are mock functions. In V3, each specialist would be
     a LangGraph subgraph with its own nodes and tools. How would you ensure
     specialist subgraphs share the same LangGraph checkpointer (for pause/resume)?

  5. "67-agent firm council" is listed in the roadmap's POSTPONE section.
     Why is this postponed? What would need to be true about the system
     before 67 agents becomes a viable product feature rather than a liability?
""")
