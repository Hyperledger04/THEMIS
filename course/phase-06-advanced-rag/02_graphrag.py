# ── SECTION 1: PROBLEM — WHAT VECTOR SEARCH CANNOT DO ──────────────────────────────────────
#
# File: course/phase-06-advanced-rag/02_graphrag.py
# LexAgent source: lexagent/tools/legal_kg.py
# Toggle: LEX_GRAPHRAG_ENABLED=true  (OFF by default)
#
# Vector search answers: "find chunks semantically similar to this query."
# It cannot answer: "which cases DISTINGUISH Maneka Gandhi?" or
# "what later cases OVERRULE A.K. Gopalan?" — because those are RELATIONAL questions.
#
# The chunk that mentions Maneka Gandhi in the context of a different doctrine
# gets a high cosine score. That is wrong. You need a graph.

import re
from collections import defaultdict


# ── SECTION 2: SOLUTION — EXTRACT ENTITIES, BUILD GRAPH, TRAVERSE ───────────────────────────
#
# The pipeline:
#   raw text → entity extraction → relation extraction → knowledge graph → graph query
#
# In production: use an LLM to extract entities and relations precisely.
# In this demo: use regex — good enough to show the concept, zero API cost.


# ── SECTION 3: ENTITIES IN INDIAN LAW ────────────────────────────────────────────────────────
#
# Entity types we care about:
#   Party   — "Maneka Gandhi", "Union of India"
#   Court   — "Supreme Court", "High Court of Bombay"
#   Judge   — "Justice Bhagwati", "CJI Chandrachud"
#   Statute — "Constitution of India", "Indian Penal Code"
#   Section — "Article 21", "Section 300"
#   Date    — "1978", "2023"
#
# Relations between case nodes:
#   CITES          — case A cites case B
#   OVERRULES      — case A overrules case B (stronger than DISTINGUISHES)
#   FOLLOWS        — case A follows the ratio in case B
#   DISTINGUISHES  — case A distinguishes itself from case B on facts
#   INTERPRETS     — case A interprets a constitutional provision / statute
#   APPLIES        — case A applies the ratio from case B to new facts


def extract_case_names(text: str) -> list[str]:
    """Extract 'Party v. Party' style case names from raw text."""
    # WHY: Indian case law uses "v." (with dot) or "v" (without).
    # We require Title Case on both sides to avoid false positives.
    pattern = r'[A-Z][a-zA-Z\s]+\s+v\.?\s+[A-Z][a-zA-Z\s]+'
    matches = re.findall(pattern, text)
    # Strip trailing whitespace that the greedy \s+ can pull in.
    return [m.strip() for m in matches]


def extract_statutes(text: str) -> list[str]:
    """Extract 'Article N' and 'Section N of Act' references."""
    pattern = r'Article\s+\d+[A-Z]?|Section\s+\d+[A-Z]?(?:\s+of\s+[A-Z][a-zA-Z\s]+)?'
    return re.findall(pattern, text)


# ── SECTION 4: THE KNOWLEDGE GRAPH ───────────────────────────────────────────────────────────
#
# Representation: adjacency list.
#   node  → list of (relation, target_node) pairs
#
# Nodes are strings (case names, statute names, etc.).
# In production: store in Neo4j or NetworkX for real graph traversal.
# Here: plain Python dict — sufficient for the teaching demo.


class LegalKG:
    """
    A minimal directed knowledge graph for Indian case law.

    Nodes:  any string (case name, statute, concept)
    Edges:  directed, labelled with a relation string
    """

    def __init__(self):
        # WHY: defaultdict(list) means we never get KeyError on first insert.
        self._graph: dict[str, list[tuple[str, str]]] = defaultdict(list)

    def add_relation(self, source: str, relation: str, target: str) -> None:
        self._graph[source].append((relation, target))

    def query(self, node: str, relation: str | None = None) -> list[tuple[str, str]]:
        """Return all edges from `node`, optionally filtered by relation type."""
        results = self._graph.get(node, [])
        if relation:
            return [(r, t) for r, t in results if r == relation]
        return results

    def reverse_query(self, target: str, relation: str | None = None) -> list[str]:
        """Return all nodes that point TO `target` (optionally filtered)."""
        sources = []
        for node, edges in self._graph.items():
            for r, t in edges:
                if t == target and (relation is None or r == relation):
                    sources.append(node)
        return sources


# ── SECTION 5: DEMO — BUILD AND QUERY A SMALL LEGAL GRAPH ────────────────────────────────────

def main() -> None:
    kg = LegalKG()

    # Seed the graph with three canonical Indian constitutional law relations.
    kg.add_relation("Maneka Gandhi v UOI (1978)",     "INTERPRETS",    "Article 21")
    kg.add_relation("Francis Coralie v UT Delhi (1981)", "FOLLOWS",    "Maneka Gandhi v UOI (1978)")
    kg.add_relation("A.K. Gopalan v State of Madras (1950)", "DISTINGUISHES", "Article 21")
    kg.add_relation("Olga Tellis v Bombay MC (1985)", "FOLLOWS",       "Maneka Gandhi v UOI (1978)")
    kg.add_relation("Olga Tellis v Bombay MC (1985)", "INTERPRETS",    "Article 21")

    print("=== GraphRAG Demo ===\n")

    # Query 1: Which cases INTERPRET Article 21?
    print("Q1: Cases that INTERPRET Article 21:")
    interpreters = kg.reverse_query("Article 21", relation="INTERPRETS")
    for case in interpreters:
        print(f"  → {case}")

    # Query 2: What does Maneka Gandhi do in the graph?
    print("\nQ2: All edges from 'Maneka Gandhi v UOI (1978)':")
    for relation, target in kg.query("Maneka Gandhi v UOI (1978)"):
        print(f"  {relation} → {target}")

    # Query 3: Which cases FOLLOW Maneka Gandhi?
    print("\nQ3: Cases that FOLLOW Maneka Gandhi:")
    followers = kg.reverse_query("Maneka Gandhi v UOI (1978)", relation="FOLLOWS")
    for case in followers:
        print(f"  → {case}")

    # Entity extraction on a raw text snippet
    print("\n=== Entity Extraction Demo ===")
    snippet = (
        "In Maneka Gandhi v Union of India (1978), the Supreme Court held that "
        "Article 21 must be read with Article 14 and Article 19. "
        "The earlier view in A.K. Gopalan v State of Madras was distinguished."
    )
    cases    = extract_case_names(snippet)
    statutes = extract_statutes(snippet)
    print(f"Snippet: {snippet[:80]}...")
    print(f"Cases found    : {cases}")
    print(f"Statutes found : {statutes}")


if __name__ == "__main__":
    main()


# ── PAUSE AND THINK ─────────────────────────────────────────────────────────────────────────
#
# 1. Where does LexAgent's knowledge graph actually get built?
#    Which node (intake / research / cite) would call LegalKG.add_relation()?
#
# 2. The production version uses an LLM to extract relations.
#    What prompt would you write to extract (source_case, relation, target) triples?
#
# 3. What happens when the same case appears under different name spellings?
#    ("Maneka Gandhi" vs "Maneka Gandhi v. Union of India" vs "1978 AIR 597")
#    How would you normalise case identity before inserting into the graph?
#
# 4. Open lexagent/config.py.  Add LEX_GRAPHRAG_ENABLED: bool = False.
#    Which node would read this flag and conditionally call LegalKG?
#
# 5. Graph traversal vs vector search: for the query "cases that follow Maneka Gandhi",
#    which approach gives a more precise answer, and why?
