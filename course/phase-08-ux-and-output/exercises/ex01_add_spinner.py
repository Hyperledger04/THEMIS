"""
Phase 8 — Exercise 01: Add a Live Spinner to the Pipeline
==========================================================
Implement animate_graph_run() — a function that drives a Rich Live
spinner through all graph nodes, showing a different loading message
for each node.

Install: pip install rich
Run:     python ex01_add_spinner.py
"""

import time
import random

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.spinner import Spinner

console = Console()

# ── THE MESSAGES DICT ─────────────────────────────────────────────────────────
# This mirrors the subset of lexagent/data/loading_messages.yaml
# that your animate_graph_run() function will use.

LOADING_MESSAGES = {
    "intake": [
        "Analysing your brief...",
        "Reading your matter brief...",
        "Identifying matter type and parties...",
    ],
    "research": [
        "Searching Indian Kanoon for precedents...",
        "Reading judgments and extracting citations...",
        "Reading 47 judgments so you don't have to...",
    ],
    "draft": [
        "Drafting your petition...",
        "Writing with verified citations...",
        "Hereinafter referred to as 'almost done'...",
    ],
    "cite": [
        "Verifying citations against Indian Kanoon corpus...",
        "Cross-examining citations...",
        "Holding citations in contempt...",
    ],
    "review": [
        "Final review — checking length and citations...",
        "Quality check in progress...",
        "Your Honour, the draft is ready...",
    ],
}


# ── YOUR TASK ─────────────────────────────────────────────────────────────────

def animate_graph_run(
    node_names: list[str],
    loading_messages: dict[str, list[str]],
) -> None:
    """
    Animate a live spinner through the given list of graph nodes.

    For each node_name in node_names:
      1. Pick a random message from loading_messages[node_name]
         (use get_message() below — it handles missing keys safely)
      2. Update the Live display with a Spinner showing that message
      3. Wait 1 second (simulating node execution time)

    After all nodes complete, clear the spinner and show a completion Panel.

    Args:
        node_names:       Ordered list of node names to animate through.
                          e.g. ["intake", "research", "draft", "cite", "review"]
        loading_messages: Dict of node_name → list of message strings.
                          Same structure as lexagent/data/loading_messages.yaml.

    Reference implementations:
      - lexagent/ui/live.py — LiveStatus class and task_start()/task_done()
      - 02_rich_live.py SECTION 5 — demo_pipeline_messages()
    """

    # TODO 1: Create a Live() context manager with refresh_per_second=10.
    #         Inside it, iterate over node_names.
    #         Use live.update(Spinner("dots", text=...)) for each node.
    #         Wait 1 second between nodes to simulate execution.
    #         Hint: transient=True clears the spinner when the with-block exits.
    pass  # replace this with your implementation

    # TODO 2: After the with-block exits (spinner cleared), print a completion
    #         Panel using console.print(Panel(...)).
    #         Include: a green ✓, the count of nodes run, and the text "complete".
    #         Hint: look at how 02_rich_live.py demo_pipeline_messages() does it.
    pass  # replace this with your implementation


def get_message(node_name: str, messages: dict) -> str:
    """
    Return a random message for node_name with a safe fallback.
    Already implemented — use this inside animate_graph_run().
    """
    # TODO 3: Implement this helper.
    #   - If node_name exists in messages, return random.choice(messages[node_name])
    #   - If node_name does NOT exist, return "Working..." as a fallback
    #   - Do NOT raise KeyError — new nodes may not have messages yet
    pass  # replace this with your implementation


# ── DRIVER ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    console.print()
    console.print(
        Panel(
            "[bold]Exercise 01 — Add a Live Spinner[/bold]\n"
            "[dim]Implement animate_graph_run() and get_message()[/dim]",
            border_style="blue",
        )
    )
    console.print()

    # Test 1: Full 5-node pipeline
    console.rule("[bold]Test 1 — Full pipeline[/bold]")
    animate_graph_run(
        node_names=["intake", "research", "draft", "cite", "review"],
        loading_messages=LOADING_MESSAGES,
    )

    console.print()

    # Test 2: Unknown node — should use fallback, not crash
    console.rule("[bold]Test 2 — Unknown node (fallback test)[/bold]")
    animate_graph_run(
        node_names=["rag_retrieval"],   # not in LOADING_MESSAGES
        loading_messages=LOADING_MESSAGES,
    )

    console.print()

    # Test 3: Single node
    console.rule("[bold]Test 3 — Single node[/bold]")
    animate_graph_run(
        node_names=["draft"],
        loading_messages=LOADING_MESSAGES,
    )

    console.print()


# ── REFLECTION QUESTIONS ──────────────────────────────────────────────────────
#
# Q1. LexAgent's LiveStatus in lexagent/ui/live.py does NOT use `with Live(...)`.
#     It stores a reference and manages the display manually.
#     Why might the LexAgent team have made this choice for an async pipeline?
#     What would break if you used `with Live(...)` across multiple `await` calls?
#
# Q2. In get_message(), you used messages.get(node_name) instead of
#     messages[node_name]. If a future developer adds a new graph node
#     "rag_retrieval" to lexagent/graph.py without adding it to
#     loading_messages.yaml, what does the user see? Is this acceptable?
#     What would be a better design to surface the missing key to the developer?
#
# Q3. The 1-second delay in animate_graph_run() is hard-coded.
#     In production LexAgent, the delay is the actual node execution time
#     (up to 60 seconds for a research call). How would you restructure
#     animate_graph_run() as an async context manager so the caller
#     controls when each node "completes"? Sketch the signature.
