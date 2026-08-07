"""A thin client for the arXiv Atom API.

Chosen over a HuggingFace snapshot because a snapshot has an end date. The
`gfissore/arxiv-abstracts-2021` dump stops in December 2021, which would leave a
corpus that cannot answer anything about work published since — the majority of
what anyone would ask an AI-research assistant today. This queries arXiv itself,
so the corpus reaches the present and can be refreshed by re-running.

API terms ask for no more than one request every three seconds. That limit is
respected here and is not configurable, because ignoring it is how a client gets
blocked for everybody.

Docs: https://info.arxiv.org/help/api/user-manual.html
"""

import calendar
import random
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass

API = "https://export.arxiv.org/api/query"
ATOM = "{http://www.w3.org/2005/Atom}"
OPENSEARCH = "{http://a9.com/-/spec/opensearch/1.1/}"

# arXiv's published terms say one request every three seconds. Their *unpublished*
# behaviour is stricter: sustained querying earns a soft block where the endpoint
# accepts the TCP connection and then never answers. Four seconds costs a few extra
# minutes on a full fetch and has not triggered it.
MIN_REQUEST_INTERVAL = 4.0
PAGE_SIZE = 200

# A soft block lasts minutes, not seconds. Backing off 6s/12s/24s and giving up —
# which is what the first version did — turns a temporary throttle into a failed run.
MAX_RETRIES = 6
THROTTLE_BACKOFF = [60, 180, 300, 600, 900]  # seconds, when rate-limited
USER_AGENT = "papermind/0.1 (https://github.com/bunyamin-polat/papermind)"

_last_request_at = 0.0


def _is_throttled(exc: Exception) -> bool:
    """429, or the silent stall arXiv uses instead of one."""
    if isinstance(exc, urllib.error.HTTPError) and exc.code in (429, 503):
        return True
    return isinstance(exc, TimeoutError | socket.timeout | urllib.error.URLError)


@dataclass(frozen=True)
class Paper:
    id: str
    title: str
    abstract: str
    authors: str
    categories: str
    published: str


def _throttled_get(params: dict[str, str | int]) -> bytes:
    """One GET, never faster than the rate limit, with backoff on failure."""
    global _last_request_at

    url = f"{API}?{urllib.parse.urlencode(params)}"
    for attempt in range(MAX_RETRIES):
        wait = MIN_REQUEST_INTERVAL - (time.monotonic() - _last_request_at)
        if wait > 0:
            time.sleep(wait)

        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                _last_request_at = time.monotonic()
                return response.read()
        except Exception as exc:  # noqa: BLE001 — any transport failure is retryable
            _last_request_at = time.monotonic()
            if attempt == MAX_RETRIES - 1:
                raise
            if _is_throttled(exc):
                backoff = THROTTLE_BACKOFF[min(attempt, len(THROTTLE_BACKOFF) - 1)]
                print(f"    throttled by arXiv ({exc}); waiting {backoff // 60}m {backoff % 60}s")
            else:
                backoff = MIN_REQUEST_INTERVAL * 2 ** (attempt + 1)
                print(f"    request failed ({exc}); retrying in {backoff:.0f}s")
            time.sleep(backoff)
    raise RuntimeError("unreachable")


def _strip_version(entry_id: str) -> str:
    """`http://arxiv.org/abs/2608.06377v1` -> `2608.06377`.

    The version suffix must go: it is not stable, and two versions of one paper
    would otherwise become two rows with two different primary keys.
    """
    slug = entry_id.rsplit("/", 1)[-1]
    return slug.rsplit("v", 1)[0] if "v" in slug else slug


def _parse(xml: bytes) -> tuple[list[Paper], int]:
    root = ET.fromstring(xml)

    total_node = root.find(f"{OPENSEARCH}totalResults")
    total = int(total_node.text) if total_node is not None and total_node.text else 0

    papers = []
    for entry in root.findall(f"{ATOM}entry"):
        entry_id = entry.findtext(f"{ATOM}id", "")
        title = entry.findtext(f"{ATOM}title", "")
        summary = entry.findtext(f"{ATOM}summary", "")
        published = entry.findtext(f"{ATOM}published", "")
        authors = [a.findtext(f"{ATOM}name", "") for a in entry.findall(f"{ATOM}author")]
        categories = [c.get("term", "") for c in entry.findall(f"{ATOM}category")]

        if not entry_id or not summary:
            continue

        papers.append(
            Paper(
                id=_strip_version(entry_id),
                title=title,
                abstract=summary,
                authors=", ".join(a for a in authors if a),
                categories=" ".join(c for c in categories if c),
                published=published[:10],
            )
        )
    return papers, total


def _categories_clause(categories: list[str]) -> str:
    return "(" + " OR ".join(f"cat:{c}" for c in categories) + ")"


def year_range(year: int) -> str:
    return f"submittedDate:[{year}01010000 TO {year}12312359]"


def month_range(year: int, month: int) -> str:
    last_day = calendar.monthrange(year, month)[1]
    return f"submittedDate:[{year}{month:02d}010000 TO {year}{month:02d}{last_day}2359]"


def count_for_year(categories: list[str], year: int) -> int:
    """How many papers exist for this category set and year. One cheap request."""
    query = f"{_categories_clause(categories)} AND {year_range(year)}"
    _, total = _parse(_throttled_get({"search_query": query, "start": 0, "max_results": 1}))
    return total


def count_window(categories: list[str], date_clause: str) -> int:
    """How many papers the window holds. One cheap request, used to place the offset."""
    query = f"{_categories_clause(categories)} AND {date_clause}"
    _, total = _parse(_throttled_get({"search_query": query, "start": 0, "max_results": 1}))
    return total


def fetch_window(
    categories: list[str],
    date_clause: str,
    wanted: int,
    rng: random.Random | None = None,
    total: int | None = None,
) -> list[Paper]:
    """`wanted` papers from a randomly-placed slice of one submission-date window.

    Two bugs were found here, one inside the other, and the second is why `rng`
    exists.

    Asking for the newest N of a whole *year* returns only that year's final weeks:
    the result set is date-sorted and truncated. That produced a corpus where 2018
    meant "10-31 December 2018". Narrowing the window to a month looked like the
    fix — but arXiv publishes more AI papers in a day than a month's quota, so the
    truncation simply moved down a level and every month collapsed onto its last
    day. 98% of that corpus came from days 22-31.

    Truncation is unavoidable when the API only sorts by date. What is avoidable is
    always truncating at the *same end*. So the slice is taken from a random offset
    inside the window: still contiguous, but no longer systematically month-end.
    """
    query = f"{_categories_clause(categories)} AND {date_clause}"
    collected: list[Paper] = []
    seen: set[str] = set()

    start = 0
    if rng is not None:
        if total is None:
            total = count_window(categories, date_clause)
        if total > wanted:
            start = rng.randint(0, total - wanted)

    first_start = start
    while len(collected) < wanted:
        page = min(PAGE_SIZE, wanted - len(collected))
        papers, _ = _parse(
            _throttled_get(
                {
                    "search_query": query,
                    "start": start,
                    "max_results": page,
                    "sortBy": "submittedDate",
                    "sortOrder": "descending",
                }
            )
        )
        if not papers:
            if start > first_start or first_start == 0:
                break  # pagination exhausted
            start = 0  # offset landed past the end; fall back to the window start
            continue

        for paper in papers:
            if paper.id not in seen:
                seen.add(paper.id)
                collected.append(paper)

        start += len(papers)

    return collected
