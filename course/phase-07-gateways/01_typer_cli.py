"""
Phase 7, Lesson 1: Typer CLI — Making LexAgent Accessible from the Terminal
# pip install typer
"""
# ── SECTION 1: The problem ─────────────────────────────────────────────────────
print("=" * 60)
print("Typer CLI — from function to command")
print("=" * 60)
print("""
  Without a CLI:
    python -c "import asyncio; from lexagent.cli import _run_draft; asyncio.run(_run_draft(...))"

  With Typer:
    lex draft "I need a writ petition challenging an illegal demolition order"

  Typer reads Python type annotations and builds the argument parser automatically.
  No argparse boilerplate. No manual --help writing.
""")

# ── SECTION 2: Basic Typer app ─────────────────────────────────────────────────
try:
    import typer
except ImportError:
    print("Install typer: pip install typer")
    raise SystemExit(1)

import asyncio
from typing import Optional
from pathlib import Path

app = typer.Typer(name="lex", help="LexAgent — AI legal assistant for Indian litigation")

# ── SECTION 3: Commands ────────────────────────────────────────────────────────
@app.command()
def draft(
    matter: str = typer.Argument(..., help="Your matter brief in plain English"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Save draft as .docx"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show debug output"),
):
    """Draft a court-ready document from your matter brief."""
    typer.echo(f"[LexAgent] Processing matter: {matter[:60]}...")
    if verbose:
        typer.echo("[debug] Loading config, building graph...")
    # The async bridge: Typer is sync; graph is async
    asyncio.run(_run_draft(matter, output, verbose))


@app.command()
def search(
    query: str = typer.Argument(..., help="Legal search query"),
    limit: int = typer.Option(5, "--limit", "-n", help="Number of results"),
):
    """Search Indian Kanoon case law."""
    typer.echo(f"[LexAgent] Searching: {query} (top {limit})")
    # Stub results for demo
    cases = [
        ("Maneka Gandhi v. Union of India", "AIR 1978 SC 597"),
        ("Kesavananda Bharati v. Kerala", "AIR 1973 SC 1461"),
    ]
    for title, citation in cases[:limit]:
        typer.echo(f"  • {title} — {citation}")


@app.command()
def setup():
    """First-run wizard: create your SOUL.md profile."""
    typer.echo("[LexAgent] Setup wizard")
    name = typer.prompt("Your name")
    bar = typer.prompt("Bar Council enrollment number")
    typer.echo(f"[LexAgent] Creating SOUL.md for {name} ({bar})...")
    typer.echo(typer.style("✓ Setup complete", fg=typer.colors.GREEN))


# ── SECTION 4: Async bridge ────────────────────────────────────────────────────
async def _run_draft(matter: str, output: Optional[Path], verbose: bool):
    """The actual async work — what the CLI calls via asyncio.run()."""
    # In production: graph.astream(initial_state, config)
    # Here: stub that simulates graph execution
    if verbose:
        typer.echo("[intake] matter_type=writ_petition")
        typer.echo("[research] searching Indian Kanoon...")
        typer.echo("[draft] generating draft...")

    fake_draft = (
        "IN THE HIGH COURT OF DELHI AT NEW DELHI\n\n"
        f"WRIT PETITION (CIVIL) NO. ___/2024\n\n"
        f"In the matter of:\n{matter[:30]}...\n\n"
        "MOST RESPECTFULLY SHOWETH:\n"
        "1. That the petitioner is aggrieved by..."
    )
    typer.echo("\n" + "─" * 50)
    typer.echo(fake_draft)
    typer.echo("─" * 50)

    if output:
        output.write_text(fake_draft)
        typer.echo(typer.style(f"\n✓ Saved to {output}", fg=typer.colors.GREEN))


# ── SECTION 5: Sub-apps (LexAgent has 6) ──────────────────────────────────────
# LexAgent's cli.py has 6 sub-typers:
# app.add_typer(matter_app, name="matter")   → lex matter list
# app.add_typer(agent_app, name="agent")     → lex agent create
# app.add_typer(config_app, name="config")   → lex config show
# app.add_typer(contract_app, name="contract") → lex contract review
# etc.

print("── Running demo commands ──\n")
print("Simulating: lex draft 'I need a writ petition' --verbose")
print("─" * 50)

# Simulate running a command programmatically (for demo without subprocess)
from typer.testing import CliRunner
runner = CliRunner()

result = runner.invoke(app, ["draft", "I need a writ petition against illegal demolition", "--verbose"])
print(result.output)

result2 = runner.invoke(app, ["search", "article 21 personal liberty", "--limit", "2"])
print("Simulating: lex search 'article 21 personal liberty' --limit 2")
print(result2.output)

# ── PAUSE AND THINK ───────────────────────────────────────────────────────────
print("── PAUSE AND THINK ──")
print("""
  1. Open lexagent/cli.py — it's 2275 lines. How many sub-typers does it have?
     Run `grep -n "add_typer" lexagent/cli.py` to find them all.

  2. Every CLI command calls asyncio.run(). Why can't Typer call async functions
     directly? What happens if you have nested asyncio.run() calls?

  3. The CliRunner in tests is from typer.testing. Open the LexAgent test files
     and find where CliRunner is used. What commands are tested?

  4. LexAgent has a 180-second timeout on graph runs. Where in cli.py is this set?
     Hint: search for "timeout" in lexagent/cli.py.

  5. The `setup` command calls typer.prompt() for interactive input. How does
     the Telegram gateway handle the same setup flow without a terminal?
""")
