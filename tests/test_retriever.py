"""Retrieval. The tests that need Postgres skip cleanly when it is not running,
so `pytest` still passes on a fresh clone before `docker compose up`."""

import pytest

from core.config import settings
from retrieval import retriever
from retrieval.backends import postgres


@pytest.fixture(scope="module")
def conn():
    psycopg = pytest.importorskip("psycopg")
    try:
        c = postgres.connect()
    except psycopg.OperationalError as exc:
        pytest.skip(f"database not reachable: {exc}")
    if c.execute("SELECT count(*) FROM embeddings").fetchone()[0] == 0:
        pytest.skip("corpus not embedded — run `python -m ingestion.embed`")
    yield c
    c.close()


def test_search_sql_filters_by_model():
    """Without the model filter, a corpus embedded twice would return neighbours
    from two different vector spaces mixed together."""
    sql = " ".join(postgres.SEARCH.split())
    assert "WHERE e.model = %s" in sql


def test_search_orders_by_distance_not_by_id():
    sql = " ".join(postgres.SEARCH.split())
    assert "ORDER BY e.embedding <=> %s" in sql


def test_connection_sets_ef_search_explicitly(conn):
    """pgvector's default is 40, the single value at which the planner abandons
    the index. Leaving it unset is the bug this asserts against."""
    assert conn.execute("SHOW hnsw.ef_search").fetchone()[0] == str(settings.hnsw_ef_search)
    assert settings.hnsw_ef_search != 40


def test_query_plan_actually_uses_the_index(conn):
    """The regression this catches is invisible in the results.

    A sequential scan returns exactly the same papers in exactly the same order —
    just 19x slower. No error, no warning, nothing to notice in output. Only the
    plan shows it, so the plan is what gets asserted.
    """
    vector = retriever._model().encode("attention mechanism", normalize_embeddings=True)
    rows = conn.execute(
        "EXPLAIN " + postgres.SEARCH,
        (vector, settings.embedding_model, vector, retriever.DEFAULT_K),
    ).fetchall()
    plan = "\n".join(r[0] for r in rows)
    assert "embeddings_hnsw_idx" in plan, f"planner did not use the HNSW index:\n{plan}"


def test_search_returns_k_results_closest_first(conn):
    results = retriever.search("neural machine translation", k=5)
    assert len(results) == 5
    # Ordering is by whatever the configured backend ranks by. Dense returns
    # ascending distance; hybrid returns descending RRF score and its distances
    # are in no particular order — asserting distance order here would be
    # asserting that the default backend is dense, which it is not.
    if results[0].score is not None:
        assert [r.score for r in results] == sorted((r.score for r in results), reverse=True)
    else:
        assert [r.distance for r in results] == sorted(r.distance for r in results)


def test_every_result_carries_a_resolvable_citation(conn):
    """A citation that cannot be followed is decoration. `url` is a generated
    column derived from `id`, so this asserts the two cannot drift apart."""
    for result in retriever.search("graph neural networks", k=5):
        assert result.url == f"https://arxiv.org/abs/{result.paper_id}"
        assert result.title and result.abstract


def test_on_topic_ranks_closer_than_off_topic(conn):
    """The property step 6 will turn into a refusal: an unanswerable question
    lands measurably further away than an answerable one."""
    on_topic = retriever.search("transformer attention mechanism", k=5)
    off_topic = retriever.search("how do you bake sourdough bread", k=5)
    assert on_topic[0].distance < off_topic[0].distance


def test_model_mismatch_is_detected(conn, monkeypatch):
    """Embedding a question with a different model than the corpus is the failure
    that produces no error — so it is made into one."""
    monkeypatch.setattr(settings, "embedding_model", "some/other-model")
    with pytest.raises(retriever.ModelMismatch):
        postgres.check_corpus(conn)
