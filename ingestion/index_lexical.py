"""Step 10a — build the BM25 index from the corpus already in Postgres.

Postgres stays the source of truth. This is a derived index, rebuilt from it in
minutes, which is why the compose service runs without security or persistence
worth protecting: losing it costs one command.

Run:  uv run python -m ingestion.index_lexical
      uv run python -m ingestion.index_lexical --rebuild   # drop and start over
"""

import argparse
import json
import time

from retrieval.backends.lexical import INDEX, SearchUnavailable, _request
from storage.db import connection

#: Documents per bulk request. Large enough that HTTP overhead disappears, small
#: enough that one failure does not cost minutes of work.
BATCH = 1000

#: The analyzer decides what counts as a term, which is most of what BM25 *is*.
MAPPING = {
    "mappings": {
        "properties": {
            # The arXiv id, searchable as one term. `english` stemming would
            # shred it, so it is a keyword: `2406.17831` must match as itself and
            # not as three numbers with punctuation between them. Without this
            # field the id exists only as Elasticsearch's `_id`, which
            # `multi_match` does not search — an identifier lookup then returns
            # nothing at all, which is worse than the dense failure it was added
            # to fix.
            "id": {"type": "keyword"},
            "title": {"type": "text", "analyzer": "english"},
            # Author search is only possible through the lexical arm: a name
            # carries no meaning to embed, so dense retrieval cannot answer
            # "papers by Yoshua Bengio" at all. Analysed as text rather than
            # keyword so a surname matches inside a full author list.
            "authors": {"type": "text", "analyzer": "standard"},
            "abstract": {"type": "text", "analyzer": "english"},
            "url": {"type": "keyword", "index": False},
        }
    },
    "settings": {"number_of_shards": 1, "number_of_replicas": 0},
}


def build(rebuild: bool = False) -> int:
    if rebuild:
        try:
            _request("DELETE", f"/{INDEX}")
            print(f"dropped index {INDEX}")
        except SearchUnavailable:
            pass  # not existing is the state we wanted

    try:
        _request("GET", f"/{INDEX}")
        print(f"index {INDEX} exists; re-indexing over it (documents are upserted by id)")
    except SearchUnavailable:
        _request("PUT", f"/{INDEX}", MAPPING)
        print(f"created index {INDEX}")

    with connection() as conn, conn.cursor() as cur:
        cur.execute("select count(*) from papers")
        total = cur.fetchone()[0]
        cur.execute("select id, title, abstract, url, authors from papers")
        rows = cur.fetchall()

    started = time.perf_counter()
    written = 0
    for start in range(0, len(rows), BATCH):
        batch = rows[start : start + BATCH]
        # The bulk format is newline-delimited pairs: an action line, then the
        # document. `index` upserts on the id, so re-running replaces rather than
        # duplicating — the same property `clean` has, for the same reason.
        lines = []
        for paper_id, title, abstract, url, authors in batch:
            lines.append(json.dumps({"index": {"_index": INDEX, "_id": paper_id}}))
            lines.append(
                json.dumps({"id": paper_id, "title": title, "abstract": abstract,
                            "authors": authors, "url": url})
            )
        _bulk("\n".join(lines) + "\n")
        written += len(batch)
        print(f"  {written:,}/{total:,}", end="\r")

    _request("POST", f"/{INDEX}/_refresh")
    elapsed = time.perf_counter() - started
    indexed = _request("GET", f"/{INDEX}/_count")["count"]
    print(f"  {written:,}/{total:,}        ")
    print(f"indexed {indexed:,} papers in {elapsed:.1f}s ({written / max(elapsed, 0.01):.0f}/s)")
    return indexed


def _bulk(payload: str) -> None:
    """Bulk needs ndjson, not JSON, so it bypasses the JSON helper."""
    import urllib.request

    from core.config import settings

    request = urllib.request.Request(
        f"{settings.elastic_host}/_bulk",
        data=payload.encode(),
        method="POST",
        headers={"Content-Type": "application/x-ndjson"},
    )
    with urllib.request.urlopen(request, timeout=settings.elastic_timeout_s) as response:
        body = json.loads(response.read())
    if body.get("errors"):
        first = next(
            (item["index"]["error"] for item in body["items"] if "error" in item.get("index", {})),
            None,
        )
        raise SearchUnavailable(f"bulk index reported errors, first: {first}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rebuild", action="store_true", help="drop the index first")
    args = parser.parse_args()
    build(rebuild=args.rebuild)


if __name__ == "__main__":
    main()
