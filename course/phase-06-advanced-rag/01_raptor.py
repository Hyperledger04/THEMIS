# ── SECTION 1: RAPTOR — Recursive Abstractive Processing for Tree-Organized Retrieval ──────────
#
# File: course/phase-06-advanced-rag/01_raptor.py
# LexAgent source: lexagent/tools/raptor_summarizer.py
# Toggle: LEX_RAPTOR_ENABLED=true  (OFF by default — costs extra LLM calls at ingestion time)
#
# PROBLEM this file solves
# ─────────────────────────
# Your research node returns 10 case summaries, each ~500 words = 5,000 words total.
# When a lawyer asks "what is the doctrine on legitimate expectation?", you cannot stuff
# all 5,000 words into every LLM prompt — you will burn context window fast.
#
# RAPTOR's answer: cluster → summarise → build a tree.
# Broad questions query the cluster summaries (level 1).
# Specific citation lookups query the raw chunks (level 0).
# You pay the LLM cost ONCE at ingestion time. Query time is free.

import math


# ── SECTION 2: THE DATA ──────────────────────────────────────────────────────────────────
#
# In LexAgent these come from research_findings in LexState (state.py).
# For this demo, we hardcode 10 short case summaries.

CASE_SUMMARIES = [
    # Constitutional / Fundamental Rights cluster
    {
        "id": "c1",
        "text": (
            "Maneka Gandhi v. Union of India (1978) 1 SCC 248: The Supreme Court expanded "
            "Article 21 to require that the procedure prescribed by law must be fair, just "
            "and reasonable. Passport impounded without hearing. Held: violates natural justice."
        ),
    },
    {
        "id": "c2",
        "text": (
            "K.S. Puttaswamy v. Union of India (2017) 10 SCC 1: Nine-judge bench unanimously "
            "held right to privacy is a fundamental right under Article 21. Aadhaar challenged. "
            "Privacy includes informational self-determination."
        ),
    },
    {
        "id": "c3",
        "text": (
            "Navtej Singh Johar v. Union of India (2018) 10 SCC 1: Section 377 IPC read down. "
            "Article 21 protects dignity and sexual autonomy. Criminalising consensual adult "
            "same-sex relations unconstitutional."
        ),
    },
    # Limitation / Procedural cluster
    {
        "id": "c4",
        "text": (
            "Rajender Singh v. Santa Singh (1973) 2 SCC 705: Section 5 Limitation Act. "
            "Sufficient cause must be shown for delay. Courts should be liberal but not "
            "condone gross negligence. Party must explain every day of delay."
        ),
    },
    {
        "id": "c5",
        "text": (
            "Collector Land Acquisition v. Mst. Katiji (1987) 2 SCC 107: Liberal approach to "
            "condonation of delay in government cases. State's delay should not prejudice "
            "citizens; however, unexplained delays cannot be condoned mechanically."
        ),
    },
    {
        "id": "c6",
        "text": (
            "N. Balakrishnan v. M. Krishnamurthy (1998) 7 SCC 123: Limitation is a matter "
            "of procedure not substantive right. Courts must lean in favour of deciding on "
            "merits when no prejudice caused by delay."
        ),
    },
    # Contract / Commercial cluster
    {
        "id": "c7",
        "text": (
            "Hadley v. Baxendale principle adopted in India: Karsandas H. Thacker v. "
            "Saran Engineering (1965) AIR SC 1981. Damages for breach limited to what "
            "parties contemplated at contract formation. Remote consequences excluded."
        ),
    },
    {
        "id": "c8",
        "text": (
            "ONGC v. Saw Pipes (2003) 5 SCC 705: Arbitral award can be set aside if "
            "contrary to fundamental policy of Indian law, interests of India, or justice "
            "and morality. Section 34 Arbitration Act expanded."
        ),
    },
    {
        "id": "c9",
        "text": (
            "Bharat Sanchar Nigam Ltd v. Motorola India (2009) 2 SCC 337: Specific "
            "performance granted in telecom contract dispute. Court will not rewrite "
            "commercial contracts but will enforce clear obligations."
        ),
    },
    {
        "id": "c10",
        "text": (
            "Ssangyong Engineering v. NHAI (2019) 15 SCC 131: Patent illegality ground "
            "under Section 34(2A) applies to domestic awards only. Court clarified ONGC "
            "v. Saw Pipes scope. Pro-arbitration approach affirmed."
        ),
    },
]


# ── SECTION 3: CLUSTERING ────────────────────────────────────────────────────────────────
#
# Real LexAgent uses TF-IDF vectors with sklearn's KMeans.
# Here we show the SAME LOGIC with a simplified word-overlap approach so you can run
# this file without installing sklearn.
#
# The key concept is identical: group cases that talk about similar things.

CLUSTERS = {
    # Manually assigned for demo; in production this is k-means output
    "constitutional_rights": ["c1", "c2", "c3"],
    "limitation_procedure":  ["c4", "c5", "c6"],
    "contract_commercial":   ["c7", "c8", "c9", "c10"],
}

print("=" * 60)
print("RAPTOR STEP 1: Raw chunks (Level 0)")
print("=" * 60)
for case in CASE_SUMMARIES:
    print(f"  [{case['id']}] {case['text'][:70]}...")
print(f"\nTotal chunks: {len(CASE_SUMMARIES)}")
print(f"Total words:  {sum(len(c['text'].split()) for c in CASE_SUMMARIES)}")
print()


# ── SECTION 4: CLUSTER SUMMARISATION ─────────────────────────────────────────────────────
#
# WRONG WAY — inline LLM call in a loop, no caching, no abstraction:
#
#   for cluster in clusters:
#       response = openai.chat.complete(prompt=f"Summarise {texts}")  # NO! Not LangGraph
#
# RIGHT WAY — pass a summarize_fn (dependency injection).
# In production: summarize_fn = lambda text: call_llm([HumanMessage(text)], cfg)
# In tests: summarize_fn = lambda text: text[:80]  # cheap, deterministic
# This pattern is exactly how raptor_summarizer.py structures it.

def _fake_summarize(text: str) -> str:
    """
    Stub summarizer — returns first 120 chars of concatenated text.
    In production this is replaced by an actual LLM call.
    Cost: 1 LLM call per cluster. For k=3 clusters → 3 calls total.
    """
    snippet = text.replace("\n", " ")[:120]
    return f"[SUMMARY] {snippet}..."


def build_raptor_tree(
    chunks: list[dict],
    cluster_assignments: dict[str, list[str]],
    summarize_fn,
) -> dict:
    """
    Returns:
        {
          "level_0": { chunk_id: chunk_text, ... },   # raw
          "level_1": { cluster_name: summary, ... },  # cluster summaries
          "level_2": overall_summary                  # root
        }
    """
    # Level 0: raw chunks indexed by id
    level_0 = {c["id"]: c["text"] for c in chunks}

    # Level 1: summarise each cluster
    level_1 = {}
    print("=" * 60)
    print("RAPTOR STEP 2: Cluster summarisation (Level 1)")
    print("=" * 60)
    for cluster_name, chunk_ids in cluster_assignments.items():
        combined = "\n\n".join(level_0[cid] for cid in chunk_ids if cid in level_0)
        summary = summarize_fn(combined)
        level_1[cluster_name] = summary
        print(f"\nCluster: {cluster_name}")
        print(f"  Contains: {chunk_ids}")
        print(f"  Summary : {summary}")

    # Level 2: summarise all cluster summaries → root
    all_summaries = "\n\n".join(level_1.values())
    level_2 = summarize_fn(all_summaries)

    print()
    print("=" * 60)
    print("RAPTOR STEP 3: Root summary (Level 2)")
    print("=" * 60)
    print(f"Overall root: {level_2}")

    return {"level_0": level_0, "level_1": level_1, "level_2": level_2}


# ── SECTION 5: QUERY ROUTING ─────────────────────────────────────────────────────────────
#
# After building the tree, how do we SEARCH it?
#
# Rule of thumb used in lexagent/tools/raptor_summarizer.py:
#   - Broad doctrine query → search level_1 summaries (3 candidates instead of 10)
#   - Specific citation query → search level_0 raw chunks (exact match needed)
#
# "Broad" heuristic: query < 8 words and no case citation pattern (no "v." or year in parens)

import re

def route_query(query: str) -> str:
    """Return 'level_1' for broad questions, 'level_0' for specific lookups."""
    has_citation = bool(re.search(r'\bv\.\b|\(\d{4}\)', query, re.IGNORECASE))
    is_short = len(query.split()) < 8
    if is_short and not has_citation:
        return "level_1"
    return "level_0"


def search_tree(query: str, tree: dict) -> list[str]:
    """Naive keyword search over the appropriate tree level."""
    level = route_query(query)
    search_space = tree[level]

    query_words = set(query.lower().split())
    results = []

    if isinstance(search_space, dict):
        for key, text in search_space.items():
            text_words = set(text.lower().split())
            overlap = len(query_words & text_words)
            if overlap > 0:
                results.append((overlap, f"[{level}:{key}] {text[:100]}..."))
    else:
        # level_2 is a string (root summary)
        results.append((1, f"[level_2:root] {search_space[:100]}..."))

    results.sort(reverse=True)
    return [r[1] for r in results[:3]]


# ── SECTION 6: PUTTING IT ALL TOGETHER ───────────────────────────────────────────────────

tree = build_raptor_tree(CASE_SUMMARIES, CLUSTERS, _fake_summarize)

print()
print("=" * 60)
print("RAPTOR STEP 4: Query routing demo")
print("=" * 60)

queries = [
    "what is the doctrine on fundamental rights",           # broad → level_1
    "Maneka Gandhi v. Union of India (1978) limitation",    # specific → level_0
    "condonation of delay procedure",                       # broad → level_1
    "ONGC v. Saw Pipes (2003) arbitration award",          # specific → level_0
]

for q in queries:
    level = route_query(q)
    hits = search_tree(q, tree)
    print(f"\nQuery   : {q!r}")
    print(f"Routed  : {level}")
    for hit in hits:
        print(f"  Hit   : {hit}")


# ── SECTION 7: COST ANALYSIS ─────────────────────────────────────────────────────────────

print()
print("=" * 60)
print("COST ANALYSIS")
print("=" * 60)
n_chunks   = len(CASE_SUMMARIES)
n_clusters = len(CLUSTERS)

print(f"Chunks              : {n_chunks}")
print(f"Clusters            : {n_clusters}")
print(f"LLM calls at ingest : {n_clusters + 1}  (1 per cluster + 1 for root)")
print(f"LLM calls at query  : 0  (summaries already computed)")
print()
print("Compare to naive approach (summarise all chunks on every query):")
print(f"  LLM calls per query : {n_chunks}")
print()
print("With RAPTOR and 100 queries over this corpus:")
cost_raptor = n_clusters + 1 + 0 * 100
cost_naive  = n_chunks * 100
print(f"  RAPTOR total LLM calls : {cost_raptor}")
print(f"  Naive  total LLM calls : {cost_naive}")
print(f"  Savings                : {cost_naive - cost_raptor} calls  "
      f"({100 * (1 - cost_raptor/cost_naive):.0f}%)")


# ── PAUSE AND THINK ──────────────────────────────────────────────────────────────────────
#
# 1. Open lexagent/tools/raptor_summarizer.py.
#    What function signature does it use for summarize_fn?
#    How is it injected — constructor, parameter, or module-level?
#
# 2. The toggle LEX_RAPTOR_ENABLED lives in lexagent/config.py as a Field() on LexConfig.
#    What is the default value and why is it False by default?
#
# 3. In lexagent/nodes/research.py, WHERE in the node lifecycle is build_raptor_tree()
#    called — before the LLM writes research_findings, or after?
#    Why does the order matter for token cost?
#
# 4. The cluster routing logic uses a heuristic (short query + no citation = broad).
#    What would break if a lawyer typed a short citation like "Maneka Gandhi"?
#    How would you fix the route_query function to handle this edge case?
#
# 5. RAPTOR costs n_clusters LLM calls at ingestion time.
#    If a matter has 50 research findings clustered into 8 groups, how many
#    LLM calls does ingest cost total? How does that compare to a single GPT-4 call
#    that reads all 50 chunks naively?
