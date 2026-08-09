"""Freeze the corpus into files the deployed instance can load without a database.

Reads from Postgres, writes three files:

    vectors.npy     float32 (N, 768), normalised, in the same row order as papers
    papers.parquet  id, title, abstract, url
    manifest.json   what built it, when, and with which embedding model

At 30,061 papers that is 92 MB of vectors and 23 MB of text. Bundled into the image it
removes an RDS instance, a VPC and a NAT gateway from the deployment — about $45 a
month to serve a database that measured slower than a dot product.

The manifest exists so the two halves cannot drift apart silently: the memory backend
refuses to load an artifact built with an embedding model other than the configured one,
which is the same guard the Postgres backend has and the same failure it prevents.

Run:  uv run python -m scripts.build_artifact
"""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from core.config import settings
from retrieval.backends.postgres import connect

# Ordered by id so the artifact is byte-identical across rebuilds of the same corpus.
QUERY = """
    SELECT p.id, p.title, p.abstract, p.url, e.embedding::text AS vector
    FROM embeddings e
    JOIN papers p ON p.id = e.paper_id
    WHERE e.model = %s
    ORDER BY p.id
"""


def build(out_dir: Path) -> None:
    with connect() as conn:
        rows = conn.execute(QUERY, (settings.embedding_model,)).fetchall()

    if not rows:
        raise SystemExit(
            f"no embeddings for {settings.embedding_model!r} — "
            f"run `python -m ingestion.embed` first"
        )

    papers = pd.DataFrame(
        [{"id": r[0], "title": r[1], "abstract": r[2], "url": r[3]} for r in rows]
    )
    vectors = np.asarray(
        [np.fromstring(r[4][1:-1], sep=",", dtype=np.float32) for r in rows],
        dtype=np.float32,
    )

    # They are written normalised by ingestion.embed, but an artifact that quietly
    # contained unnormalised vectors would return plausible, subtly wrong neighbours —
    # so it is checked here rather than assumed.
    norms = np.linalg.norm(vectors, axis=1)
    if not np.allclose(norms, 1.0, atol=1e-3):
        raise SystemExit(
            f"vectors are not normalised (min {norms.min():.4f}, max {norms.max():.4f}); "
            f"the memory backend treats the dot product as cosine similarity"
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    np.save(out_dir / "vectors.npy", vectors)
    papers.to_parquet(out_dir / "papers.parquet", index=False)
    (out_dir / "manifest.json").write_text(
        json.dumps(
            {
                "built_on": datetime.now(UTC).date().isoformat(),
                "embedding_model": settings.embedding_model,
                "papers": len(papers),
                "dimensions": int(vectors.shape[1]),
            },
            indent=2,
        )
    )

    size = sum(f.stat().st_size for f in out_dir.iterdir()) / 1e6
    print(f"{len(papers):,} papers x {vectors.shape[1]} dims -> {out_dir}  ({size:.0f} MB)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path(settings.artifact_dir))
    build(parser.parse_args().out)


if __name__ == "__main__":
    main()
