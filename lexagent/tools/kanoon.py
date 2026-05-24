# WHY: We use Playwright (not Selenium or API) because Indian Kanoon's search
# requires real browser interactions — clicking result links, waiting for judgment
# divs to hydrate, and navigating paginated results. Playwright's async API
# integrates cleanly with LangGraph's async node contract.
#
# headless=False by default so you can watch the browser during development.
# Set LEX_KANOON_HEADLESS=true in .env for CI or background runs.
#
# --- Key bugs fixed (2025-05) ---
# 1. docfragment URLs: search result links point to /docfragment/{id}/ (an AJAX
#    fragment endpoint) not /doc/{id}/ (the full page). Navigating to a fragment
#    URL gives a raw HTML snippet with no .judgments div → scraper returned
#    "Judgment div not found". Fix: rewrite href before navigation.
# 2. Stale element handles: collecting result elements then calling page.go_back()
#    invalidated the DOM nodes. Fix: collect all hrefs first, then navigate fresh.
# 3. domcontentloaded too early: .judgments div is JS-rendered after DOM ready.
#    Fix: wait_until="networkidle" + broader selector fallback.

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

# WHY: Indian Kanoon uses several CSS classes for the judgment body across
# different page layouts. We try each in order so one layout change doesn't
# break the whole scraper.
_JUDGMENT_SELECTORS = [
    ".judgments",
    "#judgment",
    ".judgment",
    "[class*='judg']",
    ".doc_content",
]


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


def _fix_doc_url(href: str) -> str:
    """
    Convert a /docfragment/{id}/ AJAX href to the full /doc/{id}/ page URL.

    WHY: Indian Kanoon search results link to /docfragment/{id}/?formInput=...
    which is an AJAX fragment endpoint — navigating to it directly gives a raw
    HTML snippet with no .judgments div. The real judgment page is /doc/{id}/.
    """
    # /docfragment/12345678/?formInput=... → /doc/12345678/
    fixed = re.sub(r"/docfragment/(\d+)/.*", r"/doc/\1/", href)
    # Strip any remaining query string from /doc/ URLs too
    fixed = re.sub(r"(/doc/\d+/).*", r"\1", fixed)
    return fixed


async def _search_kanoon(page: Page, query: str, max_results: int = 5) -> list[dict]:
    """
    Navigate to Indian Kanoon search and collect result titles + full /doc/ URLs.

    WHY: We collect ALL hrefs into plain strings before any navigation.
    Navigating away from the search page invalidates Playwright element handles,
    causing stale-element errors if we try to read them after page.go_back().
    """
    search_url = SEARCH_URL.format(query=quote_plus(query))
    console.print(f"[dim]→ Navigating to search: {search_url}[/dim]")

    await page.goto(search_url, wait_until="domcontentloaded", timeout=30_000)
    await page.wait_for_selector(".result_title", timeout=15_000)

    result_elements = await page.query_selector_all(".result_title a")

    # Collect titles and hrefs as plain values before any navigation
    raw_results: list[dict] = []
    for el in result_elements[:max_results]:
        title = (await el.inner_text()).strip()
        href = await el.get_attribute("href")
        if href and title:
            # Convert /docfragment/ → /doc/ before storing
            clean_href = _fix_doc_url(href)
            full_url = KANOON_BASE + clean_href if clean_href.startswith("/") else clean_href
            raw_results.append({"title": title, "url": full_url})

    # Grab snippets from the still-loaded search page
    snippet_elements = await page.query_selector_all(".result_title + p, .docsource_main")
    for i, el in enumerate(snippet_elements[:max_results]):
        if i < len(raw_results):
            raw_results[i]["snippet"] = (await el.inner_text()).strip()[:300]

    console.print(f"[green]✓ Found {len(raw_results)} results[/green]")
    return raw_results


async def _fetch_judgment(page: Page, url: str) -> dict:
    """
    Open a single /doc/{id}/ judgment page and extract:
    - Full text of the judgment
    - Citation header (case name, court, date)
    - All internal citation links (other cases cited within)
    """
    console.print(f"[dim]→ Opening judgment: {url}[/dim]")

    # WHY: networkidle waits until no network requests fire for 500ms — ensures
    # the JS-rendered .judgments div is in the DOM before we query it.
    # domcontentloaded is too early; the judgment body loads after DOM ready.
    await page.goto(url, wait_until="networkidle", timeout=40_000)

    # Try selectors in order — Indian Kanoon has used several class names
    judgment_el = None
    matched_selector = None
    for selector in _JUDGMENT_SELECTORS:
        try:
            await page.wait_for_selector(selector, timeout=8_000)
            judgment_el = await page.query_selector(selector)
            if judgment_el:
                matched_selector = selector
                break
        except Exception:
            continue

    if judgment_el is None:
        # Last resort: dump the full visible body text
        body_text = await page.inner_text("body")
        if len(body_text.strip()) > 200:
            console.print("[yellow]⚠ .judgments not found — falling back to body text[/yellow]")
            full_text = re.sub(r"\n{3,}", "\n\n", body_text).strip()[:15_000]
            return {
                "url": url,
                "header": "",
                "full_text": full_text,
                "citations_found": [],
                "status": "success",
                "selector_used": "body_fallback",
            }
        return {"url": url, "error": "Judgment div not found — page may have redirected"}

    # --- Extract judgment header (case name, court, bench, date) ---
    header_text = ""
    header_el = await page.query_selector(".docsource_main, h2.doc_title, .doc_title")
    if header_el:
        header_text = (await header_el.inner_text()).strip()

    # --- Extract full judgment text ---
    raw_text = await judgment_el.inner_text()
    full_text = re.sub(r"\n{3,}", "\n\n", raw_text).strip()

    # --- Extract cited cases (links inside the judgment body) ---
    # WHY: These are real citations used by the court — gold for citation verification.
    cited_links = await page.query_selector_all(f"{matched_selector} a[href*='/doc/']")
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
    seen: set[str] = set()
    unique_citations: list[dict] = []
    for c in citations:
        if c["url"] not in seen:
            seen.add(c["url"])
            unique_citations.append(c)

    console.print(
        f"[green]✓ Fetched judgment ({len(full_text)} chars, "
        f"{len(unique_citations)} cited cases, selector={matched_selector})[/green]"
    )

    return {
        "url": url,
        "header": header_text,
        "full_text": full_text[:15_000],  # WHY: cap at 15k chars to stay within LLM context limits
        "citations_found": unique_citations[:20],
        "status": "success",
        "selector_used": matched_selector,
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
    effective_headless = getattr(config, "kanoon_headless", headless)

    async with async_playwright() as pw:
        browser, page = await _get_page(pw, headless=effective_headless)

        try:
            search_results = await _search_kanoon(page, query, max_results)

            enriched: list[dict] = []
            for result in search_results:
                console.print(f"[bold]Fetching:[/bold] {result['title']}")

                # WHY: Navigate to each judgment URL directly rather than using
                # page.go_back(). go_back() returns to the JS-rendered search page
                # and invalidates the element handles we captured earlier.
                # Direct goto is safer and avoids stale-element race conditions.
                judgment_data = await _fetch_judgment(page, result["url"])
                enriched.append({**result, **judgment_data})

                # Brief pause so the site doesn't rate-limit us
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
