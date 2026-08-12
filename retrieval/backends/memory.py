"""The deployment backend: the whole corpus in memory, searched by matrix multiply.

30,061 vectors of 768 float32 is 92 MB. One dot product against all of them and a
partial sort takes 2.9 ms — faster than the same query through pgvector with an HNSW
index, because at this size the index is overhead rather than help.

Vectors are stored normalised, so cosine distance is `1 - dot`. Nothing here builds an
index, and that is the point: an artifact with no index cannot have an index the query
planner quietly stops using.
"""

import json
from functools import lru_cache
from pathlib import Path

import numpy as np

from core.config import settings
from retrieval.backends.base import Query, Result

ARTIFACT_DIR = Path(settings.artifact_dir)
VECTORS = "vectors.npy"
PAPERS = "papers.parquet"
MANIFEST = "manifest.json"


class ArtifactMissing(RuntimeError):
    pass


class ArtifactMismatch(RuntimeError):
    """Built with a different embedding model than the one configured.

    Same failure the Postgres backend guards against, and just as silent: the query and
    the corpus would be embedded into different vector spaces and the results would look
    like results.
    """


@lru_cache(maxsize=1)
def _load(directory: str = None):
    """Read once per process. At startup, not on the first request."""
    import pandas as pd

    root = Path(directory) if directory else ARTIFACT_DIR
    if not (root / VECTORS).exists():
        raise ArtifactMissing(
            f"no corpus artifact at {root}. Build one with "
            f"`python -m scripts.build_artifact` against a populated database."
        )

    manifest = json.loads((root / MANIFEST).read_text())
    if manifest["embedding_model"] != settings.embedding_model:
        raise ArtifactMismatch(
            f"artifact was built with {manifest['embedding_model']!r}, configured model "
            f"is {settings.embedding_model!r}"
        )

    vectors = np.load(root / VECTORS)
    papers = pd.read_parquet(root / PAPERS)
    if len(vectors) != len(papers):
        raise ArtifactMismatch(f"{len(vectors)} vectors but {len(papers)} papers")

    return vectors, papers, manifest


class MemoryBackend:
    name = "memory"

    def search(self, query: Query, k: int) -> list[Result]:
        vectors, papers, _ = _load()
        vector = np.asarray(query.vector, dtype=np.float32)

        # Both sides are normalised, so the dot product is cosine similarity and
        # `1 - similarity` is the same distance pgvector's `<=>` returns.
        similarity = vectors @ vector

        # argpartition finds the top k without sorting 30,000 elements; only the k
        # survivors are ordered.
        top = np.argpartition(-similarity, min(k, len(similarity) - 1))[:k]
        top = top[np.argsort(-similarity[top])]

        return [
            Result(
                paper_id=papers.iat[i, papers.columns.get_loc("id")],
                title=papers.iat[i, papers.columns.get_loc("title")],
                abstract=papers.iat[i, papers.columns.get_loc("abstract")],
                url=papers.iat[i, papers.columns.get_loc("url")],
                distance=float(1.0 - similarity[i]),
            )
            for i in top
        ]

    def health(self) -> dict:
        vectors, papers, manifest = _load()
        return {
            "backend": self.name,
            "papers": len(papers),
            "embeddings": len(vectors),
            "artifact_built_on": manifest.get("built_on"),
        }
