"""Step 3 — question in, relevant papers out.

A hit is a whole paper, not a fragment: step 2 measured that abstracts fit the
embedding window intact, so nothing was chunked and nothing has to be stitched
back together. That keeps citation simple — every result already *is* the unit a
reader would want to open.
"""

import functools
from dataclasses import dataclass

import psycopg
from pgvector.psycopg import register_vector

from core.config import settings

# Measured at step 4 on 24 in-corpus questions, not guessed:
#
#   k = 1  →  hit-rate 88%,  MRR 0.875
#   k = 3  →  hit-rate 92%,  MRR 0.889
#   k = 5  →  hit-rate 92%,  MRR 0.889
#   k = 10 →  hit-rate 100%, MRR 0.903
#
# Latency is flat across k (~39 ms), so k costs nothing here — but at step 5 each
# result becomes prompt context, and there k is paid for in tokens.
#
# 3 and 5 measured identically; with 24 questions one question is 4 points, so the
# eval set cannot distinguish them. 5 is kept for margin. k = 10 reaches 100%, but
# both of the misses sit at rank 6 — choosing k for them would be fitting to this
# particular set of questions rather than to the problem. Revisit when the eval set
# is larger and token cost is real.
DEFAULT_K = 5

SEARCH = """
    SELECT p.id, p.title, p.abstract, p.url, e.embedding <=> %s AS distance
    FROM embeddings e
    JOIN papers p ON p.id = e.paper_id
    WHERE e.model = %s
    ORDER BY e.embedding <=> %s
    LIMIT %s
"""


@dataclass(frozen=True)
class Result:
    paper_id: str
    title: str
    abstract: str
    url: str
    distance: float  # cosine distance: 0 is identical, 2 is opposite


class ModelMismatch(RuntimeError):
    """The corpus was embedded with a different model than the one configured.

    This is the failure mode that produces no error and no crash — just quietly
    meaningless neighbours, because the question and the corpus live in different
    vector spaces. Checked at startup so it fails loudly instead.
    """


@functools.lru_cache(maxsize=1)
def _model():
    """Loaded once. Instantiating a SentenceTransformer takes seconds, which is
    fine at import time and not fine per request."""
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(settings.embedding_model)


def _connect() -> psycopg.Connection:
    conn = psycopg.connect(settings.database_url)
    register_vector(conn)
    # Explicit, never left to the server default. pgvector's default ef_search is
    # 40, and 40 is the one value at which the planner drops the index for a
    # sequential scan — 19x slower with no error. See scripts/bench_index.py.
    conn.execute(f"SET hnsw.ef_search = {settings.hnsw_ef_search}")
    return conn


def check_corpus(conn: psycopg.Connection) -> None:
    """Fail loudly if the corpus and the query would use different models."""
    models = [r[0] for r in conn.execute("SELECT DISTINCT model FROM embeddings")]
    if not models:
        raise ModelMismatch("no embeddings — run `python -m ingestion.embed` first")
    if settings.embedding_model not in models:
        raise ModelMismatch(
            f"corpus embedded with {models}, but configured model is "
            f"{settings.embedding_model!r}. Embedding a question with a different "
            f"model than the corpus returns neighbours that mean nothing."
        )


def search(question: str, k: int = DEFAULT_K) -> list[Result]:
    """The k nearest papers to `question`, closest first."""
    vector = _model().encode(question, normalize_embeddings=True)

    with _connect() as conn:
        check_corpus(conn)
        rows = conn.execute(
            SEARCH, (vector, settings.embedding_model, vector, k)
        ).fetchall()

    return [
        Result(paper_id=pid, title=title, abstract=abstract, url=url, distance=float(dist))
        for pid, title, abstract, url, dist in rows
    ]
