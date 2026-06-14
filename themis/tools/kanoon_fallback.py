"""
Playwright-based fallback scraper for Indian Kanoon.

WHY: Used only when the REST API (kanoon_api.py) returns an empty or broken
judgment text for a specific docid. The API is preferred because it is stable
and 10x faster; the Playwright path is the safety net when the API fails for
a particular document (e.g., restricted access or encoding errors).

Exposes a single public function: fetch_doc_playwright(url) -> str | None
The rest of the Playwright logic lives in kanoon.py — this file imports it
rather than duplicating it, so there is one source of truth for scraper fixes.
"""
from __future__ import annotations

from themis.tools.kanoon import _fetch_judgment, _get_page


async def fetch_doc_playwright(url: str, headless: bool = True) -> str | None:
    """
    Fetch judgment full text from a /doc/{id}/ URL using a real Chrome browser.

    Args:
        url: Full Indian Kanoon /doc/{id}/ URL.
        headless: True runs Chrome in background (CI/production default).

    Returns:
        Full judgment text (up to 15k chars), or None if fetch fails.
    """
    from playwright.async_api import async_playwright

    async with async_playwright() as pw:
        browser, page = await _get_page(pw, headless=headless)
        try:
            result = await _fetch_judgment(page, url)
            if result.get("status") == "success":
                return result.get("full_text") or None
            return None
        except Exception:
            return None
        finally:
            await browser.close()
