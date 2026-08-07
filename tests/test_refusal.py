"""Refusal, end to end. These call a real model, so they are slow and marked.

    uv run pytest -m llm          # run them
    uv run pytest -m "not llm"    # skip them (the default in CI without Ollama)

Refusal is the single most trust-building behaviour in a grounded QA system, and
it is the one that degrades silently: a model that quietly stops refusing looks
exactly like a model that got better at answering.
"""

import pytest

from core import llm
from retrieval.answer import ask

pytestmark = pytest.mark.llm


@pytest.fixture(scope="module", autouse=True)
def require_llm():
    try:
        llm.complete("Reply with the single word: ok")
    except llm.LLMError as exc:
        pytest.skip(f"no LLM available: {exc}")


@pytest.mark.parametrize(
    "question",
    [
        "what is the best recipe for sourdough bread?",
        "who won the 2018 FIFA World Cup?",
        "how do I change a flat car tyre?",
    ],
)
def test_refuses_questions_the_corpus_cannot_answer(question):
    answer = ask(question)
    assert answer.refused, f"answered an out-of-corpus question: {answer.text[:120]}"


def test_answers_a_question_the_corpus_can_answer():
    """The other half of the trade-off. A system that refuses everything passes the
    test above and is useless — measured at step 5, the small model refuses 12.5%
    of answerable questions."""
    answer = ask("how can learned noise protect private data sent to a cloud inference service?")
    assert not answer.refused
    assert answer.sources


def test_an_answer_never_invents_a_source_number():
    """Across 68 generated answers at step 5 this held every time, because the model
    is never shown an identifier — only positions it cannot inflate into a real one."""
    answer = ask("how are graph convolutional networks used to forecast traffic?")
    assert answer.invalid_citations == []


def test_cited_sources_resolve_to_real_papers():
    answer = ask("what is an attention mechanism in neural networks?")
    for source in answer.sources:
        assert source.url == f"https://arxiv.org/abs/{source.paper_id}"
        assert source in answer.retrieved
