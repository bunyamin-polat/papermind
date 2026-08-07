"""Step 2 — embed every abstract and store the vector in pgvector.

No chunking. That was measured, not assumed: with a 512-token window, 3,999 of
4,000 abstracts fit whole (median 206 tokens, p99 394, max 541). Splitting a
206-token abstract would cut apart context that belongs together and buy nothing.

The original plan used `all-MiniLM-L6-v2`, which has a 256-token window and would
have truncated 26% of the corpus — losing ~15% of the text in each, with no error
raised anywhere. Widening the window was the fix; chunking would only have hidden
the problem behind more machinery.

Run:  uv run python -m ingestion.embed
"""

import argparse
import time

import psycopg
from pgvector.psycopg import register_vector

from core.config import settings
from storage import db

SELECT_UNEMBEDDED = """
    SELECT p.id, p.title, p.abstract
    FROM papers p
    LEFT JOIN embeddings e ON e.paper_id = p.id AND e.model = %s
    WHERE e.paper_id IS NULL
    ORDER BY p.id
"""

INSERT = """
    INSERT INTO embeddings (paper_id, model, embedding)
    VALUES (%s, %s, %s)
    ON CONFLICT (paper_id, model) DO UPDATE SET
        embedding  = EXCLUDED.embedding,
        created_at = now()
"""


def to_document(title: str, abstract: str) -> str:
    """What actually gets embedded.

    Title and abstract together, because a question often echoes title wording that
    the abstract never repeats ("attention is all you need" vs an abstract that only
    says "we propose a new architecture"). Both fit inside the window with room to
    spare, so including the title costs nothing.
    """
    return f"{title.strip()}\n\n{abstract.strip()}"


def embed(batch_size: int | None = None, limit: int | None = None) -> int:
    from sentence_transformers import SentenceTransformer

    model_name = settings.embedding_model
    batch_size = batch_size or settings.embedding_batch_size

    db.init_schema()

    with psycopg.connect(settings.database_url) as conn:
        register_vector(conn)
        rows = conn.execute(SELECT_UNEMBEDDED, (model_name,)).fetchall()
        if limit:
            rows = rows[:limit]

        if not rows:
            print(f"nothing to do — every paper already embedded with {model_name}")
            return 0

        print(f"embedding {len(rows):,} papers with {model_name}")
        model = SentenceTransformer(model_name)
        print(f"  device={model.device}  window={model.max_seq_length} tokens")

        started = time.perf_counter()
        done = 0
        # Committed per batch, so an interrupted run keeps everything already done
        # and the next run picks up exactly where it stopped — the LEFT JOIN above
        # is what makes resuming free.
        for i in range(0, len(rows), batch_size):
            batch = rows[i : i + batch_size]
            vectors = model.encode(
                [to_document(title, abstract) for _, title, abstract in batch],
                batch_size=batch_size,
                normalize_embeddings=True,  # cosine distance becomes a dot product
                show_progress_bar=False,
            )
            pairs = zip(batch, vectors, strict=True)
            with conn.cursor() as cur:
                cur.executemany(INSERT, [(pid, model_name, v) for (pid, _, _), v in pairs])
            conn.commit()

            done += len(batch)
            rate = done / (time.perf_counter() - started)
            eta = (len(rows) - done) / rate
            print(f"  {done:,}/{len(rows):,}  {rate:.0f}/s  eta {eta / 60:.1f}m", end="\r")

        elapsed = time.perf_counter() - started
        print(f"\nembedded {done:,} papers in {elapsed / 60:.1f}m ({done / elapsed:.0f}/s)")
        return done


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-size", type=int, default=None)
    parser.add_argument("--limit", type=int, default=None, help="embed only N papers (for testing)")
    args = parser.parse_args()
    embed(args.batch_size, args.limit)


if __name__ == "__main__":
    main()
