"""The two retrieval backends must return the same thing.

This is the guard that makes having two of them acceptable. Postgres serves development,
a numpy array serves the deployed instance, and the danger is not that one breaks — a
broken backend is loud. The danger is that they drift: both keep returning plausible
papers, in slightly different orders, and the deployed system quietly stops being the
system that was measured.

Every defect in this project's ledger had that shape. So the parity is asserted on the
real evaluation questions rather than on a synthetic vector, and it is asserted on the
identifiers and their order, not on "both returned five papers".
"""

import json
from pathlib import Path

import numpy as np
import pytest

from core.config import settings

ROOT = Path(__file__).parent.parent
K = 5


@pytest.fixture(scope="module")
def backends():
    """Both backends, or a skip. Needs Postgres up and an artifact built."""
    psycopg = pytest.importorskip("psycopg")
    pytest.importorskip("pandas")

    from retrieval.backends.memory import ArtifactMissing, MemoryBackend
    from retrieval.backends.postgres import PostgresBackend

    try:
        PostgresBackend().health()
    except psycopg.OperationalError as exc:
        pytest.skip(f"database not reachable: {exc}")

    memory = MemoryBackend()
    try:
        memory.health()
    except ArtifactMissing:
        pytest.skip("no artifact — run `python -m scripts.build_artifact`")

    return PostgresBackend(), memory


@pytest.fixture(scope="module")
def questions():
    path = ROOT / "evaluation" / "questions.jsonl"
    return [json.loads(line)["question"] for line in path.read_text().splitlines() if line.strip()]


@pytest.fixture(scope="module")
def vectors(questions):
    from retrieval.retriever import _model

    model = _model()
    return [model.encode(q, normalize_embeddings=True) for q in questions]


def test_both_backends_hold_the_same_corpus(backends):
    pg, memory = backends
    assert pg.health()["papers"] == memory.health()["papers"]
    assert pg.health()["embeddings"] == memory.health()["embeddings"]


def _exact_search(vector, k=K):
    """Postgres with the index disabled: the ground truth both backends approximate."""
    from retrieval.backends.postgres import connect

    with connect() as conn:
        conn.execute("SET enable_indexscan = off")
        rows = conn.execute(
            "SELECT p.id FROM embeddings e JOIN papers p ON p.id = e.paper_id "
            "WHERE e.model = %s ORDER BY e.embedding <=> %s LIMIT %s",
            (settings.embedding_model, vector, k),
        ).fetchall()
    return [r[0] for r in rows]


def test_memory_backend_is_exact(backends, questions, vectors):
    """The hard invariant: brute force must equal brute force.

    Compared against Postgres *with the index disabled*, not against HNSW. HNSW is an
    approximate index and is allowed to differ; numpy is not. Written the other way
    round first, this test failed — and the failure was the index being approximate,
    not the artifact being wrong.
    """
    _, memory = backends
    disagreements = []

    for question, vector in zip(questions, vectors, strict=True):
        exact = _exact_search(vector)
        from_memory = [r.paper_id for r in memory.search(vector, K)]
        if exact != from_memory:
            disagreements.append((question, exact, from_memory))

    assert not disagreements, "the artifact does not match exact search:\n" + "\n".join(
        f"  {q[:50]}\n    exact:  {a}\n    memory: {b}" for q, a, b in disagreements[:5]
    )


def test_hnsw_approximation_stays_within_bounds(backends, questions, vectors):
    """HNSW may miss results; it may not miss many.

    Measured across all 34 evaluation questions: 30 rankings identical to exact search,
    33 of 34 with the same top result, 96.5% overlap at k=5. An earlier benchmark over
    12 queries reported 100% recall at every ef_search setting — which was a property of
    that query set, not of the index. These floors sit just below what is measured, so a
    real degradation fails and normal variation does not.
    """
    pg, _ = backends
    same_top1 = 0
    overlap = 0.0

    for vector in vectors:
        exact = _exact_search(vector)
        approx = [r.paper_id for r in pg.search(vector, K)]
        same_top1 += exact[0] == approx[0]
        overlap += len(set(exact) & set(approx)) / K

    assert same_top1 / len(vectors) >= 0.90, f"top-1 agreement fell to {same_top1}/{len(vectors)}"
    assert overlap / len(vectors) >= 0.90, f"overlap@{K} fell to {overlap / len(vectors):.1%}"


def test_both_backends_report_the_same_distances(backends, vectors):
    """`<=>` in pgvector and `1 - dot` in numpy must agree, or the refusal threshold
    measured against one does not hold for the other."""
    pg, memory = backends

    for vector in vectors[:10]:
        from_pg = [r.distance for r in pg.search(vector, K)]
        from_memory = [r.distance for r in memory.search(vector, K)]
        assert np.allclose(from_pg, from_memory, atol=1e-5), (
            f"distances differ: {from_pg} vs {from_memory}"
        )


def test_memory_backend_refuses_an_artifact_from_another_model(backends, monkeypatch):
    """Same guard the Postgres backend has, against the same silent failure: a query
    embedded by one model searched against a corpus embedded by another."""
    from retrieval.backends import memory as memory_module

    memory_module._load.cache_clear()
    monkeypatch.setattr(settings, "embedding_model", "some/other-model")
    with pytest.raises(memory_module.ArtifactMismatch):
        memory_module.MemoryBackend().health()
    memory_module._load.cache_clear()
