"""
Phase 4, Lesson 2: HTTP Clients in Async Python
================================================
Run with: python 02_http_clients.py

LexAgent's tools make HTTP requests to Indian Kanoon's API, external legal
databases, and potentially court websites. This lesson teaches the RIGHT
way to do async HTTP — and exactly WHY the naive approach breaks under load.

No external dependencies needed for the concepts. The async demo requires
httpx: `uv add httpx` or `pip install httpx`.
"""

import asyncio
import time
import json

# ── SECTION 1: THE WRONG WAY — BLOCKING THE EVENT LOOP ────────────────────────

print("=" * 60)
print("SECTION 1: Why requests.get() breaks async code.")
print("=" * 60)
print()

# Python's asyncio runs in a single thread using an event loop.
# When you call a blocking function (like requests.get), it FREEZES
# the entire event loop until the HTTP response comes back.
# While it's frozen, no other coroutine can run.

# WRONG WAY:
def search_kanoon_WRONG(query: str) -> list:
    """
    This function uses the `requests` library — synchronous, blocking.
    If this runs inside an async node, it freezes the event loop.
    The LangGraph graph runner, streaming callbacks, timeouts — all frozen.
    """
    import urllib.request  # stdlib equivalent — also blocking

    # In production this would be: import requests; requests.get(url)
    # Using urllib here so this lesson has zero deps for the demo.
    print(f"  [WRONG] Blocking call for query: '{query}' — event loop frozen!")

    # Simulating what a blocking call does:
    time.sleep(0.1)  # represents network wait — NOTHING ELSE can run
    return [{"title": "Maneka Gandhi v. UoI", "tid": "fake-001"}]

print("Problem: calling a blocking HTTP function inside an async node.")
print()

async def demonstrate_blocking_problem():
    """Show how blocking calls prevent concurrent execution."""

    async def concurrent_task(name: str, delay: float):
        """This task should run while the other is waiting."""
        await asyncio.sleep(delay)  # non-blocking wait
        print(f"  [Task {name}] Completed after {delay}s")

    async def bad_research_node(state: dict) -> dict:
        """A node that calls a blocking function."""
        # This blocks the event loop — concurrent_task cannot run during this
        results = search_kanoon_WRONG(state["query"])
        return {"findings": results}

    print("Attempting concurrent execution with BLOCKING call:")
    start = time.time()
    # If bad_research_node were truly blocking, concurrent_task would be delayed
    # We can't perfectly demo this in a simple script, but the principle holds.
    task1 = asyncio.create_task(concurrent_task("A", 0.05))
    task2 = asyncio.create_task(concurrent_task("B", 0.05))
    node_result = await bad_research_node({"query": "article 21"})
    await task1
    await task2
    elapsed = time.time() - start
    print(f"  [Node result] Found {len(node_result['findings'])} cases")
    print(f"  Elapsed: {elapsed:.2f}s")
    print(f"  NOTE: In real async code with actual requests.get(), concurrent")
    print(f"  tasks would be BLOCKED during the HTTP call — not just slowed.")

asyncio.run(demonstrate_blocking_problem())
print()


# ── SECTION 2: THE RIGHT WAY — ASYNC HTTP WITH HTTPX ──────────────────────────

print("=" * 60)
print("SECTION 2: The right way — httpx.AsyncClient.")
print("=" * 60)
print()

# httpx is the async-first HTTP library that LexAgent uses.
# It has the same API as requests but works properly in async code.

# Pattern 1: async context manager (preferred — auto-closes connection)
async def search_kanoon_RIGHT_demo():
    """
    Demonstrates the async HTTP pattern WITHOUT actually making a request.
    The real implementation in lexagent/tools/kanoon_tool.py looks like this.
    """
    print("Pattern: async with httpx.AsyncClient() as client:")
    print()

    # --- What the real code looks like ---
    REAL_CODE = '''
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://api.indiankanoon.org/search/",
            params={"formInput": query, "pagenum": 0},
            headers={
                "Authorization": f"Token {cfg.kanoon_api_key}",
                "User-Agent": "LexAgent/1.0",   # polite API citizen
            },
            timeout=30.0,   # ALWAYS set a timeout — never let a request hang forever
        )
        response.raise_for_status()   # raises on 4xx/5xx — catches bad API keys, 404s
        data = response.json()
        return data.get("docs", [])
    '''
    # WHY async with? The context manager CLOSES the underlying TCP connection
    # when the block exits — even if an exception occurs. Without this,
    # you leak file descriptors and hit "too many open connections" errors
    # in production.

    print("Real httpx code (not executed — no API key required for this lesson):")
    for line in REAL_CODE.strip().split('\n'):
        print(f"  {line}")
    print()


asyncio.run(search_kanoon_RIGHT_demo())


# ── SECTION 3: RETRY WITH EXPONENTIAL BACKOFF ──────────────────────────────────

print("=" * 60)
print("SECTION 3: Retry logic with exponential backoff.")
print("=" * 60)
print()

# Indian Kanoon's API is rate-limited. Network errors happen.
# Naive code fails permanently on the first error.
# Good code retries with increasing delays.

async def fetch_with_retry(url: str, max_attempts: int = 3) -> dict:
    """
    Retry pattern used throughout lexagent/tools/.

    Attempt 1: immediate
    Attempt 2: wait 2^1 = 2s
    Attempt 3: wait 2^2 = 4s
    After 3 failures: return error dict (never raise)
    """
    last_error = None

    for attempt in range(max_attempts):
        if attempt > 0:
            # WHY exponential? Linear backoff (wait 1s each time) can overload
            # a struggling server. Exponential gives the server time to recover.
            wait_secs = 2 ** attempt
            print(f"  Attempt {attempt + 1}: waiting {wait_secs}s before retry...")
            await asyncio.sleep(wait_secs)
        else:
            print(f"  Attempt {attempt + 1}: immediate...")

        try:
            # Simulate a flaky API — fails on attempts 1 and 2
            if attempt < 2:
                raise ConnectionError(f"Network timeout (simulated attempt {attempt + 1})")

            # Attempt 3 succeeds
            print(f"  Attempt {attempt + 1}: SUCCESS")
            return {"status": "ok", "docs": [{"title": "Maneka Gandhi v. UoI"}]}

        except Exception as e:
            last_error = e
            print(f"  Attempt {attempt + 1}: FAILED — {e}")

    # All attempts exhausted — return error dict, never raise
    # WHY never raise? Nodes must not crash the graph. Return the error
    # in a dict and let the graph handle routing.
    return {"error": str(last_error), "docs": []}


print("Simulating a flaky API call with 3 retry attempts:")
result = asyncio.run(fetch_with_retry("https://api.indiankanoon.org/search/"))
print(f"Final result: {result}")
print()


# ── SECTION 4: ERROR HANDLING — NEVER RAISE FROM A TOOL ──────────────────────

print("=" * 60)
print("SECTION 4: Error handling — tools return errors, never raise.")
print("=" * 60)
print()

# WHY this rule? LangGraph nodes call tools during graph execution.
# If a tool raises an exception, it crashes the entire graph run.
# The user sees a stack trace. Progress is lost.
# Instead: tools return {"error": "..."}. The node checks for the key
# and sets state["error"]. The graph can route on the error field.

async def search_kanoon_safe(query: str, api_key: str = "") -> dict:
    """
    The safe pattern: every possible error is caught and returned as data.
    """
    if not api_key:
        # Missing config — return structured error
        return {
            "error": "kanoon_api_key not configured. Set KANOON_API_KEY env var.",
            "docs": [],
        }

    try:
        # Simulate the HTTP call
        if "bad_query" in query:
            raise ValueError("Query contains invalid characters")

        return {
            "docs": [{"tid": "001", "title": "Sample Case", "headline": "..."}],
            "total": 1,
        }

    except ValueError as e:
        # Known error type — give a helpful message
        return {"error": f"Invalid query: {e}", "docs": []}

    except Exception as e:
        # Unknown error — log it but don't let it propagate
        return {"error": f"Unexpected error fetching from Indian Kanoon: {e}", "docs": []}


print("Testing safe error handling:")

result1 = asyncio.run(search_kanoon_safe("maneka gandhi", api_key="fake-key-123"))
print(f"Valid query result: {result1}")

result2 = asyncio.run(search_kanoon_safe("bad_query here", api_key="fake-key-123"))
print(f"Invalid query result: {result2}")

result3 = asyncio.run(search_kanoon_safe("anything", api_key=""))
print(f"Missing API key result: {result3}")
print()


# ── SECTION 5: THE STUB PATTERN ───────────────────────────────────────────────

print("=" * 60)
print("SECTION 5: The stub pattern — offline development without API keys.")
print("=" * 60)
print()

# LexAgent has three modes for the Kanoon tool (from LexConfig):
#   "stub"  — return hardcoded fake data (development, tests, this course)
#   "api"   — hit the real Indian Kanoon API (production)
#   "mcp"   — call through an MCP server (Claude Desktop integration)
#
# The mode is controlled by cfg.kanoon_mode, which reads from the
# LEXAGENT_KANOON_MODE environment variable.
# WHY three modes? Developers can work offline. Tests don't need API keys.
# The MCP mode lets Claude Desktop users query Kanoon through Claude.

STUB_RESPONSES = {
    "article 21": [
        {
            "tid": "stub-maneka",
            "title": "Maneka Gandhi v. Union of India",
            "citation": "AIR 1978 SC 597",
            "headline": "Article 21 protects against arbitrary state action; procedure must be fair, just and reasonable.",
            "court": "Supreme Court of India",
            "year": 1978,
        },
        {
            "tid": "stub-puttaswamy",
            "title": "K.S. Puttaswamy v. Union of India",
            "citation": "(2017) 10 SCC 1",
            "headline": "Right to privacy is a fundamental right under Article 21.",
            "court": "Supreme Court of India",
            "year": 2017,
        },
    ],
    "cheque bounce 138": [
        {
            "tid": "stub-cheque001",
            "title": "Dashrath Rupsingh Rathod v. State of Maharashtra",
            "citation": "(2014) 9 SCC 129",
            "headline": "Territorial jurisdiction for NI Act s.138 lies where the cheque is presented, not issued.",
            "court": "Supreme Court of India",
            "year": 2014,
        },
    ],
}

async def search_kanoon_with_stub(query: str, kanoon_mode: str = "stub") -> list:
    """
    The actual stub check from lexagent/tools/kanoon_tool.py (simplified).
    """
    # Check mode FIRST — before any network code
    if kanoon_mode == "stub":
        # Find the best matching stub response
        query_lower = query.lower()
        for key, docs in STUB_RESPONSES.items():
            if any(word in query_lower for word in key.split()):
                print(f"  [STUB MODE] Returning {len(docs)} hardcoded results for: '{query}'")
                return docs
        print(f"  [STUB MODE] No stub match for '{query}', returning empty list")
        return []

    elif kanoon_mode == "api":
        # Real API call would go here (not executed in this lesson)
        print(f"  [API MODE] Would call api.indiankanoon.org for: '{query}'")
        return []

    elif kanoon_mode == "mcp":
        print(f"  [MCP MODE] Would route through MCP server for: '{query}'")
        return []

    else:
        return [{"error": f"Unknown kanoon_mode: {kanoon_mode}"}]


print("Stub mode (development — no API key needed):")
results = asyncio.run(search_kanoon_with_stub("article 21 personal liberty", "stub"))
for r in results:
    print(f"  [{r['citation']}] {r['title']}")
print()

print("API mode (production — would need KANOON_API_KEY):")
asyncio.run(search_kanoon_with_stub("article 21", "api"))
print()


# ── SECTION 6: TIMEOUTS ────────────────────────────────────────────────────────

print("=" * 60)
print("SECTION 6: Always set timeouts. Here is why.")
print("=" * 60)
print()

print("""
httpx timeout settings (from lexagent/tools/kanoon_tool.py):

  Search requests  → timeout=30.0   (quick query, should return fast)
  Document fetch   → timeout=60.0   (full judgment text can be large)
  Never            → timeout=None   (NEVER do this — hangs forever if server dies)

The timeout parameter in httpx accepts:
  - A single float: connect + read timeout (both use the same value)
  - httpx.Timeout(connect=5.0, read=30.0): separate connect vs read timeouts

Example:
  timeout = httpx.Timeout(connect=5.0, read=30.0)
  response = await client.get(url, timeout=timeout)

WHY separate connect vs read?
  Connect timeout: how long to wait for the TCP handshake.
  Read timeout: how long to wait for each chunk of the response body.
  A server that accepts connections but sends data slowly needs a long read
  timeout but a short connect timeout.
""")


# ── PAUSE AND THINK ──────────────────────────────────────────────────────────

print("=" * 60)
print("PAUSE AND THINK")
print("=" * 60)
print("""
1. Open lexagent/tools/kanoon_tool.py. Find where it checks cfg.kanoon_mode.
   Is the stub check at the top of the function (before any network code)?
   Why does placement matter for performance?

2. The retry loop uses `2 ** attempt` for backoff delays. What is the total
   wait time if all 3 attempts fail? Is this acceptable for a user-facing
   CLI app that should respond in under 60 seconds?

3. LexAgent uses httpx.AsyncClient as a context manager. Some tutorials show
   creating a module-level client and reusing it:
       client = httpx.AsyncClient()  # module level
   What are the tradeoffs? When would reuse be better?

4. The stub pattern returns hardcoded data keyed by query words. Look at
   lexagent/tools/kanoon_tool.py — does the real stub use the same approach
   or does it load stub data from a JSON file? Why might a file be better
   for a teaching codebase?

5. In lexagent/nodes/react_research.py, the node calls the Kanoon tool
   inside a try/except. Given that the tool itself already catches all
   exceptions and returns {"error": ...}, why does the node ALSO wrap
   the call in try/except? What error could the tool dict still raise
   that the tool's internal try/except cannot catch?
""")
