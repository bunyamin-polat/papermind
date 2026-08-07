"""Database access. Everything that talks to Postgres goes through here."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import psycopg

from core.config import settings

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


@contextmanager
def connection() -> Iterator[psycopg.Connection]:
    """A connection that commits on success and rolls back on any exception."""
    with psycopg.connect(settings.database_url) as conn:
        yield conn


def init_schema() -> None:
    """Apply schema.sql. Written to be idempotent, so it is safe to call on every run.

    Real migrations (Alembic) are not warranted yet — there is one table and no
    production data. Revisit if the schema starts changing under a live system.
    """
    with connection() as conn:
        conn.execute(SCHEMA_PATH.read_text())


def count_papers() -> int:
    with connection() as conn:
        row = conn.execute("SELECT count(*) FROM papers").fetchone()
        return row[0] if row else 0
