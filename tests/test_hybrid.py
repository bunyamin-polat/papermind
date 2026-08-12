"""RRF fusion, tested on known rankings rather than on the live index.

The arms are stubs here on purpose. Fusion is arithmetic over ranks, and the
question this file answers is whether that arithmetic is right — which is
answerable without Postgres, Elasticsearch, or an embedding model, and therefore
answerable in CI on a fork pull request.

`tests/test_hybrid_live.py` covers the wiring against real services; this covers
the part where a subtle mistake would still return plausible papers.
"""

import pytest

from retrieval.backends.base import Query, Result
from retrieval.backends.hybrid import HybridBackend

QUERY = Query(text="anything", vector=None)


def paper(paper_id: str, distance: float | None = None) -> Result:
    return Result(
        paper_id=paper_id,
        title=f"title {paper_id}",
        abstract=f"abstract {paper_id}",
        url=f"https://arxiv.org/abs/{paper_id}",
        distance=distance,
    )


class Stub:
    """A backend that returns a fixed ranking."""

    def __init__(self, ids: list[str], with_distance: bool = False) -> None:
        self.results = [
            paper(pid, distance=0.1 * (i + 1) if with_distance else None)
            for i, pid in enumerate(ids)
        ]

    def search(self, query: Query, k: int) -> list[Result]:
        return self.results[:k]

    def health(self) -> dict:
        return {"stub": True}


class Broken:
    def search(self, query: Query, k: int) -> list[Result]:
        raise RuntimeError("search is down")

    def health(self) -> dict:
        return {"reachable": False}


def fuse(dense: list[str], lexical: list[str], k: int = 5, rrf_k: int = 60) -> list[str]:
    backend = HybridBackend(Stub(dense), Stub(lexical), pool=50, rrf_k=rrf_k)
    return [r.paper_id for r in backend.search(QUERY, k)]


def test_agreement_beats_a_single_strong_opinion():
    """The whole reason to fuse: two arms liking a paper outweighs one loving it.

    `b` is second in both lists and wins. `a` is first in one and absent from the
    other, and loses. If this ever inverts, fusion has become a rename of
    whichever arm is listed first.
    """
    assert fuse(["a", "b"], ["z", "b"])[0] == "b"


def test_a_paper_only_one_arm_found_still_surfaces():
    """Lexical-only hits are the point of adding lexical at all."""
    assert "z" in fuse(["a", "b", "c"], ["z"])


def test_rank_order_within_one_arm_is_preserved_when_the_other_is_empty():
    assert fuse(["a", "b", "c"], []) == ["a", "b", "c"]


def test_exactly_reversed_rankings_produce_a_dead_tie():
    """Two arms in perfect disagreement must cancel, and this is the sharpest
    available proof that fusion reads positions rather than the arms' numbers.

    `a` and `c` are mirror images — first in one arm, last in the other — so they
    must score *identically*: 1/61 + 1/63 against 1/63 + 1/61. The dense stub
    carries distances and the lexical stub does not, so if either number leaked
    into the sum the mirror would break and one of them would come first. That is
    the mistake ranks exist to prevent.

    `b` is second in both and scores 2/62, which is **lower** — because 1/x is
    convex, so the extremes beat the middle. That is the opposite of the
    agreement-beats-a-single-opinion case above, and both are correct: agreement
    wins when the disagreement is partial, and cancels exactly when it is total.

    (Two earlier versions of this test asserted the wrong thing — first that `c`
    wins, then that all three tie. The arithmetic was right both times and the
    expectation was not. A test is as likely to be wrong as the code, and here it
    was wrong twice in a row.)
    """
    backend = HybridBackend(Stub(["a", "b", "c"], with_distance=True), Stub(["c", "b", "a"]))
    scores = {r.paper_id: r.score for r in backend.search(QUERY, 3)}
    assert scores["a"] == pytest.approx(scores["c"]), "mirrored ranks must score identically"
    assert scores["b"] < scores["a"], "1/x is convex: the extremes beat the middle"


def test_fused_score_is_the_reciprocal_rank_sum():
    backend = HybridBackend(Stub(["a"]), Stub(["a"]), pool=50, rrf_k=60)
    (result,) = backend.search(QUERY, 1)
    assert result.score == pytest.approx(2 / 61)


def test_a_dead_lexical_arm_degrades_to_dense_instead_of_failing():
    """A search outage must cost quality, not availability — dense alone was the
    baseline for the whole project and remains a correct answer."""
    backend = HybridBackend(Stub(["a", "b"]), Broken(), pool=50)
    assert [r.paper_id for r in backend.search(QUERY, 5)] == ["a", "b"]


def test_the_distance_survives_fusion_for_papers_dense_found():
    """The UI renders distance, and the lexical arm has none to give. A paper both
    arms returned must keep the number rather than the None."""
    backend = HybridBackend(Stub(["a"], with_distance=True), Stub(["a"]), pool=50)
    (result,) = backend.search(QUERY, 1)
    assert result.distance == pytest.approx(0.1)
