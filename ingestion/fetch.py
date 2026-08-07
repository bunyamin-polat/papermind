"""Step 1a — build the corpus from the arXiv API.

Queries arXiv directly rather than downloading a HuggingFace snapshot. The
snapshot that was used first (`gfissore/arxiv-abstracts-2021`) ends in December
2021: a corpus frozen there cannot answer anything about work published since,
which is most of what anyone would ask an AI-research assistant. Querying the API
means the corpus reaches today and can be refreshed by re-running this.

Writes a parquet file and a manifest recording when it was built. Nothing here
touches the database — fetching and loading are separate so a slow, rate-limited
download is paid for once.

Run:  uv run python -m ingestion.fetch
"""

import argparse
import json
import random
from datetime import date
from pathlib import Path

import pandas as pd

from ingestion import arxiv_api

# arXiv's core AI set, plus cs.MA. Deliberately not broader: categories like
# cs.RO and cs.CR already reach this corpus through cross-listing (an ML-heavy
# robotics paper carries cs.LG too), so adding them explicitly would only pull in
# the papers that carry *no* AI tag — by definition the least relevant ones.
# cs.MA is the exception: multi-agent work is under-represented by cross-listing
# and is directly on topic.
AI_CATEGORIES = ["cs.AI", "cs.CL", "cs.CV", "cs.IR", "cs.LG", "cs.MA", "cs.NE", "stat.ML"]

# One month per window, and a randomly-placed slice inside it. Two earlier
# schemes failed in the same way at different scales: "newest N of the year"
# collapsed each year onto its final three weeks, and "newest N of the month"
# collapsed each month onto its final day (98% of that corpus fell on days 22-31).
# The scheme is recorded in the checkpoint filename so changing it invalidates old
# data instead of silently reusing it.
SAMPLING_SCHEME = "monthly-offset"

# Fixed, so the corpus is reproducible: the same seed picks the same offsets, and
# a metric measured at step 4 stays comparable to the same metric at step 12.
SEED = 20260807

# 2015 is roughly where the modern deep-learning literature begins.
FROM_YEAR = 2015

# Every year gets at least this many papers, however small its output was.
# Without a floor, proportional allocation starves the early years, and the
# foundational work the corpus most needs to explain lives there.
MIN_PER_YEAR = 250

RAW_PATH = Path("data/raw/papers.parquet")
MANIFEST_PATH = Path("data/raw/manifest.json")

# Each year is checkpointed here as it completes. A rate-limited fetch takes
# minutes, and the first version of this script lost an entire run to a failure
# on the last line. Now a crash costs one year, and a re-run resumes.
CHECKPOINT_DIR = Path("data/raw/years")

# How many papers each month holds. A past month's count never changes, so this is
# cached across runs — it halves the request count on a resume, which matters
# because arXiv soft-blocks clients that query too much in one sitting.
COUNTS_PATH = Path("data/raw/month_counts.json")


def _load_counts() -> dict[str, int]:
    return json.loads(COUNTS_PATH.read_text()) if COUNTS_PATH.exists() else {}


def _save_counts(counts: dict[str, int]) -> None:
    COUNTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    COUNTS_PATH.write_text(json.dumps(counts, indent=2, sort_keys=True))


def allocate(counts: dict[int, int], limit: int) -> dict[int, int]:
    """Split `limit` across years: proportional to real output, with a floor.

    Proportional alone would put most of the corpus in the last two years, since
    AI output roughly doubles every few years. The floor keeps early years
    representable without flattening the distribution entirely.
    """
    years = sorted(counts)
    floors = {y: min(MIN_PER_YEAR, counts[y]) for y in years}
    remaining = limit - sum(floors.values())

    if remaining <= 0:  # limit too small for the floors — scale them down instead
        share = limit / max(sum(floors.values()), 1)
        return {y: max(1, int(floors[y] * share)) for y in years}

    headroom = {y: counts[y] - floors[y] for y in years}
    total_headroom = sum(headroom.values()) or 1
    quota = {y: floors[y] + int(remaining * headroom[y] / total_headroom) for y in years}

    # Integer division loses a few; give them to the most recent year.
    quota[years[-1]] += limit - sum(quota.values())
    return quota


def fetch(limit: int, out_path: Path = RAW_PATH, refresh: bool = False) -> pd.DataFrame:
    this_year = date.today().year
    years = list(range(FROM_YEAR, this_year + 1))

    print(f"counting arXiv papers per year for {AI_CATEGORIES}")
    counts = {}
    for year in years:
        counts[year] = arxiv_api.count_for_year(AI_CATEGORIES, year)
        print(f"    {year}: {counts[year]:,} available")

    quota = allocate(counts, limit)
    print(f"\nallocation across {len(years)} years (floor {MIN_PER_YEAR}/year):")
    print("   " + "  ".join(f"{y}:{quota[y]:,}" for y in years))

    print("\nfetching (arXiv allows one request per 3s — this takes a few minutes)")
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    rng = random.Random(SEED)
    month_counts = _load_counts()
    frames = []
    for year in years:
        if quota[year] <= 0:
            continue

        # The scheme is in the filename on purpose: changing how the corpus is
        # sampled must invalidate old checkpoints rather than silently reuse them.
        checkpoint = CHECKPOINT_DIR / f"{year}-{SAMPLING_SCHEME}.parquet"
        if checkpoint.exists() and not refresh:
            cached = pd.read_parquet(checkpoint)
            if len(cached) >= quota[year]:
                print(f"    {year}: {len(cached):,} papers (cached)")
                frames.append(cached)
                continue

        months = range(1, 13) if year < this_year else range(1, date.today().month + 1)
        per_month = max(1, -(-quota[year] // len(months)))  # ceil

        papers = []
        for month in months:
            window = arxiv_api.month_range(year, month)
            key = f"{year}-{month:02d}"

            # The current month is still filling up, so its count is not cacheable.
            if key in month_counts and not (year == this_year and month == date.today().month):
                total = month_counts[key]
            else:
                total = arxiv_api.count_window(AI_CATEGORIES, window)
                month_counts[key] = total
                _save_counts(month_counts)

            papers.extend(
                arxiv_api.fetch_window(AI_CATEGORIES, window, per_month, rng, total)
            )
            print(f"    {year}: {len(papers):,}/{quota[year]:,} (through {month:02d})", end="\r")

        year_df = pd.DataFrame([p.__dict__ for p in papers]).drop_duplicates(subset="id")
        year_df.to_parquet(checkpoint, index=False)
        frames.append(year_df)
        print(f"    {year}: {len(year_df):,} papers across {len(months)} months        ")

    df = pd.concat(frames, ignore_index=True).drop_duplicates(subset="id", keep="first")
    print(f"\ncollected {len(df):,} unique papers")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path, index=False)

    # arXiv keeps growing, so this fetch is not reproducible from the query alone.
    # The parquet is the reproducible artifact; the manifest says what it is.
    MANIFEST_PATH.write_text(
        json.dumps(
            {
                "built_on": date.today().isoformat(),
                "source": "arXiv Atom API",
                "categories": AI_CATEGORIES,
                "years": [years[0], years[-1]],
                "papers": len(df),
                "per_year": df["published"].str[:4].value_counts().sort_index().to_dict(),
            },
            indent=2,
        )
    )
    print(f"wrote {len(df):,} rows to {out_path} (+ manifest)")
    return df


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=10_000, help="corpus size (default 10000)")
    parser.add_argument("--out", type=Path, default=RAW_PATH)
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="ignore per-year checkpoints and re-query arXiv (use to pull newer papers)",
    )
    args = parser.parse_args()
    fetch(args.limit, args.out, args.refresh)


if __name__ == "__main__":
    main()
