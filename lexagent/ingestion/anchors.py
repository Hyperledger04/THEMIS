"""Source-anchor helpers for page + line footnotes."""

from __future__ import annotations

from lexagent.workspace.models import SourceAnchor


def build_line_anchors(
    *,
    matter_id: str,
    document_id: str,
    page: int,
    text: str,
    extractor_agent: str = "document_processing_agent",
    extraction_run_id: str | None = None,
) -> list[SourceAnchor]:
    """
    Convert extracted page text into clickable line anchors.

    MVP anchor standard: page + extracted line number. Later OCR/PDF bounding
    boxes can be added without changing the footnote-facing shape.
    """
    anchors: list[SourceAnchor] = []
    for idx, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        anchors.append(
            SourceAnchor(
                matter_id=matter_id,
                document_id=document_id,
                page=page,
                line_start=idx,
                line_end=idx,
                excerpt=line,
                confidence=1.0,
                extractor_agent=extractor_agent,
                extraction_run_id=extraction_run_id,
            )
        )
    return anchors
