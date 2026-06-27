"""
Grid analysis node (doc-haus pattern).

Runs a fixed question list across every document in the matter workspace
in parallel: {question: {doc_name: answer}}.

WHY asyncio.gather: each (question, doc) pair is an independent LLM call;
parallel cuts latency from O(Q×D) to O(max_single_call_latency).
WHY error-per-cell: one bad document must not abort the entire grid run.
WHY _list_matter_docs is a standalone function: Phase 4 will swap it for a
workspace.repository.list_documents(matter_id) call with no node changes.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from themis.config import LexConfig
from themis.state import SeniorCounselState


def _list_matter_docs(matter_id: str) -> list[str]:
    cfg = LexConfig()
    matter_dir = Path(cfg.matters_dir).expanduser() / matter_id / "docs"
    if not matter_dir.exists():
        return []
    return [
        str(p) for p in matter_dir.iterdir()
        if p.suffix.lower() in {".pdf", ".docx", ".txt"}
    ]


async def _run_qa(question: str, doc_path: str, state: SeniorCounselState) -> dict:
    from themis.nodes.document_qa import run as qa_run
    return await qa_run({**state, "qa_question": question, "qa_document_path": doc_path})


async def run(state: SeniorCounselState) -> dict:
    questions: list[str] = state.get("grid_questions") or []
    if not questions:
        return {}
    matter_id = state.get("matter_id") or ""
    docs = _list_matter_docs(matter_id)
    if not docs:
        return {"grid_results": {q: {} for q in questions}}

    async def _cell(question: str, doc: str) -> tuple[str, str, str]:
        doc_name = Path(doc).name
        try:
            r = await _run_qa(question, doc, state)
            return question, doc_name, r.get("qa_answer") or ""
        except Exception as exc:
            return question, doc_name, f"[error: {exc}]"

    cells = await asyncio.gather(*[_cell(q, d) for q in questions for d in docs])
    grid: dict[str, dict[str, str]] = {q: {} for q in questions}
    for question, doc_name, answer in cells:
        grid[question][doc_name] = answer
    return {"grid_results": grid}
