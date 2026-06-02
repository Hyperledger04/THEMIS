"""
Phase 7 — Exercise 2: Implement a Telegram /draft Handler

No real Telegram token needed — we use mock classes throughout.
"""
import asyncio


# ── Mock classes (do not modify) ──────────────────────────────────────────────
class MockUser:
    id = 99999
    first_name = "Priya"

class MockMessage:
    def __init__(self, text: str):
        self.text = text
        self.from_user = MockUser()
        self._replies: list[str] = []

    async def reply_text(self, text: str, **kwargs):
        self._replies.append(text)
        print(f"  BOT: {text[:100]}{'...' if len(text) > 100 else ''}")

class MockUpdate:
    def __init__(self, text: str):
        self.message = MockMessage(text)
        self.effective_user = MockUser()


# ── TODO 1: Implement draft_handler ──────────────────────────────────────────
async def draft_handler(update: MockUpdate, context=None) -> None:
    """
    Handle /draft <matter_brief> command.

    Requirements:
    1. Extract the brief from update.message.text by stripping the "/draft " prefix
    2. If brief is empty after stripping, reply "Please provide a brief: /draft your matter"
    3. If brief is provided:
       a. Reply "⚖️ Processing your matter..."
       b. Call run_draft_stub(brief)
       c. Reply with the draft result
    """
    # TODO: implement
    pass


# ── TODO 2: Implement run_draft_stub ─────────────────────────────────────────
async def run_draft_stub(brief: str) -> str:
    """
    Stub that simulates graph execution.
    Return a 3-line fake draft that mentions the brief.
    Include the matter_type ("writ petition" / "legal notice" / "affidavit") based on keywords.
    """
    # TODO: implement
    # Hint: check if "writ" in brief.lower(), "notice" in brief.lower(), etc.
    # Return a formatted string like:
    #   "IN THE HIGH COURT...\n\nWRIT PETITION...\n\nFor: {brief[:40]}..."
    pass


# ── TODO 3: Implement a button renderer for a follow-up question ──────────────
class SimpleButton:
    def __init__(self, text: str, callback_data: str):
        self.text = text
        self.callback_data = callback_data
    def __repr__(self): return f"[{self.text}]"

async def ask_court_question(update: MockUpdate) -> None:
    """
    After receiving the brief, ask which court with mock buttons.
    Reply with: "Which court?" + display 3 buttons (High Court, SC, District Court)
    """
    # TODO: create 3 SimpleButton objects, display them as a row
    # await update.message.reply_text("Which court?")
    # print the buttons in one line
    pass


# ── TESTS ─────────────────────────────────────────────────────────────────────
async def run_tests():
    print("── Test 1: /draft with a full brief ──")
    update1 = MockUpdate("/draft I need a writ petition against illegal demolition of my shop")
    await draft_handler(update1)
    assert len(update1.message._replies) >= 2, "Should send at least 2 replies (processing + draft)"
    assert any("Processing" in r or "⚖️" in r for r in update1.message._replies), \
        "Should send a processing message"
    assert any(len(r) > 20 for r in update1.message._replies), \
        "Should send a substantive draft reply"
    print("✓ Full brief handled correctly\n")

    print("── Test 2: /draft with no brief ──")
    update2 = MockUpdate("/draft")
    await draft_handler(update2)
    assert len(update2.message._replies) == 1, "Should send exactly 1 reply for empty brief"
    assert "Please" in update2.message._replies[0] or "brief" in update2.message._replies[0].lower(), \
        "Should ask for a brief"
    print("✓ Empty brief handled correctly\n")

    print("── Test 3: Court question buttons ──")
    update3 = MockUpdate("test")
    print("  Rendering court selection buttons:")
    await ask_court_question(update3)
    print("✓ Court question rendered\n")

    print("✅ All tests passed!")


if __name__ == "__main__":
    asyncio.run(run_tests())

# ── PAUSE AND THINK ───────────────────────────────────────────────────────────
# 1. Open lexagent/gateway/telegram.py — how does the real handler extract
#    the brief? Does it use text.removeprefix("/draft ") or another method?
# 2. Your handler sends 2 messages: "Processing..." then the draft.
#    The real gateway might edit the first message instead of sending a second.
#    What's the UX difference? Which is better for long drafts?
# 3. What happens if run_draft_stub raises an exception?
#    Add a try/except block to draft_handler that replies with a friendly error.
