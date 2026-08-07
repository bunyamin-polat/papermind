"""Embedding logic. The model itself is not loaded here — these cover the parts
that decide *what* gets embedded and *which rows* still need it, which is where
the bugs would be."""

from ingestion.embed import SELECT_UNEMBEDDED, to_document


def test_document_joins_title_and_abstract():
    doc = to_document("Attention Is All You Need", "We propose a new architecture.")
    assert doc == "Attention Is All You Need\n\nWe propose a new architecture."


def test_document_strips_stray_whitespace():
    """clean.py normalises on the way in, but embedding must not depend on that."""
    assert to_document("  Padded  ", "\n Body \n") == "Padded\n\nBody"


def test_title_is_included_not_dropped():
    """A question often echoes title wording the abstract never repeats — dropping
    the title would make those questions unanswerable for no gain."""
    doc = to_document("Sparse Transformers", "The method reduces cost.")
    assert "Sparse Transformers" in doc
    assert "The method reduces cost." in doc


def test_resume_query_selects_only_unembedded_rows_for_this_model():
    """Resumability is a LEFT JOIN, not a bookmark. Two properties matter: it must
    filter on the model (so switching models re-embeds rather than silently
    skipping), and it must return only rows with no matching embedding."""
    sql = " ".join(SELECT_UNEMBEDDED.split())
    assert "LEFT JOIN embeddings e" in sql
    assert "e.model = %s" in sql
    assert "e.paper_id IS NULL" in sql
