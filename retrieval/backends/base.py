"""What a retrieval backend is, and the one type everything above it speaks.

There are two backends because development and deployment want different things from
the same data, and measurement said so:

    brute-force numpy over 30,061 x 768   2.9 ms
    pgvector with an HNSW index           3.7 ms
    pgvector with no index               70.5 ms

At this corpus size the database is not faster. What Postgres genuinely buys is
everything *around* a query — SQL, incremental re-indexing, the ability to add papers
without rebuilding anything — and all of that matters while building the corpus and
none of it matters to a read-only deployed instance.

So Postgres stays the development backend and the deployed instance carries the vectors
in memory. That removed an RDS instance, a VPC and a NAT gateway from the deployment:
about $45 a month, to serve a database slower than a dot product.

The real risk of two implementations is that they drift apart and nobody notices,
because both keep returning plausible papers. `tests/test_backend_parity.py` runs the
evaluation questions through both and asserts identical results.
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Query:
    """A question in both the forms a backend might need.

    Dense search wants the vector; BM25 wants the words. Carrying both means the
    embedding is computed once per question rather than once per backend, and a
    hybrid backend can hand the same object to each arm without knowing which
    half either of them will use.
    """

    text: str
    vector: object  # np.ndarray, kept loose so this module imports no numpy


@dataclass(frozen=True)
class Result:
    paper_id: str
    title: str
    abstract: str
    url: str

    #: Cosine distance: 0 is identical, 2 is opposite. Dense backends only.
    distance: float | None = None

    #: Whatever the backend ranks by — a BM25 score, an RRF score. **Not
    #: comparable across backends**, which is the whole reason fusion happens on
    #: ranks rather than on these numbers.
    score: float | None = None


class Backend(Protocol):
    """Every retrieval strategy implements exactly this."""

    def search(self, query: Query, k: int) -> list[Result]:
        """The k best papers for a question, best first."""
        ...

    def health(self) -> dict:
        """Enough to tell whether this backend can answer, and with what."""
        ...
