# LLM-based cross-encoder re-ranker for retrieval results.
#
# RAGFlow uses "multiple recall paired with fused re-ranking" — after BM25 and
# vector retrieval produce candidate chunks, a re-ranker scores (query, passage)
# pairs jointly. This is the cross-encoder pattern: the LLM sees both the query
# and the passage together, giving much better precision than bi-encoder fusion.
#
# WHY a separate reranker instead of just using the draft LLM:
#   The draft node gets all top-k passages at once. A bad passage in that context
#   window can distract the LLM. Re-ranking first ensures the top-3 are the best
#   possible matches before the draft LLM ever sees them.
#
# WHY off by default (reranker_enabled=False):
#   One extra LLM call per retrieval. For typical matters (3-5 citations) this
#   adds ~1-2s and one API call. Lawyers can enable it with LEX_RERANKER_ENABLED=true.

from __future__ import annotations

import re

from lexagent.tools.retriever import RetrievalResult


class LLMReranker:
    """
    Re-rank a list of RetrievalResult objects using the LLM as a cross-encoder.

    The LLM rates each passage 0-10 for relevance to the query in a single
    batched prompt (one API call regardless of the number of passages).

    Usage:
        reranker = LLMReranker(llm=get_llm(cfg), top_k=5)
        reranked = await reranker.rerank(query, results)
    """

    def __init__(self, llm, top_k: int = 5) -> None:
        self._llm = llm
        self._top_k = top_k

    async def rerank(
        self, query: str, results: list[RetrievalResult]
    ) -> list[RetrievalResult]:
        """
        Return results re-sorted by LLM relevance score.
        Falls back to original order on any error.
        """
        if not results:
            return results

        try:
            scores = await self._score_passages(query, results)
        except Exception:
            # WHY: Any LLM failure (timeout, API error, parse failure) must
            # degrade gracefully — the re-ranker is an optional quality boost,
            # not a hard dependency of the cite pipeline.
            return results[: self._top_k]

        scored = sorted(
            zip(scores, results),
            key=lambda x: x[0],
            reverse=True,
        )
        return [r for _, r in scored][: self._top_k]

    async def _score_passages(
        self, query: str, results: list[RetrievalResult]
    ) -> list[float]:
        """
        Send a single prompt to the LLM asking it to rate each passage 0-10.
        Returns a list of float scores aligned with results.
        """
        passages = []
        for i, r in enumerate(results, start=1):
            # Use child chunk text — it's the precise match unit
            passages.append(f"[{i}] {r.child.chunk_text[:400]}")

        passages_text = "\n\n".join(passages)
        prompt = (
            "You are a legal research relevance judge. For each numbered passage below, "
            "rate its relevance to the following legal query on a scale from 0 (completely "
            "irrelevant) to 10 (directly answers the query). Reply ONLY with a JSON array "
            "of numbers, one per passage, in order. Example: [7, 3, 9, 2]\n\n"
            f"Query: {query}\n\n"
            f"Passages:\n{passages_text}"
        )

        response = await self._llm.ainvoke(prompt)
        raw = response.content if hasattr(response, "content") else str(response)
        return _parse_scores(raw, expected_count=len(results))


def _parse_scores(raw: str, expected_count: int) -> list[float]:
    """
    Parse LLM output like "[7, 3, 9, 2]" or "7, 3, 9, 2" into a float list.
    Returns a list of 1.0 (neutral) scores on any parse failure so the caller
    sees results in unchanged order rather than crashing.
    """
    # Extract the first JSON array found in the response
    m = re.search(r"\[([0-9,\s.]+)\]", raw)
    if m:
        try:
            scores = [float(x.strip()) for x in m.group(1).split(",") if x.strip()]
            if len(scores) == expected_count:
                return scores
        except ValueError:
            pass

    # Fallback: try comma-separated numbers anywhere in the text
    numbers = re.findall(r"\b(\d+(?:\.\d+)?)\b", raw)
    if len(numbers) >= expected_count:
        return [float(n) for n in numbers[:expected_count]]

    # Total fallback: neutral scores preserve original order
    return [1.0] * expected_count
