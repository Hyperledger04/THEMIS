"""
03 — Async / Await
==================
Every node in LexAgent is an `async def` function.
The graph is invoked with `await graph.ainvoke(...)` or `await graph.astream(...)`.

If you have never used async Python, this feels like magic.
This file will make it feel completely obvious.

Run this file:
    python 03_async_await.py
"""

import asyncio
import time

# ──────────────────────────────────────────────
# SECTION 1: The problem async solves
# ──────────────────────────────────────────────
# LexAgent does three slow things during a single request:
#   1. Calls the LLM API (network, ~2-5 seconds)
#   2. Searches Indian Kanoon (network, ~1-3 seconds)
#   3. Reads/writes files (disk, fast but still I/O)
#
# If you write this synchronously (normal Python), the program WAITS for step 1
# to finish before starting step 2. Total time = 2 + 1 + 0 = 3+ seconds.
# With async, you can START both network calls at the same time. Total time = max(2, 1) = 2s.

# SYNCHRONOUS version (the slow way):
def call_llm_sync() -> str:
    """Pretend we're calling the Anthropic API. It takes 2 seconds."""
    time.sleep(2)  # simulates network wait
    return "Here is your draft..."

def search_kanoon_sync() -> list:
    """Pretend we're searching Indian Kanoon. It takes 1 second."""
    time.sleep(1)
    return ["AIR 1973 SC 1461"]

def run_research_sync():
    start = time.time()
    draft = call_llm_sync()      # wait 2s for LLM
    cases = search_kanoon_sync() # THEN wait 1s for search
    elapsed = time.time() - start
    print(f"Sync: draft + cases took {elapsed:.1f}s (sequential)")

# ──────────────────────────────────────────────
# SECTION 2: async def — defining a coroutine
# ──────────────────────────────────────────────
# `async def` creates a COROUTINE function — a function that CAN be paused.
# When Python sees `await`, it pauses this function and lets other coroutines run.
# This is cooperative multitasking — you explicitly yield control with `await`.

async def call_llm_async() -> str:
    """Same LLM call, but async. asyncio.sleep() yields control while waiting."""
    await asyncio.sleep(2)   # yield control for 2 seconds (simulates network wait)
    return "Here is your draft..."

async def search_kanoon_async() -> list:
    """Same search, but async."""
    await asyncio.sleep(1)
    return ["AIR 1973 SC 1461"]

# ──────────────────────────────────────────────
# SECTION 3: Running two coroutines concurrently with asyncio.gather()
# ──────────────────────────────────────────────
# asyncio.gather() runs multiple coroutines AT THE SAME TIME.
# Both start, both yield on their sleeps, and both finish without blocking each other.

async def run_research_async():
    start = time.time()
    # Run both at the same time:
    draft, cases = await asyncio.gather(
        call_llm_async(),
        search_kanoon_async(),
    )
    elapsed = time.time() - start
    print(f"Async: draft + cases took {elapsed:.1f}s (concurrent)")
    return draft, cases


# ──────────────────────────────────────────────
# SECTION 4: asyncio.run() — the entry point
# ──────────────────────────────────────────────
# You cannot call an async function from regular (sync) Python directly.
# asyncio.run() creates an event loop and runs one top-level coroutine.
# LexAgent's CLI does exactly this:
#   asyncio.run(some_async_function())

print("=== SECTION 1-4: Sync vs Async timing ===")
run_research_sync()                    # synchronous — runs immediately
asyncio.run(run_research_async())      # async — needs an event loop


# ──────────────────────────────────────────────
# SECTION 5: The exact pattern LexAgent nodes use
# ──────────────────────────────────────────────
# Every node in lexagent/nodes/ looks like this:

from typing import TypedDict, Optional, List

class LexState(TypedDict):
    user_input: str
    matter_type: Optional[str]
    draft_output: Optional[str]
    messages: List[dict]
    error: Optional[str]

async def intake_node(state: LexState) -> dict:
    """
    This is the structure of EVERY LexAgent node:

    1. `async def run(state: LexState) -> dict:` — always this signature
    2. Read from state with state.get()
    3. Do some async work (call LLM, search, etc.)
    4. Return ONLY the keys you changed
    5. NEVER raise — catch everything, return {"error": str(e)}
    """
    try:
        user_input = state.get("user_input", "")

        # Simulate asking the LLM "what matter type is this?"
        await asyncio.sleep(0.1)   # in real code: await call_llm(...)
        detected_type = "writ petition"  # in real code: parsed from LLM response

        # Return ONLY the keys that changed:
        return {
            "matter_type": detected_type,
            "messages": state.get("messages", []) + [
                {"role": "assistant", "content": f"Detected: {detected_type}"}
            ],
        }
    except Exception as e:
        # Nodes NEVER raise. They set error and return.
        return {"error": str(e)}

async def draft_node(state: LexState) -> dict:
    try:
        matter_type = state.get("matter_type") or "general petition"

        await asyncio.sleep(0.1)   # simulate LLM call
        draft = f"IN THE HIGH COURT OF DELHI\n\nWrit Petition [{matter_type.upper()}]..."

        return {"draft_output": draft}
    except Exception as e:
        return {"error": str(e)}

# Run them in sequence (this is what the graph does):
async def run_two_nodes():
    initial_state: LexState = {
        "user_input": "Draft a writ petition",
        "matter_type": None,
        "draft_output": None,
        "messages": [],
        "error": None,
    }

    print("\n=== SECTION 5: Running LexAgent-style nodes ===")
    # Node 1:
    intake_result = await intake_node(initial_state)
    print(f"After intake: {intake_result}")

    # Merge into state (LangGraph does this for you):
    state_after_intake = {**initial_state, **intake_result}

    # Node 2:
    draft_result = await draft_node(state_after_intake)
    print(f"After draft: matter_type→{state_after_intake['matter_type']}")
    print(f"Draft first line: {draft_result['draft_output'].split(chr(10))[0]}")

asyncio.run(run_two_nodes())


# ──────────────────────────────────────────────
# SECTION 6: async for — streaming tokens
# ──────────────────────────────────────────────
# When LexAgent streams output to the terminal, it uses `async for`.
# The LLM returns tokens one by one, and we print each as it arrives.

async def stream_draft():
    tokens = ["IN THE HIGH COURT", " OF DELHI", "\n\n", "WRIT PETITION", "..."]

    print("\n=== SECTION 6: Streaming tokens ===", end="")
    async def fake_stream(tokens):
        """Simulate a streaming LLM response."""
        for token in tokens:
            await asyncio.sleep(0.1)
            yield token

    async for token in fake_stream(tokens):
        print(token, end="", flush=True)
    print()  # newline after streaming

asyncio.run(stream_draft())


# ──────────────────────────────────────────────
# SECTION 7: Common async mistakes and how to avoid them
# ──────────────────────────────────────────────

print("\n=== SECTION 7: Async gotchas ===")

# MISTAKE 1: Calling an async function without await.
# This returns a coroutine OBJECT — it doesn't run the function.
coroutine_object = intake_node.__call__    # don't do this
print("This is a function object, NOT a result:", type(coroutine_object))

# CORRECT: Always await async functions:
# result = await intake_node(state)   ← correct
# result = intake_node(state)         ← returns coroutine, doesn't run

# MISTAKE 2: Using time.sleep() inside an async function.
# time.sleep() BLOCKS the event loop — nothing else can run.
# Use asyncio.sleep() instead — it yields control.
print("Rule: inside async def, always use asyncio.sleep(), never time.sleep()")

# MISTAKE 3: Forgetting to await a coroutine inside asyncio.gather().
# asyncio.gather(coro1(), coro2()) — correct, both are called (creates coroutines)
# asyncio.gather(coro1, coro2)    — wrong, these are function objects


# ──────────────────────────────────────────────
# PAUSE AND THINK
# ──────────────────────────────────────────────
# Before moving to 04_pydantic_settings.py:
#
# 1. What is the difference between `def` and `async def`?
# 2. What does `await` do? What happens while a function is awaited?
# 3. What does asyncio.gather() do that a sequential await cannot?
# 4. Why do LexAgent nodes use asyncio.sleep() and not time.sleep()?
# 5. Open lexagent/nodes/draft.py in the repo. Find the `async def run(state)` signature.
#    Count how many `await` calls it makes.
#
# When you can answer all five, move on.

print("\n=== DONE — move on to 04_pydantic_settings.py ===")
