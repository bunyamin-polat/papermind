"""Question in, papers out. One entry point, two backends behind it.

Which backend runs is `RETRIEVAL_BACKEND`: `postgres` while building the corpus,
`memory` in a deployed instance. Everything above this module — the API, the UI, the
evaluation harness — never asks which, so the same eval can measure both and
`tests/test_backend_parity.py` asserts they agree.

See `retrieval/backends/base.py` for why there are two.
"""

import functools

from core.config import settings
from retrieval.backends.base import Result
from retrieval.backends.memory import ArtifactMismatch, ArtifactMissing, MemoryBackend
from retrieval.backends.postgres import ModelMismatch, PostgresBackend

__all__ = [
    "DEFAULT_K",
    "ArtifactMismatch",
    "ArtifactMissing",
    "ModelMismatch",
    "Result",
    "backend",
    "health",
    "search",
]

# Measured at step 4 on 24 in-corpus questions, not guessed:
#
#   k = 1  →  hit-rate 88%,  MRR 0.875
#   k = 3  →  hit-rate 92%,  MRR 0.889
#   k = 5  →  hit-rate 92%,  MRR 0.889
#   k = 10 →  hit-rate 100%, MRR 0.903
#
# Retrieval latency is flat across k, but at step 5 each result becomes prompt context,
# where k is paid for in tokens. 3 and 5 measured identically and 24 questions cannot
# distinguish them, so 5 is kept for margin. k = 10 reaches 100%, but both misses sit at
# rank 6 — choosing k for them would be fitting to this particular set of questions.
DEFAULT_K = 5

_BACKENDS = {"postgres": PostgresBackend, "memory": MemoryBackend}


@functools.lru_cache(maxsize=1)
def backend():
    try:
        return _BACKENDS[settings.retrieval_backend]()
    except KeyError:
        raise ValueError(
            f"unknown RETRIEVAL_BACKEND {settings.retrieval_backend!r}; "
            f"expected one of {sorted(_BACKENDS)}"
        ) from None


@functools.lru_cache(maxsize=1)
def _model():
    """Loaded once. Instantiating a SentenceTransformer takes about eight seconds,
    which is fine at startup and not fine per request."""
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(settings.embedding_model)


def search(question: str, k: int = DEFAULT_K) -> list[Result]:
    """The k nearest papers to `question`, closest first."""
    vector = _model().encode(question, normalize_embeddings=True)
    return backend().search(vector, k)


def health() -> dict:
    """What the configured backend can say about itself."""
    return {**backend().health(), "embedding_model": settings.embedding_model}
