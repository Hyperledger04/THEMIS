"""
Phase 7 — Exercise 1: Add a `lex research` CLI Command
# pip install typer
"""
import asyncio
from typing import Optional

try:
    import typer
    from typer.testing import CliRunner
except ImportError:
    print("Install typer: pip install typer")
    raise SystemExit(1)

app = typer.Typer(name="lex", help="LexAgent — AI legal assistant")


def stub_search(query: str, limit: int) -> list[dict]:
    """Stub — returns fake Indian Kanoon results. Do not modify."""
    all_cases = [
        {"title": "Maneka Gandhi v. Union of India", "citation": "AIR 1978 SC 597",
         "snippet": "Article 21 personal liberty includes right to travel abroad..."},
        {"title": "Kesavananda Bharati v. State of Kerala", "citation": "AIR 1973 SC 1461",
         "snippet": "Basic structure of the Constitution cannot be amended..."},
        {"title": "A.K. Gopalan v. State of Madras", "citation": "AIR 1950 SC 27",
         "snippet": "Preventive detention and the scope of Article 21..."},
        {"title": "Olga Tellis v. Bombay Municipal Corporation", "citation": "1985 SCC 545",
         "snippet": "Right to livelihood is part of right to life under Article 21..."},
    ]
    return all_cases[:limit]


# ── TODO 1: Add a "research" command ──────────────────────────────────────────
# The command should:
#   - Accept a required "query" argument (the search query string)
#   - Accept an optional "--limit" / "-n" option with default value 3
#   - Call asyncio.run(_run_research(query, limit))
#
# Example usage:
#   lex research "article 21 right to life" --limit 2

# TODO: write the @app.command() decorated function here


# ── TODO 2: Add an async _run_research function ────────────────────────────────
# The function should:
#   - Print a "Searching..." message
#   - Call stub_search(query, limit) to get results
#   - Print each result as: "  • Title — Citation\n    Snippet..."
#
# Example output:
#   Searching Indian Kanoon for: 'article 21 right to life'
#   Found 2 results:
#   • Maneka Gandhi v. Union of India — AIR 1978 SC 597
#     Article 21 personal liberty includes right to travel abroad...

# TODO: write the async def _run_research function here


# ── TODO 3: Add a second command "matter list" using a sub-app ─────────────────
# Create a matter_app = typer.Typer() and add it to app with name="matter"
# The "list" command should print: "Matters: [no matters yet]"
#
# Example usage: lex matter list

# TODO: create matter_app and add a list command


# ── TESTS ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    runner = CliRunner()

    # Test research command
    result = runner.invoke(app, ["research", "article 21 right to life", "--limit", "2"])
    assert result.exit_code == 0, f"Command failed: {result.output}"
    assert "Maneka Gandhi" in result.output, "Should show Maneka Gandhi in results"
    assert "AIR 1978 SC 597" in result.output, "Should show citation"
    print("✓ research command works:")
    print(result.output)

    # Test --limit flag
    result2 = runner.invoke(app, ["research", "article 21", "--limit", "1"])
    assert result2.exit_code == 0
    output_lines = [l for l in result2.output.split("\n") if "•" in l]
    assert len(output_lines) == 1, f"Expected 1 result with --limit 1, got {len(output_lines)}"
    print("✓ --limit flag works")

    print("\n✅ All tests passed!")

# ── PAUSE AND THINK ───────────────────────────────────────────────────────────
# 1. Open lexagent/cli.py — find the actual `research` command.
#    How does it differ? Does it use stub_search or call the real Kanoon tool?
# 2. The CliRunner in tests doesn't actually run a subprocess — it invokes the
#    Typer app in-process. What's the advantage of this over subprocess testing?
# 3. Your research command is synchronous (asyncio.run). What happens if
#    _run_research raises an exception? Does the CLI show a clean error or a traceback?
