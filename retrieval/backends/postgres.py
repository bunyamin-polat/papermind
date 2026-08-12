"""The development backend: pgvector with an HNSW index.

This is where the corpus is built and where it can change. Adding papers is an insert
and a re-index rather than regenerating an artifact, and everything is queryable with
SQL — which is how the sampling bugs in step 1 were found at all.
"""

import psycopg
from pgvector.psycopg import register_vector

from core.config import settings
from retrieval.backends.base import Query, Result

SEARCH = """
    SELECT p.id, p.title, p.abstract, p.url, e.embedding <=> %s AS distance
    FROM embeddings e
    JOIN papers p ON p.id = e.paper_id
    WHERE e.model = %s
    ORDER BY e.embedding <=> %s
    LIMIT %s
"""


class ModelMismatch(RuntimeError):
    """The corpus was embedded with a different model than the one configured.

    The failure this prevents produces no error and no crash — just quietly meaningless
    neighbours, because the question and the corpus live in different vector spaces.
    """


class NotConfigured(RuntimeError):
    """This backend was selected but has no credentials.

    The database settings carry defaults so the memory backend can run without them.
    That convenience has to be paid for here: selecting Postgres without a password is a
    configuration error, and it should say so rather than fail later inside psycopg with
    a message about authentication.
    """


def connect() -> psycopg.Connection:
    if not settings.postgres_password:
        raise NotConfigured(
            "RETRIEVAL_BACKEND=postgres but POSTGRES_PASSWORD is empty. "
            "Set it, or use RETRIEVAL_BACKEND=memory with a built artifact."
        )
    conn = psycopg.connect(settings.database_url)
    register_vector(conn)
    # Explicit, never left to the server default. pgvector's default ef_search is 40,
    # and 40 is the one value at which the planner drops the index for a sequential
    # scan: 19x slower, no error. See scripts/bench_index.py.
    conn.execute(f"SET hnsw.ef_search = {settings.hnsw_ef_search}")
    return conn


def check_corpus(conn: psycopg.Connection) -> None:
    models = [r[0] for r in conn.execute("SELECT DISTINCT model FROM embeddings")]
    if not models:
        raise ModelMismatch("no embeddings — run `python -m ingestion.embed` first")
    if settings.embedding_model not in models:
        raise ModelMismatch(
            f"corpus embedded with {models}, but configured model is "
            f"{settings.embedding_model!r}. Embedding a question with a different model "
            f"than the corpus returns neighbours that mean nothing."
        )


class PostgresBackend:
    name = "postgres"

    def search(self, query: Query, k: int) -> list[Result]:
        vector = query.vector
        with connect() as conn:
            check_corpus(conn)
            rows = conn.execute(SEARCH, (vector, settings.embedding_model, vector, k)).fetchall()

        return [
            Result(paper_id=pid, title=t, abstract=a, url=u, distance=float(d))
            for pid, t, a, u, d in rows
        ]

    def health(self) -> dict:
        with connect() as conn:
            papers = conn.execute("SELECT count(*) FROM papers").fetchone()[0]
            embeddings = conn.execute(
                "SELECT count(*) FROM embeddings WHERE model = %s", (settings.embedding_model,)
            ).fetchone()[0]
        return {"backend": self.name, "papers": papers, "embeddings": embeddings}
