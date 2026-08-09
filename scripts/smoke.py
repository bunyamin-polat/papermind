#!/usr/bin/env python3
"""Post-deploy health checks. Exits non-zero so a pipeline can gate on it.

    uv run python scripts/smoke.py dev
    uv run python scripts/smoke.py dev --url https://example.cloudfront.net

The interesting check is the streaming one, and the reason is this: a buffered response
returns 200, carries the right body, and looks entirely correct. Every place streaming can
break in this stack fails that way —

  1. AWS_LWA_INVOKE_MODE missing from the image
  2. invoke_mode = "BUFFERED" on the Function URL
  3. compress = true on the CloudFront behaviour carrying /api/*

— so a smoke test that asserts on status codes and payloads passes happily while the UI
delivers its whole answer in one lump at the end. This one asserts on *when* the bytes
arrive, which is the only thing that can tell the difference.
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass

import httpx
from _common import (
    APP_STACK,
    DeployError,
    backend_config,
    fail,
    load_config,
    select_workspace,
    step,
    terraform,
    terraform_outputs,
)

# The app sleeps 150 ms between words. Anything that arrives more than 50 ms after its
# predecessor was genuinely sent separately rather than unpacked from one buffer.
GAP_THRESHOLD_S = 0.05
MIN_STREAMED_GAPS = 3


@dataclass
class Result:
    name: str
    passed: bool
    detail: str

    def render(self) -> str:
        mark = "\033[32m✓\033[0m" if self.passed else "\033[31m✗\033[0m"
        return f"  {mark} {self.name}: {self.detail}"


def check_health(client: httpx.Client, attempts: int = 5) -> Result:
    """Retry, because the first request after a deploy pays the cold start."""
    last = ""
    for attempt in range(1, attempts + 1):
        started = time.monotonic()
        try:
            response = client.get("/healthz")
            elapsed = (time.monotonic() - started) * 1000
            if response.status_code == 200 and response.json().get("status") == "ok":
                return Result("health", True, f"200 in {elapsed:.0f} ms (attempt {attempt})")
            last = f"status {response.status_code}, body {response.text[:80]!r}"
        except httpx.HTTPError as exc:
            last = str(exc)
        time.sleep(2)
    return Result("health", False, f"never became healthy: {last}")


def check_page(client: httpx.Client) -> Result:
    try:
        response = client.get("/")
    except httpx.HTTPError as exc:
        return Result("page", False, str(exc))

    if response.status_code != 200:
        return Result("page", False, f"status {response.status_code}")

    content_type = response.headers.get("content-type", "")
    if "text/html" not in content_type:
        return Result("page", False, f"content-type was {content_type!r}, expected text/html")

    return Result("page", True, f"200, {len(response.content)} bytes of HTML")


def check_streaming(client: httpx.Client) -> Result:
    """Measure when each event arrives, not merely that they all did."""
    arrivals: list[float] = []
    started = time.monotonic()

    try:
        with client.stream("GET", "/api/stream") as response:
            if response.status_code != 200:
                return Result("streaming", False, f"status {response.status_code}")

            content_type = response.headers.get("content-type", "")
            if "text/event-stream" not in content_type:
                return Result("streaming", False, f"content-type was {content_type!r}")

            for line in response.iter_lines():
                if line.startswith("data: "):
                    arrivals.append(time.monotonic() - started)
    except httpx.HTTPError as exc:
        return Result("streaming", False, str(exc))

    if len(arrivals) < 2:
        return Result("streaming", False, f"only {len(arrivals)} event(s) arrived")

    gaps = [b - a for a, b in zip(arrivals, arrivals[1:], strict=False)]
    real_gaps = sum(1 for gap in gaps if gap > GAP_THRESHOLD_S)
    first_ms = arrivals[0] * 1000
    total_ms = arrivals[-1] * 1000

    if real_gaps < MIN_STREAMED_GAPS:
        return Result(
            "streaming",
            False,
            f"BUFFERED — {len(arrivals)} events arrived together "
            f"(first at {first_ms:.0f} ms, last at {total_ms:.0f} ms). "
            "Check AWS_LWA_INVOKE_MODE in the image, invoke_mode on the Function URL, "
            "and compress on the CloudFront behaviour.",
        )

    return Result(
        "streaming",
        True,
        f"{len(arrivals)} events, first at {first_ms:.0f} ms, "
        f"total {total_ms:.0f} ms, {real_gaps} real gaps",
    )


def resolve_url(environment: str) -> str:
    backend = backend_config(APP_STACK)
    terraform(["init", "-input=false", f"-backend-config={backend}"], APP_STACK)
    select_workspace(environment, APP_STACK)
    outputs = terraform_outputs(APP_STACK)
    url = outputs.get("url")
    if not url:
        raise DeployError(f"No url output for {environment}. Is it deployed?")
    return str(url)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("environment", help="dev, test or prod")
    parser.add_argument(
        "--url",
        help="Check this URL instead of asking Terraform. Useful in CI, and for checking "
        "a deploy from a machine that has no Terraform state.",
    )
    args = parser.parse_args()

    try:
        # Loaded even when --url is given, so an unknown environment name fails here
        # rather than after three checks against the wrong thing.
        environment = load_config(args.environment).environment
        url = args.url or resolve_url(environment)
    except DeployError as exc:
        return fail(exc)

    step(f"Smoke testing {environment} at {url}")

    with httpx.Client(base_url=url, timeout=60.0, follow_redirects=True) as client:
        results = [
            check_health(client),
            check_page(client),
            check_streaming(client),
        ]

    print()
    for result in results:
        print(result.render())

    failed = [r for r in results if not r.passed]
    if failed:
        print(f"\n\033[31m{len(failed)} of {len(results)} checks failed.\033[0m", file=sys.stderr)
        return 1

    print(f"\n\033[32mAll {len(results)} checks passed.\033[0m")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
