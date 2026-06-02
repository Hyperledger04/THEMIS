"""
Phase 6 — Exercise 1: Build a RAPTOR Summary Tree

Implement cluster assignment and tree building WITHOUT clustering libraries.
Use simple modulo assignment: finding i goes to cluster (i % n_clusters).
"""

FINDINGS = [
    "Maneka Gandhi v Union of India AIR 1978 SC 597: Article 21 personal liberty "
    "includes right to travel abroad. Passport cannot be impounded without hearing.",

    "Francis Coralie Mullin v Delhi 1981 SC: Article 21 right to live with dignity. "
    "Bare necessities of life must be provided. Human dignity is constitutionally protected.",

    "Olga Tellis v Bombay Municipal 1985 SCC: Right to livelihood is part of Article 21. "
    "Eviction without alternative shelter violates fundamental rights.",

    "Kesavananda Bharati v Kerala AIR 1973 SC 1461: Basic structure doctrine. "
    "Parliament cannot amend Constitution to destroy its basic features.",

    "Minerva Mills v Union of India AIR 1980 SC 1789: Judicial review is part of basic "
    "structure. Parliament cannot exclude courts from constitutional questions.",

    "Indira Nehru Gandhi v Raj Narain AIR 1975 SC 2299: Free and fair elections are "
    "part of basic structure. Cannot be abridged even by constitutional amendment.",
]


def assign_clusters(findings: list[str], n_clusters: int = 2) -> dict[int, list[str]]:
    """
    Assign each finding to a cluster using modulo (simple round-robin).
    finding[0] → cluster 0, finding[1] → cluster 1, finding[2] → cluster 0, ...

    Returns: {cluster_id: [finding1, finding2, ...]}
    """
    # TODO: implement using {i % n_clusters: [] for i in range(n_clusters)} pattern
    pass


def summarize_cluster(findings: list[str]) -> str:
    """
    Stub summarizer: return first 80 chars of the first finding + "..."
    (In production: actual LLM call to summarize the cluster)
    """
    # TODO: implement — return findings[0][:80] + "..." if findings else ""
    pass


def build_raptor_tree(findings: list[str], n_clusters: int = 2) -> dict:
    """
    Build a 2-level RAPTOR tree.

    Returns:
        {
            "level_0": findings,             # raw research findings
            "level_1": [cluster summaries],  # one summary per cluster
            "clusters": {cluster_id: [...]}, # which findings are in each cluster
            "n_clusters": n_clusters,
        }

    Usage: query level_1 for broad doctrine questions (fewer tokens),
           query level_0 for specific citation lookups.
    """
    # TODO: call assign_clusters, then summarize_cluster for each cluster
    pass


# ── TESTS ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    tree = build_raptor_tree(FINDINGS, n_clusters=2)

    assert tree is not None, "build_raptor_tree returned None"
    assert "level_0" in tree, "Missing level_0"
    assert "level_1" in tree, "Missing level_1"
    assert "clusters" in tree, "Missing clusters"

    assert len(tree["level_0"]) == len(FINDINGS), \
        f"level_0 should have {len(FINDINGS)} findings, got {len(tree['level_0'])}"
    print(f"✓ level_0: {len(tree['level_0'])} raw findings")

    assert len(tree["level_1"]) == 2, f"Expected 2 cluster summaries, got {len(tree['level_1'])}"
    print(f"✓ level_1: {len(tree['level_1'])} cluster summaries")
    for i, summary in enumerate(tree["level_1"]):
        cluster_size = len(tree["clusters"][i])
        print(f"  Cluster {i} ({cluster_size} findings): {summary[:60]}...")

    # Verify all findings accounted for
    all_in_clusters = sum(len(v) for v in tree["clusters"].values())
    assert all_in_clusters == len(FINDINGS), "All findings must be in a cluster"
    print(f"✓ All {len(FINDINGS)} findings assigned to clusters")

    print("\n── RAPTOR Tree Structure ──")
    print("  Level 1 (cluster summaries — query these for broad questions):")
    for i, s in enumerate(tree["level_1"]):
        print(f"    Cluster {i}: {s}")
    print("  Level 0 (raw findings — query these for citation lookups):")
    for f in tree["level_0"][:2]:
        print(f"    {f[:60]}...")

    print("\n✅ All tests passed!")

# ── PAUSE AND THINK ───────────────────────────────────────────────────────────
# 1. Open lexagent/tools/raptor_summarizer.py — does it use sklearn k-means for
#    clustering instead of modulo? Why would k-means produce better clusters?
# 2. Your summarize_cluster is a stub. In production, it's an LLM call.
#    If you have 10 clusters and each summary costs $0.001, how much does
#    building the RAPTOR tree cost per matter? Is that acceptable?
# 3. The tree has 2 levels. RAPTOR stands for "Recursive" — when would you add
#    a level_2 (summaries of summaries)? How large would the corpus need to be?
