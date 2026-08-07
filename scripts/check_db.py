"""Step 0's proof that something runs.

Answers three questions:
  1. Can the app reach the database with the credentials in .env?
  2. Is pgvector actually enabled in this database?
  3. Does vector maths work *inside Postgres* — not in Python?

Run:  uv run python -m scripts.check_db
"""

import psycopg

from core.config import settings


def main() -> None:
    print(f"connecting to {settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}")

    with psycopg.connect(settings.database_url) as conn, conn.cursor() as cur:
        cur.execute("SELECT version()")
        version = cur.fetchone()[0]
        print(f"  postgres : {version.split(',')[0]}")

        cur.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
        row = cur.fetchone()
        if row is None:
            raise SystemExit(
                "  pgvector : NOT INSTALLED\n"
                "  The init script only runs on a fresh volume. Reset with:\n"
                "    docker compose down -v && docker compose up -d"
            )
        print(f"  pgvector : {row[0]}")

        # <=> is cosine DISTANCE, not similarity. Two perpendicular vectors have
        # cosine similarity 0, so their distance is 1. Step 3 depends on knowing
        # which of the two this operator returns — smaller means closer.
        cur.execute("SELECT '[1,0]'::vector <=> '[0,1]'::vector")
        print(f"  cosine distance between [1,0] and [0,1] : {cur.fetchone()[0]}")

    print("\nstep 0 OK")


if __name__ == "__main__":
    main()
