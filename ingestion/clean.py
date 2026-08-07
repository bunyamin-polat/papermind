"""Step 1b — clean the fetched parquet and load it into the `papers` table.

Cleaning is not cosmetic here. arXiv abstracts arrive with hard line wrapping and
leading whitespace from the original TeX submission, so the same sentence can
contain newlines at arbitrary points. Left alone, that noise ends up inside the
chunks at step 2 and inside the embeddings at step 3 — a retrieval bug with no
error message anywhere. Fix it once, at the boundary.

Run:  uv run python -m ingestion.clean
"""

import argparse
import re
from pathlib import Path

import pandas as pd

from ingestion.fetch import RAW_PATH
from storage import db

# Any run of whitespace, including the newlines arXiv wraps abstracts at.
WHITESPACE = re.compile(r"\s+")

MIN_ABSTRACT_CHARS = 100

COLUMNS = ["id", "title", "abstract", "authors", "categories", "published"]

INSERT = """
    INSERT INTO papers (id, title, abstract, authors, categories, published)
    VALUES (%s, %s, %s, %s, %s, %s)
    ON CONFLICT (id) DO UPDATE SET
        title      = EXCLUDED.title,
        abstract   = EXCLUDED.abstract,
        authors    = EXCLUDED.authors,
        categories = EXCLUDED.categories,
        published  = EXCLUDED.published
"""


def normalise(text: str) -> str:
    return WHITESPACE.sub(" ", str(text)).strip()


def clean(df: pd.DataFrame) -> pd.DataFrame:
    start = len(df)

    for column in ("title", "abstract", "authors", "categories"):
        df[column] = df[column].map(normalise)
    df["published"] = pd.to_datetime(df["published"], errors="coerce").dt.date

    df = df[df["abstract"].str.len() >= MIN_ABSTRACT_CHARS]
    print(f"  dropped {start - len(df):,} with an abstract under {MIN_ABSTRACT_CHARS} chars")

    before = len(df)
    df = df.drop_duplicates(subset="id", keep="first")
    print(f"  dropped {before - len(df):,} duplicate ids")

    # arXiv carries genuine near-duplicates: the same work resubmitted under a new
    # id. Same title and same abstract is a real duplicate, not a coincidence.
    before = len(df)
    df = df.drop_duplicates(subset=["title", "abstract"], keep="first")
    print(f"  dropped {before - len(df):,} duplicate title+abstract pairs")

    return df


def load(df: pd.DataFrame) -> int:
    db.init_schema()
    rows = list(df[COLUMNS].itertuples(index=False, name=None))
    with db.connection() as conn, conn.cursor() as cur:
        cur.executemany(INSERT, rows)
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=RAW_PATH)
    args = parser.parse_args()

    if not args.input.exists():
        raise SystemExit(f"{args.input} not found — run `uv run python -m ingestion.fetch` first")

    df = pd.read_parquet(args.input)
    print(f"read {len(df):,} rows from {args.input}")

    df = clean(df)
    print(f"  {len(df):,} rows survive cleaning")

    written = load(df)
    print(f"\nwrote {written:,} rows; papers table now holds {db.count_papers():,}")


if __name__ == "__main__":
    main()
