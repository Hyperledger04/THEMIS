# Document QA node: parse PDF/DOCX, chunk, retrieve, answer with [1][2] inline citations.
# Invoked by `lex qa <file>` — not part of the main draft graph.
#
# Answer format:
#   Claim or finding [1] and further elaboration [2].
#
#   Sources:
#     [1] Page 4 — "The licensee shall not sub-license..."
#     [2] Page 8, Clause 18.1 — "Governing law: Delhi courts..."

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text

from lexagent.config import LexConfig
from lexagent.tools.chunker import Chunk, chunk_text
from lexagent.tools.retriever import HybridRetriever

console = Console()


@dataclass
class DocChunk:
    """A chunk from a parsed document with page/location metadata."""
    text: str
    page: Optional[int]        # 1-based page number (PDF) or None for DOCX
    location: str              # e.g. "Page 4" or "Clause 12.3"
    chunk_index: int


def parse_pdf(path: Path) -> list[DocChunk]:
    """Extract text from PDF, preserving page numbers."""
    try:
        import pdfplumber  # type: ignore[import]
    except ImportError:
        raise ImportError("pdfplumber is required for PDF QA: uv add pdfplumber")

    chunks: list[DocChunk] = []
    idx = 0
    with pdfplumber.open(str(path)) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            if not text.strip():
                continue
            # Chunk each page's text separately so chunk.page is unambiguous
            for sub in chunk_text(text, source_doc=path.name, max_tokens=200):
                loc = _infer_location(sub.chunk_text, page_num)
                chunks.append(DocChunk(
                    text=sub.chunk_text,
                    page=page_num,
                    location=loc,
                    chunk_index=idx,
                ))
                idx += 1
    return chunks


def parse_docx(path: Path) -> list[DocChunk]:
    """Extract text from DOCX, using heading structure as location labels."""
    try:
        from docx import Document  # type: ignore[import]
    except ImportError:
        raise ImportError("python-docx is required for DOCX QA: uv add python-docx")

    doc = Document(str(path))
    chunks: list[DocChunk] = []
    idx = 0
    current_heading = "Introduction"
    buffer: list[str] = []

    def _flush(heading: str) -> None:
        nonlocal idx
        text = "\n".join(buffer).strip()
        if not text:
            return
        for sub in chunk_text(text, source_doc=path.name, max_tokens=200):
            chunks.append(DocChunk(
                text=sub.chunk_text,
                page=None,
                location=heading,
                chunk_index=idx,
            ))
            idx += 1
        buffer.clear()

    for para in doc.paragraphs:
        if para.style.name.startswith("Heading"):
            _flush(current_heading)
            current_heading = para.text.strip() or current_heading
        elif para.text.strip():
            buffer.append(para.text.strip())

    _flush(current_heading)
    return chunks


def _infer_location(text: str, page: int) -> str:
    """Try to extract a clause/section label from the chunk text for richer citation."""
    # Match patterns like "Clause 12.3", "Section 4", "Article 7"
    m = re.search(
        r"\b(Clause\s+[\d.]+|Section\s+[\d.]+[A-Za-z]?|Article\s+[\d.]+)\b",
        text,
        re.IGNORECASE,
    )
    if m:
        return f"Page {page}, {m.group(0)}"
    return f"Page {page}"


def build_retriever(chunks: list[DocChunk]) -> HybridRetriever:
    """Build a HybridRetriever over DocChunks by converting to findings format."""
    findings = [
        {
            "full_text": c.text,
            "citation": c.location,
            "case_name": c.location,
        }
        for c in chunks
    ]
    return HybridRetriever.from_findings(
        findings,
        child_max_tokens=200,
        parent_max_tokens=600,
        query_expansion=False,  # speed — document is already loaded
    )


_CITATION_PROMPT = """\
You are a document QA assistant. Answer the question using ONLY the provided source passages.

For every factual claim, add an inline citation marker like [1], [2], etc.
Each marker must correspond to the numbered source below.
Do not invent information not in the sources.
If no source is relevant, say "The document does not appear to address this."

Sources:
{sources}

Question: {question}

Answer (with inline [N] markers):"""


async def answer_question(
    question: str,
    chunks: list[DocChunk],
    retriever: HybridRetriever,
    cfg: LexConfig,
    top_k: int = 5,
) -> tuple[str, list[DocChunk]]:
    """
    Retrieve top_k relevant chunks, ask the LLM to answer with inline citations.
    Returns (answer_text, cited_chunks) where cited_chunks[i] corresponds to [i+1].
    """
    results = retriever.retrieve(question, top_k=top_k)

    if not results:
        return "The document does not appear to address this question.", []

    cited_chunks: list[DocChunk] = []
    source_lines: list[str] = []
    for i, r in enumerate(results, start=1):
        # Map retrieval result back to a DocChunk by matching text
        dc = _find_doc_chunk(r.child.chunk_text, chunks)
        if dc:
            cited_chunks.append(dc)
            snippet = dc.text[:200].replace("\n", " ")
            source_lines.append(f"[{i}] {dc.location} — \"{snippet}\"")
        else:
            cited_chunks.append(DocChunk(
                text=r.child.chunk_text,
                page=None,
                location=r.child.source_doc,
                chunk_index=i,
            ))
            snippet = r.child.chunk_text[:200].replace("\n", " ")
            source_lines.append(f"[{i}] {r.child.source_doc} — \"{snippet}\"")

    prompt = _CITATION_PROMPT.format(
        sources="\n".join(source_lines),
        question=question,
    )

    from lexagent.nodes._llm import call_llm
    result = await call_llm(
        [
            {"role": "system", "content": "You are a precise document QA assistant for legal documents."},
            {"role": "user", "content": prompt},
        ],
        cfg,
        # Document context — bypass PII anonymization to preserve citation accuracy
        is_document_context=True,
    )
    return result["content"].strip(), cited_chunks


def _find_doc_chunk(text: str, chunks: list[DocChunk]) -> Optional[DocChunk]:
    """Find the DocChunk whose text best matches a retrieval result."""
    text_stripped = text.strip()
    for c in chunks:
        if c.text.strip() == text_stripped:
            return c
        if text_stripped in c.text or c.text in text_stripped:
            return c
    return None


def render_answer(answer: str, cited_chunks: list[DocChunk]) -> None:
    """Print the answer panel followed by a Sources panel — Rich-formatted."""
    console.print(Rule("Answer", style="bold green"))
    console.print(Panel(answer, border_style="green", padding=(0, 1)))

    if cited_chunks:
        console.print(Rule("Sources", style="dim"))
        for i, dc in enumerate(cited_chunks, start=1):
            snippet = dc.text[:160].replace("\n", " ").strip()
            loc = dc.location or (f"Page {dc.page}" if dc.page else "Unknown")
            console.print(f"  [bold cyan]\\[{i}][/bold cyan] {loc} — [dim]\"{snippet}…\"[/dim]")
        console.print()


async def run_document_qa_session(file_path: Path, cfg: LexConfig) -> None:
    """
    Interactive QA loop for a single document.
    Parses the file, builds retriever, then runs a question-answer REPL.
    Exit with 'quit', 'exit', or Ctrl-C/D.
    """
    suffix = file_path.suffix.lower()

    console.print(Panel(
        f"[bold]Document QA[/bold]  [dim]{file_path.name}[/dim]\n"
        "Ask questions about this document. Answers include inline [N] citations.\n"
        "[dim]Type 'exit' or press Ctrl-C to quit.[/dim]",
        border_style="blue",
        padding=(0, 1),
    ))

    with console.status("[bold blue]Parsing document…"):
        if suffix == ".pdf":
            chunks = parse_pdf(file_path)
        elif suffix in (".docx", ".doc"):
            chunks = parse_docx(file_path)
        else:
            console.print(f"[red]Unsupported file type: {suffix}. Use .pdf or .docx[/red]")
            return

        retriever = build_retriever(chunks)

    console.print(f"[green]✓ Loaded {len(chunks)} chunks from {file_path.name}[/green]\n")

    import prompt_toolkit
    from prompt_toolkit import PromptSession
    from prompt_toolkit.patch_stdout import patch_stdout

    session: PromptSession = PromptSession()

    while True:
        try:
            with patch_stdout():
                question = await session.prompt_async("You: ")
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Exiting document QA.[/dim]")
            break

        question = question.strip()
        if not question:
            continue
        if question.lower() in ("exit", "quit", "q"):
            break

        with console.status("[bold blue]Searching…"):
            answer, cited = await answer_question(question, chunks, retriever, cfg)

        render_answer(answer, cited)
