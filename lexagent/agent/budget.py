"""
IterationBudget — guards the LexAgentLoop from infinite tool-call cycles.

WHY: Inspired by Hermes Agent's budget system. Without a hard cap, a tool-calling
loop can spin indefinitely if the LLM keeps asking for tools. The budget tracks:
  - iterations (each LLM call → tool call → LLM call counts as one cycle)
  - cost in USD (approximated from token counts)
  - elapsed wall-clock time

Any limit breach stops the loop and returns whatever the agent has so far.
"""

import time
from dataclasses import dataclass, field


@dataclass
class IterationBudget:
    max_iter: int = 10
    max_cost_usd: float = 0.50
    max_seconds: float = 120.0

    _iterations: int = field(default=0, init=False, repr=False)
    _cost_usd: float = field(default=0.0, init=False, repr=False)
    _start: float = field(default_factory=time.monotonic, init=False, repr=False)

    def tick(self, input_tokens: int = 0, output_tokens: int = 0) -> None:
        """Record one completed iteration with token usage."""
        self._iterations += 1
        # Rough cost estimate: $3/M input + $15/M output (claude-sonnet tier)
        self._cost_usd += (input_tokens * 3 + output_tokens * 15) / 1_000_000

    @property
    def exhausted(self) -> bool:
        """Return True if any limit has been hit."""
        if self._iterations >= self.max_iter:
            return True
        if self._cost_usd >= self.max_cost_usd:
            return True
        if time.monotonic() - self._start >= self.max_seconds:
            return True
        return False

    @property
    def reason(self) -> str | None:
        """Return the reason the budget was exhausted, or None if still running."""
        if self._iterations >= self.max_iter:
            return f"max iterations ({self.max_iter}) reached"
        if self._cost_usd >= self.max_cost_usd:
            return f"cost limit (${self.max_cost_usd:.2f}) reached"
        elapsed = time.monotonic() - self._start
        if elapsed >= self.max_seconds:
            return f"time limit ({self.max_seconds:.0f}s) reached"
        return None

    @property
    def iterations(self) -> int:
        return self._iterations

    @property
    def cost_usd(self) -> float:
        return self._cost_usd
