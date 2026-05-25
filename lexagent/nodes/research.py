# Research node: queries Indian Kanoon for relevant case law and runs a
# limitation check. Runs after intake completes; feeds research_findings
# and limitation_analysis into the draft node.

import asyncio
import re

from rich.console import Console

from lexagent.config import LexConfig
from lexagent.state import LexState

# WHY: Importing limitation here ensures @ToolRegistry.register fires at startup.
# Tools self-register on first import — no explicit registration call needed.
import lexagent.tools.limitation  # noqa: F401
from lexagent.tools.kanoon import search_and_fetch
from lexagent.tools.kanoon_api import search_and_fetch_api
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


def _build_parallel_queries(state: LexState) -> list[str]:
    """
    Build 2-3 complementary search queries for parallel execution.
    Each angle targets a different retrieval dimension so the combined
    result set is richer than a single broad query.
    WHY: Indian Kanoon's BM25 engine is sensitive to query phrasing —
    splitting matter type + purpose + court into separate queries avoids
    over-stuffing a single query that dilutes all three signals.
    """
    matter_type = state.get("matter_type") or ""
    purpose = (state.get("purpose") or "")[:120]
    jurisdiction = state.get("jurisdiction") or ""
    statutes = state.get("statutes_cited") or []
    user_input = (state.get("user_input") or "")[:150]

    queries: list[str] = []

    # Primary: matter type + purpose
    primary = " ".join(p for p in [matter_type, purpose] if p)
    if primary:
        queries.append(primary)

    # Secondary: jurisdiction + matter type
    secondary = " ".join(p for p in [jurisdiction, matter_type] if p)
    if secondary and secondary != primary:
        queries.append(secondary)

    # Tertiary: statute-focused (if any statutes already identified)
    statute_query = " ".join(statutes[:2]) if statutes else ""
    if statute_query:
        queries.append(statute_query)
    elif purpose and jurisdiction:
        # No statutes yet — use purpose + jurisdiction as third angle
        third = f"{purpose[:80]} {jurisdiction}"
        if third not in queries:
            queries.append(third)

    # Fallback to single query if nothing else built
    if not queries:
        queries.append(user_input or "legal matter India")

    return queries[:3]  # cap at 3 to keep latency reasonable


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

    # WHY: when kanoon_backend=api, delegate to the ReAct research node which
    # applies the citation enforcement gate and playwright fallback per-doc.
    # The gate guarantees every finding has title/url/doc_excerpt/citation before
    # reaching the draft node — impossible to guarantee in the legacy path below.
    if config.kanoon_backend == "api":
        from lexagent.nodes.react_research import run as react_run
        return await react_run(state)

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
        elif config.kanoon_backend == "api":
            # WHY: REST API is stable and fast; Playwright breaks on page-structure changes.
            # Requires KANOON_API_KEY in .env. Falls back gracefully if key is absent.
            if not config.kanoon_api_key:
                console.print("[yellow]→ Kanoon API:[/yellow] KANOON_API_KEY not set — skipping.")
                kanoon_result = {"results": []}
            else:
                kanoon_result = await search_and_fetch_api(
                    query=query,
                    api_key=config.kanoon_api_key,
                    max_results=config.kanoon_max_results,
                    base_url=config.kanoon_api_base_url,
                )
        else:
            # T2-A: run 2-3 parallel queries instead of one broad query.
            # WHY: Kanoon BM25 is phrasing-sensitive. Multi-angle search covers
            # matter-type, jurisdiction, and statute dimensions simultaneously,
            # returning a richer result set in the same wall-clock time.
            parallel_queries = _build_parallel_queries(state)
            console.print(
                f"[bold blue]→ Research:[/bold blue] "
                f"[{len(parallel_queries)} queries firing in parallel]"
            )
            for i, q in enumerate(parallel_queries, 1):
                console.print(f"  [{i}/{len(parallel_queries)}] [dim]{q[:70]}...[/dim]")

            import time as _time

            async def _fetch_one(q: str, idx: int) -> list[dict]:
                t0 = _time.monotonic()
                try:
                    r = await search_and_fetch(
                        query=q,
                        max_results=config.kanoon_max_results,
                        headless=config.kanoon_headless,
                    )
                    hits = r.get("results", []) if isinstance(r, dict) else []
                    elapsed = _time.monotonic() - t0
                    console.print(
                        f"  [{idx}/{len(parallel_queries)}] "
                        f"[green]✓[/green] {len(hits)} case(s) ({elapsed:.1f}s)"
                    )
                    return hits
                except Exception as exc:
                    console.print(f"  [{idx}/{len(parallel_queries)}] [yellow]✗ {exc}[/yellow]")
                    return []

            all_batches = await asyncio.gather(
                *[_fetch_one(q, i) for i, q in enumerate(parallel_queries, 1)]
            )

            # Deduplicate by URL — preserve order, first occurrence wins.
            seen_urls: set[str] = set()
            results = []
            for batch in all_batches:
                for r in batch:
                    url = r.get("url", "")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        results.append(r)
                    elif not url:
                        results.append(r)

        # Phase 8: if Kanoon returned nothing and eCourts is not configured, surface nudge
        # via a special state key — telegram.py reads this and shows the configure button.
        kanoon_empty_nudge = (
            kanoon_approved
            and config.kanoon_backend != "stub"
            and len(results) == 0
            and config.ecourts_backend == "stub"
        )

        # Limitation check — run concurrently with any remaining work
        # WHY asyncio.to_thread: check_limitation is CPU-bound/sync; wrapping it lets
        # the event loop remain unblocked so other coroutines can run in parallel.
        check_lim = ToolRegistry.get("check_limitation")
        coa_date = state.get("cause_of_action_date") or ""

        console.print("[dim]  ↳ Limitation analysis...[/dim]")
        limitation_result = await asyncio.to_thread(
            check_lim,
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
            from lexagent.tools.raptor_summarizer import RaptorSummarizer, raptor_tree_to_findings

            summarizer = RaptorSummarizer(
                cfg=config,
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
