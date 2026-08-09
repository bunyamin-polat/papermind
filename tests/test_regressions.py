"""Guards for defects that were found once and produced no error.

Every test here exists because something specific went wrong, ran to completion and
printed plausible output. They assert on *shape* and on *configuration* rather than
on results, because results were correct in each case.

The ledger in CLAUDE.md lists thirteen such defects. These cover the ones that could
silently return.
"""

import json
import tomllib
from collections import Counter
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).parent.parent


# --- corpus sampling (ledger #3, #4) -----------------------------------------
#
# Two sampling schemes shipped before anyone noticed: "newest N per year" made each
# year its final three weeks, and "newest N per month" made each month its final
# day — 98.3% of papers landed on days 22-31. Both produced the right row count and
# the right per-year totals. Only the distribution showed it.


@pytest.fixture(scope="module")
def corpus():
    psycopg = pytest.importorskip("psycopg")
    from retrieval.backends.postgres import connect

    try:
        conn = connect()
    except psycopg.OperationalError as exc:
        pytest.skip(f"database not reachable: {exc}")
    if conn.execute("SELECT count(*) FROM papers").fetchone()[0] == 0:
        pytest.skip("corpus not loaded")
    yield conn
    conn.close()


def test_papers_are_spread_across_the_month(corpus):
    """No quarter of the month should hold most of the corpus."""
    rows = corpus.execute("SELECT extract(day from published)::int FROM papers").fetchall()
    buckets = Counter(min((d[0] - 1) // 8, 3) for d in rows)
    largest = max(buckets.values()) / len(rows)
    assert largest < 0.45, (
        f"{largest:.0%} of papers fall in one part of the month — the sampling has "
        f"collapsed onto a window again. Distribution: {dict(sorted(buckets.items()))}"
    )


def test_every_complete_year_covers_twelve_months(corpus):
    rows = corpus.execute(
        """SELECT extract(year from published)::int,
                  count(DISTINCT date_trunc('month', published))
           FROM papers GROUP BY 1 ORDER BY 1"""
    ).fetchall()
    # The most recent year is still in progress, so it is allowed to be short.
    for year, months in rows[:-1]:
        assert months == 12, f"{year} covers only {months} months"


# --- CPU-only torch (ledger #12) ---------------------------------------------
#
# `[tool.uv.sources]` applies only to *direct* dependencies. torch arrived
# transitively through sentence-transformers, so the CPU index was ignored and 4.5 GB
# of CUDA went into the Linux image — while `uv lock` reported success both times.


def test_torch_is_a_direct_dependency():
    """If it stops being declared, the CPU index silently stops applying."""
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())
    declared = " ".join(pyproject["project"]["dependencies"])
    assert "torch" in declared


def test_lock_resolves_torch_from_the_cpu_index():
    lock = (ROOT / "uv.lock").read_text()
    assert "download.pytorch.org/whl/cpu" in lock, "the CPU index is not in the lock"
    assert "+cpu" in lock, "no CPU-tagged torch wheel in the lock"


def test_lock_contains_no_cuda_packages():
    """The tell that the override stopped working, in one assertion."""
    lock = (ROOT / "uv.lock").read_text()
    for package in ('name = "nvidia-', 'name = "triton"'):
        assert package not in lock, f"{package} is back in the lock — CUDA is being installed"


# --- compose environment (ledger #13) ----------------------------------------
#
# Compose reads .env, where OLLAMA_HOST is localhost:11434 — correct on the host and
# wrong in a container, where localhost is the container. Interpolating it imported
# the host's value and broke generation while ports, health and curl all looked fine.


@pytest.fixture(scope="module")
def compose():
    return yaml.safe_load((ROOT / "docker-compose.yml").read_text())


def test_compose_does_not_interpolate_the_host_ollama_url(compose):
    value = compose["services"]["api"]["environment"]["OLLAMA_HOST"]
    assert "${OLLAMA_HOST" not in value, (
        "compose is reading OLLAMA_HOST from .env, which is the host's value and "
        "resolves to the container itself"
    )
    assert "localhost" not in value


def test_api_container_reaches_postgres_by_service_name(compose):
    """`localhost` here is the other classic: correct outside, wrong inside."""
    env = compose["services"]["api"]["environment"]
    assert env["POSTGRES_HOST"] == "db"
    assert str(env["POSTGRES_PORT"]) == "5432", "the published host port is not the container's"


def test_ui_talks_to_the_api_over_http(compose):
    assert compose["services"]["ui"]["environment"]["API_URL"].startswith("http://api:")


# --- eval harness (ledger #9) ------------------------------------------------


def test_evaluation_warms_up_before_timing():
    """The first call loads the embedding model — 8.3 seconds that once appeared as
    p95 query latency in an otherwise sane report."""
    source = (ROOT / "evaluation" / "run.py").read_text()
    warm = source.index("search(")
    loop = source.index("for q in questions")
    assert warm < loop, "timing starts before anything has warmed the model"


# --- eval questions (ledger: the eval set is itself an instrument) ------------


def test_no_expected_paper_is_used_twice():
    path = ROOT / "evaluation" / "questions.jsonl"
    expected = [
        json.loads(line)["expected"]
        for line in path.read_text().splitlines()
        if line.strip() and json.loads(line)["slice"] == "in_corpus"
    ]
    assert len(expected) == len(set(expected))
