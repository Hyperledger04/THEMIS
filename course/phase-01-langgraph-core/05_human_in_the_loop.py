"""
05 — Human-in-the-Loop
========================
The most subtle pattern in LexAgent.

The intake node doesn't loop back to itself. Instead, it stops the graph (returns END),
the CLI shows the question to the lawyer, the lawyer answers, and the CLI re-invokes
the graph with the answer added to the message history.

This file shows EXACTLY how that works.

Run this file:
    python 05_human_in_the_loop.py
"""

import asyncio
from typing import List, Optional, TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph


class MatterState(TypedDict):
    user_input: str
    matter_type: Optional[str]
    jurisdiction: Optional[str]
    purpose: Optional[str]
    intake_complete: bool
    pending_question: Optional[str]   # the question the agent wants to ask
    messages: List[dict]
    error: Optional[str]


# ──────────────────────────────────────────────
# THE INTAKE NODE — asks questions one at a time
# ──────────────────────────────────────────────

async def intake_node(state: MatterState) -> dict:
    """
    Collect information from the lawyer by asking questions one at a time.
    After each question, return END (stop the graph).
    The CLI shows the question, gets the answer, and re-invokes the graph.
    """
    messages = state.get("messages") or []

    # Check what we have so far:
    matter_type = state.get("matter_type")
    jurisdiction = state.get("jurisdiction")
    purpose = state.get("purpose")

    # Extract any recent lawyer answer from the message history:
    recent_answer = None
    for msg in reversed(messages):
        if msg["role"] == "user":
            recent_answer = msg["content"]
            break

    print(f"  [intake] state check:")
    print(f"    matter_type={matter_type}, jurisdiction={jurisdiction}, purpose={purpose}")
    print(f"    recent_answer='{recent_answer}'")

    # ── QUESTION 1: What type of matter? ──
    if matter_type is None:
        if recent_answer and "matter_type" not in str(messages[:-1]):
            # The lawyer just answered our first question:
            return {
                "matter_type": recent_answer,
                "messages": messages + [
                    {"role": "assistant", "content": f"Got it: {recent_answer}. Now, which court?"}
                ],
                "pending_question": "Which court and state?",
            }
        else:
            # Ask the first question:
            question = "What type of document do you need? (e.g., writ petition, injunction, legal notice)"
            return {
                "pending_question": question,
                "messages": messages + [
                    {"role": "assistant", "content": question}
                ],
            }

    # ── QUESTION 2: Which court? ──
    if jurisdiction is None:
        if recent_answer:
            return {
                "jurisdiction": recent_answer,
                "messages": messages + [
                    {"role": "assistant", "content": f"Court noted: {recent_answer}. What relief are you seeking?"}
                ],
                "pending_question": "What relief are you seeking?",
            }
        else:
            question = "Which court? (e.g., Delhi High Court, Bombay HC, Supreme Court)"
            return {
                "pending_question": question,
                "messages": messages + [
                    {"role": "assistant", "content": question}
                ],
            }

    # ── QUESTION 3: What purpose? ──
    if purpose is None:
        if recent_answer:
            return {
                "purpose": recent_answer,
                "intake_complete": True,   # ← all required fields collected
                "messages": messages + [
                    {"role": "assistant", "content": "All information collected. Starting research and drafting..."}
                ],
            }
        else:
            question = "What relief are you seeking? (e.g., stay on government order, compensation)"
            return {
                "pending_question": question,
                "messages": messages + [
                    {"role": "assistant", "content": question}
                ],
            }

    # All fields collected:
    return {"intake_complete": True}


def route_after_intake(state: MatterState) -> str:
    if state.get("error"):
        return END
    if state.get("intake_complete"):
        return "draft"
    # Not complete — stop and wait for the lawyer's answer:
    return END


async def draft_node(state: MatterState) -> dict:
    print(f"\n  [draft] creating document...")
    print(f"    type: {state.get('matter_type')}")
    print(f"    court: {state.get('jurisdiction')}")
    print(f"    purpose: {state.get('purpose')}")
    return {"draft_output": "[DRAFT COMPLETE]"}


def build_graph():
    graph = StateGraph(MatterState)
    graph.add_node("intake", intake_node)
    graph.add_node("draft", draft_node)
    graph.set_entry_point("intake")
    graph.add_conditional_edges("intake", route_after_intake)
    graph.add_edge("draft", END)
    return graph


# ──────────────────────────────────────────────
# THE CLI LOOP — the human-in-the-loop pattern
# ──────────────────────────────────────────────
# This simulates what lexagent/cli.py does:
# 1. Invoke the graph
# 2. If it returns a pending_question, ask the lawyer
# 3. Add the answer to messages
# 4. Re-invoke the graph with the updated messages
# 5. Repeat until draft_output appears

async def simulate_cli_conversation():
    print("=== SIMULATING LexAgent CLI intake ===")
    print("(In real LexAgent, these prompts go to the terminal)")
    print()

    graph_def = build_graph()
    graph = graph_def.compile(checkpointer=MemorySaver())

    # The thread_id is what lets the graph resume from where it left off.
    # Same thread_id = same "conversation". Different thread_id = fresh start.
    thread_id = "matter-brahm-001"
    config = {"configurable": {"thread_id": thread_id}}

    # Initial state — just the lawyer's original brief:
    state: MatterState = {
        "user_input": "I need help with a matter",
        "matter_type": None,
        "jurisdiction": None,
        "purpose": None,
        "intake_complete": False,
        "pending_question": None,
        "messages": [],
        "error": None,
    }

    # Simulate a lawyer who answers questions one at a time:
    simulated_lawyer_answers = [
        "writ petition",           # answer to Q1: what type?
        "Delhi High Court",        # answer to Q2: which court?
        "stay on demolition order" # answer to Q3: what relief?
    ]
    answer_idx = 0

    max_iterations = 10  # safety limit
    for i in range(max_iterations):
        print(f"\n── Graph invocation #{i+1} ──")

        # Re-invoke the graph (with the same thread_id to resume state):
        final_state = await graph.ainvoke(state, config=config)

        # Check if draft is ready:
        if final_state.get("draft_output"):
            print(f"\n✓ DRAFT READY: {final_state['draft_output']}")
            break

        # Check if there's a question to ask:
        pending_question = final_state.get("pending_question")
        if pending_question:
            print(f"\nAgent asks: {pending_question}")

            # In real code: input() or Telegram message waits here for lawyer
            if answer_idx < len(simulated_lawyer_answers):
                answer = simulated_lawyer_answers[answer_idx]
                answer_idx += 1
                print(f"Lawyer answers: {answer}")
            else:
                print("(No more simulated answers)")
                break

            # Add the lawyer's answer to messages and re-invoke:
            state = {
                **final_state,
                "messages": final_state.get("messages", []) + [
                    {"role": "user", "content": answer}
                ],
                "pending_question": None,   # clear the pending question
            }
        else:
            print("No pending question and no draft — something unexpected")
            break

    print("\n=== Conversation complete ===")
    print(f"Final matter_type: {final_state.get('matter_type')}")
    print(f"Final jurisdiction: {final_state.get('jurisdiction')}")
    print(f"Final purpose: {final_state.get('purpose')}")


# ──────────────────────────────────────────────
# WHY NOT LOOP BACK TO INTAKE?
# ──────────────────────────────────────────────

print("""
WHY DOES INTAKE RETURN END INSTEAD OF LOOPING?

OPTION A (what LexAgent does): intake → END → CLI shows question → lawyer answers
  → CLI re-invokes graph with answer in messages → intake → END → ... → draft → END

OPTION B (tempting but wrong): intake → asks question → asks question → asks question → draft

With Option B:
  - The LLM runs multiple turns with NO new user input between turns
  - The user sees a spinning indicator with nothing happening
  - Questions appear all at once at the end (bad UX)
  - You can't inject the lawyer's answers between LLM calls

With Option A (human-in-the-loop via END):
  - Each question appears immediately
  - The lawyer answers before the next question is generated
  - The LLM sees the lawyer's actual answer when deciding the next question
  - Telegram users see inline buttons, CLI users see prompts
  - Everything works naturally

This is THE most important architectural decision in LexAgent.
""")

asyncio.run(simulate_cli_conversation())
print("\n=== DONE — move on to 06_checkpointers.py ===")
