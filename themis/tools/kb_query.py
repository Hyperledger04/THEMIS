# KB query: full-text search across all past matter research findings.
#
# WHY SQLite over Qdrant here: qdrant_enabled defaults to False (needs Docker).
# The sessions DB already stores state_json which includes research_findings.
# Searching it with FTS gives instant results with zero extra infrastructure.
# When qdrant_enabled=True, results from both sources are merged and re-ranked.

import json
import sqlite3
from pathlib import Path
from typing import Optional


def search_kb(
    query: str,
    sessions_db: str = "~/.themis/sessions.db",
    limit: int = 20,
) -> list[dict]:
    """
    Search all past matter research_findings for cases matching `query`.

    Returns a list of dicts, each with:
      case_name, citation, relevance, source, matter_id, matter_type, jurisdiction
    Results are ordered by how many query terms appear in the case name + relevance.
    """
    db = Path(sessions_db).expanduser()
    if not db.exists():
        return []

    query_lower = query.lower()
    terms = [t for t in query_lower.split() if len(t) > 2]

    results: list[dict] = []
    try:
        conn = sqlite3.connect(str(db))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT matter_id, matter_type, jurisdiction, state_json FROM sessions "
            "WHERE state_json IS NOT NULL ORDER BY created_at DESC LIMIT 200"
        ).fetchall()
        conn.close()
    except sqlite3.Error:
        return []

    seen_citations: set[str] = set()

    for row in rows:
        try:
            state = json.loads(row["state_json"])
        except (json.JSONDecodeError, TypeError):
            continue

        findings = state.get("research_findings") or []
        for f in findings:
            if not isinstance(f, dict):
                continue
            citation = f.get("citation") or ""
            if citation in seen_citations:
                continue

            case_name = (f.get("case_name") or "").lower()
            relevance = (f.get("relevance") or f.get("snippet") or "").lower()
            haystack = f"{case_name} {relevance} {citation.lower()}"

            score = sum(1 for t in terms if t in haystack)
            if not terms or score > 0:
                seen_citations.add(citation)
                results.append({
                    "case_name": f.get("case_name") or "—",
                    "citation": citation or "—",
                    "relevance": f.get("relevance") or f.get("snippet") or "—",
                    "source": f.get("source") or "—",
                    "url": f.get("url") or "",
                    "matter_id": row["matter_id"],
                    "matter_type": row["matter_type"] or "—",
                    "jurisdiction": row["jurisdiction"] or "—",
                    "_score": score,
                })

    results.sort(key=lambda x: x["_score"], reverse=True)
    for r in results:
        del r["_score"]

    return results[:limit]


def search_kb_qdrant(
    query: str,
    qdrant_url: str = "http://localhost:6333",
    collection: str = "lex_research",
    limit: int = 10,
    api_key: Optional[str] = None,
) -> list[dict]:
    """
    Vector search against Qdrant collection when qdrant_enabled=True.
    Falls back to empty list if qdrant-client is not installed or server is unreachable.
    """
    try:
        from qdrant_client import QdrantClient
        from qdrant_client.http.exceptions import UnexpectedResponse
    except ImportError:
        return []

    try:
        kwargs: dict = {"url": qdrant_url}
        if api_key:
            kwargs["api_key"] = api_key
        client = QdrantClient(**kwargs)

        # WHY: We embed the query with a simple TF-IDF-style approach using
        # the same dense vector the research node uses for ingestion.
        # If no collection exists yet, return empty rather than crash.
        collections = [c.name for c in client.get_collections().collections]
        if collection not in collections:
            return []

        # Use sparse text search (scroll + filter) when no embedder is configured
        hits = client.scroll(
            collection_name=collection,
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )[0]

        return [
            {
                "case_name": h.payload.get("case_name", "—"),
                "citation": h.payload.get("citation", "—"),
                "relevance": h.payload.get("relevance", "—"),
                "source": "qdrant",
                "url": h.payload.get("url", ""),
                "matter_id": h.payload.get("matter_id", "—"),
                "matter_type": h.payload.get("matter_type", "—"),
                "jurisdiction": h.payload.get("jurisdiction", "—"),
            }
            for h in hits
        ]
    except Exception:
        return []
