"""
Phase 7, Lesson 4: Streaming — Tokens to Terminal and Telegram

Two levels of streaming in LexAgent:
  1. LangGraph node-level: astream() yields chunks per node
  2. LLM token-level: stream_cb called for each token from the LLM
"""
import asyncio
import time

print("=" * 60)
print("Streaming — Making 60-Second Waits Bearable")
print("=" * 60)

# ── SECTION 1: The problem ─────────────────────────────────────────────────────
print("""
  Without streaming:
    User sends brief → 45 seconds of silence → full draft appears

  With token streaming:
    User sends brief → "IN THE HIGH..." → " COURT..." → " OF DELHI..." → ...

  Two levels:
  Level 1: LangGraph astream() — yields one dict per completed node
    {"intake": {"matter_type": "writ_petition"}}
    {"research": {"research_findings": [...]}}
    {"draft": {"draft_output": "IN THE HIGH COURT..."}}

  Level 2: LLM token streaming — call_llm(stream_cb=on_token)
    calls on_token("IN") → on_token(" THE") → on_token(" HIGH") → ...
""")

# ── SECTION 2: Terminal token streaming ────────────────────────────────────────
print("── Terminal Streaming (token-by-token) ──\n")

def on_token_terminal(token: str) -> None:
    """Callback: print each token as it arrives. flush=True is critical."""
    print(token, end="", flush=True)
    # Without flush=True: Python buffers output, user sees nothing until the buffer fills

async def fake_llm_stream(prompt: str):
    """Simulates LiteLLM streaming — yields tokens with delay."""
    FAKE_DRAFT = (
        "IN THE HIGH COURT OF DELHI AT NEW DELHI\n\n"
        "WRIT PETITION (CIVIL) NO. ___/2024\n\n"
        "In the matter of:\n"
        "Ram Sharma                    ...Petitioner\n"
        "versus\n"
        "State of Delhi                ...Respondent\n\n"
        "MOST RESPECTFULLY SHOWETH:\n\n"
        "1. That the petitioner is aggrieved by the impugned order\n"
        "   dated 15.01.2024 passed by the Respondent authority."
    )
    for word in FAKE_DRAFT.split(" "):
        yield word + " "
        await asyncio.sleep(0.03)  # simulate LLM latency

async def stream_to_terminal(brief: str):
    print(f"[Drafting for: {brief[:40]}...]\n")
    print("─" * 50)
    async for token in fake_llm_stream(brief):
        on_token_terminal(token)
    print("\n" + "─" * 50)
    print("\n[Draft complete]")

asyncio.run(stream_to_terminal("writ petition challenging illegal demolition"))

# ── SECTION 3: LangGraph astream() — node-level ────────────────────────────────
print("""
\n── LangGraph astream() — yields one chunk per node ──

  async for chunk in graph.astream(state, config):
      # chunk is a dict: {node_name: {changed_keys}}
      # e.g. {"intake": {"matter_type": "writ_petition", "jurisdiction": "delhi"}}
      node_name = list(chunk.keys())[0]
      updates = list(chunk.values())[0]
      print(f"[{node_name}] updated: {list(updates.keys())}")

  This is different from token streaming:
  - astream() yields AFTER each node completes (node granularity)
  - stream_cb fires DURING LLM generation (token granularity)
  - Use astream() to update the spinner between nodes
  - Use stream_cb to stream the actual draft text to the user
""")

# ── SECTION 4: Telegram streaming ─────────────────────────────────────────────
print("── Telegram Streaming (edit message as tokens arrive) ──\n")

class MockTelegramMessage:
    def __init__(self):
        self._text = "Drafting..."
        self._edit_count = 0

    async def edit_text(self, new_text: str):
        self._text = new_text
        self._edit_count += 1
        # Only show every 5th edit to avoid flooding output
        if self._edit_count % 5 == 0:
            print(f"  [EDIT #{self._edit_count}]: {new_text[:60]}...")


async def stream_to_telegram(brief: str, message: MockTelegramMessage):
    """
    Stream draft to Telegram by editing the same message as tokens arrive.
    Rate-limit edits: Telegram allows ~20 edits/second per chat.
    """
    buffer = ""
    token_count = 0
    EDIT_EVERY = 8  # edit message every 8 tokens (rate limiting)

    async for token in fake_llm_stream(brief):
        buffer += token
        token_count += 1
        if token_count % EDIT_EVERY == 0:
            await message.edit_text(buffer)

    # Final edit with complete text
    await message.edit_text(buffer + "\n\n✅ Draft complete")
    print(f"\n  Total edits: {message._edit_count}")

print("Simulating Telegram draft streaming (showing every 5th edit):\n")
telegram_msg = MockTelegramMessage()
asyncio.run(stream_to_telegram("writ petition", telegram_msg))

# ── PAUSE AND THINK ───────────────────────────────────────────────────────────
print("\n── PAUSE AND THINK ──")
print("""
  1. Open lexagent/nodes/_llm.py — find the stream_cb parameter.
     What type annotation does it have? Where does it get called in the LLM loop?

  2. The Telegram edit approach has a race condition: if two edits arrive
     simultaneously, they may overwrite each other. How does the real Telegram
     gateway in lexagent/gateway/telegram.py handle this?

  3. The fake_llm_stream here splits on spaces (word-level).
     Real LLM streaming is sub-word token level (e.g. " petit" then "ion").
     Does this affect the Telegram streaming logic? What would render badly?

  4. LexAgent has a 180-second timeout on graph runs (asyncio.wait_for).
     What happens to the streaming Telegram message if the graph times out?
     Where would you catch this to send a proper error message?

  5. open lexagent/cli.py — search for "stream_cb". How does the CLI pass
     its on_token callback to the graph nodes? Is it via state, config, or closure?
""")
