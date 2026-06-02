# Phase 4 — Tools and APIs: Real Case Law Retrieval

> **Status: Coming soon.** Complete Phases 0-3 first.

## What you will build

By the end of this phase, your agent will:
- Search Indian Kanoon for real case law using the official API
- Calculate limitation periods under the Limitation Act 1963
- Expose tools through a self-registering registry (add tool = drop a file)
- Use Tavily for general legal web research when Kanoon doesn't have it

## The files you will understand

- `lexagent/tools/registry.py` — `@ToolRegistry.register` decorator, self-registration
- `lexagent/tools/kanoon.py` — `search_and_fetch()`, Kanoon API + Playwright fallback
- `lexagent/tools/kanoon_api.py` — raw HTTP client for the Kanoon REST API
- `lexagent/tools/limitation.py` — `check_limitation()` with the 1963 Act tables
- `lexagent/tools/tavily_search.py` — web research fallback
- `lexagent/nodes/research.py` — how the research node calls these tools
- `lexagent/nodes/react_research.py` — ReAct loop (think → act → observe)

## Key concepts

- **Tool registry pattern** — self-registration via decorator (no central list to update)
- **BYOK backends** — stub / api / mcp modes per tool, switched by config
- **ReAct pattern** — Reason, Act, Observe loop for multi-step research
- **Citation gate** — dropping hallucinated citations before they reach the draft
- **Playwright fallback** — when the API returns no text, open a headless browser

## The architecture choice that matters

LexAgent supports three backends for every data source:
- `stub` — returns fake data; works offline; used in all tests
- `api` — real HTTP call with the lawyer's API key
- `mcp` — delegates to an MCP server (E-courts, Claude.ai plugins)

This is why you can run `pytest` without any API keys. And why enabling Kanoon
in production is just: `KANOON_API_KEY=... LEX_KANOON_BACKEND=api` in `.env`.

## Coming in this phase

1. `01_tool_registry.py` — the decorator registration pattern
2. `02_http_clients.py` — httpx, respx for mocking, auth headers
3. `03_kanoon_api.py` — build the Indian Kanoon API client
4. `04_limitation_calculator.py` — Limitation Act 1963 lookup tables
5. `05_react_loop.py` — the ReAct (Reason-Act-Observe) pattern
6. `exercises/ex01_write_a_tool.py` — register a new tool
7. `exercises/ex02_add_backend_mode.py` — add stub/api/mcp switching
