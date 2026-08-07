"""Which vector index, and why — measured rather than assumed.

Timing is taken from the server (EXPLAIN ANALYZE "Execution Time"), not from the
client. Client-side wall clock on this path is dominated by psycopg's prepared-
statement caching, which kicks in after five executions and produced numbers that
contradicted each other across runs.

Recall is measured against exact search, because an approximate index that is fast
and wrong is worse than a slow one that is right.

The ef_search sweep exists because of what it found: pgvector 0.8.6's HNSW cost
estimate is non-monotonic, and the planner abandons the index at exactly
ef_search = 40 — which is pgvector's own default. Leave the setting alone and you
get the one value that does not work.

Run:  uv run python -m scripts.bench_index
"""

import re
import statistics as st
import time

import psycopg
from pgvector.psycopg import register_vector
from sentence_transformers import SentenceTransformer

from core.config import settings

QUERIES = [
    "attention mechanism in transformers", "contrastive self-supervised learning",
    "graph neural network for molecules", "diffusion model image generation",
    "retrieval augmented generation", "federated learning privacy",
    "reinforcement learning from human feedback", "speech recognition end to end",
    "neural architecture search", "adversarial robustness certification",
    "multi agent coordination", "medical image segmentation",
]
K = 5
SQL = "SELECT paper_id FROM embeddings ORDER BY embedding <=> %s LIMIT 5"


def measure(conn, vectors, truth):
    times, recalls, used_index = [], [], 0
    for vec, exact in zip(vectors, truth, strict=True):
        rows = conn.execute("EXPLAIN (ANALYZE, TIMING ON) " + SQL, (vec,)).fetchall()
        plan = "\n".join(r[0] for r in rows)
        times.append(float(re.search(r"Execution Time: ([\d.]+) ms", plan).group(1)))
        used_index += "Index Scan" in plan
        got = [r[0] for r in conn.execute(SQL, (vec,)).fetchall()]
        recalls.append(len(set(got) & set(exact)) / K)
    return st.median(times), max(times), st.mean(recalls) * 100, used_index


def main() -> None:
    model = SentenceTransformer(settings.embedding_model)
    vectors = [model.encode(q, normalize_embeddings=True) for q in QUERIES]

    with psycopg.connect(settings.database_url, autocommit=True) as conn:
        register_vector(conn)
        conn.execute("SET max_parallel_workers_per_gather = 0")
        conn.execute("SET maintenance_work_mem = '512MB'")
        conn.execute("DROP INDEX IF EXISTS emb_hnsw")
        conn.execute("DROP INDEX IF EXISTS emb_ivf")

        truth = [[r[0] for r in conn.execute(SQL, (v,)).fetchall()] for v in vectors]
        n = conn.execute("SELECT count(*) FROM embeddings").fetchone()[0]
        print(f"{n:,} vectors x {settings.embedding_dim} dims, top-{K}\n")
        print(f"{'configuration':<26}{'median':>9}{'p95':>9}{'recall':>9}   index used")

        med, p95, rec, used = measure(conn, vectors, truth)
        n_q = len(QUERIES)
        print(f"{'no index (exact)':<26}{med:8.1f}ms{p95:8.1f}ms{rec:8.1f}%   {used}/{n_q}")

        specs = [
            ("HNSW", "emb_hnsw",
             "CREATE INDEX emb_hnsw ON embeddings USING hnsw (embedding vector_cosine_ops)",
             "hnsw.ef_search", [5, 10, 20, 30, 40, 50, 64, 100, 200]),
            ("IVFFlat", "emb_ivf",
             "CREATE INDEX emb_ivf ON embeddings USING ivfflat "
             "(embedding vector_cosine_ops) WITH (lists = 173)",
             "ivfflat.probes", [10, 20, 40]),
        ]
        for name, index, ddl, knob, values in specs:
            started = time.perf_counter()
            conn.execute(ddl)
            build = time.perf_counter() - started
            size = conn.execute(f"SELECT pg_size_pretty(pg_relation_size('{index}'))").fetchone()[0]
            conn.execute("ANALYZE embeddings")
            for v in vectors:  # warm the index before timing it
                conn.execute(SQL, (v,)).fetchall()

            print(f"\n{name}  built in {build:.1f}s, {size}")
            for value in values:
                conn.execute(f"SET {knob} = {value}")
                med, p95, rec, used = measure(conn, vectors, truth)
                label = f"  {knob.split('.')[1]}={value}"
                print(f"{label:<26}{med:8.1f}ms{p95:8.1f}ms{rec:8.1f}%   {used}/{n_q}")
            conn.execute(f"DROP INDEX {index}")


if __name__ == "__main__":
    main()
