"""Tests for themis/tools/query_expander.py"""
from themis.tools.query_expander import LEGAL_SYNONYMS, expand_query, weight_terms, _tokenize


# -----------------------------------------------------------------------
# _tokenize
# -----------------------------------------------------------------------

def test_tokenize_single_word():
    tokens = _tokenize("injunction")
    assert "injunction" in tokens


def test_tokenize_multi_word_phrase():
    tokens = _tokenize("res judicata applies here")
    assert "res judicata" in tokens


def test_tokenize_mixed_case():
    tokens = _tokenize("Injunction Property")
    assert "injunction" in tokens
    assert "property" in tokens


def test_tokenize_empty():
    assert _tokenize("") == []


# -----------------------------------------------------------------------
# expand_query
# -----------------------------------------------------------------------

def test_expand_query_adds_synonyms():
    expanded = expand_query("injunction")
    assert "injunction" in expanded
    # At least one synonym from the map should appear
    assert any(syn in expanded for syn in ["stay", "interim relief", "ad interim stay"])


def test_expand_query_property():
    expanded = expand_query("property dispute")
    assert "property" in expanded
    assert any(syn in expanded for syn in ["land", "immovable property", "premises"])


def test_expand_query_original_term_present():
    # The original query term must appear in the expanded output
    expanded = expand_query("stay")
    assert "stay" in expanded.split()


def test_expand_query_citation_abbreviation():
    expanded = expand_query("AIR 1978")
    # Lowercase matching — "air" should expand
    assert "air" in expanded.lower() or "all india reporter" in expanded.lower()


def test_expand_query_no_known_term():
    # Unknown terms pass through unchanged
    expanded = expand_query("xyz123")
    assert "xyz123" in expanded


def test_expand_query_empty():
    assert expand_query("") == ""


# -----------------------------------------------------------------------
# weight_terms
# -----------------------------------------------------------------------

def test_weight_terms_known_term():
    weights = weight_terms("injunction bail")
    # injunction and bail are in _TERM_WEIGHTS with weight > 1
    assert weights.get("injunction", 1.0) >= 1.5 or weights.get("bail", 1.0) >= 1.5


def test_weight_terms_unknown_term():
    weights = weight_terms("someunknownword")
    assert weights.get("someunknownword") == 1.0


def test_weight_terms_empty():
    assert weight_terms("") == {}


# -----------------------------------------------------------------------
# LEGAL_SYNONYMS structure
# -----------------------------------------------------------------------

def test_legal_synonyms_not_empty():
    assert len(LEGAL_SYNONYMS) > 10


def test_legal_synonyms_values_are_lists():
    for key, val in LEGAL_SYNONYMS.items():
        assert isinstance(val, list), f"Key '{key}' has non-list value"
        assert len(val) > 0, f"Key '{key}' has empty synonym list"
