"""
ReAct research node with citation enforcement gate.

WHY: The original research.py runs a single search-and-fetch pass. This node
adds:
1. API-first strategy: kanoon_api → playwright fallback for empty docs only.
2. Tavily web search for statutes / gazette notifications (opt-in).
3. Citation enforcement gate: every finding returned to the graph MUST have
   title, citation (or docsource), doc_excerpt, and url. Findings without
   these fields are logged and dropped before writing to state — "if it can't
   be cited, it can't be used." This prevents hallucinated citations from
   reaching the draft node.
4. Judgment auto-cache: verified findings written to
   ~/.lexagent/judgments/{docid}.txt so the precedent board (Phase R9) can
   serve repeat queries instantly without hitting the API again.

# LANGGRAPH: node contract — async def run(state) -> dict returning only
# changed keys. Never raises; all exceptions go to state["error"].
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from rich.console import Console

from lexagent.config import LexConfig
from lexagent.state import LexState

console = Console()


# ---------------------------------------------------------------------------
# Citation enforcement gate
# ---------------------------------------------------------------------------

def _enforce_citation_gate(findings: list[dict]) -> tuple[list[dict], list[dict]]:
    """
    Split findings into (passed, dropped) based on the citation gate.

    A finding passes if it has ALL of:
    - title (non-empty string)
    - url   (non-empty string)
    - doc_excerpt OR full_text (at least one must be non-empty)
    - citation OR docsource (at least one present — normalised to 'citation')

    WHY: The gate runs before research_findings is written to state.
    Dropping here guarantees the draft node never sees an uncitable finding
    rather than silently producing a hallucinated citation.
    """
    passed: list[dict] = []
    dropped: list[dict] = []

    for f in findings:
        has_title = bool(f.get("title", "").strip())
        has_url = bool(f.get("url", "").strip())
        has_text = bool(f.get("doc_excerpt", "").strip() or f.get("full_text", "").strip())
        has_cite = bool(f.get("citation", "").strip() or f.get("docsource", "").strip())

        if has_title and has_url and has_text and has_cite:
            # Normalise: promote docsource → citation when citation is absent
            if not f.get("citation") and f.get("docsource"):
                f = {**f, "citation": f["docsource"]}
            # Normalise: ensure doc_excerpt exists (truncate full_text if needed)
            if not f.get("doc_excerpt") and f.get("full_text"):
                f = {**f, "doc_excerpt": f["full_text"][:500]}
            passed.append(f)
        else:
            dropped.append(f)

    return passed, dropped


# ---------------------------------------------------------------------------
# Judgment cache helpers
# ---------------------------------------------------------------------------

def _cache_path(docid: int | str, judgments_dir: str) -> Path:
    return Path(judgments_dir).expanduser() / f"{docid}.txt"


def _load_cached(docid: int | str, judgments_dir: str) -> str | None:
    p = _cache_path(docid, judgments_dir)
    return p.read_text(encoding="utf-8") if p.exists() else None


def _save_cached(docid: int | str, text: str, judgments_dir: str) -> None:
    p = _cache_path(docid, judgments_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


# ---------------------------------------------------------------------------
# Core research helpers
# ---------------------------------------------------------------------------

async def _fetch_with_fallback(
    hit: dict,
    cfg: LexConfig,
) -> dict:
    """
    Enrich a search hit with full judgment text.

    Strategy:
    1. Check local judgment cache (~/.lexagent/judgments/{tid}.txt).
    2. Try the REST API's fetch_doc().
    3. If API returns empty/error, fall back to Playwright scraper.
    4. Attach doc_excerpt (first 500 chars of full_text) to the result.
    """
    docid = hit.get("tid")
    url = hit.get("url", "")
    judgments_dir = cfg.judgments_cache_dir

    # Cache hit: skip API entirely
    if docid:
        cached = _load_cached(docid, judgments_dir)
        if cached:
            console.print(f"[dim]  ↩ Cache hit: {hit.get('title', '')[:50]}[/dim]")
            return {**hit, "full_text": cached, "doc_excerpt": cached[:500], "status": "cached"}

    full_text = ""

    # Try REST API first
    if docid and cfg.kanoon_api_key:
        try:
            from lexagent.tools.kanoon_api import KanoonAPIClient
            async with KanoonAPIClient(cfg.kanoon_api_key, base_url=cfg.kanoon_api_base_url) as client:
                doc = await client.fetch_doc(docid)
                if doc.get("status") == "success":
                    full_text = doc.get("full_text", "")
                    # Merge citation info from the doc response
                    hit = {**hit, **doc}
        except Exception as e:
            console.print(f"[yellow]  ⚠ API fetch failed for {docid}: {e}[/yellow]")

    # Playwright fallback when API returned empty
    if not full_text and url and cfg.kanoon_fallback_playwright:
        console.print(f"[dim]  → Playwright fallback: {url[:60]}[/dim]")
        try:
            from lexagent.tools.kanoon_fallback import fetch_doc_playwright
            full_text = await fetch_doc_playwright(url, headless=cfg.kanoon_headless) or ""
        except Exception as e:
            console.print(f"[yellow]  ⚠ Playwright fallback failed: {e}[/yellow]")

    # Cache the result if we got text
    if full_text and docid:
        _save_cached(docid, full_text, judgments_dir)

    return {
        **hit,
        "full_text": full_text,
        "doc_excerpt": full_text[:500],
        "status": "success" if full_text else "empty",
    }


async def _run_kanoon_search(query: str, cfg: LexConfig) -> list[dict]:
    """Search Indian Kanoon via REST API and enrich each hit with full text."""
    if not cfg.kanoon_api_key:
        console.print("[yellow]  ⚠ KANOON_API_KEY not set — skipping API search[/yellow]")
        return []

    try:
        from lexagent.tools.kanoon_api import KanoonAPIClient
        async with KanoonAPIClient(cfg.kanoon_api_key, base_url=cfg.kanoon_api_base_url) as client:
            hits = await client.search(query, max_results=cfg.kanoon_max_results)

        console.print(f"[green]  ✓ Kanoon API:[/green] {len(hits)} hits for '{query[:60]}'")

        # Fetch full text for each hit concurrently
        enriched = await asyncio.gather(
            *[_fetch_with_fallback(hit, cfg) for hit in hits],
            return_exceptions=True,
        )
        # Filter out exceptions
        return [r for r in enriched if isinstance(r, dict)]

    except Exception as e:
        console.print(f"[red]  ✗ Kanoon search error: {e}[/red]")
        return []


async def _run_tavily_search(query: str, cfg: LexConfig) -> list[dict]:
    """Web search for statutory texts and gazette notifications (opt-in)."""
    if not (cfg.tavily_enabled and cfg.tavily_api_key):
        return []

    try:
        from lexagent.tools.tavily_search import web_search_async
        results = await web_search_async(query, max_results=5)
        # Shape Tavily results to match the research_findings format
        shaped = []
        for r in results:
            if r.get("error"):
                continue
            shaped.append({
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "snippet": r.get("content", "")[:300],
                "full_text": r.get("content", ""),
                "doc_excerpt": r.get("content", "")[:500],
                "citation": r.get("url", ""),  # URL as citation for web sources
                "docsource": "Tavily Web Search",
                "status": "success",
            })
        console.print(f"[cyan]  ✓ Tavily:[/cyan] {len(shaped)} web results")
        return shaped
    except Exception as e:
        console.print(f"[yellow]  ⚠ Tavily search error: {e}[/yellow]")
        return []


# ---------------------------------------------------------------------------
# Main node
# ---------------------------------------------------------------------------

async def run(state: LexState) -> dict:
    """
    API-first research node with citation enforcement gate.

    Uses kanoon_api → playwright fallback for each hit, then optionally
    augments with Tavily web search. All findings pass through the citation
    gate before being written to state — any finding without title, url,
    doc_excerpt, and citation/docsource is dropped and logged.

    # LANGGRAPH: returns only changed keys; never raises.
    """
    cfg = LexConfig()
    try:
        # Build search query from intake fields
        parts = [
            state.get("matter_type", ""),
            state.get("purpose", "")[:150],
            state.get("jurisdiction", ""),
        ]
        query = " ".join(p for p in parts if p).strip() or state.get("user_input", "legal matter India")[:200]

        console.print(f"[bold blue]→ ReAct Research:[/bold blue] {query[:80]}")

        # Collect findings from all sources concurrently
        kanoon_task = asyncio.create_task(_run_kanoon_search(query, cfg))
        tavily_task = asyncio.create_task(_run_tavily_search(query, cfg))

        kanoon_results, tavily_results = await asyncio.gather(kanoon_task, tavily_task)

        raw_findings: list[dict] = kanoon_results + tavily_results

        # Citation enforcement gate
        passed, dropped = _enforce_citation_gate(raw_findings)

        if dropped:
            console.print(
                f"[yellow]  ⚠ Citation gate dropped {len(dropped)} finding(s) "
                f"(missing title/url/excerpt/citation)[/yellow]"
            )

        console.print(
            f"[green]✓ ReAct Research:[/green] {len(passed)} finding(s) passed gate "
            f"({len(kanoon_results)} kanoon, {len(tavily_results)} web)"
        )

        # Extract statute references from passed findings
        import re
        _STATUTE_RE = re.compile(
            r"\b(CPC|IPC\s+[Ss](?:ection)?\.?\s*\d+|CrPC\s+[Ss](?:ection)?\.?\s*\d+"
            r"|NI\s+Act\s+[Ss](?:ection)?\.?\s*\d+|Specific\s+Relief\s+Act\s+[Ss](?:ection)?\.?\s*\d+"
            r"|Indian\s+Contract\s+Act\s+[Ss](?:ection)?\.?\s*\d+"
            r"|Constitution\s+of\s+India\s+(?:Article|Art\.?)\s*\d+)\b"
        )
        statutes: set[str] = set()
        for f in passed:
            text = f.get("full_text", "") + " " + f.get("snippet", "")
            for m in _STATUTE_RE.finditer(text):
                statutes.add(m.group(0).strip()[:80])

        # Limitation check
        try:
            from lexagent.tools.registry import ToolRegistry
            import lexagent.tools.limitation  # noqa: F401 — triggers self-registration
            check_lim = ToolRegistry.get("check_limitation")
            coa_date = state.get("cause_of_action_date") or ""
            limitation_result = check_lim(
                matter_type=state.get("matter_type") or "",
                cause_of_action_date=coa_date if isinstance(coa_date, str) else "",
            )
        except Exception:
            limitation_result = {"risk": "unknown", "error": "limitation tool unavailable"}

        return {
            "research_findings": passed,
            "statutes_cited": list(statutes)[:15],
            "limitation_analysis": json.dumps(limitation_result),
            "citation_gate_dropped": dropped if dropped else None,
            "research_agent_trace": [
                {
                    "step": "kanoon_api_search",
                    "query": query,
                    "hits": len(kanoon_results),
                    "passed_gate": len([f for f in kanoon_results if f in passed]),
                },
                {
                    "step": "tavily_search",
                    "query": query,
                    "hits": len(tavily_results),
                    "passed_gate": len([f for f in tavily_results if f in passed]),
                },
            ],
        }

    except Exception as e:
        return {"error": str(e)}
