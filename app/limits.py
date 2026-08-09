"""A rate limit, because the deployed instance calls a paid model.

Local runs use Ollama and cost nothing, so this is dead weight there — and it is still
on by default, because a limit that is only enabled in production is a limit that has
never been exercised before the day it matters.

In-memory and per-process. That is honest rather than ideal: with more than one instance
the effective limit multiplies, and a restart forgets everything. For a demo behind a
single Lambda or one App Runner container it holds, and the alternative is Redis, which
would cost more per month than the model calls it protects. If this ever fronts real
traffic, replace it — do not tune it.

The real spending guard is elsewhere and layered: `llm_max_tokens` caps one answer, the
AWS budget alarm caps the account, and this caps how often anyone can ask.
"""

import time
from collections import deque

from fastapi import HTTPException, Request

from core.config import settings

_hits: dict[str, deque[float]] = {}


def _client(request: Request) -> str:
    # Behind CloudFront or a Function URL the peer address is the proxy, so the
    # forwarded header is the only thing that identifies a caller. It is spoofable;
    # this is a courtesy limit for a demo, not a security control, and pretending
    # otherwise would be worse than saying so.
    forwarded = request.headers.get("x-forwarded-for", "")
    return forwarded.split(",")[0].strip() or (request.client.host if request.client else "unknown")


def enforce(request: Request) -> None:
    if settings.rate_limit_per_minute <= 0:
        return

    now = time.monotonic()
    window = 60.0
    key = _client(request)

    hits = _hits.setdefault(key, deque())
    while hits and now - hits[0] > window:
        hits.popleft()

    if len(hits) >= settings.rate_limit_per_minute:
        retry_after = int(window - (now - hits[0])) + 1
        raise HTTPException(
            status_code=429,
            detail=(
                f"{settings.rate_limit_per_minute} questions per minute on this shared "
                f"demo. Try again in {retry_after}s, or run it locally where it is free."
            ),
            headers={"Retry-After": str(retry_after)},
        )

    hits.append(now)

    # Unbounded growth would be a slow leak in a long-lived process. Cheap to prevent,
    # and the cost of getting it wrong is a memory graph nobody looks at until it pages.
    if len(_hits) > 10_000:
        for stale, times in list(_hits.items()):
            if not times or now - times[-1] > window:
                del _hits[stale]
