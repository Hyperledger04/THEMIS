"""
Phase 7, Lesson 2: Telegram Bot — Another Gateway to the Same Graph

The key insight: voice, CLI, Telegram, and web API all call the same
_run_graph_for_user() function. The graph never knows which gateway sent the request.

This file demonstrates the pattern using mock classes (no real token needed).
"""
import asyncio

print("=" * 60)
print("Telegram Bot — Gateway Pattern")
print("=" * 60)

# ── SECTION 1: Gateway abstraction ─────────────────────────────────────────────
print("""
  LexAgent's gateway pattern:

    [Telegram] ─┐
    [CLI]      ─┼──► _run_graph_for_user(thread_id, brief, cfg) ──► LangGraph
    [Voice]    ─┘

  Every gateway:
  1. Authenticates the user (Telegram user_id / CLI user / JWT token)
  2. Extracts the matter brief from the channel-specific format
  3. Creates or resumes a thread_id (= LangGraph checkpoint key)
  4. Calls _run_graph_for_user()
  5. Formats the response back to the channel
""")

# ── SECTION 2: Mock Telegram classes for demo ──────────────────────────────────
# (Real usage requires: pip install python-telegram-bot and a real token from BotFather)

class MockUser:
    id = 12345
    first_name = "Arjun"

class MockMessage:
    def __init__(self, text: str):
        self.text = text
        self.from_user = MockUser()

    async def reply_text(self, text: str, **kwargs):
        print(f"  [BOT → USER]: {text[:100]}{'...' if len(text) > 100 else ''}")

class MockUpdate:
    def __init__(self, text: str):
        self.message = MockMessage(text)
        self.effective_user = MockUser()

# ── SECTION 3: Handler functions ───────────────────────────────────────────────
async def start_handler(update: MockUpdate, context=None):
    """/start command — welcome message."""
    name = update.effective_user.first_name
    await update.message.reply_text(
        f"Welcome to LexAgent, {name}!\n\n"
        "Send me your matter brief and I'll draft a court-ready document.\n\n"
        "Example: 'I need a writ petition against illegal demolition of my shop'"
    )

async def message_handler(update: MockUpdate, context=None):
    """Handle any text message as a matter brief."""
    user_id = update.effective_user.id
    brief = update.message.text

    # Guard: ignore empty messages
    if not brief.strip():
        await update.message.reply_text("Please describe your legal matter.")
        return

    await update.message.reply_text("⚖️ Processing your matter... (this takes ~30 seconds)")

    # The gateway abstraction: same function for CLI and Telegram
    thread_id = str(user_id)  # one thread per Telegram user
    result = await _run_graph_for_user(thread_id, brief)

    await update.message.reply_text(
        f"📄 Draft ready:\n\n{result['draft'][:500]}...\n\n"
        "Type /help for more options."
    )

async def _run_graph_for_user(thread_id: str, brief: str) -> dict:
    """
    The gateway abstraction — same regardless of which gateway calls it.
    In production: invokes LangGraph with the thread_id as checkpoint key.
    """
    print(f"  [graph] thread_id={thread_id}, brief='{brief[:40]}...'")
    # Simulate graph execution time
    await asyncio.sleep(0.1)
    return {
        "draft": (
            "IN THE HIGH COURT OF DELHI AT NEW DELHI\n\n"
            "WRIT PETITION (CIVIL) NO. ___/2024\n\n"
            "MOST RESPECTFULLY SHOWETH:\n"
            "1. That the petitioner is aggrieved by the impugned action..."
        ),
        "matter_type": "writ_petition",
        "thread_id": thread_id,
    }

# ── SECTION 4: thread_id is matter continuity ──────────────────────────────────
print("""
── thread_id: How LangGraph remembers conversations ──

  In LangGraph, thread_id groups checkpoints into a "conversation":
    thread_id = str(telegram_user.id)  → one thread per Telegram user
    thread_id = matter_id              → one thread per matter (CLI)

  This means:
  - User 12345 sends message 1 → graph runs, checkpoint saved under "12345"
  - User 12345 sends message 2 → graph resumes from "12345" checkpoint
  - User 67890 → completely separate checkpoint ("67890"), isolated state

  LexAgent graph invocation:
    config = {"configurable": {"thread_id": thread_id}}
    graph.astream(state, config)
""")

# ── SECTION 5: Live demo ───────────────────────────────────────────────────────
print("── Simulated Telegram conversation ──\n")

async def demo():
    # User starts the bot
    start_update = MockUpdate("/start")
    print("USER: /start")
    await start_handler(start_update)
    print()

    # User sends a matter brief
    matter_update = MockUpdate(
        "I need a writ petition. The municipal corporation demolished my shop "
        "without notice under Delhi Municipal Corporation Act."
    )
    print("USER: I need a writ petition. The municipal corporation demolished...")
    await message_handler(matter_update)

asyncio.run(demo())

# ── PAUSE AND THINK ───────────────────────────────────────────────────────────
print("\n── PAUSE AND THINK ──")
print("""
  1. Open lexagent/gateway/telegram.py — find _run_graph_for_user().
     How does it differ from the stub here? Does it use graph.astream() or graph.invoke()?

  2. The thread_id for Telegram is str(user_id). What happens if the same lawyer
     uses both CLI and Telegram? Do they share state or have separate threads?

  3. The bot sends a "Processing..." message before running the graph.
     Why is this important? What is the Telegram timeout for responding to messages?

  4. Open lexagent/gateway/telegram.py — how does it handle the case where
     the graph returns an error in state["error"]?

  5. LexAgent's Telegram bot supports inline buttons (next lesson). But this
     lesson uses free-text intake. What are the tradeoffs of buttons vs free text
     for collecting matter information from a lawyer?
""")
