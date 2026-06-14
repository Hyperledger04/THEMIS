"""Tests for themis/tools/legal_kg.py"""
import pytest

from themis.tools.legal_kg import (
    EntityType,
    LegalEntity,
    LegalKnowledgeGraph,
    extract_entities,
    _normalize,
)


# -----------------------------------------------------------------------
# _normalize
# -----------------------------------------------------------------------

def test_normalize_lowercase():
    assert _normalize("Supreme Court") == "supreme court"


def test_normalize_collapses_whitespace():
    assert _normalize("  res   judicata  ") == "res judicata"


# -----------------------------------------------------------------------
# extract_entities — citations
# -----------------------------------------------------------------------

def test_extract_citation_air():
    entities = extract_entities("As held in AIR 1978 SC 597, the court ruled.")
    citations = [e for e in entities if e.type == EntityType.CITATION]
    assert any("AIR 1978 SC 597" in e.name for e in citations)


def test_extract_citation_scc():
    entities = extract_entities("See (2021) 5 SCC 143 for the ratio.")
    citations = [e for e in entities if e.type == EntityType.CITATION]
    assert len(citations) >= 1


def test_extract_no_false_citation():
    entities = extract_entities("The year 2024 saw many changes.")
    citations = [e for e in entities if e.type == EntityType.CITATION]
    assert citations == []


# -----------------------------------------------------------------------
# extract_entities — statutes
# -----------------------------------------------------------------------

def test_extract_statute_section():
    text = "Section 138 of the NI Act applies here."
    entities = extract_entities(text)
    statutes = [e for e in entities if e.type == EntityType.STATUTE]
    assert any("138" in e.name for e in statutes)


def test_extract_statute_article():
    text = "Article 21 of the Constitution guarantees right to life."
    entities = extract_entities(text)
    statutes = [e for e in entities if e.type == EntityType.STATUTE]
    assert any("21" in e.name for e in statutes)


# -----------------------------------------------------------------------
# extract_entities — courts
# -----------------------------------------------------------------------

def test_extract_supreme_court():
    entities = extract_entities("The Supreme Court of India held that...")
    courts = [e for e in entities if e.type == EntityType.COURT]
    assert len(courts) >= 1


def test_extract_high_court():
    entities = extract_entities("The High Court of Bombay dismissed the appeal.")
    courts = [e for e in entities if e.type == EntityType.COURT]
    assert any("Bombay" in e.name for e in courts)


# -----------------------------------------------------------------------
# extract_entities — doctrines
# -----------------------------------------------------------------------

def test_extract_res_judicata():
    entities = extract_entities("The plea of res judicata was upheld.")
    doctrines = [e for e in entities if e.type == EntityType.DOCTRINE]
    assert any("res judicata" in e.normalized for e in doctrines)


def test_extract_natural_justice():
    entities = extract_entities("Principles of natural justice were violated.")
    doctrines = [e for e in entities if e.type == EntityType.DOCTRINE]
    assert any("natural justice" in e.normalized for e in doctrines)


# -----------------------------------------------------------------------
# extract_entities — parties
# -----------------------------------------------------------------------

def test_extract_parties():
    text = "Ram Lal v. Shyam Sundar: The plaintiff filed suit."
    entities = extract_entities(text)
    parties = [e for e in entities if e.type == EntityType.PARTY]
    assert len(parties) >= 1


# -----------------------------------------------------------------------
# LegalKnowledgeGraph
# -----------------------------------------------------------------------

def test_kg_add_text_populates_entities():
    kg = LegalKnowledgeGraph()
    kg.add_text("AIR 1978 SC 597 established that natural justice applies.", source="test")
    d = kg.to_dict()
    assert len(d["entities"]) >= 1


def test_kg_deduplicates_entities():
    kg = LegalKnowledgeGraph()
    kg.add_text("AIR 1978 SC 597 is a landmark case.", source="doc1")
    kg.add_text("See AIR 1978 SC 597 for the principle.", source="doc2")
    d = kg.to_dict()
    normalized_names = [e["normalized"] for e in d["entities"]]
    # Should appear only once despite two insertions
    assert normalized_names.count("air 1978 sc 597") == 1


def test_kg_co_occurrence_edges():
    kg = LegalKnowledgeGraph()
    kg.add_text(
        "AIR 1978 SC 597 applied Section 138 of the NI Act. Natural justice was considered.",
        source="j1"
    )
    d = kg.to_dict()
    assert len(d["edges"]) >= 1


def test_kg_query_returns_connected_entities():
    kg = LegalKnowledgeGraph()
    kg.add_text("AIR 1978 SC 597 applied Section 138 of the NI Act.", source="j1")
    results = kg.query("AIR 1978 SC 597")
    assert isinstance(results, list)


def test_kg_query_empty_graph():
    kg = LegalKnowledgeGraph()
    assert kg.query("anything") == []


def test_kg_to_dict_structure():
    kg = LegalKnowledgeGraph()
    kg.add_text("Supreme Court held in (2021) 5 SCC 143.")
    d = kg.to_dict()
    assert "entities" in d
    assert "edges" in d
    assert isinstance(d["entities"], list)
    assert isinstance(d["edges"], list)


# -----------------------------------------------------------------------
# SQLite persistence
# -----------------------------------------------------------------------

def test_save_and_load_entity_graph(tmp_path):
    from themis.tools.legal_kg import save_entity_graph, load_entity_graph

    db = str(tmp_path / "test_sessions.db")
    graph = {"entities": [{"name": "AIR 1978 SC 597", "type": "CITATION"}], "edges": []}

    save_entity_graph(graph, matter_id="M001", sessions_db=db)
    loaded = load_entity_graph("M001", sessions_db=db)

    assert loaded is not None
    assert loaded["entities"][0]["name"] == "AIR 1978 SC 597"


def test_load_entity_graph_missing(tmp_path):
    from themis.tools.legal_kg import load_entity_graph
    result = load_entity_graph("NONEXISTENT", sessions_db=str(tmp_path / "no.db"))
    assert result is None
