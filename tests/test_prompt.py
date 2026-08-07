"""The grounding prompt and citation mapping. No model is called — these cover the
code that decides what the model sees and what is trusted from what it returns."""

from retrieval.prompt import (
    REFUSAL,
    build,
    cited_indices,
    invalid_citations,
    is_refusal,
)
from retrieval.retriever import Result


def paper(pid: str, title: str = "A Title", abstract: str = "An abstract.") -> Result:
    return Result(
        paper_id=pid, title=title, abstract=abstract,
        url=f"https://arxiv.org/abs/{pid}", distance=0.2,
    )


def test_sources_are_numbered_from_one():
    """The numbering is the citation contract. Off-by-one here would map every
    citation to the wrong paper — silently, since both are real papers."""
    text = build("q", [paper("1"), paper("2"), paper("3")])
    assert "[1]" in text and "[2]" in text and "[3]" in text
    assert "[0]" not in text


def test_prompt_never_contains_the_arxiv_id():
    """The model must not be able to copy an identifier, because then it can also
    invent one that looks just like it. It cites positions; code resolves them."""
    text = build("q", [paper("2406.06538")])
    assert "2406.06538" not in text
    assert "arxiv.org" not in text.lower()


def test_whitespace_is_flattened_in_sources():
    text = build("q", [paper("1", title="Line\nbroken", abstract="Wrapped\n  text")])
    assert "Line broken" in text
    assert "Wrapped text" in text


def test_cited_indices_are_deduplicated_and_ordered_by_use():
    assert cited_indices("first [2], then [1], again [2]", 3) == [2, 1]


def test_out_of_range_citations_are_dropped_not_resolved():
    """`[9]` with five sources points nowhere. Showing it would be a citation the
    reader cannot follow — worse than showing none."""
    assert cited_indices("see [9] and [2]", 5) == [2]


def test_invented_citations_are_reported_separately():
    """Dropped is not the same as unnoticed. If the prompt stops holding, the count
    is how we find out."""
    assert invalid_citations("see [9] and [2] and [0]", 5) == [0, 9]
    assert invalid_citations("see [1][2]", 5) == []


def test_answer_with_no_citations_yields_none():
    assert cited_indices("An answer with no sources at all.", 5) == []


def test_refusal_is_an_exact_sentence_not_a_vibe():
    """Step 6 needs to detect refusal reliably. 'say you don't know' cannot be
    tested; one exact sentence can."""
    assert is_refusal(REFUSAL)
    assert is_refusal(f"  {REFUSAL}  ")
    assert not is_refusal("The sources say attention is useful [1].")


def test_refusal_sentence_is_in_the_system_prompt():
    from retrieval.prompt import SYSTEM

    assert REFUSAL in SYSTEM
