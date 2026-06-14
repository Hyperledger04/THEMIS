# GraphRAG: Legal Entity Knowledge Graph for Indian court documents.
#
# Inspired by RAGFlow's rag/graphrag/ (entity_resolution.py, NER module).
# RAGFlow extracts entities (person, org, location, statute, citation),
# resolves duplicates, and builds edges between co-occurring entities.
#
# Our implementation uses pure regex-based NER — no ML model needed.
# This keeps it offline-capable and deterministic, which matters for
# citation extraction where precision > recall.
#
# Entity types:
#   CITATION  — "AIR 1978 SC 597", "(2021) 5 SCC 143"
#   STATUTE   — "Section 138 of the NI Act", "Article 21 of the Constitution"
#   COURT     — "Supreme Court", "High Court of Bombay"
#   JUDGE     — "Justice Chandrachud", "Honourable Justice K.S. Puttaswamy"
#   PARTY     — extracted from "v." or "versus" patterns
#   DOCTRINE  — "res judicata", "locus standi", "natural justice"

from __future__ import annotations

import json
import re
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Entity types and regex patterns
# ---------------------------------------------------------------------------

class EntityType:
    CITATION = "CITATION"
    STATUTE = "STATUTE"
    COURT = "COURT"
    JUDGE = "JUDGE"
    PARTY = "PARTY"
    DOCTRINE = "DOCTRINE"


_CITATION_RE = re.compile(
    r"(?<!\w)("
    r"AIR\s+\d{4}\s+(?:SC|All|Bom|Cal|Mad|Del|Ker|Kar|MP|Raj|Guj|P&H)\s+\d+"
    r"|\(\d{4}\)\s+\d+\s+SCC\s+\d+"
    r"|\d{4}\s+\(\d+\)\s+SCC\s+\d+"
    r"|\d{4}\s+SCC\s+\(L&S\)\s+\d+"
    r"|\d{4}\s+SCR\s+\d+"
    r"|\(\d{4}\)\s+\d+\s+MLJ\s+\d+"
    r")"
)

_STATUTE_RE = re.compile(
    r"(?:"
    r"Section\s+\d+[A-Z]?\s+(?:of\s+the\s+)?[A-Z][A-Za-z\s]+Act"
    r"|Article\s+\d+[A-Z]?\s+(?:of\s+the\s+Constitution|of\s+India)?"
    r"|Order\s+[IVXLCDM]+\s+Rule\s+\d+"
    r"|S\.\s*\d+[A-Z]?\s+(?:of\s+the\s+)?[A-Z][A-Za-z\s]+Act"
    r")",
    re.IGNORECASE,
)

_COURT_RE = re.compile(
    r"(?:"
    r"(?:Hon(?:'?ble|ourable)?\s+)?Supreme\s+Court(?:\s+of\s+India)?"
    r"|High\s+Court\s+of\s+[A-Z][a-z]+"
    r"|[A-Z][a-z]{3,}\s+High\s+Court"
    r"|District\s+Court"
    r"|Sessions\s+Court"
    r"|National\s+Company\s+Law\s+Tribunal|NCLT"
    r"|National\s+Consumer\s+Disputes\s+Redressal\s+Commission|NCDRC"
    r")",
    re.IGNORECASE,
)

_JUDGE_RE = re.compile(
    r"(?:Justice|J\.|Hon(?:'?ble|ourable)?\s+Justice)\s+[A-Z][A-Za-z.\s]{2,40}(?=\s*[,;.]|\s+held|\s+observed)",
    re.IGNORECASE,
)

_PARTY_RE = re.compile(
    r"([A-Z][A-Za-z\s&.]{2,50})\s+[vV](?:ersus|\.)\.?\s+([A-Z][A-Za-z\s&.]{2,50})"
)

_DOCTRINE_KEYWORDS: list[str] = [
    "res judicata", "issue estoppel", "locus standi", "natural justice",
    "audi alteram partem", "nemo judex in causa sua", "promissory estoppel",
    "legitimate expectation", "ultra vires", "intra vires",
    "ejusdem generis", "expressio unius", "in pari materia",
    "force majeure", "caveat emptor", "mens rea", "actus reus",
    "prima facie", "ex parte", "inter partes", "suo motu",
]
_DOCTRINE_RE = re.compile(
    "|".join(re.escape(d) for d in _DOCTRINE_KEYWORDS),
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class LegalEntity:
    type: str           # One of EntityType constants
    name: str           # Raw extracted text
    normalized: str     # Lowercase, whitespace-normalised form for deduplication
    sources: list[str] = field(default_factory=list)  # source doc / citation refs


@dataclass
class KGEdge:
    entity_a: str       # normalized name
    entity_b: str       # normalized name
    relation: str       # e.g. "co-occurs", "cited_in", "applies_statute"
    source: str         # document where this edge was found


# ---------------------------------------------------------------------------
# Knowledge Graph
# ---------------------------------------------------------------------------

class LegalKnowledgeGraph:
    """
    In-memory knowledge graph for legal entities extracted from research findings.

    Usage:
        kg = LegalKnowledgeGraph()
        kg.add_text(judgment_text, source="AIR 1978 SC 597")
        graph_dict = kg.to_dict()
    """

    def __init__(self) -> None:
        self._entities: dict[str, LegalEntity] = {}  # normalized → entity
        self._edges: list[KGEdge] = []

    def add_text(self, text: str, source: str = "") -> None:
        """Extract entities from text and add them (and co-occurrence edges) to the graph."""
        entities = extract_entities(text, source=source)
        for entity in entities:
            self._merge_entity(entity)

        # Build co-occurrence edges between entities in the same text
        entity_norms = [e.normalized for e in entities]
        for i, a in enumerate(entity_norms):
            for b in entity_norms[i + 1:]:
                if a != b:
                    self._edges.append(KGEdge(
                        entity_a=a,
                        entity_b=b,
                        relation="co-occurs",
                        source=source,
                    ))

    def query(self, entity_name: str) -> list[dict]:
        """
        Return all entities and edges connected to entity_name.
        Matches by substring on normalized names.
        """
        norm_query = _normalize(entity_name)
        matching_norms = {
            norm for norm in self._entities
            if norm_query in norm or norm in norm_query
        }

        results: list[dict] = []
        for edge in self._edges:
            if edge.entity_a in matching_norms or edge.entity_b in matching_norms:
                other = edge.entity_b if edge.entity_a in matching_norms else edge.entity_a
                entity = self._entities.get(other)
                results.append({
                    "entity": other,
                    "type": entity.type if entity else "UNKNOWN",
                    "relation": edge.relation,
                    "source": edge.source,
                })
        return results

    def to_dict(self) -> dict:
        """Serialise the full graph to a JSON-compatible dict for storage in LexState."""
        return {
            "entities": [
                {
                    "type": e.type,
                    "name": e.name,
                    "normalized": e.normalized,
                    "sources": e.sources,
                }
                for e in self._entities.values()
            ],
            "edges": [
                {
                    "entity_a": ed.entity_a,
                    "entity_b": ed.entity_b,
                    "relation": ed.relation,
                    "source": ed.source,
                }
                for ed in self._edges
            ],
        }

    def _merge_entity(self, entity: LegalEntity) -> None:
        """Add entity to graph or merge with existing entity of same normalized name."""
        existing = self._entities.get(entity.normalized)
        if existing:
            # Merge sources — keep the longer/richer name
            existing.sources.extend(entity.sources)
            if len(entity.name) > len(existing.name):
                existing.name = entity.name
        else:
            self._entities[entity.normalized] = entity


# ---------------------------------------------------------------------------
# Entity extraction (public)
# ---------------------------------------------------------------------------

def extract_entities(text: str, source: str = "") -> list[LegalEntity]:
    """
    Extract all legal entities from text using regex patterns.
    Returns a list of LegalEntity objects.
    """
    entities: list[LegalEntity] = []

    for m in _CITATION_RE.finditer(text):
        entities.append(LegalEntity(
            type=EntityType.CITATION,
            name=m.group(0).strip(),
            normalized=_normalize(m.group(0)),
            sources=[source] if source else [],
        ))

    for m in _STATUTE_RE.finditer(text):
        name = m.group(0).strip()
        if len(name) > 4:  # filter out noise
            entities.append(LegalEntity(
                type=EntityType.STATUTE,
                name=name,
                normalized=_normalize(name),
                sources=[source] if source else [],
            ))

    for m in _COURT_RE.finditer(text):
        entities.append(LegalEntity(
            type=EntityType.COURT,
            name=m.group(0).strip(),
            normalized=_normalize(m.group(0)),
            sources=[source] if source else [],
        ))

    for m in _JUDGE_RE.finditer(text):
        name = m.group(0).strip()
        if len(name.split()) >= 2:
            entities.append(LegalEntity(
                type=EntityType.JUDGE,
                name=name,
                normalized=_normalize(name),
                sources=[source] if source else [],
            ))

    for m in _PARTY_RE.finditer(text):
        for grp in (m.group(1), m.group(2)):
            if grp and grp.strip():
                entities.append(LegalEntity(
                    type=EntityType.PARTY,
                    name=grp.strip(),
                    normalized=_normalize(grp),
                    sources=[source] if source else [],
                ))

    for m in _DOCTRINE_RE.finditer(text):
        entities.append(LegalEntity(
            type=EntityType.DOCTRINE,
            name=m.group(0).strip(),
            normalized=_normalize(m.group(0)),
            sources=[source] if source else [],
        ))

    return entities


# ---------------------------------------------------------------------------
# SQLite persistence
# ---------------------------------------------------------------------------

def save_entity_graph(
    graph_dict: dict,
    matter_id: str,
    sessions_db: str = "~/.themis/sessions.db",
) -> None:
    """
    Persist the serialised entity graph alongside the sessions database.
    Creates a 'entity_graphs' table if it does not exist.
    """
    path = Path(sessions_db).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS entity_graphs (
                matter_id TEXT PRIMARY KEY,
                graph_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        from datetime import datetime
        conn.execute(
            "INSERT OR REPLACE INTO entity_graphs (matter_id, graph_json, updated_at) VALUES (?, ?, ?)",
            (matter_id, json.dumps(graph_dict, ensure_ascii=False), datetime.now().isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


def load_entity_graph(
    matter_id: str,
    sessions_db: str = "~/.themis/sessions.db",
) -> Optional[dict]:
    """Load the entity graph for a matter. Returns None if not found."""
    path = Path(sessions_db).expanduser()
    if not path.exists():
        return None
    conn = sqlite3.connect(str(path))
    try:
        try:
            row = conn.execute(
                "SELECT graph_json FROM entity_graphs WHERE matter_id = ?", (matter_id,)
            ).fetchone()
        except sqlite3.OperationalError:
            return None
        return json.loads(row[0]) if row else None
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _normalize(text: str) -> str:
    """Lowercase and collapse whitespace for entity deduplication."""
    return re.sub(r"\s+", " ", text.lower().strip())
