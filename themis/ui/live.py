"""
LiveStatus — Rich Live display for the Themis pipeline.

Replaces the silent 90-second spinner with a Hermes-style running commentary:
  - Strategy announcement (1 cheap LLM call before the pipeline starts)
  - Per-task progress lines with elapsed time
  - Streaming draft tokens written word-by-word
  - Status bar: model | matter ID | elapsed | token count

Usage:
    async with LiveStatus(matter_id, model_str) as live:
        await live.announce_strategy("S.138 demand notice, 30-day limitation period")
        live.task_start(1, 3, "Searching Kanoon for cheque dishonour cases")
        live.task_done(1, 3, "8 cases", elapsed=2.1)
        live.begin_streaming()
        live.stream_token("LEGAL NOTICE")
"""

import asyncio
import time
from contextlib import asynccontextmanager
from typing import Optional

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

console = Console()


class LiveStatus:
    """
    Context manager that wraps Rich Live to display agent activity.

    WHY not just print(): Rich Live lets us update a fixed region at the bottom
    (status bar, task list) while also appending new lines above it — giving the
    feel of a live terminal dashboard rather than a scrolling log.
    """

    def __init__(self, matter_id: str, model_str: str) -> None:
        self._matter_id = matter_id
        self._model_str = model_str
        self._start = time.monotonic()
        self._token_count = 0
        self._lines: list[str] = []
        self._strategy: str = ""
        self._streaming = False
        self._draft_tokens: list[str] = []
        self._live: Optional[Live] = None
        self._console = Console()

    # ----------------------------------------------------------------
    # Public API — called by nodes and chat.py
    # ----------------------------------------------------------------

    async def announce_strategy(self, strategy: str) -> None:
        """Display the agent's strategy before the pipeline starts."""
        self._strategy = strategy
        self._console.print()
        self._console.print(
            Panel(
                f"[bold cyan]{strategy}[/bold cyan]",
                title=f"[bold]⚖ Themis — {self._matter_id}[/bold]",
                border_style="cyan",
                padding=(0, 2),
            )
        )

    def task_start(self, idx: int, total: int, description: str) -> None:
        """Announce a task starting (fires immediately, no elapsed yet)."""
        self._console.print(
            f"  [[bold cyan]{idx}/{total}[/bold cyan]] {description}[dim]...[/dim]"
        )

    def task_done(self, idx: int, total: int, result: str, elapsed: float) -> None:
        """Mark a task completed with elapsed time."""
        self._console.print(
            f"  [[bold cyan]{idx}/{total}[/bold cyan]] "
            f"[green]✓[/green] {result} [dim]({elapsed:.1f}s)[/dim]"
        )

    def begin_streaming(self) -> None:
        """Print the drafting header before tokens start flowing."""
        self._streaming = True
        self._console.print()
        self._console.print(Rule("[bold cyan]Drafting[/bold cyan]", style="cyan"))
        self._console.print()

    def stream_token(self, token: str) -> None:
        """Write one token to the console (called by stream_cb in call_llm)."""
        self._token_count += len(token.split())
        self._console.print(token, end="", markup=False, highlight=False)

    def finish(self) -> None:
        """Print the status footer after the pipeline completes."""
        elapsed = time.monotonic() - self._start
        self._console.print()
        self._console.print()
        self._console.print(
            f"[dim]{self._model_str} | {self._matter_id} | "
            f"{elapsed:.1f}s | ~{self._token_count} words[/dim]"
        )

    # ----------------------------------------------------------------
    # Context manager
    # ----------------------------------------------------------------

    async def __aenter__(self) -> "LiveStatus":
        return self

    async def __aexit__(self, *_) -> None:
        self.finish()
