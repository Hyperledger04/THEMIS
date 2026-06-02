"""
Phase 10, Lesson 5: The Dynamic Planner — DAGs Instead of Hardcoded Graphs

Today: lexagent/graph.py has hardcoded conditional edges.
V3: Planner Counsel generates an execution DAG per matter type and goal.
"""
from pydantic import BaseModel
from typing import Optional

print("=" * 60)
print("Dynamic Planner — From Static Graph to DAGs")
print("=" * 60)

# ── SECTION 1: The problem with the current graph ─────────────────────────────
print("""
  Current graph.py (hardcoded routing):

    intake → [route_after_intake] → research OR draft OR contract_review
    research → [route_after_research] → draft
    draft → [route_after_draft] → cite OR review

  Problems:
    - Adding "NI Act Section 138" workflow = editing graph.py + adding conditions
    - Different forums need different node sequences (Supreme Court ≠ NCLT)
    - The graph doesn't know it's doing a writ vs. arbitration until mid-run
    - Every new matter type = more conditional edges = harder to reason about

  V3: Planner generates the graph at runtime from a template or LLM output.
""")

# ── SECTION 2: ExecutionDAG model ─────────────────────────────────────────────
class ExecutionDAG(BaseModel):
    matter_type: str
    nodes: list[str]
    dependencies: dict[str, list[str]]  # node → list of nodes it depends on
    approval_gates: list[str]           # nodes needing human approval before continuing
    tools_required: dict[str, list[str]]  # node → tools it needs


# ── SECTION 3: Template DAGs (MVP — before LLM-generated DAGs) ─────────────────
LEGAL_NOTICE_DAG = ExecutionDAG(
    matter_type="legal_notice",
    nodes=["intake_facts", "limitation_check", "draft_notice", "risk_review", "final_notice"],
    dependencies={
        "intake_facts": [],
        "limitation_check": ["intake_facts"],
        "draft_notice": ["intake_facts", "limitation_check"],
        "risk_review": ["draft_notice"],
        "final_notice": ["risk_review"],
    },
    approval_gates=["final_notice"],  # lawyer must approve before sending
    tools_required={
        "limitation_check": ["calculate_limitation"],
        "draft_notice": ["load_skill", "call_llm"],
        "risk_review": ["call_llm"],
    }
)

WRIT_PETITION_DAG = ExecutionDAG(
    matter_type="writ_petition",
    nodes=[
        "intake_facts", "check_alternative_remedy", "rights_research",
        "statutory_research", "draft_petition", "citation_verification",
        "risk_attack", "revision", "final_petition"
    ],
    dependencies={
        "intake_facts": [],
        "check_alternative_remedy": ["intake_facts"],
        "rights_research": ["check_alternative_remedy"],
        "statutory_research": ["intake_facts"],
        "draft_petition": ["rights_research", "statutory_research"],
        "citation_verification": ["draft_petition"],
        "risk_attack": ["draft_petition"],
        "revision": ["citation_verification", "risk_attack"],
        "final_petition": ["revision"],
    },
    approval_gates=["final_petition"],
    tools_required={
        "rights_research": ["search_kanoon", "expand_query"],
        "statutory_research": ["search_gazette"],
        "draft_petition": ["load_skill", "call_llm"],
        "citation_verification": ["verify_citation", "hybrid_retriever"],
        "risk_attack": ["call_llm"],
    }
)

NI_ACT_138_DAG = ExecutionDAG(
    matter_type="ni_act_138",
    nodes=[
        "document_checklist", "cheque_extraction", "limitation_compliance",
        "complaint_draft", "evidence_bundle", "final_complaint"
    ],
    dependencies={
        "document_checklist": [],
        "cheque_extraction": ["document_checklist"],
        "limitation_compliance": ["cheque_extraction"],
        "complaint_draft": ["cheque_extraction", "limitation_compliance"],
        "evidence_bundle": ["complaint_draft"],
        "final_complaint": ["evidence_bundle"],
    },
    approval_gates=["evidence_bundle", "final_complaint"],
    tools_required={
        "cheque_extraction": ["extract_dates", "extract_entities"],
        "limitation_compliance": ["calculate_limitation"],
        "complaint_draft": ["load_skill", "call_llm"],
        "evidence_bundle": ["write_docx"],
    }
)

TEMPLATES = {
    "legal_notice": LEGAL_NOTICE_DAG,
    "writ_petition": WRIT_PETITION_DAG,
    "ni_act_138": NI_ACT_138_DAG,
    "writ": WRIT_PETITION_DAG,  # alias
}

# ── SECTION 4: Planner — select and return template ───────────────────────────
def select_template(matter_type: str) -> Optional[ExecutionDAG]:
    """
    MVP Planner: return template DAG for the matter type.
    Returns None if no template exists.
    V3 upgrade path: call LLM to generate DAG for unknown matter types.
    """
    return TEMPLATES.get(matter_type.lower())


# ── SECTION 5: Topological sort ───────────────────────────────────────────────
def topo_sort(dag: ExecutionDAG) -> list[str]:
    """
    Order nodes by their dependencies (Kahn's algorithm).
    Nodes with no dependencies run first.
    Returns ordered list of node names.
    """
    in_degree = {node: len(dag.dependencies.get(node, [])) for node in dag.nodes}
    queue = [n for n in dag.nodes if in_degree[n] == 0]
    result = []

    while queue:
        node = queue.pop(0)
        result.append(node)
        # Reduce in-degree for nodes that depend on this one
        for other in dag.nodes:
            deps = dag.dependencies.get(other, [])
            if node in deps:
                in_degree[other] -= 1
                if in_degree[other] == 0:
                    queue.append(other)

    return result


# ── SECTION 6: Demo ───────────────────────────────────────────────────────────
print("── Execution Orders for 3 Matter Types ──")

for matter_type in ["legal_notice", "writ_petition", "ni_act_138"]:
    dag = select_template(matter_type)
    order = topo_sort(dag)
    gates = dag.approval_gates

    print(f"\n{matter_type.upper().replace('_', ' ')}:")
    for i, node in enumerate(order):
        gate = " ⏸ LAWYER APPROVAL REQUIRED" if node in gates else ""
        print(f"  {i+1}. {node}{gate}")

print("""
── How the Planner fits into V3 graph.py ──

  V3 graph.py:
    1. "planner" node calls select_template(state["matter_type"])
    2. Stores ExecutionDAG in state["execution_dag"]
    3. "runtime" node reads dag, calls topo_sort, executes nodes in order
    4. At approval gates: runtime returns END, waits for lawyer signal
    5. After approval: runtime resumes from checkpoint, continues next node

  This replaces the hardcoded add_conditional_edges in current graph.py.
  New matter types = new template dict entry, no graph.py changes needed.
""")

print("── Comparison: Current vs V3 ──")
print("""
  Current graph.py routing:
    route_after_intake() → "research" | "draft" | "contract_review"
    Add NI Act 138 → edit route_after_intake(), add "ni_act_research" node,
                      add edges, add state fields, rebuild graph

  V3 planner:
    select_template("ni_act_138") → returns NI_ACT_138_DAG
    Runtime executes in topological order
    Add NI Act 138 → add NI_ACT_138_DAG to TEMPLATES dict. Done.
""")

# ── PAUSE AND THINK ───────────────────────────────────────────────────────────
print("── PAUSE AND THINK ──")
print("""
  1. Read LEXAGENT_OS_V3_ARCHITECTURE_ROADMAP.md Section 7.
     The roadmap says to start with template plans before LLM-generated DAGs.
     Why? What could go wrong if you let the LLM generate the execution graph?

  2. Open lexagent/graph.py — count the add_conditional_edges calls.
     Each one is a routing decision that would become a template in V3.
     How many matter types does the current graph handle?

  3. The NI_ACT_138_DAG has 2 approval gates (evidence_bundle and final_complaint).
     This means the lawyer must review twice. For a simple legal notice (1 gate),
     the lawyer reviews once. Design a risk-based rule for when to add more gates.

  4. topo_sort() orders nodes linearly. But rights_research and statutory_research
     in WRIT_PETITION_DAG can run in PARALLEL (no dependency between them).
     How would you modify topo_sort to identify parallelizable node groups?

  5. What should the planner return if matter_type is "consumer_forum_complaint"
     and there's no template? Three options: (a) refuse, (b) fall back to
     writ_petition template, (c) call LLM to generate a DAG. What are the
     safety implications of option (c)?
""")
