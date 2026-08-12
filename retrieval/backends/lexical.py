"""BM25 over Elasticsearch — the lexical half of hybrid retrieval.

Dense search is semantically strong and lexically blind. Two failures were
measured against this corpus rather than quoted from a blog post:

- Asked for `2406.06538` — a paper that *is* in the corpus — dense search does not
  return it in the top 20. An identifier carries no meaning to embed, so there is
  nothing for a vector to be near. BM25 finds it in one lookup.
- Asked for "papers that do NOT use transformers", the second dense result is
  *Simplifying Transformer Blocks*. Embeddings have no representation for
  negation: "not X" lands next to "X". BM25 does not fix this either, but it fails
  differently, and fusion is what turns two different failures into one better
  ranking.

**Why Elasticsearch and not Postgres full-text search.** Staying in one datastore
was the obvious alternative and it was not chosen: BM25 is what production systems
actually put in front of this problem, `2406.06538` is exactly the query it exists
for, and running the two engines side by side is what makes the comparison
publishable — dense alone, lexical alone, and fused, over the same questions.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from core.config import settings
from retrieval.backends.base import Query, Result

INDEX = "papers"


class SearchUnavailable(RuntimeError):
    """Elasticsearch is not reachable, or the index has not been built.

    Distinguished from an empty result on purpose: no papers found is an answer,
    and a search engine that is down is not.
    """


def _request(method: str, path: str, body: dict | None = None) -> dict:
    url = f"{settings.elastic_host}{path}"
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        url, data=data, method=method, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=settings.elastic_timeout_s) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as error:
        detail = error.read().decode()[:200]
        raise SearchUnavailable(f"{method} {path} returned {error.code}: {detail}") from error
    except urllib.error.URLError as error:
        raise SearchUnavailable(
            f"cannot reach Elasticsearch at {settings.elastic_host} ({error.reason}). "
            f"Start it with `docker compose up -d search`."
        ) from error


class LexicalBackend:
    """BM25. Ranks by term overlap, weighted by how rare each term is."""

    def search(self, query: Query, k: int) -> list[Result]:
        body = {
            "size": k,
            "query": {
                "multi_match": {
                    "query": query.text,
                    # Title carries more signal per word than the abstract — a term
                    # in a title is what the paper is *about*, the same term in an
                    # abstract may be one mention in passing. `id` is weighted
                    # hardest: a question containing an arXiv identifier is asking
                    # for that exact paper and nothing else.
                    "fields": ["id^10", "title^2", "abstract"],
                }
            },
        }
        hits = _request("POST", f"/{INDEX}/_search", body)["hits"]["hits"]
        return [
            Result(
                paper_id=hit["_id"],
                title=hit["_source"]["title"],
                abstract=hit["_source"]["abstract"],
                url=hit["_source"]["url"],
                # No distance: BM25 has no notion of one. Leaving it None rather
                # than inventing a number is what stops it being averaged with a
                # cosine distance somewhere downstream.
                score=float(hit["_score"]),
            )
            for hit in hits
        ]

    def health(self) -> dict:
        try:
            count = _request("GET", f"/{INDEX}/_count")["count"]
        except SearchUnavailable as error:
            return {"backend": "lexical", "reachable": False, "detail": str(error)[:120]}
        return {"backend": "lexical", "reachable": True, "papers": count}
