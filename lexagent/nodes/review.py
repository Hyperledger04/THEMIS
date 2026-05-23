# Review node: validation gate that runs after cite, before .docx output.
#
# Checks:
#   1. All citations are grounded (no unverified_citations)
#   2. Draft length is within jurisdiction-appropriate limits
#   3. If --output was requested, calls docx_writer and sets docx_path in state
#
# The review node never raises — all errors go to state["error"].

from rich.console import Console

from lexagent.state import LexState

console = Console()

# WHY: Rough word-count limits by document type.
# These are practical guidance, not hard legal maxima.
_WORD_LIMITS: dict[str, int] = {
    "injunction": 5000,
    "writ petition": 8000,
    "legal notice": 2000,
    "plaint": 10000,
    "written statement": 10000,
    "affidavit": 3000,
    "vakalatnama": 500,
}
_DEFAULT_WORD_LIMIT = 12000


def _word_count(text: str) -> int:
    return len(text.split())


def _jurisdiction_limit(matter_type: str | None) -> int:
    if not matter_type:
        return _DEFAULT_WORD_LIMIT
    key = matter_type.lower().strip()
    for known, limit in _WORD_LIMITS.items():
        if known in key:
            return limit
    return _DEFAULT_WORD_LIMIT


async def run(state: LexState) -> dict:
    try:
        draft = state.get("draft_output") or ""
        unverified = state.get("unverified_citations") or []
        grounded = state.get("grounded_citations") or []
        matter_type = state.get("matter_type")
        docx_output_path: str | None = state.get("docx_path")

        issues: list[str] = []

        # Check 1: all citations grounded
        if unverified:
            issues.append(
                f"{len(unverified)} citation(s) could not be grounded: "
                + ", ".join(unverified[:3])
                + (" ..." if len(unverified) > 3 else "")
            )

        # Check 2: draft length within limit
        limit = _jurisdiction_limit(matter_type)
        wc = _word_count(draft)
        if wc > limit:
            issues.append(
                f"Draft is {wc} words — exceeds {matter_type or 'document'} "
                f"guidance of {limit} words"
            )

        # Check 3: draft is not empty
        if not draft.strip():
            issues.append("Draft output is empty")

        if issues:
            for issue in issues:
                console.print(f"[yellow]⚠ Review:[/yellow] {issue}")
        else:
            console.print("[green]✓ Review:[/green] All checks passed")

        # Generate .docx if a path was requested (--output flag in CLI)
        # WHY run_in_executor: write_docx does synchronous disk I/O (python-docx).
        # Running it in the default ThreadPoolExecutor keeps the asyncio event loop
        # unblocked — critical for serving concurrent Telegram users.
        docx_path_out: str | None = None
        if docx_output_path and draft.strip():
            import asyncio
            from lexagent.tools.docx_writer import write_docx
            loop = asyncio.get_event_loop()
            docx_path_out = await loop.run_in_executor(None, write_docx, state, docx_output_path)
            console.print(f"[bold green]✓ Draft saved to:[/bold green] {docx_path_out}")

        return {
            "docx_path": docx_path_out,
            # Re-surface issues as a risk annotation so the CLI can show them
            "risk_annotations": [{"clause": "review", "risk_level": "M", "note": i} for i in issues] if issues else None,
        }

    except Exception as e:
        return {"error": str(e)}
