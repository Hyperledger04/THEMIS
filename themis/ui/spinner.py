# WHY: A single place for all CLI animation logic.
# The spinner runs as an asyncio background task while a graph node is executing.
# Because graph.astream() yields only AFTER a node finishes, we can't know mid-node
# progress — but we CAN cycle funny lawyer phrases to keep the lawyer entertained.

from __future__ import annotations

import asyncio
import random
from typing import Optional

# ---------------------------------------------------------------------------
# Phrase pools — one per graph phase
# ---------------------------------------------------------------------------

_PHRASES: dict[str, list[str]] = {
    "starting": [
        "⚖  analyzing your brief...",
        "⚖  reading between the lines...",
        "⚖  thinking like a senior advocate...",
        "⚖  putting on the wig...",
        "⚖  calling the matter to order...",
    ],
    "intake": [
        "📋  lexatating...",
        "📋  extracting the facts like a cross-examination...",
        "📋  identifying parties, jurisdiction, and tea preference...",
        "📋  reading your brief very carefully indeed...",
        "📋  raising objections internally...",
        "📋  drafting the clarifying questions (objection overruled)...",
    ],
    "research": [
        "🔍  negotiating with Indian Kanoon...",
        "🔍  arguing with databases...",
        "🔍  reading 47 judgments so you don't have to...",
        "🔍  finding loopholes (legally)...",
        "🔍  debating precedent with Blackstone...",
        "🔍  distinguishing your case from every bad judgment ever...",
        "🔍  the research is now in recess...",
        "🔍  cross-examining the corpus juris...",
        "🔍  lexatating intensifies...",
        "🔍  summoning the ghosts of Chief Justices past...",
        "🔍  the citation is in the building...",
    ],
    "draft": [
        "✍  drafting with extreme prejudice...",
        "✍  objecting to bad sentence structure...",
        "✍  channeling decades of judicial wisdom...",
        "✍  arguing with the keyboard...",
        "✍  hereinafter referred to as 'almost done'...",
        "✍  lawyering...",
        "✍  the draft is in contempt of being slow...",
        "✍  composing the petition (objection: overruled)...",
        "✍  writing like Nani Palkhivala would approve...",
        "✍  the matter stands adjourned for drafting...",
        "✍  citing cases you've never heard of (but they're real)...",
    ],
    "cite": [
        "📌  cross-examining citations...",
        "📌  holding citations in contempt...",
        "📌  verifying evidence beyond reasonable doubt...",
        "📌  the citation has taken the stand...",
        "📌  objection: citation not found. Sustained. Checking again...",
        "📌  grounding precedents in actual precedent...",
    ],
    "review": [
        "✅  your Honour, the draft is ready...",
        "✅  final arguments in progress...",
        "✅  the ayes have it...",
        "✅  checking that the court fee is correct (it never is)...",
        "✅  the bench is satisfied. Almost.",
        "✅  quality control: did we win? Yes. Probably.",
    ],
}

_DEFAULT_INTERVAL = 2.8  # seconds between phrase changes


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


class LexAnimator:
    """
    Runs a background asyncio task that cycles funny lawyer phrases
    through a Rich status spinner while a node executes.

    Usage:
        with console.status("...") as status:
            anim = LexAnimator(status, phase="starting")
            anim.start()
            # ... do async work ...
            anim.set_phase("research")
            # ... more work ...
            anim.stop()
    """

    def __init__(self, status, phase: str = "starting", interval: float = _DEFAULT_INTERVAL):
        self._status = status
        self._phase = phase
        self._interval = interval
        self._task: Optional[asyncio.Task] = None
        self._seen: set[str] = set()

    def set_phase(self, phase: str) -> None:
        self._phase = phase
        self._seen.clear()

    def start(self) -> None:
        self._task = asyncio.create_task(self._loop())

    def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
        self._task = None

    async def _loop(self) -> None:
        while True:
            pool = _PHRASES.get(self._phase, _PHRASES["starting"])
            # Shuffle through unseen phrases before repeating
            unseen = [p for p in pool if p not in self._seen]
            if not unseen:
                self._seen.clear()
                unseen = pool[:]
            phrase = random.choice(unseen)
            self._seen.add(phrase)
            try:
                self._status.update(phrase)
            except Exception:
                pass
            try:
                await asyncio.sleep(self._interval)
            except asyncio.CancelledError:
                return


def pick(phase: str) -> str:
    """Return a single random phrase for a phase (for one-shot use)."""
    pool = _PHRASES.get(phase, _PHRASES["starting"])
    return random.choice(pool)
