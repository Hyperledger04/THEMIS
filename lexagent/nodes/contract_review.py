# Contract review node: ingests a PDF contract, extracts text, and produces a
# structured risk report with clause-level findings in Indian contract law context.
#
# This is a terminal branch — it routes directly to END without going through
# the research → draft → cite → review pipeline.
#
# Triggered when: state["workflow_mode"] == "contract_review"
# Input: state["contract_upload_path"] — path to the uploaded PDF
# Output: state["contract_review_output"], state["contract_risk_analysis"],
#         state["draft_output"] (set so CLI rendering works unchanged)

import asyncio
from pathlib import Path

import litellm
from rich.console import Console

from lexagent.config import LexConfig
from lexagent.state import LexState

console = Console()

# WHY: Hard cap on contract text fed to the LLM. Most commercial contracts are
# under 30k tokens. Above this we chunk and summarise per-section instead.
_MAX_CONTRACT_CHARS = 80_000


def _load_prompt(filename: str) -> str:
    prompts_dir = Path(__file__).parent.parent / "prompts"
    return (prompts_dir / filename).read_text(encoding="utf-8")


def _extract_pdf_text(pdf_path: str) -> str:
    """Extract text from a PDF using pdfplumber (sync — called via run_in_executor)."""
    import pdfplumber  # already in deps (Phase 6)
    text_parts: list[str] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
    return "\n\n".join(text_parts)


def _chunk_contract(text: str, max_chars: int = _MAX_CONTRACT_CHARS) -> list[str]:
    """
    Split oversized contracts into overlapping chunks for sequential analysis.
    WHY: LLM context windows are finite. We chunk at paragraph boundaries rather
    than character boundaries to avoid splitting mid-clause.
    """
    if len(text) <= max_chars:
        return [text]

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    current = ""
    for para in paragraphs:
        if len(current) + len(para) + 2 > max_chars:
            if current:
                chunks.append(current)
            current = para
        else:
            current = (current + "\n\n" + para).strip()
    if current:
        chunks.append(current)
    return chunks


def _build_risk_analysis(report_text: str) -> dict:
    """
    Parse the LLM's markdown risk report into a structured dict for state storage.
    Uses simple heuristics — exact structure depends on LLM output format.
    """
    import re

    overall_match = re.search(r"\*\*Overall Risk Level\*\*:\s*(HIGH|MEDIUM|LOW)", report_text, re.IGNORECASE)
    contract_type_match = re.search(r"\*\*Contract Type\*\*:\s*(.+)", report_text)

    findings: list[dict] = []
    # Extract each **HIGH/MEDIUM/LOW — Category** block
    for m in re.finditer(
        r"\*\*(HIGH|MEDIUM|LOW)\s*—\s*([^\*]+)\*\*\s*\n"
        r"\*Clause/Section\*:\s*(.+?)\n"
        r"\*Issue\*:\s*(.+?)\n"
        r"\*Impact\*:\s*(.+?)\n"
        r"\*Recommendation\*:\s*(.+?)(?=\n\n|\Z)",
        report_text,
        re.DOTALL,
    ):
        findings.append({
            "risk_level": m.group(1).upper(),
            "category": m.group(2).strip(),
            "clause_ref": m.group(3).strip(),
            "issue": m.group(4).strip(),
            "impact": m.group(5).strip(),
            "recommendation": m.group(6).strip(),
        })

    return {
        "overall_risk": overall_match.group(1) if overall_match else "UNKNOWN",
        "contract_type": contract_type_match.group(1).strip() if contract_type_match else "Unknown",
        "findings": findings,
        "finding_count": len(findings),
        "high_count": sum(1 for f in findings if f["risk_level"] == "HIGH"),
        "medium_count": sum(1 for f in findings if f["risk_level"] == "MEDIUM"),
        "low_count": sum(1 for f in findings if f["risk_level"] == "LOW"),
    }


async def run(state: LexState) -> dict:
    """
    Contract review node.
    Reads a PDF, sends it to the LLM with the contract review system prompt,
    and returns a structured risk report.
    """
    try:
        cfg = LexConfig()
        upload_path = state.get("contract_upload_path")

        if not upload_path:
            return {"error": "contract_review node: no contract_upload_path in state"}

        pdf_path = Path(upload_path).expanduser()
        if not pdf_path.exists():
            return {"error": f"contract_review node: file not found: {upload_path}"}

        console.print(f"[bold blue]→ Contract Review:[/bold blue] {pdf_path.name}")

        # Extract PDF text off the event loop (synchronous I/O)
        loop = asyncio.get_event_loop()
        contract_text = await loop.run_in_executor(None, _extract_pdf_text, str(pdf_path))

        if not contract_text.strip():
            return {"error": f"contract_review node: could not extract text from {pdf_path.name}"}

        console.print(f"  Extracted {len(contract_text):,} characters")

        system_prompt = _load_prompt("contract_review_system.md")

        # Inject lawyer soul context if available
        lawyer_soul = state.get("lawyer_soul")
        if lawyer_soul and isinstance(lawyer_soul, dict) and lawyer_soul.get("raw"):
            system_prompt = f"## Instructing Lawyer Profile\n{lawyer_soul['raw']}\n\n---\n\n{system_prompt}"

        chunks = _chunk_contract(contract_text)
        all_reports: list[str] = []

        for i, chunk in enumerate(chunks):
            if len(chunks) > 1:
                console.print(f"  Reviewing section {i+1}/{len(chunks)}…")

            user_msg = (
                f"Please review the following contract text and provide a risk report:\n\n"
                f"---\n{chunk}\n---"
            )

            response = await litellm.acompletion(
                model=f"{cfg.model_provider}/{cfg.default_model}",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_msg},
                ],
            )
            all_reports.append(response.choices[0].message.content)

        # Merge multi-chunk reports or use the single report directly
        full_report = (
            all_reports[0]
            if len(all_reports) == 1
            else "# Contract Risk Report (Multi-Section)\n\n" + "\n\n---\n\n".join(all_reports)
        )

        risk_analysis = _build_risk_analysis(full_report)

        console.print(
            f"[green]✓ Contract review complete:[/green] "
            f"{risk_analysis['high_count']} HIGH, "
            f"{risk_analysis['medium_count']} MEDIUM, "
            f"{risk_analysis['low_count']} LOW findings"
        )

        return {
            "contract_review_output": full_report,
            "contract_risk_analysis": risk_analysis,
            # Populate draft_output so the CLI's existing rendering logic works
            # without a separate code path for contract review results.
            "draft_output": full_report,
            "plain_english_summary": (
                f"Contract review complete. "
                f"Overall risk: {risk_analysis['overall_risk']}. "
                f"{risk_analysis['high_count']} high-risk findings require immediate attention."
            ),
            "messages": list(state.get("messages", [])) + [{"role": "assistant", "content": full_report}],
        }

    except Exception as e:
        return {"error": f"contract_review node failed: {e}"}
