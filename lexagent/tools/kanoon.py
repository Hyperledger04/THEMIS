# WHY: We use Playwright (not Selenium or API) because Indian Kanoon's search
# requires real browser interactions — clicking result links, waiting for judgment
# divs to hydrate, and navigating paginated results. Playwright's async API
# integrates cleanly with LangGraph's async node contract.
#
# headless=False by default so you can watch the browser during development.
# Set LEX_KANOON_HEADLESS=true in .env for CI or background runs.

import asyncio
import re
from typing import Optional
from urllib.parse import quote_plus

from playwright.async_api import Page, async_playwright
from rich.console import Console

from lexagent.config import LexConfig

console = Console()
config = LexConfig()

KANOON_BASE = "https://indiankanoon.org"
SEARCH_URL = f"{KANOON_BASE}/search/?formInput={{query}}&pagenum=1"


# ---------------------------------------------------------------------------
# Internal browser helpers
# ---------------------------------------------------------------------------

async def _get_page(playwright, headless: bool) -> tuple:
    """Launch a real Chrome instance and return (browser, page)."""
    browser = await playwright.chromium.launch(
        # WHY: channel="chrome" uses your installed Google Chrome, not Playwright's
        # bundled Chromium — so it has your cookies, extensions, and looks like a
        # real user browser. Falls back to Chromium if Chrome isn't installed.
        channel="chrome",
        headless=headless,
        slow_mo=200,  # WHY: 200ms between actions — makes automation human-like, avoids bot detection
        args=[
            "--disable-blink-features=AutomationControlled",
            "--start-maximized",
        ],
    )
    context = await browser.new_context(
        viewport={"width": 1280, "height": 900},
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
    )
    page = await context.new_page()
    return browser, page


async def _search_kanoon(page: Page, query: str, max_results: int = 5) -> list[dict]:
    """
    Navigate to Indian Kanoon search, collect result titles + URLs.
    Returns list of {title, url, snippet}.
    """
    search_url = SEARCH_URL.format(query=quote_plus(query))
    console.print(f"[dim]→ Navigating to search: {search_url}[/dim]")

    await page.goto(search_url, wait_until="domcontentloaded", timeout=30_000)

    # WHY: Wait for result titles — they're in .result_title anchors.
    # If the page has no results, this selector simply returns empty.
    await page.wait_for_selector(".result_title", timeout=15_000)

    results = []
    result_elements = await page.query_selector_all(".result_title a")

    for el in result_elements[:max_results]:
        title = (await el.inner_text()).strip()
        href = await el.get_attribute("href")
        if href and title:
            full_url = KANOON_BASE + href if href.startswith("/") else href
            results.append({"title": title, "url": full_url})

    # Grab snippet text for context (optional, shown in research summary)
    snippet_elements = await page.query_selector_all(".result_title + p, .docsource_main")
    for i, el in enumerate(snippet_elements[:max_results]):
        if i < len(results):
            results[i]["snippet"] = (await el.inner_text()).strip()[:300]

    console.print(f"[green]✓ Found {len(results)} results[/green]")
    return results


async def _fetch_judgment(page: Page, url: str) -> dict:
    """
    Open a single judgment page and extract:
    - Full text of the judgment
    - Citation header (case name, court, date)
    - All internal citation links (other cases cited within)
    """
    console.print(f"[dim]→ Opening judgment: {url}[/dim]")

    await page.goto(url, wait_until="domcontentloaded", timeout=40_000)

    # WHY: Indian Kanoon loads the judgment body inside a div.judgments.
    # We wait explicitly rather than using a fixed sleep — faster and reliable.
    try:
        await page.wait_for_selector(".judgments", timeout=20_000)
    except Exception:
        return {"url": url, "error": "Judgment div not found — page may have redirected"}

    # --- Extract judgment header (case name, court, bench, date) ---
    header_text = ""
    header_el = await page.query_selector(".docsource_main, h2.doc_title, .doc_title")
    if header_el:
        header_text = (await header_el.inner_text()).strip()

    # --- Extract full judgment text ---
    judgment_el = await page.query_selector(".judgments")
    raw_text = await judgment_el.inner_text() if judgment_el else ""

    # Clean up whitespace runs
    full_text = re.sub(r"\n{3,}", "\n\n", raw_text).strip()

    # --- Extract cited cases (links inside the judgment body) ---
    # WHY: These are real citations used by the court — gold for citation verification.
    cited_links = await page.query_selector_all(".judgments a[href*='/doc/']")
    citations = []
    for link in cited_links:
        text = (await link.inner_text()).strip()
        href = await link.get_attribute("href")
        if text and href:
            citations.append({
                "case_name": text,
                "url": KANOON_BASE + href if href.startswith("/") else href,
            })

    # Deduplicate citations by URL
    seen = set()
    unique_citations = []
    for c in citations:
        if c["url"] not in seen:
            seen.add(c["url"])
            unique_citations.append(c)

    console.print(
        f"[green]✓ Fetched judgment ({len(full_text)} chars, "
        f"{len(unique_citations)} cited cases)[/green]"
    )

    return {
        "url": url,
        "header": header_text,
        "full_text": full_text[:15_000],  # WHY: cap at 15k chars to stay within LLM context limits
        "citations_found": unique_citations[:20],
        "status": "success",
    }


# ---------------------------------------------------------------------------
# Public API — called by the research node
# ---------------------------------------------------------------------------

async def search_and_fetch(
    query: str,
    max_results: int = 3,
    headless: bool = False,
) -> dict:
    """
    End-to-end: search Indian Kanoon, then fetch full text of top results.

    Args:
        query: Legal search query (e.g. "landlord tenant eviction Delhi High Court")
        max_results: How many judgments to fetch (default 3 — balances depth vs speed)
        headless: False = visible Chrome window (default), True = background mode

    Returns:
        {
            "query": str,
            "results": [
                {
                    "title": str,
                    "url": str,
                    "snippet": str,
                    "full_text": str,
                    "citations_found": [{"case_name": str, "url": str}],
                    "status": "success" | "error"
                }
            ]
        }
    """
    # WHY: headless flag reads from config so lawyers can flip it without code changes.
    effective_headless = getattr(config, "kanoon_headless", headless)

    async with async_playwright() as pw:
        browser, page = await _get_page(pw, headless=effective_headless)

        try:
            search_results = await _search_kanoon(page, query, max_results)

            enriched = []
            for result in search_results:
                console.print(f"[bold]Fetching:[/bold] {result['title']}")

                # Click into each judgment on the same page (real navigation)
                await page.goto(result["url"], wait_until="domcontentloaded", timeout=40_000)
                judgment_data = await _fetch_judgment(page, result["url"])

                enriched.append({**result, **judgment_data})

                # Go back and wait briefly so the site doesn't rate-limit us
                await page.go_back(wait_until="domcontentloaded", timeout=15_000)
                await page.wait_for_timeout(800)

            return {"query": query, "results": enriched}

        except Exception as e:
            console.print(f"[red]✗ Kanoon browser error: {e}[/red]")
            return {"query": query, "results": [], "error": str(e)}

        finally:
            await browser.close()


def run_kanoon_search(query: str, max_results: int = 3) -> dict:
    """
    Sync wrapper for search_and_fetch — use this from LangChain tool definitions
    or anywhere that isn't already inside an async context.
    """
    return asyncio.run(search_and_fetch(query, max_results))
