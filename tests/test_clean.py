"""Cleaning is where retrieval bugs get created silently, so it gets tests."""

import pandas as pd

from ingestion.clean import MIN_ABSTRACT_CHARS, clean, normalise


def _paper(pid: str, title: str = "A title", abstract: str | None = None) -> dict:
    return {
        "id": pid,
        "title": title,
        "abstract": abstract if abstract is not None else "x" * (MIN_ABSTRACT_CHARS + 10),
        "authors": "A. Author",
        "categories": "cs.LG",
        "published": "2021-06-01",
    }


def test_normalise_collapses_the_line_wrapping_arxiv_ships():
    raw = "  Attention is\n  all you   need\n"
    assert normalise(raw) == "Attention is all you need"


def test_normalise_leaves_clean_text_alone():
    assert normalise("Already clean") == "Already clean"


def test_short_abstracts_are_dropped():
    df = pd.DataFrame([_paper("2101.00001"), _paper("2101.00002", abstract="too short")])
    assert clean(df)["id"].tolist() == ["2101.00001"]


def test_duplicate_ids_are_dropped_keeping_the_first():
    df = pd.DataFrame([_paper("2101.00001", title="First"), _paper("2101.00001", title="Second")])
    result = clean(df)
    assert len(result) == 1
    assert result["title"].iloc[0] == "First"


def test_resubmissions_under_a_new_id_are_dropped():
    # Same work, different arXiv id — a real pattern, not a coincidence.
    body = "y" * (MIN_ABSTRACT_CHARS + 10)
    df = pd.DataFrame(
        [
            _paper("2101.00001", title="Same paper", abstract=body),
            _paper("2102.00002", title="Same paper", abstract=body),
        ]
    )
    assert len(clean(df)) == 1


def test_whitespace_is_normalised_before_deduplication():
    """Two rows differing only in line wrapping must collapse to one."""
    body = "y " * 80
    df = pd.DataFrame(
        [
            _paper("2101.00001", title="Same\npaper", abstract=body),
            _paper("2102.00002", title="Same paper", abstract=body.replace(" ", "\n  ")),
        ]
    )
    assert len(clean(df)) == 1
