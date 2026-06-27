"""
Phase 10 — 08: Cross-Document Grid Analysis
============================================
Run:  pip install pydantic
      python 08_grid_analysis.py

The problem: due diligence on a bundle of contracts is tedious because
every question must be asked about every document one at a time. Ask
"what is the notice period?" of 40 NDAs and you make 40 separate queries,
wait for each, then assemble the answers manually.

The insight: each (question, document) pair is independent — there is no
shared state between them. That means they can all run in parallel using
asyncio.gather. The result is a matrix:

  {
    "What is the notice period?": {
        "nda_google.pdf":   "30 days",
        "nda_microsoft.pdf": "60 days",
        "nda_acme.pdf":      "90 days",
    },
    "Who bears indemnity?": { ... }
  }

This is the doc-haus grid pattern. Real code: themis/nodes/grid.py
CLI: lex grid my-matter -q "What is the notice period?" --csv out.csv
"""

from __future__ import annotations
import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

print("=" * 60)
print("PART 1: The sequential vs. parallel problem")
print("=" * 60)

# Simulate sequential QA
QUESTIONS = [
    "What is the notice period?",
    "Who bears indemnity?",
    "What is the governing law?",
]
DOCS = ["nda_alpha.pdf", "nda_beta.pdf", "nda_gamma.pdf", "nda_delta.pdf"]

print(f"\n{len(QUESTIONS)} questions × {len(DOCS)} documents = {len(QUESTIONS) * len(DOCS)} LLM calls")
print(f"If each call takes 2 seconds:")
print(f"  Sequential: {len(QUESTIONS) * len(DOCS) * 2}s")
print(f"  Parallel:   ~2s  (bottleneck = slowest single call)")
print("\nWith asyncio.gather, all 12 calls fire simultaneously.")
print("The total time ≈ the time of the single slowest call.")

# ---------------------------------------------------------------------------
# Pause and think:
# ---------------------------------------------------------------------------
# Q: Can we always parallelize LLM calls like this?
#
# A: Only when they are independent — no call depends on the output of
#    another. In the chamber (lesson 7), calls are sequential because the
#    Challenger needs the Reviewer's output. Here, each (question, doc) pair
#    is entirely self-contained. Recognizing independence is the key to
#    knowing when to use gather vs. await in sequence.

# ---------------------------------------------------------------------------
# Section 2: asyncio.gather in detail
# ---------------------------------------------------------------------------
print("\n" + "=" * 60)
print("PART 2: asyncio.gather — parallel coroutines")
print("=" * 60)


async def fake_qa(question: str, doc: str, delay: float = 0.1) -> tuple[str, str, str]:
    """Simulates an LLM QA call with a short delay."""
    await asyncio.sleep(delay)
    answers = {
        ("What is the notice period?", "nda_alpha.pdf"): "30 days",
        ("What is the notice period?", "nda_beta.pdf"): "60 days",
        ("What is the notice period?", "nda_gamma.pdf"): "90 days",
        ("What is the notice period?", "nda_delta.pdf"): "Not specified",
        ("Who bears indemnity?", "nda_alpha.pdf"): "Each party indemnifies the other",
        ("Who bears indemnity?", "nda_beta.pdf"): "Disclosing party only",
        ("Who bears indemnity?", "nda_gamma.pdf"): "Mutual indemnity",
        ("Who bears indemnity?", "nda_delta.pdf"): "Receiving party",
        ("What is the governing law?", "nda_alpha.pdf"): "Laws of India",
        ("What is the governing law?", "nda_beta.pdf"): "English law",
        ("What is the governing law?", "nda_gamma.pdf"): "Laws of Singapore",
        ("What is the governing law?", "nda_delta.pdf"): "Laws of India",
    }
    answer = answers.get((question, doc), "Not found")
    return question, doc, answer


async def run_grid_parallel(questions: list[str], docs: list[str]) -> dict:
    """Run all (question, doc) pairs in parallel."""

    # Build the list of all coroutines
    tasks = [fake_qa(q, d) for q in questions for d in docs]

    # Fire all at once — gather waits for ALL to complete
    results = await asyncio.gather(*tasks)

    # Assemble into the grid matrix
    grid: dict[str, dict[str, str]] = {q: {} for q in questions}
    for question, doc, answer in results:
        grid[question][doc] = answer

    return grid


async def run_grid_sequential(questions: list[str], docs: list[str]) -> dict:
    """For comparison: the slow sequential version."""
    grid: dict[str, dict[str, str]] = {q: {} for q in questions}
    for q in questions:
        for d in docs:
            _, _, answer = await fake_qa(q, d)
            grid[q][d] = answer
    return grid


# Time both approaches
async def compare():
    t0 = time.perf_counter()
    await run_grid_sequential(QUESTIONS, DOCS)
    seq_time = time.perf_counter() - t0

    t0 = time.perf_counter()
    grid = await run_grid_parallel(QUESTIONS, DOCS)
    par_time = time.perf_counter() - t0

    print(f"\nSequential time: {seq_time:.3f}s")
    print(f"Parallel time:   {par_time:.3f}s")
    print(f"Speedup:         {seq_time / par_time:.1f}x")
    return grid


grid = asyncio.run(compare())

# ---------------------------------------------------------------------------
# Section 3: Displaying the grid
# ---------------------------------------------------------------------------
print("\n" + "=" * 60)
print("PART 3: Rendering the result as a table")
print("=" * 60)

# Simple ASCII table (the real code uses Rich)
col_w = 22
header = "Question".ljust(35) + "".join(d[:col_w].ljust(col_w) for d in DOCS)
print("\n" + header)
print("-" * len(header))
for question, row in grid.items():
    line = question[:34].ljust(35)
    for doc in DOCS:
        ans = row.get(doc, "")[:col_w - 1]
        line += ans.ljust(col_w)
    print(line)

# ---------------------------------------------------------------------------
# Section 4: Error handling — one bad doc must not abort the run
# ---------------------------------------------------------------------------
print("\n" + "=" * 60)
print("PART 4: Error isolation — per-cell errors, not whole-run failures")
print("=" * 60)

print("""
In a real run, one document might fail to parse, one API call might timeout.
If we let exceptions propagate, asyncio.gather cancels everything.

The solution: catch exceptions inside each cell coroutine and return
an error string instead of raising.

async def _cell(question, doc, state):
    try:
        result = await _run_qa(question, doc, state)
        return question, doc, result.get("qa_answer", "")
    except Exception as exc:
        return question, doc, f"[error: {exc}]"   ← error per cell

The grid always completes. The lawyer sees:
  "What is the notice period?" | nda_bad.pdf | [error: parse failed]

...and can inspect that file manually instead of losing the entire run.
""")


async def run_grid_with_error():
    """Demonstrates error isolation."""

    async def cell_with_possible_error(q: str, doc: str) -> tuple[str, str, str]:
        if doc == "nda_gamma.pdf" and q == "Who bears indemnity?":
            raise ValueError("PDF parse failed: corrupted stream at offset 4096")
        return await fake_qa(q, d=doc)

    tasks = [cell_with_possible_error(q, d) for q in QUESTIONS for d in DOCS]

    # gather(return_exceptions=True) stores exceptions as results instead of raising
    raw = await asyncio.gather(*tasks, return_exceptions=True)

    grid: dict[str, dict[str, str]] = {q: {} for q in QUESTIONS}
    for item in raw:
        if isinstance(item, Exception):
            # We lose which (q, d) raised it — need the wrapper approach
            continue
        q, doc, answer = item
        grid[q][doc] = answer

    return grid


# Better: use the _cell wrapper pattern
async def run_grid_safe(questions: list[str], docs: list[str]) -> dict:
    async def _cell(q: str, d: str) -> tuple[str, str, str]:
        try:
            if d == "nda_gamma.pdf" and q == "Who bears indemnity?":
                raise ValueError("PDF parse failed")
            return await fake_qa(q, d)
        except Exception as exc:
            return q, d, f"[error: {exc}]"  # per-cell error, not a raised exception

    results = await asyncio.gather(*[_cell(q, d) for q in questions for d in docs])
    grid = {q: {} for q in questions}
    for q, d, ans in results:
        grid[q][d] = ans
    return grid


safe_grid = asyncio.run(run_grid_safe(QUESTIONS, DOCS))
print("Grid with one failing cell:")
for q, row in safe_grid.items():
    for doc, ans in row.items():
        if "error" in ans:
            print(f"  ⚠️  [{q[:30]}] [{doc}] → {ans}")

# ---------------------------------------------------------------------------
# Section 5: How the real node works
# ---------------------------------------------------------------------------
print("\n" + "=" * 60)
print("PART 5: The real implementation (themis/nodes/grid.py)")
print("=" * 60)

print("""
Key design decision: _list_matter_docs is a standalone function.

def _list_matter_docs(matter_id: str) -> list[str]:
    cfg = LexConfig()
    matter_dir = Path(cfg.matters_dir) / matter_id / "docs"
    if not matter_dir.exists():
        return []
    return [str(p) for p in matter_dir.iterdir()
            if p.suffix.lower() in {".pdf", ".docx", ".txt"}]

WHY: Phase 4 (Bulk Document Intelligence) will replace this with:
    workspace.repository.list_documents(matter_id)

The node interface — asyncio.gather over _cell(q, doc) — stays identical.
Only this one function swaps. That is a clean seam.

CLI usage:
    lex grid my-matter \\
        --questions "What is the notice period?" \\
        --questions "Who bears indemnity?" \\
        --csv /tmp/dd_grid.csv

The Rich table renders in the terminal.
The CSV is for the lawyer to open in Excel.
""")

print("✅ Run: lex grid my-matter -q 'What is the notice period?'")
