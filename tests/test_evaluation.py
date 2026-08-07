"""The harness itself. If the instrument is wrong, every number after it is wrong —
two of the eight defects found so far were in measurement code, not product code."""

import pytest

from evaluation.run import Outcome, hit_rate, load_questions, mrr


def outcome(rank: int | None, expected: str | None = "1234.5678") -> Outcome:
    return Outcome(
        question="q", slice="in_corpus", expected=expected, rank=rank,
        top_distance=0.2, top_title="t", latency_ms=1.0,
    )


def test_questions_file_is_well_formed():
    questions = load_questions()
    assert len(questions) >= 30
    for q in questions:
        assert q["slice"] in {"in_corpus", "keyword", "out_of_corpus"}
        assert q["question"].strip()


def test_in_corpus_questions_all_name_an_expected_paper():
    for q in load_questions():
        if q["slice"] == "in_corpus":
            assert q["expected"], f"no expected paper for: {q['question']}"


def test_out_of_corpus_questions_expect_nothing():
    """They exist to measure distance, not rank. An expected id here would mean
    the slice was mislabelled."""
    for q in load_questions():
        if q["slice"] == "out_of_corpus":
            assert q["expected"] is None


def test_expected_papers_are_unique():
    """A duplicate gold label would silently weight one paper twice."""
    ids = [q["expected"] for q in load_questions() if q["slice"] == "in_corpus"]
    assert len(ids) == len(set(ids))


def test_hit_rate_counts_any_rank_as_a_hit():
    assert hit_rate([outcome(1), outcome(5), outcome(None)]) == pytest.approx(2 / 3)


def test_hit_rate_ignores_questions_with_no_expected_paper():
    """Out-of-corpus questions must not dilute the score — there is nothing to hit."""
    assert hit_rate([outcome(1), outcome(None, expected=None)]) == 1.0


def test_mrr_separates_rank_one_from_rank_five():
    """The reason MRR is reported next to hit-rate: hit-rate cannot tell them apart."""
    assert hit_rate([outcome(1)]) == hit_rate([outcome(5)])
    assert mrr([outcome(1)]) > mrr([outcome(5)])


def test_mrr_scores_a_miss_as_zero():
    assert mrr([outcome(None)]) == 0.0
