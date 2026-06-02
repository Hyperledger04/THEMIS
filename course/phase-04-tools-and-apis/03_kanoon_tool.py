"""
03_kanoon_tool.py — Indian Kanoon Search Tool
==============================================
Indian Kanoon (https://indiankanoon.org) is the primary free legal database
for Indian case law. Their paid API gives structured JSON. Until you have a
key, you can develop against stub data — same interface, zero network calls.
"""

# ── SECTION 1: THREE MODES ────────────────────────────────────────────────────
#
# This tool supports three operating modes, controlled by a `mode` argument:
#
#  "stub"  → Offline development. Returns hardcoded data.
#             Use this while building — no API key needed, instant, deterministic.
#
#  "api"   → Production. Calls the real Indian Kanoon REST API.
#             Requires INDIANKANOON_API_KEY env var.
#             Docs: https://api.indiankanoon.org/
#
#  "mcp"   → Claude Desktop / agent use. Delegates to the E-courts MCP server
#             (already wired into Claude's tool list in production).
#             In this mode the function is essentially a no-op — the MCP
#             server handles the HTTP call externally.
#
# WHY three modes: You want identical call sites in your nodes regardless of
# environment. Tests and offline dev use stub; CI/CD and production flip to api.

MODE = "stub"  # change to "api" in production

# ── SECTION 2: STUB DATA ──────────────────────────────────────────────────────
#
# Hardcoded sample cases for offline development.
# Keys mirror the real API response shape so you can swap modes without
# touching any calling code.

STUB_RESULTS = [
    {
        "tid": "1234567",
        "title": "Maneka Gandhi v. Union of India",
        "citation": "AIR 1978 SC 597",
        "headline": (
            "Article 21 guarantees right to travel abroad as part of personal "
            "liberty. Passport cannot be impounded without giving the holder "
            "a hearing. Any law curtailing Article 21 must be just, fair, and "
            "reasonable — not merely procedurally authorised."
        ),
        "court": "Supreme Court of India",
        "year": 1978,
    },
    {
        "tid": "2345678",
        "title": "Kesavananda Bharati v. State of Kerala",
        "citation": "AIR 1973 SC 1461",
        "headline": (
            "Basic structure of the Constitution cannot be amended even by a "
            "constitutional amendment under Article 368. Parliament's amending "
            "power is wide but not unlimited."
        ),
        "court": "Supreme Court of India",
        "year": 1973,
    },
    {
        "tid": "3456789",
        "title": "Vishaka v. State of Rajasthan",
        "citation": "AIR 1997 SC 3011",
        "headline": (
            "Sexual harassment at the workplace violates Articles 14, 15, and "
            "21. In the absence of enacted law, the Supreme Court laid down "
            "binding guidelines (the Vishaka Guidelines) for employers."
        ),
        "court": "Supreme Court of India",
        "year": 1997,
    },
]

STUB_JUDGMENT_TEXT = """
SUPREME COURT OF INDIA
{title} — {citation}

BENCH: Seven-judge constitutional bench

HELD:
This is a stub judgment text for offline development.
In production, the full judgment text (often 50–200 pages) is returned here.

Key passages would appear here for citation extraction.
The research node chunks this text, embeds it, and retrieves relevant paragraphs.

[Stub ends — replace with real API call in production]
"""

# ── SECTION 3: search_kanoon ──────────────────────────────────────────────────

def search_kanoon(query: str, mode: str = MODE) -> list[dict]:
    """
    Search Indian Kanoon for cases matching `query`.

    Returns a list of result dicts, each containing:
        tid, title, citation, headline, court, year
    """
    if mode == "stub":
        # Filter stub results whose headline contains any query word
        query_words = query.lower().split()
        hits = [
            r for r in STUB_RESULTS
            if any(w in r["headline"].lower() or w in r["title"].lower()
                   for w in query_words)
        ]
        return hits or STUB_RESULTS[:1]  # always return at least one in stub

    if mode == "api":
        # In api mode:
        # import httpx, os
        # api_key = os.environ["INDIANKANOON_API_KEY"]
        # response = httpx.get(
        #     "https://api.indiankanoon.org/search/",
        #     params={"formInput": query, "pagenum": 0},
        #     headers={"Authorization": f"Token {api_key}"},
        #     timeout=15,
        # )
        # response.raise_for_status()
        # return response.json().get("docs", [])
        raise NotImplementedError("Set mode='stub' for offline dev")

    if mode == "mcp":
        # The E-courts MCP tool handles this externally.
        # Your LangGraph node calls the MCP tool; this function is never invoked.
        raise NotImplementedError("MCP mode is handled by the agent framework")

    raise ValueError(f"Unknown mode: {mode!r}. Choose stub | api | mcp")


# ── SECTION 4: fetch_judgment ─────────────────────────────────────────────────

def fetch_judgment(tid: str, mode: str = MODE) -> str:
    """
    Fetch the full text of a judgment by its Indian Kanoon document ID (tid).

    In production this returns a very long string (the entire judgment).
    The research node then chunks → embeds → retrieves the relevant paragraphs.
    """
    if mode == "stub":
        # Find the matching stub result for a realistic title/citation
        match = next((r for r in STUB_RESULTS if r["tid"] == tid), STUB_RESULTS[0])
        return STUB_JUDGMENT_TEXT.format(
            title=match["title"], citation=match["citation"]
        )

    if mode == "api":
        # import httpx, os
        # api_key = os.environ["INDIANKANOON_API_KEY"]
        # response = httpx.get(
        #     f"https://api.indiankanoon.org/doc/{tid}/",
        #     headers={"Authorization": f"Token {api_key}"},
        #     timeout=30,
        # )
        # response.raise_for_status()
        # return response.json().get("doc", "")
        raise NotImplementedError("Set mode='stub' for offline dev")

    raise ValueError(f"Unknown mode: {mode!r}")


# ── SECTION 5: LIVE DEMO ──────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("DEMO: Searching for 'article 21 right to life'")
    print("=" * 60)

    results = search_kanoon("article 21 right to life")
    print(f"\nFound {len(results)} result(s):\n")

    for i, r in enumerate(results[:2], 1):
        print(f"  [{i}] {r['title']}")
        print(f"       Citation : {r['citation']}")
        print(f"       Court    : {r['court']} ({r['year']})")
        print(f"       Headline : {r['headline'][:80]}...")
        print()

    # Fetch full text of the first result
    first_tid = results[0]["tid"]
    print(f"Fetching full judgment for tid={first_tid} ...")
    text = fetch_judgment(first_tid)
    print(text[:300])
    print("...(truncated)")


# ── PAUSE AND THINK ───────────────────────────────────────────────────────────
#
# 1. In `lexagent/tools/kanoon_tool.py`, which config field controls the mode?
#    (Hint: look at LexConfig in lexagent/config.py for a `kanoon_mode` field.)
#
# 2. The real API returns up to 10 results per page. How would you implement
#    pagination to retrieve results 11–20 for a broad query?
#
# 3. `lexagent/nodes/react_research.py` calls this tool in a loop. What stops
#    it from making 100 API calls and burning your budget?
#
# 4. Why do we return `list[dict]` instead of Pydantic models here?
#    When would you switch to Pydantic for the return type?
#
# 5. The headline is a short excerpt. For citation verification you need the
#    full judgment. At what point in the graph does `fetch_judgment` get called,
#    and which node stores the text for the cite checker?
