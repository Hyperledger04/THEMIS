"""Tests for lexagent/tools/chunker.py"""
import os
import tempfile

import pytest

from lexagent.tools.chunker import (
    Chunk,
    _approx_tokens,
    _extract_pdf_text,
    _split_on_headers,
    _table_to_markdown,
    chunk_text,
)


# -----------------------------------------------------------------------
# _approx_tokens
# -----------------------------------------------------------------------

def test_approx_tokens_empty():
    assert _approx_tokens("") == 0


def test_approx_tokens_single_word():
    assert _approx_tokens("hello") == 1


def test_approx_tokens_sentence():
    assert _approx_tokens("the quick brown fox") == 4


# -----------------------------------------------------------------------
# _split_on_headers
# -----------------------------------------------------------------------

def test_split_no_headers_returns_single_section():
    text = "This is plain text with no headers."
    sections = _split_on_headers(text)
    assert len(sections) == 1
    assert sections[0][0] == "para_0"
    assert "plain text" in sections[0][1]


def test_split_detects_section_header():
    text = "Preamble text.\n\nSection 3 The scope of this Act.\nSome content here."
    sections = _split_on_headers(text)
    ids = [s[0] for s in sections]
    assert any("Section 3" in sid for sid in ids)


def test_split_preamble_captured():
    text = "This is the preamble.\n\nSection 1 Short title.\nContent."
    sections = _split_on_headers(text)
    assert sections[0][0] == "preamble"
    assert "preamble" in sections[0][1].lower()


def test_split_multiple_sections():
    text = (
        "Section 1 Title.\nContent of section one.\n\n"
        "Section 2 Definitions.\nContent of section two.\n\n"
        "Section 3 Scope.\nContent of section three."
    )
    sections = _split_on_headers(text)
    assert len(sections) == 3


# -----------------------------------------------------------------------
# chunk_text
# -----------------------------------------------------------------------

def test_chunk_text_returns_list_of_chunks():
    text = "Section 1 Commencement.\nThis Act shall come into force."
    chunks = chunk_text(text, source_doc="test.txt")
    assert isinstance(chunks, list)
    assert all(isinstance(c, Chunk) for c in chunks)


def test_chunk_text_sets_source_doc():
    chunks = chunk_text("Section 1 Foo.\nBar content.", source_doc="my_act.txt")
    assert all(c.source_doc == "my_act.txt" for c in chunks)


def test_chunk_text_non_empty_chunks_only():
    chunks = chunk_text("   \n\n   \n\nSection 2 Empty.\n   ", source_doc="x")
    for c in chunks:
        assert c.chunk_text.strip() != ""


def test_chunk_text_unique_chunk_indices():
    text = "\n\n".join([f"Section {i} Title.\nSome content here for section {i}." for i in range(5)])
    chunks = chunk_text(text, source_doc="act.txt")
    indices = [c.chunk_index for c in chunks]
    assert indices == list(range(len(chunks)))


def test_chunk_text_large_section_split():
    # A section with more than max_tokens words should be split further
    long_section = "Section 5 Long.\n" + " ".join(["word"] * 600)
    chunks = chunk_text(long_section, source_doc="long.txt", max_tokens=100)
    assert len(chunks) > 1


def test_chunk_text_empty_input():
    chunks = chunk_text("", source_doc="empty.txt")
    assert chunks == []


def test_chunk_text_plain_text_no_sections():
    text = "This is just a paragraph. No sections here."
    chunks = chunk_text(text, source_doc="plain.txt")
    assert len(chunks) == 1
    assert "paragraph" in chunks[0].chunk_text


def test_chunk_text_article_header():
    text = "Article 21 Right to life.\nNo person shall be deprived of life."
    chunks = chunk_text(text, source_doc="constitution.txt")
    assert any("Article 21" in c.section_id for c in chunks)


def test_chunk_text_sub_clause_header():
    text = "(a) This is clause a.\n(b) This is clause b."
    chunks = chunk_text(text, source_doc="clauses.txt")
    assert len(chunks) >= 2


# -----------------------------------------------------------------------
# _table_to_markdown
# -----------------------------------------------------------------------

def test_table_to_markdown_empty():
    assert _table_to_markdown([]) == ""


def test_table_to_markdown_header_only():
    md = _table_to_markdown([["Case", "Court", "Year"]])
    assert "Case" in md
    assert "---" in md


def test_table_to_markdown_with_rows():
    table = [["Case", "Court"], ["AIR 1978 SC 597", "Supreme Court"]]
    md = _table_to_markdown(table)
    assert "AIR 1978 SC 597" in md
    assert "Supreme Court" in md


def test_table_to_markdown_none_cells():
    table = [["Case", None], [None, "SC"]]
    md = _table_to_markdown(table)
    # None cells become empty strings — no crash
    assert "SC" in md


# -----------------------------------------------------------------------
# _extract_pdf_text — ImportError path (pdfplumber not installed)
# -----------------------------------------------------------------------

def test_extract_pdf_text_missing_pdfplumber(monkeypatch):
    """_extract_pdf_text raises ImportError with helpful message when pdfplumber absent."""
    import builtins
    real_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if name == "pdfplumber":
            raise ImportError("No module named 'pdfplumber'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", mock_import)
    with pytest.raises(ImportError, match="pdfplumber"):
        _extract_pdf_text("any.pdf")


# -----------------------------------------------------------------------
# chunk_file with a real .txt temp file
# -----------------------------------------------------------------------

def test_chunk_file_txt(tmp_path):
    from lexagent.tools.chunker import chunk_file
    f = tmp_path / "act.txt"
    f.write_text("Section 1 Short title.\nThis Act may be called the Test Act.")
    chunks = chunk_file(str(f))
    assert len(chunks) >= 1
    assert chunks[0].source_doc == str(f)
