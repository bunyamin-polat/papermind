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
class Result:
    paper_id: str
    title: str
    abstract: str
    url: str
    distance: float  # cosine distance: 0 is identical, 2 is opposite


class Backend(Protocol):
    """Both backends implement exactly this."""

    def search(self, vector, k: int) -> list[Result]:
        """The k nearest papers to an already-embedded query, closest first."""
        ...

    def health(self) -> dict:
        """Enough to tell whether this backend can answer, and with what."""
        ...
