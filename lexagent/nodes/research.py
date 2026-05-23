# Research node: queries Indian Kanoon for relevant case law and runs a
# limitation check. Runs after intake completes; feeds research_findings
# and limitation_analysis into the draft node.

import re

from rich.console import Console

from lexagent.config import LexConfig
from lexagent.state import LexState

# WHY: Importing limitation here ensures @ToolRegistry.register fires at startup.
# Tools self-register on first import — no explicit registration call needed.
import lexagent.tools.limitation  # noqa: F401
from lexagent.tools.kanoon import search_and_fetch
from lexagent.tools.registry import ToolRegistry

console = Console()

# Matches common Indian statutory references found in judgment text
_STATUTE_RE = re.compile(
    r"\b("
    r"CPC(?:\s+O(?:rder)?\.?\s*[IVXLCDM]+\s+R(?:ule)?\.?\s*[\d&,\s]*)?"
    r"|IPC\s+[Ss](?:ection)?\.?\s*\d+"
    r"|CrPC\s+[Ss](?:ection)?\.?\s*\d+"
    r"|NI\s+Act\s+[Ss](?:ection)?\.?\s*\d+"
    r"|Specific\s+Relief\s+Act\s+[Ss](?:ection)?\.?\s*\d+"
    r"|Transfer\s+of\s+Property\s+Act\s+[Ss](?:ection)?\.?\s*\d+"
    r"|Indian\s+Evidence\s+Act\s+[Ss](?:ection)?\.?\s*\d+"
    r"|Indian\s+Contract\s+Act\s+[Ss](?:ection)?\.?\s*\d+"
    r"|Constitution\s+of\s+India\s+(?:Article|Art\.?)\s*\d+"
    r")"
)


def _build_search_query(state: LexState) -> str:
    """Build an Indian Kanoon query from the intake fields collected so far."""
    parts: list[str] = []
    if matter_type := state.get("matter_type"):
        parts.append(matter_type)
    if purpose := state.get("purpose"):
        parts.append(purpose[:150])
    if jurisdiction := state.get("jurisdiction"):
        parts.append(jurisdiction)
    if not parts:
        # Fallback: use raw brief — better than an empty query
        parts.append(state.get("user_input", "legal matter India")[:200])
    return " ".join(parts)


def _extract_statutes(results: list[dict]) -> list[str]:
    """Pull statute references from fetched judgment texts."""
    statutes: set[str] = set()
    for r in results:
        text = r.get("full_text", "") + " " + r.get("snippet", "")
        for m in _STATUTE_RE.finditer(text):
            statutes.add(m.group(0).strip()[:80])
    return list(statutes)[:15]  # cap to avoid bloating state


async def run(state: LexState) -> dict:
    config = LexConfig()
    try:
        query = _build_search_query(state)
        console.print(f"[bold blue]→ Research:[/bold blue] {query[:80]}")

        # Phase 8: respect approved_tools from Telegram tool routing.
        # None = not yet decided (Telegram hasn't asked yet); [] = user chose skip.
        # When running from CLI, approved_tools is None and we run all tools as before.
        approved_tools = state.get("approved_tools")
        kanoon_approved = (
            approved_tools is None                        # CLI mode: always run
            or "kanoon" in (approved_tools or [])        # Telegram: user selected Kanoon
        )

        results: list[dict] = []

        if not kanoon_approved or (approved_tools is not None and len(approved_tools) == 0):
            # User skipped research entirely
            console.print("[yellow]→ Research:[/yellow] Skipped by user.")
            results = []
        elif config.kanoon_backend == "stub":
            # WHY: stub avoids real Playwright browser in tests and offline dev.
            # The stub still exercises the full node code path — only the HTTP call is mocked.
            results = [
                {
                    "title": f"[Stub] Result for: {query[:50]}",
                    "url": "https://indiankanoon.org/doc/stub",
                    "snippet": "Stub — set LEX_KANOON_BACKEND=playwright for live data.",
                    "full_text": "",
                    "citations_found": [],
                    "status": "stub",
                }
            ]
        else:
            kanoon_result = await search_and_fetch(
                query=query,
                max_results=config.kanoon_max_results,
                headless=config.kanoon_headless,
            )
            # WHY: guard against search_and_fetch returning a string error message
            # instead of a dict — calling .get() on a string raises AttributeError.
            results = kanoon_result.get("results", []) if isinstance(kanoon_result, dict) else []

        # Phase 8: if Kanoon returned nothing and eCourts is not configured, surface nudge
        # via a special state key — telegram.py reads this and shows the configure button.
        kanoon_empty_nudge = (
            kanoon_approved
            and config.kanoon_backend != "stub"
            and len(results) == 0
            and config.ecourts_backend == "stub"
        )

        # Limitation check — uses the registered tool so it's discoverable by the LLM too
        check_lim = ToolRegistry.get("check_limitation")
        coa_date = state.get("cause_of_action_date") or ""
        limitation_result = check_lim(
            matter_type=state.get("matter_type") or "",
            cause_of_action_date=coa_date if isinstance(coa_date, str) else "",
        )

        statutes = _extract_statutes(results)
        console.print(
            f"[green]✓ Research:[/green] {len(results)} result(s), "
            f"{len(statutes)} statute(s), limitation: {limitation_result['risk']}"
        )

        # ----------------------------------------------------------------
        # Phase 6c: RAPTOR hierarchical summaries (optional, config-gated)
        # WHY: RAPTOR adds one LLM call per cluster — off by default so it
        # doesn't slow down every run. Enable with LEX_RAPTOR_ENABLED=true.
        # ----------------------------------------------------------------
        raptor_tree_dicts: list[dict] | None = None
        extra_findings: list[dict] = []

        if config.raptor_enabled and results:
            from lexagent.nodes._llm import get_llm
            from lexagent.tools.raptor_summarizer import RaptorSummarizer, raptor_tree_to_findings

            summarizer = RaptorSummarizer(
                llm=get_llm(config),
                max_layers=config.raptor_max_layers,
                max_cluster_size=config.raptor_max_cluster_size,
            )
            tree = await summarizer.build_tree_from_findings(results)
            raptor_tree_dicts = [
                {
                    "layer": n.layer,
                    "text": n.text,
                    "source_chunks": n.source_chunks,
                }
                for n in tree
            ]
            extra_findings = raptor_tree_to_findings(tree)
            console.print(
                f"[cyan]✓ RAPTOR:[/cyan] {len([n for n in tree if n.layer >= 1])} summary node(s)"
            )

        # ----------------------------------------------------------------
        # Phase 6d: GraphRAG entity extraction (optional, config-gated)
        # ----------------------------------------------------------------
        entity_graph_dict: dict | None = None
        if config.graphrag_enabled and results:
            from lexagent.tools.legal_kg import LegalKnowledgeGraph

            kg = LegalKnowledgeGraph()
            for finding in results:
                text = finding.get("full_text", "") + " " + finding.get("snippet", "")
                kg.add_text(text, source=finding.get("citation") or finding.get("case_name") or "")
            entity_graph_dict = kg.to_dict()
            console.print(
                f"[cyan]✓ GraphRAG:[/cyan] {len(entity_graph_dict.get('entities', []))} entities"
            )

        all_findings = results + extra_findings

        # Phase 9: index findings into Qdrant for persistent cross-session retrieval.
        # WHY: HybridRetriever is rebuilt from scratch each session; Qdrant survives restarts.
        if config.qdrant_enabled and state.get("matter_id"):
            try:
                from lexagent.tools.retriever import PersistentQdrantRetriever
                firm_id = state.get("firm_id") or config.default_firm_id
                qr = PersistentQdrantRetriever(state["matter_id"], firm_id=firm_id, cfg=config)
                n_indexed = qr.index_findings(all_findings)
                if n_indexed:
                    console.print(f"[cyan]✓ Qdrant:[/cyan] indexed {n_indexed} findings")
            except Exception as e:
                console.print(f"[yellow]Qdrant indexing skipped: {e}[/yellow]")

        return {
            "research_findings": all_findings,
            "statutes_cited": statutes,
            "limitation_analysis": limitation_result["analysis"],
            **({"raptor_tree": raptor_tree_dicts} if raptor_tree_dicts is not None else {}),
            **({"entity_graph": entity_graph_dict} if entity_graph_dict is not None else {}),
            # Phase 8: surface nudge flag so Telegram can show the eCourts configure button
            **({"ecourts_nudge": True} if kanoon_empty_nudge else {}),
        }

    except Exception as e:
        return {"error": str(e)}
