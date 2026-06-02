"""
Phase 8 — UX & Output: 02_rich_live.py
=======================================
Rich Live display for animated progress during the LexAgent pipeline.

Install: pip install rich
Run:     python 02_rich_live.py
"""

import random
import time

# ── SECTION 1: THE PROBLEM WITH SEQUENTIAL PRINTS ────────────────────────────

# WRONG — each print() adds a new line. During a 45-second LLM call,
# the user sees a static screen with no feedback at all.
def wrong_way_no_animation():
    print("Researching...")
    time.sleep(2)   # LLM thinking... user sees nothing change
    print("Drafting...")
    time.sleep(2)
    print("Done.")

# RIGHT — Rich Live holds a region at the bottom of the terminal and lets
# you UPDATE it in place without scrolling. The user sees a spinner that
# changes text as each node completes — not silence.

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.spinner import Spinner

console = Console()


# ── SECTION 2: BASIC LIVE SPINNER ────────────────────────────────────────────

def demo_basic_spinner():
    console.rule("[bold]SECTION 2 — Basic Live Spinner[/bold]")

    # Live() takes any Rich renderable as its initial content.
    # refresh_per_second controls how often the display redraws.
    # transient=True clears the spinner when the `with` block exits —
    # so it doesn't leave a frozen spinner on screen.
    console.print("[dim]Starting spinner — watch the dots animate...[/dim]")
    console.print()

    with Live(
        Spinner("dots", text="[cyan]Researching Indian Kanoon...[/cyan]"),
        refresh_per_second=10,
        transient=True,
    ) as live:
        time.sleep(1.5)

        # live.update() replaces the displayed renderable mid-display.
        # This is the key method — you call it from inside each graph node.
        live.update(Spinner("dots", text="[cyan]Pulling Supreme Court judgments...[/cyan]"))
        time.sleep(1.5)

        live.update(Spinner("dots", text="[yellow]Drafting writ petition...[/yellow]"))
        time.sleep(1.5)

        live.update(Spinner("dots", text="[yellow]Verifying citations...[/yellow]"))
        time.sleep(1.5)

        live.update(Spinner("dots", text="[green]Running final review...[/green]"))
        time.sleep(1.0)

    # After the `with` block, transient=True cleared the spinner.
    # Now we print the completion message in its place.
    console.print("[green]✓[/green] Pipeline complete.")
    console.print()


# ── SECTION 3: SPINNER STYLES ─────────────────────────────────────────────────

def demo_spinner_styles():
    console.rule("[bold]SECTION 3 — Spinner Styles[/bold]")

    # Rich has 80+ spinner animations. LexAgent uses "dots" in lexagent/ui/live.py
    # because it renders well across macOS, Linux, and Windows terminals.
    styles = ["dots", "dots2", "line", "bouncingBall", "arc"]

    for style in styles:
        with Live(
            Spinner(style, text=f"[dim]spinner style: {style!r}[/dim]"),
            refresh_per_second=10,
            transient=True,
        ):
            time.sleep(1.2)
        console.print(f"  Showed spinner: [bold]{style}[/bold]")

    console.print()


# ── SECTION 4: LOADING_MESSAGES.YAML CONCEPT ─────────────────────────────────

# Hard-coded strings are brittle — a lawyer can't edit Python.
# WRONG: spinner text lives inline in node code.
def wrong_spinner_text():
    # Changing this message requires editing Python and redeploying.
    Spinner("dots", text="Researching...")

# RIGHT: messages live in lexagent/data/loading_messages.yaml.
# The YAML file maps node_name → list of messages.
# random.choice() picks a different message each run — adds personality.

# In production, LexAgent loads this YAML with:
#   import yaml, importlib.resources as pkg
#   with pkg.open_text("lexagent.data", "loading_messages.yaml") as f:
#       MESSAGES = yaml.safe_load(f)
# Here we inline the same structure for teaching purposes.

LOADING_MESSAGES = {
    "intake":   [
        "Analysing your brief...",
        "Reading your matter brief...",
        "Identifying matter type and parties...",
        "Lexatating...",
        "Raising objections internally...",
    ],
    "research": [
        "Searching Indian Kanoon for precedents...",
        "Pulling Supreme Court and High Court judgments...",
        "Reading 47 judgments so you don't have to...",
        "Negotiating with Indian Kanoon...",
        "Debating precedent...",
    ],
    "draft": [
        "Drafting your writ petition...",
        "Writing with verified citations...",
        "Drafting with extreme prejudice...",
        "Hereinafter referred to as 'almost done'...",
        "Lawyering...",
    ],
    "cite": [
        "Verifying citations against Indian Kanoon corpus...",
        "Cross-examining citations...",
        "Holding citations in contempt...",
    ],
    "review": [
        "Final review — checking length, citations, and structure...",
        "Quality check in progress...",
        "Your Honour, the draft is ready...",
    ],
}

def get_spinner_message(node_name: str) -> str:
    """
    Pick a random message for the given node.

    WHY random.choice: variety makes repeated runs feel less mechanical.
    A lawyer running LexAgent daily notices if the same phrase appears every time.
    The .get() fallback prevents a KeyError if a new node hasn't been added to the YAML yet.
    """
    messages = LOADING_MESSAGES.get(node_name, ["Working..."])
    return random.choice(messages)


# ── SECTION 5: CYCLING THROUGH PIPELINE MESSAGES ─────────────────────────────

def demo_pipeline_messages():
    console.rule("[bold]SECTION 5 — Pipeline Node Messages[/bold]")

    # This is what LexAgent's CLI does during a real draft run —
    # a single Live display that cycles through all 5 graph nodes.
    pipeline_nodes = ["intake", "research", "draft", "cite", "review"]

    console.print("[dim]Simulating a full LexAgent pipeline run...[/dim]")
    console.print()

    with Live(refresh_per_second=10, transient=True) as live:
        for node in pipeline_nodes:
            msg = get_spinner_message(node)
            live.update(Spinner("dots", text=f"[cyan]{msg}[/cyan]"))
            time.sleep(0.5)   # In real code: await for the node coroutine

            # Show a second message for longer nodes
            if node in ("research", "draft"):
                msg2 = get_spinner_message(node)
                live.update(Spinner("dots", text=f"[cyan]{msg2}[/cyan]"))
                time.sleep(0.5)

    # After the Live block exits, print the completion Panel
    console.print(
        Panel(
            "[green]✓ Draft complete[/green]\n\n"
            "  [bold]LEX-2024-047[/bold] — Writ Petition (Civil)\n"
            "  Sharma v. Union of India | Delhi High Court\n"
            "  [dim]2,847 words  |  8 citations verified  |  41.2s[/dim]",
            title="[bold]⚖ LexAgent — Complete[/bold]",
            border_style="green",
            padding=(1, 2),
        )
    )
    console.print()


# ── SECTION 6: LIVE WITH PANEL UPDATE ────────────────────────────────────────

def demo_live_panel_update():
    """
    Show how to update the Live display with a full Panel — not just a Spinner.
    Useful for showing elapsed time or node completion counts mid-run.
    """
    console.rule("[bold]SECTION 6 — Live Panel Updates[/bold]")

    nodes_done = []
    all_nodes = ["intake", "research", "draft", "cite", "review"]

    def make_status_panel(current: str, done: list) -> Panel:
        done_lines = "\n".join(f"  [green]✓[/green] {n}" for n in done)
        current_line = f"  [cyan]→[/cyan] [bold]{current}[/bold] [dim]running...[/dim]"
        body = (done_lines + "\n" + current_line).strip()
        return Panel(body, title="[bold]Pipeline Status[/bold]", border_style="cyan")

    console.print("[dim]Watch the panel update as each node completes...[/dim]")
    console.print()

    with Live(refresh_per_second=10, transient=True) as live:
        for node in all_nodes:
            live.update(make_status_panel(node, nodes_done))
            time.sleep(0.7)
            nodes_done.append(node)

        # Show final state briefly before exiting
        final_body = "\n".join(f"  [green]✓[/green] {n}" for n in nodes_done)
        live.update(Panel(final_body, title="[bold]All nodes complete[/bold]", border_style="green"))
        time.sleep(0.5)

    console.print("[green]✓[/green] All nodes complete.\n")


# ── MAIN ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    console.print()
    console.print(
        Panel(
            "[bold]Phase 8 — UX & Output[/bold]\n"
            "[dim]Rich Live display and animated spinners[/dim]",
            border_style="blue",
        )
    )
    console.print()

    demo_basic_spinner()
    demo_spinner_styles()
    demo_pipeline_messages()
    demo_live_panel_update()


# ── PAUSE AND THINK ──────────────────────────────────────────────────────────
#
# 1. Open lexagent/ui/live.py. LiveStatus does NOT use `with Live(...)`.
#    Instead it stores `self._live` and calls console.print() directly.
#    Why might the LexAgent team have avoided the context-manager form
#    for a long-running async pipeline? (Hint: asyncio + Live interactions.)
#
# 2. lexagent/data/loading_messages.yaml has messages with {placeholders}
#    like "Searching Indian Kanoon for {matter_type} precedents...".
#    If you wanted to fill these at runtime from LexState, where in the
#    LexAgent graph would you call str.format(**state) — in the node
#    function or in the UI layer? Why does it matter?
#
# 3. The demo uses `transient=True` on the Live display. Open
#    lexagent/ui/live.py and check whether LiveStatus uses transient.
#    What is the user-visible difference between transient=True and False
#    after the pipeline finishes?
#
# 4. `refresh_per_second=10` means Rich redraws the spinner 10 times per
#    second. What would break if you set this to 1? What would be wasteful
#    about setting it to 60 on a server without a real terminal?
#
# 5. The LOADING_MESSAGES dict above mirrors the structure of
#    lexagent/data/loading_messages.yaml. If you added a new graph node
#    called "rag_retrieval" to LexAgent, name the two files you would
#    edit and the exact YAML key you would add.
