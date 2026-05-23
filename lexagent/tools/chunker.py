# Laws-template chunker: structure-preserving split for Indian legal documents.
# Treats statutory sections, sub-sections, and clauses as atomic units —
# never breaks mid-clause across chunk boundaries.
# Supports plain text (and in the future, DOCX/PDF — see _extract_text).
# Each chunk carries: source_doc, section_id, chunk_index, chunk_text.

from __future__ import annotations

import re
from dataclasses import dataclass, field


# WHY: Section anchors follow the hierarchy used in Indian legislation:
#   Section / Article → Sub-section / Clause → Proviso / Explanation
# The regex captures the opening line of each unit so we can split on it.
_SECTION_RE = re.compile(
    r"^("
    r"(?:Section|Sec\.?|S\.)\s*\d+[\w]*"          # Section 12, Sec 12A, S.12
    r"|Article\s+\d+[\w]*"                          # Article 21
    r"|\(\s*[a-z]{1,3}\s*\)"                        # (a), (b), (ab)
    r"|\(\s*[ivxlIVXL]+\s*\)"                       # (i), (ii), (iv)
    r"|\d+\.\s"                                     # 1. 2. numbered list
    r"|Proviso\b|Explanation\b|Schedule\b"
    r")",
    re.IGNORECASE | re.MULTILINE,
)

# Rough token estimator — splits on whitespace.
# WHY: We avoid tiktoken as a dependency; whitespace tokens are 20% over
# but sufficient for chunk-size decisions on legal prose.
def _approx_tokens(text: str) -> int:
    return len(text.split())


@dataclass
class Chunk:
    source_doc: str
    section_id: str    # e.g. "Section 3" or "para_0"
    chunk_index: int
    chunk_text: str
    # parent_text is filled by the retriever (5d) when building the hierarchy
    parent_text: str = field(default="")


def chunk_text(
    text: str,
    source_doc: str = "unknown",
    max_tokens: int = 256,
) -> list[Chunk]:
    """
    Split legal text into structure-preserving chunks.

    Splits on statutory section/clause headers first.
    If a resulting unit still exceeds max_tokens, it is split further on
    paragraph boundaries — never mid-sentence.
    """
    sections = _split_on_headers(text)
    chunks: list[Chunk] = []
    for section_id, body in sections:
        sub = _split_large_body(body, max_tokens)
        for i, piece in enumerate(sub):
            if piece.strip():
                chunks.append(Chunk(
                    source_doc=source_doc,
                    section_id=section_id,
                    chunk_index=len(chunks),
                    chunk_text=piece.strip(),
                ))
    return chunks


def chunk_file(path: str, max_tokens: int = 256) -> list[Chunk]:
    """Load a file and chunk it. Handles .txt and .docx."""
    text = _extract_text(path)
    return chunk_text(text, source_doc=path, max_tokens=max_tokens)


# -----------------------------------------------------------------------
# Internal helpers
# -----------------------------------------------------------------------


def _extract_text(path: str) -> str:
    """Read raw text from .txt, .docx, or .pdf."""
    if path.endswith(".docx"):
        # WHY: python-docx is in our deps for docx_writer;
        # reuse it here to avoid a separate library for reading.
        from docx import Document  # type: ignore[import]
        doc = Document(path)
        return "\n".join(p.text for p in doc.paragraphs)
    if path.endswith(".pdf"):
        return _extract_pdf_text(path)
    # Default: read as UTF-8 plain text
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _extract_pdf_text(path: str) -> str:
    """
    Extract text from a PDF using pdfplumber.

    Layout-aware extraction preserving the reading order Indian court judgments
    use (multi-column, footnotes, headers/footers). Tables are serialised as
    markdown so the downstream chunker can treat them as structured sections.

    Footnotes (font size ≤ 8pt, bottom 15% of page) are appended after the
    main body text of the same page so they stay close to the citation they
    annotate.
    """
    try:
        import pdfplumber  # type: ignore[import]
    except ImportError as exc:
        raise ImportError(
            "pdfplumber is required for PDF parsing. "
            "Run: uv add pdfplumber"
        ) from exc

    pages: list[str] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            page_text = _extract_page(page)
            if page_text.strip():
                pages.append(page_text)

    return "\n\n".join(pages)


def _extract_page(page) -> str:  # type: ignore[no-untyped-def]
    """
    Extract text from a single pdfplumber Page object.

    Separates main body from footnotes based on vertical position,
    then serialises any tables found on the page as markdown.
    """
    # Threshold: bottom 15% of page height = footnote zone
    footnote_y = page.height * 0.85

    body_words: list[str] = []
    footnote_words: list[str] = []

    # WHY: extract_words() preserves reading order and gives us bounding boxes
    # so we can separate body text from footnotes by y-coordinate.
    for word in page.extract_words():
        y_top = word.get("top", 0)
        size = word.get("size", 12)
        # Treat small font (≤8pt) in the footnote zone as footnote text
        if y_top >= footnote_y and size <= 8:
            footnote_words.append(word["text"])
        else:
            body_words.append(word["text"])

    body = " ".join(body_words)

    # Serialise tables as markdown so section headers inside tables are preserved
    table_md_parts: list[str] = []
    for table in page.extract_tables():
        if table:
            table_md_parts.append(_table_to_markdown(table))

    footnote_text = " ".join(footnote_words)

    parts = [body]
    if table_md_parts:
        parts.extend(table_md_parts)
    if footnote_text:
        # WHY: Footnotes carry citation references — keep them in the chunk stream
        # so the cite node can match them against the citation regex.
        parts.append(f"[Footnote] {footnote_text}")

    return "\n".join(p for p in parts if p.strip())


def _table_to_markdown(table: list[list]) -> str:
    """Convert a pdfplumber table (list of rows) to a markdown table string."""
    if not table:
        return ""
    rows = [[str(cell or "").strip() for cell in row] for row in table]
    if not rows:
        return ""
    header = "| " + " | ".join(rows[0]) + " |"
    separator = "| " + " | ".join("---" for _ in rows[0]) + " |"
    body_rows = ["| " + " | ".join(r) + " |" for r in rows[1:]]
    return "\n".join([header, separator] + body_rows)


def _split_on_headers(text: str) -> list[tuple[str, str]]:
    """
    Split text on statutory section headers.
    Returns [(section_id, body_text), ...].
    """
    positions: list[tuple[int, str]] = []
    for m in _SECTION_RE.finditer(text):
        positions.append((m.start(), m.group(0).strip()))

    if not positions:
        # No headers found — treat entire text as one anonymous section
        return [("para_0", text)]

    sections: list[tuple[str, str]] = []
    # Text before the first header
    if positions[0][0] > 0:
        preamble = text[: positions[0][0]].strip()
        if preamble:
            sections.append(("preamble", preamble))

    for idx, (start, header) in enumerate(positions):
        end = positions[idx + 1][0] if idx + 1 < len(positions) else len(text)
        body = text[start:end]
        sections.append((header, body))

    return sections


def _split_large_body(text: str, max_tokens: int) -> list[str]:
    """
    If a section body is larger than max_tokens, split on paragraph
    boundaries (double-newline) first, then on word boundaries for any
    paragraph that is itself longer than max_tokens.
    """
    if _approx_tokens(text) <= max_tokens:
        return [text]

    paragraphs = re.split(r"\n\s*\n", text)
    chunks: list[str] = []
    current: list[str] = []
    current_tokens = 0

    for para in paragraphs:
        t = _approx_tokens(para)
        if t > max_tokens:
            # Flush current accumulation first
            if current:
                chunks.append("\n\n".join(current))
                current = []
                current_tokens = 0
            # Split the oversized paragraph on word boundaries
            chunks.extend(_split_by_words(para, max_tokens))
        elif current_tokens + t > max_tokens and current:
            chunks.append("\n\n".join(current))
            current = [para]
            current_tokens = t
        else:
            current.append(para)
            current_tokens += t

    if current:
        chunks.append("\n\n".join(current))

    return chunks


def _split_by_words(text: str, max_tokens: int) -> list[str]:
    """Split a single long string into max_tokens-sized word windows."""
    words = text.split()
    result: list[str] = []
    for i in range(0, len(words), max_tokens):
        result.append(" ".join(words[i : i + max_tokens]))
    return result
