"""
Phase 8 — UX & Output: 01_rich_basics.py
=========================================
Teach the Rich terminal library from scratch.

Install: pip install rich
Run:     python 01_rich_basics.py
"""

# ── SECTION 1: WHY RICH? ──────────────────────────────────────────────────────

# WRONG — bare print() is invisible noise in a real CLI app.
# It can't style, align, box, or update content in place.
def wrong_way():
    print("Researching matter...")
    print("Matter ID: LEX-001")
    print("Type:      writ")
    print("Status:    in_progress")

# RIGHT — Rich gives you colour, structure, and professional CLI output.
# LexAgent rule: NEVER use print(). ALWAYS use console.print().
# Rationale: Rich is already the standard in LexAgent's codebase (see lexagent/ui/live.py).

from rich.console import Console

# One Console instance per module — it tracks terminal width, colour support,
# and markup state. Sharing it avoids interleaved output on concurrent writes.
console = Console()

# ── SECTION 2: MARKUP STYLING ─────────────────────────────────────────────────

def demo_markup():
    console.rule("[bold]SECTION 2 — Markup Styling[/bold]")

    # Rich markup uses [tag]text[/tag] syntax — similar to BBCode.
    console.print("[bold blue]LexAgent[/bold blue] — Indian Legal AI")
    console.print("[bold red]ERROR:[/bold red] API key not found in environment")
    console.print("[green]✓[/green] Draft saved to [underline]/tmp/writ.docx[/underline]")
    console.print("[dim]matter_id: LEX-001  |  model: claude-sonnet-4[/dim]")

    # Nested styles work — bold AND italic AND colour
    console.print("[bold italic cyan]Drafting your petition...[/bold italic cyan]")

    # The [/] shorthand closes the last open tag
    console.print("[bold]Phase 8[/] — UX & Output")


# ── SECTION 3: PANEL — BOXED CONTENT ─────────────────────────────────────────

from rich.panel import Panel

def demo_panel():
    console.rule("[bold]SECTION 3 — Panel[/bold]")

    # A Panel wraps content in a Unicode box with an optional title and subtitle.
    # LexAgent uses Panel in LiveStatus.announce_strategy() (lexagent/ui/live.py:63)
    # to display the agent's strategy before the pipeline starts.
    console.print(
        Panel(
            "[bold cyan]S.138 NI Act — Cheque Dishonour\n"
            "Demand notice → criminal complaint → Magistrate hearing[/bold cyan]",
            title="[bold]⚖ LexAgent — LEX-001[/bold]",
            subtitle="[dim]Research → Draft → Cite → Review[/dim]",
            border_style="cyan",
            padding=(1, 2),  # (vertical, horizontal) padding inside the box
        )
    )

    # border_style controls the box colour. Common choices:
    #   "blue", "cyan", "green", "red", "yellow", "dim"
    console.print(
        Panel(
            "[green]✓ Draft complete — 2,847 words[/green]",
            title="Status",
            border_style="green",
        )
    )


# ── SECTION 4: TABLE — STRUCTURED DATA ───────────────────────────────────────

from rich.table import Table

def demo_table():
    console.rule("[bold]SECTION 4 — Table[/bold]")

    # Tables auto-size columns to fit their content.
    table = Table(title="Matter Summary", border_style="blue", show_lines=False)

    # add_column(header, style, justify)
    # justify options: "left" (default), "center", "right"
    table.add_column("Field", style="bold cyan", justify="right")
    table.add_column("Value", style="white")

    # add_row(*values) — one string per column, markup supported
    table.add_row("Matter ID",   "LEX-001")
    table.add_row("Type",        "Writ Petition (Civil)")
    table.add_row("Parties",     "Sharma v. Union of India")
    table.add_row("Jurisdiction","Delhi High Court")
    table.add_row("Status",      "[green]Draft Complete[/green]")
    table.add_row("Citations",   "[yellow]3 unverified[/yellow]")

    console.print(table)


# ── SECTION 5: RULE — DIVIDER LINE ───────────────────────────────────────────

def demo_rule():
    console.rule("[bold]SECTION 5 — Rule (Divider)[/bold]")

    # console.rule() draws a horizontal line spanning the full terminal width.
    # LexAgent uses it in LiveStatus.begin_streaming() (lexagent/ui/live.py:89)
    # as a visual separator before draft tokens start streaming.
    console.rule("[bold cyan]Drafting[/bold cyan]", style="cyan")
    console.print("[dim]... draft tokens would appear here ...[/dim]")
    console.rule("[bold green]Complete[/bold green]", style="green")


# ── SECTION 6: LIVE DEMO — MATTER SUMMARY PANEL ──────────────────────────────

def demo_matter_summary():
    """
    Build a realistic matter summary Panel containing a Table.
    This is what LexAgent displays at the start of each draft run.
    """
    console.rule("[bold]SECTION 6 — Live Demo: Matter Summary[/bold]")

    # Inner table — matter fields
    inner_table = Table(show_header=False, box=None, padding=(0, 1))
    inner_table.add_column("field", style="bold dim")
    inner_table.add_column("value")

    inner_table.add_row("Matter ID   :", "[bold]LEX-2024-047[/bold]")
    inner_table.add_row("Type        :", "Writ Petition (Civil) — Art. 226")
    inner_table.add_row("Parties     :", "Ravi Kumar v. State of Delhi")
    inner_table.add_row("Jurisdiction:", "Delhi High Court")
    inner_table.add_row("Status      :", "[bold green]Drafting in progress...[/bold green]")

    # Outer Panel wraps the table — gives it a title and border
    matter_panel = Panel(
        inner_table,
        title="[bold]⚖ LexAgent — New Matter[/bold]",
        subtitle="[dim]Strategy: File writ petition challenging administrative order[/dim]",
        border_style="cyan",
        padding=(1, 2),
    )

    console.print()
    console.print(matter_panel)
    console.print()
    console.print(
        "[dim]Tip: This panel is generated by LiveStatus.announce_strategy() "
        "in lexagent/ui/live.py[/dim]"
    )


# ── MAIN ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    console.print()
    console.print(
        Panel(
            "[bold]Phase 8 — UX & Output[/bold]\n"
            "[dim]Rich terminal library basics[/dim]",
            border_style="blue",
        )
    )
    console.print()

    demo_markup()
    console.print()

    demo_panel()
    console.print()

    demo_table()
    console.print()

    demo_rule()
    console.print()

    demo_matter_summary()
    console.print()


# ── PAUSE AND THINK ──────────────────────────────────────────────────────────
#
# 1. Open lexagent/ui/live.py. LiveStatus.task_done() uses console.print() with
#    inline markup. Why does it NOT use a Table row for each completed task?
#    Hint: think about scrolling vs. fixed-region display.
#
# 2. In lexagent/ui/live.py:89, LiveStatus.begin_streaming() calls
#    console.rule("[bold cyan]Drafting[/bold cyan]", style="cyan").
#    What does the `style` parameter control vs. the markup inside the string?
#
# 3. LexAgent uses `Console()` at module level in live.py (line 31). Why is a
#    module-level Console better than creating `Console()` inside each function?
#
# 4. The matter summary Panel uses `show_header=False, box=None` on the inner
#    Table. What visual effect does removing the box have, and why is it better
#    inside a Panel?
#
# 5. If you added a "Lawyer" row to the matter summary Table that reads the
#    lawyer's name from ~/.lexagent/SOUL.md, which LexAgent file would you
#    edit — and which key in LexState would you read from?
#    (Hint: check lexagent/state.py for the `lawyer_soul` field.)
