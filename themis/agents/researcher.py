"""
ResearcherAgent — Full ReAct Investigation Loop (R1).

Replaces the V3.3 thin adapter that delegated straight to react_research.run().
Now runs a genuine plan → search → evaluate → loop cycle where the LLM decides:
  - Which queries to run and which tool to route each to (Kanoon vs Tavily)
  - Whether the gathered findings are sufficient to proceed to drafting
  - What gap queries to run if research is incomplete

After the loop:
  - Citation gate drops any finding without {title, url, doc_excerpt, citation}
  - Passed judgments are synchronously indexed to Qdrant so DrafterAgent can
    retrieve them in the same run (Locked Decision 17, §1 V3 architecture)

WHY a separate module from react_research.py:
  react_research.py = single-pass node wired into the legacy flat graph.
  researcher.py      = specialist subgraph dispatched by Senior Counsel via send().
  Both coexist. The legacy node is not removed (breaking change for existing
  tests/CLI flows); this module is the V3 multi-agent path.

Node contract: async def run(state: SeniorCounselState) -> dict
  Returns only changed keys. Never raises — all exceptions → state["error"].
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Optional

from rich.console import Console

from themis.config import LexConfig
from themis.nodes._llm import call_llm
from themis.nodes.react_research import (
    _enforce_citation_gate,
    _run_kanoon_search,
    _run_tavily_search,
)
from themis.state import SeniorCounselState

logger = logging.getLogger(__name__)
console = Console()

_STATUTE_RE = re.compile(
    r"\b(CPC|IPC\s+[Ss](?:ection)?\.?\s*\d+|CrPC\s+[Ss](?:ection)?\.?\s*\d+"
    r"|NI\s+Act\s+[Ss](?:ection)?\.?\s*\d+|Specific\s+Relief\s+Act\s+[Ss](?:ection)?\.?\s*\d+"
    r"|Indian\s+Contract\s+Act\s+[Ss](?:ection)?\.?\s*\d+"
    r"|Constitution\s+of\s+India\s+(?:Article|Art\.?)\s*\d+)\b"
)


# ---------------------------------------------------------------------------
# Corpus namespace detection (§3 Storage Architecture)
# ---------------------------------------------------------------------------

def _corpus_namespace(finding: dict) -> str:
    """
    Infer the Qdrant corpus collection from a finding's source metadata.
    WHY: Corpus provenance must be tagged at indexing time, not retrieval time
    (Locked Decision 3 + §16.2 confidentiality). Mixing corpora in a single
    collection without partition metadata causes jurisdictional conflation
    (Failure Mode 2, §11).
    """
    src = (finding.get("docsource", "") + " " + finding.get("citation", "")).lower()
    if "supreme court" in src or re.search(r"\bsc\b", src):
        return "corpus:india_sc"
    if "high court" in src or re.search(r"\bhc\b", src):
        for state in ("delhi", "bombay", "madras", "calcutta", "allahabad", "kerala", "gujarat", "rajasthan"):
            if state in src:
                return f"corpus:india_hc:{state}"
        return "corpus:india_hc:unknown"
    if "privy council" in src:
        return "corpus:privy_council"
    if any(k in src for k in ("uk", "united kingdom", "singapore", "australia", "england and wales")):
        return "corpus:foreign_persuasive"
    if any(k in src for k in ("gazette", "notification", "circular", "rbi", "sebi", "regulation")):
        return "corpus:regulations"
    if any(k in src for k in ("act", "statute", "code", "rules")):
        return "corpus:statutes"
    return "corpus:india_subordinate"


# ---------------------------------------------------------------------------
# Qdrant sync indexing (Locked Decision 17 — judgments sync, same run)
# ---------------------------------------------------------------------------

async def _sync_judgments_to_qdrant(
    findings: list[dict],
    matter_id: str,
    firm_id: str,
    cfg: LexConfig,
) -> int:
    """
    Index passed judgments to Qdrant synchronously.

    WHY sync (not async): DrafterAgent reads from Qdrant in the same graph run.
    If indexing were async, Drafter would get a cache miss on every first run.
    Matter summaries and lawyer feedback are indexed async (Locked Decision 17).

    Returns the number of points upserted (0 when Qdrant is disabled/unavailable).
    """
    if not cfg.qdrant_enabled or not findings:
        return 0

    try:
        # WHY lazy imports: qdrant-client and sentence-transformers are optional
        # extras. Importing at module level would crash startup when not installed.
        from qdrant_client import AsyncQdrantClient  # type: ignore[import]
        from qdrant_client import models as qm  # type: ignore[import]
        from sentence_transformers import SentenceTransformer  # type: ignore[import]
    except ImportError:
        logger.warning(
            "qdrant-client or sentence-transformers not installed — "
            "run: uv add qdrant-client sentence-transformers"
        )
        return 0

    try:
        import hashlib

        client = AsyncQdrantClient(
            url=cfg.qdrant_url,
            api_key=cfg.qdrant_api_key or None,
        )
        # WHY local encoder: all-MiniLM-L6-v2 is 22 MB, runs on CPU, handles
        # Indian legal text well. No cloud call, no PII exposure (§16.2).
        encoder = SentenceTransformer(cfg.embedding_model)

        # Group findings by corpus namespace for efficient per-collection upsert
        by_ns: dict[str, list[dict]] = {}
        for f in findings:
            ns = _corpus_namespace(f)
            by_ns.setdefault(ns, []).append(f)

        total = 0
        for namespace, ns_findings in by_ns.items():
            # Ensure collection exists with correct vector config
            try:
                await client.get_collection(namespace)
            except Exception:
                await client.create_collection(
                    collection_name=namespace,
                    vectors_config=qm.VectorParams(
                        size=cfg.embedding_dim,
                        distance=qm.Distance.COSINE,
                    ),
                )

            texts = [
                f.get("doc_excerpt") or f.get("full_text", "")[:500]
                for f in ns_findings
            ]
            embeddings = encoder.encode(texts, normalize_embeddings=True).tolist()

            points = []
            for f, vec in zip(ns_findings, embeddings):
                # WHY deterministic ID: same URL always maps to the same Qdrant
                # point, so re-indexing the same judgment is idempotent (upsert).
                point_id = (
                    int(hashlib.sha256(f.get("url", f.get("title", "")).encode()).hexdigest()[:16], 16)
                    % (2**63)
                )
                points.append(
                    qm.PointStruct(
                        id=point_id,
                        vector=vec,
                        payload={
                            "matter_id": matter_id,
                            "firm_id": firm_id,
                            "title": f.get("title", ""),
                            "citation": f.get("citation", ""),
                            "url": f.get("url", ""),
                            "doc_excerpt": (f.get("doc_excerpt") or "")[:500],
                            "corpus_namespace": namespace,
                            # WHY False: VerificationAgent sets verified=True after
                            # browser confirmation. DrafterAgent sees this flag and
                            # marks partial/unverified citations explicitly in draft.
                            "verified": False,
                        },
                    )
                )

            await client.upsert(collection_name=namespace, points=points)
            total += len(points)
            console.print(f"[dim]  ↑ Qdrant [{namespace}]: {len(points)} point(s)[/dim]")

        await client.close()
        return total

    except Exception as exc:
        logger.warning("Qdrant sync indexing failed: %s", exc)
        return 0


# ---------------------------------------------------------------------------
# ReAct Loop — Plan
# ---------------------------------------------------------------------------

async def _plan_queries(state: SeniorCounselState, cfg: LexConfig) -> list[dict]:
    """
    LLM generates targeted search queries with per-query tool routing.

    WHY LLM-routed (Locked Decision 12): the ResearcherAgent decides at
    runtime which tool covers the query better. Kanoon for binding case law;
    Tavily for statutory texts, gazette notifications, and circulars that
    Kanoon does not index.
    """
    from themis.agents.prompts.researcher import QUERY_PLANNER_SYSTEM

    matter_context = json.dumps(
        {
            "matter_type": state.get("matter_type", ""),
            "jurisdiction": state.get("jurisdiction", ""),
            "purpose": (state.get("purpose") or "")[:200],
            "parties": state.get("parties") or [],
        },
        indent=2,
    )

    try:
        response = await call_llm(
            messages=[{"role": "user", "content": f"Matter:\n{matter_context}\n\nPlan research queries."}],
            cfg=cfg,
            system=QUERY_PLANNER_SYSTEM,
            model_override=cfg.researcher_model,
        )
        raw = response["content"].strip()
        # Strip markdown fences if LLM added them despite the prompt asking not to
        if raw.startswith("```"):
            raw = re.sub(r"^```[a-z]*\n?", "", raw).rstrip("`").strip()
        queries = json.loads(raw)
        if isinstance(queries, list) and queries:
            return queries[:5]
    except Exception as exc:
        logger.warning("Query planner LLM call failed: %s — using fallback query", exc)

    # Fallback: single deterministic query from state fields
    fallback = " ".join(
        filter(None, [state.get("matter_type"), (state.get("purpose") or "")[:100], state.get("jurisdiction")])
    ) or (state.get("user_input") or "Indian legal matter")[:200]
    return [{"query": fallback, "tool": "kanoon", "angle": "general"}]


# ---------------------------------------------------------------------------
# ReAct Loop — Search (LLM-routed dispatch)
# ---------------------------------------------------------------------------

async def _execute_queries(queries: list[dict], cfg: LexConfig) -> list[dict]:
    """
    Dispatch each query to the tool the LLM specified.
    All queries in a batch run concurrently.
    """
    tasks = []
    for q in queries:
        query_str = q.get("query", "")
        if not query_str:
            continue
        if q.get("tool") == "tavily":
            tasks.append(_run_tavily_search(query_str, cfg))
        else:
            tasks.append(_run_kanoon_search(query_str, cfg))

    if not tasks:
        return []

    results = await asyncio.gather(*tasks, return_exceptions=True)
    combined: list[dict] = []
    for r in results:
        if isinstance(r, list):
            combined.extend(r)
    return combined


# ---------------------------------------------------------------------------
# ReAct Loop — Evaluate
# ---------------------------------------------------------------------------

async def _evaluate_sufficiency(
    state: SeniorCounselState,
    findings: list[dict],
    cfg: LexConfig,
) -> dict:
    """
    LLM assesses whether current findings are sufficient to draft a court document.

    Returns {"sufficient": bool, "confidence": float,
             "missing_areas": [...], "gap_queries": [...]}

    WHY: Without this gate, the loop would always stop after one iteration.
    The evaluator closes the ReAct cycle — it generates the gap_queries that
    feed directly into the next iteration's search batch.
    """
    from themis.agents.prompts.researcher import SUFFICIENCY_EVALUATOR_SYSTEM

    findings_summary = json.dumps(
        [
            {
                "title": f.get("title"),
                "citation": f.get("citation"),
                "snippet": (f.get("doc_excerpt") or "")[:150],
            }
            for f in findings[:10]
        ],
        indent=2,
    )
    matter_context = json.dumps(
        {
            "matter_type": state.get("matter_type", ""),
            "jurisdiction": state.get("jurisdiction", ""),
            "purpose": (state.get("purpose") or "")[:200],
        },
        indent=2,
    )

    try:
        response = await call_llm(
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Matter:\n{matter_context}\n\n"
                        f"Findings gathered ({len(findings)}):\n{findings_summary}\n\n"
                        "Is the research sufficient?"
                    ),
                }
            ],
            cfg=cfg,
            system=SUFFICIENCY_EVALUATOR_SYSTEM,
            model_override=cfg.researcher_model,
        )
        raw = response["content"].strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```[a-z]*\n?", "", raw).rstrip("`").strip()
        return json.loads(raw)
    except Exception as exc:
        logger.warning("Sufficiency evaluator failed: %s — assuming sufficient", exc)
        # WHY assume sufficient on failure: better to draft with what we have
        # than to loop indefinitely burning API quota.
        return {"sufficient": True, "confidence": 0.5, "missing_areas": [], "gap_queries": []}


# ---------------------------------------------------------------------------
# Statute extraction + limitation check
# ---------------------------------------------------------------------------

def _extract_statutes(findings: list[dict]) -> list[str]:
    statutes: set[str] = set()
    for f in findings:
        text = f.get("full_text", "") + " " + f.get("snippet", "")
        for m in _STATUTE_RE.finditer(text):
            statutes.add(m.group(0).strip()[:80])
    return list(statutes)[:15]


def _run_limitation_check(state: SeniorCounselState) -> str:
    try:
        from themis.tools.registry import ToolRegistry
        import themis.tools.limitation  # noqa: F401 — triggers self-registration
        check_lim = ToolRegistry.get("check_limitation")
        coa_date = state.get("cause_of_action_date") or ""
        result = check_lim(
            matter_type=state.get("matter_type") or "",
            cause_of_action_date=coa_date if isinstance(coa_date, str) else "",
        )
        return json.dumps(result)
    except Exception:
        return json.dumps({"risk": "unknown", "error": "limitation tool unavailable"})


# ---------------------------------------------------------------------------
# Main node — ReAct investigation loop
# ---------------------------------------------------------------------------

async def run(state: SeniorCounselState) -> dict:
    """
    ResearcherAgent node — dispatched by Senior Counsel via send().

    Runs a full plan → search → evaluate → loop investigation cycle,
    then applies the citation gate and syncs passed judgments to Qdrant.

    # LANGGRAPH: returns only changed keys; never raises.
    """
    cfg = LexConfig()
    matter_id: str = state.get("matter_id") or "unknown"
    firm_id: str = state.get("firm_id") or "default"

    try:
        console.print(
            f"[bold blue]→ ResearcherAgent:[/bold blue] "
            f"{state.get('matter_type', 'matter')} "
            f"[dim]({state.get('jurisdiction', '')})[/dim]"
        )

        thread_messages: list[dict] = []
        all_findings: list[dict] = []

        # --- PLAN ---
        queries = await _plan_queries(state, cfg)
        console.print(
            f"[blue]  → Planned {len(queries)} queries "
            f"(LLM-routed: {sum(1 for q in queries if q.get('tool') == 'tavily')} tavily, "
            f"{sum(1 for q in queries if q.get('tool') != 'tavily')} kanoon)[/blue]"
        )
        thread_messages.append({"step": "plan", "queries": queries})

        max_iter: int = cfg.react_research_max_iter

        for iteration in range(max_iter):
            console.print(f"[dim]  Iteration {iteration + 1}/{max_iter}[/dim]")

            # --- SEARCH ---
            batch = await _execute_queries(queries, cfg)
            all_findings.extend(batch)
            thread_messages.append(
                {
                    "step": "search",
                    "iteration": iteration,
                    "queries": [q.get("query") for q in queries],
                    "hits": len(batch),
                }
            )
            console.print(f"[dim]    {len(batch)} hits (running total: {len(all_findings)})[/dim]")

            # --- EVALUATE ---
            eval_result = await _evaluate_sufficiency(state, all_findings, cfg)
            thread_messages.append({"step": "evaluate", "iteration": iteration, **eval_result})
            console.print(
                f"[dim]    Sufficient: {eval_result.get('sufficient')} "
                f"(confidence {eval_result.get('confidence', 0):.2f})[/dim]"
            )

            if eval_result.get("sufficient") or iteration == max_iter - 1:
                break

            # --- LOOP ---
            gap_queries = eval_result.get("gap_queries") or []
            if not gap_queries:
                break
            queries = gap_queries[:3]  # cap gap queries per iteration
            console.print(f"[dim]    → {len(queries)} gap quer(ies) for next iteration[/dim]")

        # --- CITATION GATE ---
        passed, dropped = _enforce_citation_gate(all_findings)
        if dropped:
            console.print(f"[yellow]  ⚠ Citation gate dropped {len(dropped)} finding(s)[/yellow]")
        console.print(
            f"[green]✓ ResearcherAgent:[/green] {len(passed)} finding(s) passed gate "
            f"({len(all_findings)} raw, {len(dropped)} dropped)"
        )

        # --- QDRANT SYNC INDEX ---
        # WHY sync: DrafterAgent reads from Qdrant in this same run (Decision 17).
        upserted = await _sync_judgments_to_qdrant(passed, matter_id, firm_id, cfg)
        if upserted:
            console.print(f"[dim]  ↑ Qdrant: {upserted} judgment(s) indexed synchronously[/dim]")

        # --- STATUTES + LIMITATION ---
        statutes = _extract_statutes(passed)
        limitation = _run_limitation_check(state)

        # Pop researcher from execution_plan so Senior Counsel advances to next specialist
        new_plan = (state.get("execution_plan") or [])[1:]

        return {
            "research_findings": passed,
            "statutes_cited": statutes,
            "limitation_analysis": limitation,
            "execution_plan": new_plan,
            "active_specialist": None,
            "status": "researching",
            # WHY citation_gate_dropped in return: ReviewerAgent uses this list to
            # surface unverifiable findings to the lawyer without silently discarding them.
            "citation_gate_dropped": dropped if dropped else [],
        }

    except Exception as exc:
        logger.exception("ResearcherAgent failed")
        return {
            "error": f"ResearcherAgent: {exc}",
            "execution_plan": [],
            "active_specialist": None,
        }
