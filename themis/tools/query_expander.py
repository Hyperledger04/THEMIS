# Legal query expander for Indian law.
#
# RAGFlow's query.py (rag/nlp/query.py) expands BM25 queries with synonyms at
# 0.25× weight and adds proximity phrases. We implement the same idea with a
# hardcoded Indian legal synonym map — no external NLP model needed.
#
# Why hardcoded vs ML synonyms:
#   Indian legal abbreviations (AIR, SCC, HC) and doctrine terms ("locus standi",
#   "res judicata") have very specific expansions that a generic word2vec model
#   would get wrong. A curated map is more precise for this domain.

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Synonym map — key: canonical term, value: list of synonyms
# All lowercase for case-insensitive lookup.
# ---------------------------------------------------------------------------
LEGAL_SYNONYMS: dict[str, list[str]] = {
    # Interim relief terminology
    "injunction": ["stay", "ad interim stay", "interim relief", "temporary injunction", "interim injunction"],
    "stay": ["injunction", "ad interim stay", "interim relief", "suspension"],
    "interim": ["temporary", "ad interim", "provisional"],

    # Party names
    "petitioner": ["plaintiff", "applicant", "appellant", "complainant", "writ petitioner"],
    "respondent": ["defendant", "opposite party", "non-applicant"],
    "plaintiff": ["petitioner", "complainant", "claimant"],
    "defendant": ["respondent", "accused", "opposite party"],
    "appellant": ["petitioner", "plaintiff"],
    "respondent": ["appellee", "defendant", "opposite party"],

    # Court types
    "high court": ["HC", "appellate court"],
    "supreme court": ["SC", "apex court", "hon'ble supreme court"],
    "district court": ["sessions court", "civil court", "subordinate court"],
    "tribunal": ["authority", "commission", "forum", "adjudicating authority"],

    # Contract terms
    "contract": ["agreement", "deed", "instrument", "covenant", "arrangement"],
    "breach": ["violation", "contravention", "non-performance", "default"],
    "damages": ["compensation", "relief", "remedy", "loss", "quantum"],
    "consideration": ["price", "quid pro quo", "exchange"],
    "specific performance": ["enforcement", "execution"],

    # Property terms
    "property": ["land", "immovable property", "premises", "estate", "tenement"],
    "possession": ["occupation", "custody", "control"],
    "title": ["ownership", "proprietary right", "right of ownership"],
    "mortgage": ["hypothecation", "charge", "encumbrance", "security"],
    "lease": ["tenancy", "licence", "letting", "demise"],

    # Criminal law
    "accused": ["defendant", "offender", "suspect", "undertrial"],
    "bail": ["anticipatory bail", "regular bail", "interim bail", "surety"],
    "offence": ["crime", "violation", "act", "misconduct"],
    "conviction": ["finding of guilt", "sentence"],
    "acquittal": ["discharge", "exoneration"],

    # Constitutional / writ
    "writ": ["petition", "application", "prayer"],
    "fundamental rights": ["basic rights", "constitutional rights", "article 21", "article 14"],
    "locus standi": ["standing", "right to sue", "aggrieved person"],
    "natural justice": ["audi alteram partem", "nemo judex", "fair hearing", "due process"],

    # Citation series — expand abbreviations so BM25 can match full forms
    "air": ["all india reporter", "AIR"],
    "scc": ["supreme court cases", "SCC"],
    "scr": ["supreme court reports", "SCR"],
    "mlj": ["madras law journal", "MLJ"],
    "bom": ["bombay", "bombay high court"],
    "cal": ["calcutta", "calcutta high court"],
    "del": ["delhi", "delhi high court"],
    "mad": ["madras", "madras high court"],
    "all": ["allahabad", "allahabad high court"],
    "ker": ["kerala", "kerala high court"],
    "kar": ["karnataka", "karnataka high court"],
    "p&h": ["punjab and haryana", "punjab & haryana high court"],

    # Procedural
    "limitation": ["time-barred", "limitation period", "prescription", "article 113", "article 137"],
    "res judicata": ["issue estoppel", "constructive res judicata", "order 2 rule 2"],
    "cause of action": ["right to sue", "accrual"],
    "ex parte": ["unilateral", "one-sided", "without notice"],
    "interlocutory": ["interim", "ad interim", "temporary"],
}

# IDF-style weights for Indian legal terms — higher weight = more distinctive term.
# Used by weight_terms() to boost important BM25 query tokens.
_TERM_WEIGHTS: dict[str, float] = {
    "air": 2.0,
    "scc": 2.0,
    "scr": 2.0,
    "mlj": 2.0,
    "section": 1.5,
    "article": 1.5,
    "act": 1.2,
    "rule": 1.2,
    "order": 1.2,
    "injunction": 1.8,
    "bail": 1.8,
    "writ": 1.7,
    "fundamental": 1.6,
    "res judicata": 2.0,
    "locus standi": 2.0,
    "natural justice": 1.8,
    "limitation": 1.6,
    "specific performance": 1.9,
}
_DEFAULT_WEIGHT = 1.0


def expand_query(query: str) -> str:
    """
    Return an expanded query string for BM25 retrieval.

    Each token in the query is looked up in LEGAL_SYNONYMS. Synonyms are
    appended to the query at a reduced frequency (one synonym per original
    token) so BM25 scores them as supplementary matches, not primary ones.

    Example:
        "injunction property dispute" →
        "injunction property dispute stay ad interim stay land"
    """
    tokens = _tokenize(query)
    expanded: list[str] = list(tokens)  # start with original tokens

    seen_synonyms: set[str] = set()
    for token in tokens:
        syns = LEGAL_SYNONYMS.get(token, [])
        # Add first two synonyms only — too many dilute BM25 signal
        for syn in syns[:2]:
            if syn not in seen_synonyms and syn.lower() not in tokens:
                expanded.append(syn)
                seen_synonyms.add(syn)

    return " ".join(expanded)


def weight_terms(query: str) -> dict[str, float]:
    """
    Return a {term: weight} dict for the tokens in query.

    Used by callers that want to multiply BM25 scores by term importance.
    Terms not in _TERM_WEIGHTS get weight 1.0.
    """
    tokens = _tokenize(query)
    return {tok: _TERM_WEIGHTS.get(tok, _DEFAULT_WEIGHT) for tok in tokens}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> list[str]:
    """
    Lowercase and split on whitespace/punctuation, preserving multi-word
    phrases that appear in LEGAL_SYNONYMS (e.g. "res judicata").
    """
    text_lower = text.lower()
    tokens: list[str] = []

    # First pass: try to match multi-word keys from LEGAL_SYNONYMS
    remaining = text_lower
    matched_spans: list[tuple[int, int, str]] = []
    for key in sorted(LEGAL_SYNONYMS, key=lambda k: -len(k)):
        for m in re.finditer(re.escape(key), remaining):
            matched_spans.append((m.start(), m.end(), key))

    # Collect non-overlapping matches (longest first)
    used: list[tuple[int, int]] = []
    for start, end, phrase in sorted(matched_spans, key=lambda x: -(x[1] - x[0])):
        if not any(s < end and start < e for s, e in used):
            tokens.append(phrase)
            used.append((start, end))

    # Second pass: add remaining single words not covered by multi-word matches
    word_re = re.compile(r"[a-z0-9&']+")
    for m in word_re.finditer(text_lower):
        if not any(s <= m.start() < e for s, e in used):
            tokens.append(m.group())

    return tokens
