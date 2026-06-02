"""
Phase 7, Lesson 3: Telegram Inline Buttons for Structured Intake

The pending_questions field in LexState drives button rendering.
This file uses mock classes — no real Telegram token needed.
"""
import asyncio

print("=" * 60)
print("Telegram Inline Buttons — Structured Intake")
print("=" * 60)

# ── SECTION 1: Why structured intake? ─────────────────────────────────────────
print("""
  Free text intake problem:
    Lawyer: "I need to file something about a cheque bounce"
    Intake node must ask: Which court? What amount? Date of dishonour?

  Button intake solution:
    Bot shows structured questions with click-to-answer buttons.
    No ambiguity. No text parsing. Required fields guaranteed.

  LexState field: pending_questions: list[dict]
  Each question dict:
    {
      "field": "jurisdiction",          # which LexState field to set
      "question": "Which court?",       # text to show user
      "type": "mcq",                    # "binary" | "mcq" | "open"
      "options": ["High Court", "District Court", "NCLT"],
    }
""")

# ── SECTION 2: Mock Telegram button classes ────────────────────────────────────
class InlineKeyboardButton:
    def __init__(self, text: str, callback_data: str):
        self.text = text
        self.callback_data = callback_data

    def __repr__(self):
        return f"[{self.text}]"


class InlineKeyboardMarkup:
    def __init__(self, buttons: list[list[InlineKeyboardButton]]):
        self.buttons = buttons

    def display(self, indent: str = "    "):
        for row in self.buttons:
            print(indent + "  ".join(repr(b) for b in row))

    def __repr__(self):
        return f"Markup({self.buttons})"


# ── SECTION 3: The pending_questions flow ─────────────────────────────────────
PENDING_QUESTIONS = [
    {
        "field": "jurisdiction",
        "question": "Which court will you file in?",
        "type": "mcq",
        "options": ["High Court", "Supreme Court", "District Court", "NCLT / NCLAT"],
    },
    {
        "field": "matter_urgency",
        "question": "Is this matter urgent?",
        "type": "binary",
        "options": ["Yes — file within 7 days", "No — normal timeline"],
    },
    {
        "field": "parties_known",
        "question": "Do you have full party details (name, address)?",
        "type": "binary",
        "options": ["Yes, I have all details", "No, need to gather them"],
    },
]


def render_question(question: dict) -> tuple[str, InlineKeyboardMarkup]:
    """
    Convert a pending_question dict into a Telegram question text + button markup.
    callback_data format: "field_name:option_index" (e.g. "jurisdiction:0")
    """
    field = question["field"]
    options = question["options"]

    if question["type"] == "binary":
        # Two buttons on one row
        buttons = [[
            InlineKeyboardButton(options[0], f"{field}:0"),
            InlineKeyboardButton(options[1], f"{field}:1"),
        ]]
    else:
        # MCQ: one button per row (easier to read on mobile)
        buttons = [
            [InlineKeyboardButton(opt, f"{field}:{i}")]
            for i, opt in enumerate(options)
        ]

    return question["question"], InlineKeyboardMarkup(buttons)


def parse_callback(callback_data: str, questions: list[dict]) -> dict:
    """
    Parse callback_data string back into {field: value}.
    callback_data format: "field_name:option_index"
    """
    field, idx_str = callback_data.split(":", 1)
    idx = int(idx_str)
    # Find the question for this field
    for q in questions:
        if q["field"] == field:
            return {field: q["options"][idx]}
    return {field: idx_str}


# ── SECTION 4: Simulated intake flow ──────────────────────────────────────────
print("── Simulating 3-question structured intake ──\n")

# Simulated lawyer answers (what they would click)
SIMULATED_CLICKS = ["jurisdiction:0", "matter_urgency:0", "parties_known:1"]

collected_answers = {}

for i, (question_dict, click) in enumerate(zip(PENDING_QUESTIONS, SIMULATED_CLICKS)):
    question_text, markup = render_question(question_dict)

    print(f"Q{i+1}: {question_text}")
    markup.display()

    # Lawyer clicks a button
    answer = parse_callback(click, PENDING_QUESTIONS)
    collected_answers.update(answer)
    field = list(answer.keys())[0]
    value = list(answer.values())[0]
    print(f"  → Lawyer clicked: '{value}'")
    print()

print("── Collected state updates ──")
for k, v in collected_answers.items():
    print(f"  {k}: {v}")

# ── SECTION 5: How this merges back into LexState ─────────────────────────────
print("""
── How button answers update LexState ──

  After each button click, the callback handler:
  1. Parses callback_data → {field: value}
  2. Calls graph.astream() with updated state:
     {
       "jurisdiction": "High Court",
       "matter_urgency": "Yes — file within 7 days",
       # ... other existing state fields unchanged ...
     }
  3. Intake node sees pending_questions is now empty → intake_complete = True
  4. Graph proceeds to research node

  The graph doesn't know buttons were used — it just sees updated state fields.
""")

# ── PAUSE AND THINK ───────────────────────────────────────────────────────────
print("── PAUSE AND THINK ──")
print("""
  1. Open lexagent/gateway/telegram.py — find the CallbackQueryHandler.
     What function handles button clicks? How does it parse callback_data?

  2. Open lexagent/state.py — find the pending_questions field.
     What is its type annotation? How does the intake node set it?

  3. The callback_data format here is "field:index". Telegram limits callback_data
     to 64 bytes. For long option text, what would break? How would you fix it?

  4. What happens if a lawyer presses a button twice (double-click)?
     The graph gets invoked twice with the same answer. Is this idempotent?

  5. For "open" type questions (free text, no buttons), how would you handle
     the answer? The lawyer must type text — what handler catches that?
""")
