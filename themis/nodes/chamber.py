"""
Adversarial multi-agent review chamber (doc-haus pattern).

Three sequential LLM calls:
  1. Reviewer   — finds issues in the draft
  2. Challenger — rebuts the reviewer's findings
  3. Summarizer — synthesises both into actionable final review

WHY sequential: Challenger must see Reviewer output; Summarizer must see both.
WHY this node instead of full chamber agents: full subagent contracts require
Phase 7 planner DAGs; this node is the bridge that ships now and is replaced
in Phase 11 with identical external interface.
"""
from __future__ import annotations
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from themis.config import LexConfig
from themis.state import LexState


class _LLMWrapper:
    """
    Thin wrapper that adapts call_llm (function) to the object.ainvoke(prompt)
    interface used by the tests and this node.

    WHY: _llm.py exposes call_llm() as a plain async function, not a class.
    The tests patch _get_llm() to return a mock object with .ainvoke — so this
    wrapper unifies both worlds without changing the _llm.py contract.
    """

    def __init__(self, cfg: LexConfig) -> None:
        self._cfg = cfg

    async def ainvoke(self, prompt: str) -> Any:
        from themis.nodes._llm import call_llm
        result = await call_llm(
            messages=[{"role": "user", "content": prompt}],
            cfg=self._cfg,
        )
        # Return an object with a .content attribute so callers can do msg.content
        return SimpleNamespace(content=result["content"])


def _get_llm() -> _LLMWrapper:
    """
    Return an LLM wrapper for the chamber node.

    WHY a separate function: tests patch themis.nodes.chamber._get_llm to inject
    a mock, keeping LiteLLM calls out of unit tests entirely.
    """
    cfg = LexConfig()
    return _LLMWrapper(cfg)


def _load_prompt(name: str, **kwargs) -> str:
    p = Path(__file__).parent.parent / "prompts" / f"{name}.txt"
    return p.read_text().format(**kwargs)


async def run(state: LexState) -> dict:
    # Early exit: chamber is opt-in. When disabled, this node is a transparent pass-through.
    if not state.get("chamber_enabled"):
        return {}

    draft = state.get("draft_output") or ""

    try:
        llm = _get_llm()

        # Step 1 — Reviewer: identify every material weakness in the draft
        issues_msg = await llm.ainvoke(_load_prompt(
            "chamber_reviewer",
            draft_output=draft,
            active_skill=state.get("active_skill") or "",
            jurisdiction=state.get("jurisdiction") or "",
            matter_type=state.get("matter_type") or "",
        ))
        issues = issues_msg.content

        # Step 2 — Challenger: rebut the reviewer's findings
        pushback_msg = await llm.ainvoke(_load_prompt(
            "chamber_challenger",
            chamber_issues=issues,
            draft_output=draft,
        ))
        pushback = pushback_msg.content

        # Step 3 — Summarizer: synthesise into final review with action items + risk level
        final_msg = await llm.ainvoke(_load_prompt(
            "chamber_summarizer",
            chamber_issues=issues,
            chamber_pushback=pushback,
            draft_output=draft,
        ))
        final_review = final_msg.content

        return {
            "chamber_issues": issues,
            "chamber_pushback": pushback,
            "chamber_review": final_review,
        }

    except Exception as exc:
        return {"error": f"chamber: {exc}"}
