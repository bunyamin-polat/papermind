"""Reciprocal Rank Fusion of dense and lexical retrieval.

**Fusion happens on ranks, not scores.** A cosine distance runs 0 to 2 where
small is good; a BM25 score runs 0 to whatever the corpus statistics produce
where large is good. They are different units with different distributions, and
averaging them yields a number that means nothing — the only reason it looks like
it works is that the result is still an ordering, and any ordering looks
plausible when you cannot see the right one.

RRF sidesteps the problem entirely by throwing the scores away:

    score(d) = sum over arms of  1 / (K + rank of d in that arm)

A paper ranked 1st by one arm and absent from the other scores 1/61. A paper
ranked 3rd by both scores 2/63 — more. That is the behaviour worth having: the
fused ranking prefers papers that *both* strategies liked over papers that one
strategy loved, because agreement between two different failure modes is
evidence and a single strong opinion is not.

K = 60 comes from the original paper (Cormack et al., 2009). It flattens the
difference between the top few ranks: without it, rank 1 would score 1.0 against
rank 2's 0.5, and a single arm's first choice would win every fusion outright.
"""

from __future__ import annotations

from collections import defaultdict

from retrieval.backends.base import Backend, Query, Result

#: The RRF constant. Larger flattens the contribution of top ranks further.
K = 60

#: How deep each arm is asked to go before fusing. Fusing only the top k would
#: throw away the case this exists for: a paper the dense arm ranked 12th and the
#: lexical arm ranked 2nd should surface, and it cannot if neither list is long
#: enough to contain it.
POOL = 50


class HybridBackend:
    """Two retrievers, one ranking."""

    def __init__(self, dense: Backend, lexical: Backend, pool: int = POOL, rrf_k: int = K) -> None:
        self.dense = dense
        self.lexical = lexical
        self.pool = pool
        self.rrf_k = rrf_k

    def search(self, query: Query, k: int) -> list[Result]:
        arms = {"dense": self.dense.search(query, self.pool)}
        try:
            arms["lexical"] = self.lexical.search(query, self.pool)
        except Exception:  # noqa: BLE001
            # One arm down degrades to the other rather than failing the query.
            # Dense alone is the previous baseline, so this is a worse answer and
            # not a broken one — and `health()` reports the truth either way.
            arms["lexical"] = []

        scores: dict[str, float] = defaultdict(float)
        seen: dict[str, Result] = {}
        for results in arms.values():
            for rank, result in enumerate(results, start=1):
                scores[result.paper_id] += 1.0 / (self.rrf_k + rank)
                # Keep whichever arm saw it first, but prefer a copy that carries a
                # distance: the UI shows it, and the lexical arm has none to give.
                if result.paper_id not in seen or (
                    seen[result.paper_id].distance is None and result.distance is not None
                ):
                    seen[result.paper_id] = result

        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)[:k]
        return [
            Result(
                paper_id=paper_id,
                title=seen[paper_id].title,
                abstract=seen[paper_id].abstract,
                url=seen[paper_id].url,
                distance=seen[paper_id].distance,
                score=fused,
            )
            for paper_id, fused in ranked
        ]

    def health(self) -> dict:
        dense = self.dense.health()
        return {
            "backend": "hybrid",
            # Surfaced at the top level because `/health` reports corpus size and
            # must not need to know which backend is configured to find it. A
            # health endpoint that breaks when the strategy changes is the thing
            # it exists to catch.
            "papers": dense.get("papers"),
            "embeddings": dense.get("embeddings"),
            "rrf_k": self.rrf_k,
            "pool": self.pool,
            "dense": dense,
            "lexical": self.lexical.health(),
        }
