"""The HTTP layer.

An endpoint hides more than a CLI does: a 200 with a plausible body looks exactly
like every one of the nine silent failures found in this project. So these assert
on the *structure* of the response and on what happens when a dependency is down —
not merely that a request succeeded.

The LLM is faked here so the suite stays fast and runs without Ollama. Real
end-to-end behaviour is covered by `tests/test_refusal.py` under `-m llm`.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from core import llm
from core.config import settings
from retrieval import answer as answer_module
from retrieval.prompt import REFUSAL
from retrieval.retriever import ModelMismatch, Result


@pytest.fixture
def client(monkeypatch):
    # Skips rather than fails when Postgres is not up, like the retrieval tests.
    psycopg = pytest.importorskip("psycopg")
    try:
        from retrieval.backends.postgres import connect

        connect().close()
    except psycopg.OperationalError as exc:
        pytest.skip(f"database not reachable: {exc}")

    # The rate limit is real and on by default, so a test making a dozen requests from
    # one address hits it and starts getting 429s in place of whatever it was asserting.
    # Disabled here and exercised deliberately in test_rate_limit_* below.
    from app import limits

    monkeypatch.setattr(settings, "rate_limit_per_minute", 0)
    limits._hits.clear()

    with TestClient(app) as c:
        yield c


@pytest.fixture
def fake_llm(monkeypatch):
    """Replace the model with a fixed answer, so the assertions are about the API."""

    def reply(text: str):
        monkeypatch.setattr(llm, "complete", lambda *a, **kw: text)
        monkeypatch.setattr(answer_module.llm, "complete", lambda *a, **kw: text)

    return reply


def test_health_reports_corpus_and_models(client):
    body = client.get("/health").json()
    assert body["papers"] > 0
    assert body["embeddings"] == body["papers"], "some papers have no embedding"
    assert body["embedding_model"] and body["generation_model"]


def test_ask_returns_citations_that_map_to_retrieved_papers(client, fake_llm):
    fake_llm("Noise helps [1]. So does more noise [2].")
    body = client.post("/ask", json={"question": "how does learned noise help privacy?"}).json()

    assert body["refused"] is False
    assert [s["marker"] for s in body["sources"]] == [1, 2]

    retrieved_ids = {r["paper_id"] for r in body["retrieved"]}
    for source in body["sources"]:
        assert source["paper_id"] in retrieved_ids, "cited a paper that was never retrieved"
        assert source["url"] == f"https://arxiv.org/abs/{source['paper_id']}"


def test_retrieved_is_returned_even_when_nothing_is_cited(client, fake_llm):
    """The distinction the response exists to preserve: refusing after consulting
    five papers is not the same as having found nothing."""
    fake_llm(REFUSAL)
    body = client.post("/ask", json={"question": "who won the 2018 world cup?"}).json()

    assert body["refused"] is True
    assert body["sources"] == []
    assert len(body["retrieved"]) == 5


def test_invented_citations_never_reach_the_response(client, fake_llm):
    """The model claiming `[9]` of five sources must not produce a ninth source, and
    must not shift the others."""
    fake_llm("As shown in [9] and [2].")
    body = client.post("/ask", json={"question": "what is attention?"}).json()

    assert [s["marker"] for s in body["sources"]] == [2]


def test_k_controls_how_many_papers_are_consulted(client, fake_llm):
    fake_llm("An answer [1].")
    body = client.post("/ask", json={"question": "what is attention?", "k": 3}).json()
    assert len(body["retrieved"]) == 3


def test_distances_increase_down_the_retrieved_list(client, fake_llm):
    fake_llm("An answer [1].")
    body = client.post("/ask", json={"question": "what is attention?"}).json()
    distances = [r["distance"] for r in body["retrieved"]]
    assert distances == sorted(distances)


def test_llm_down_is_503_not_500(client, monkeypatch):
    """A dependency being unreachable is worth retrying; a 500 says otherwise."""

    def boom(*args, **kwargs):
        raise llm.LLMError("cannot reach Ollama at http://localhost:11434")

    monkeypatch.setattr(answer_module.llm, "complete", boom)
    response = client.post("/ask", json={"question": "what is attention?"})

    assert response.status_code == 503
    assert "ollama" in response.json()["detail"].lower()


def test_misconfiguration_is_500_not_503(client, monkeypatch):
    """A corpus embedded with another model will never work by retrying."""

    def boom(*args, **kwargs):
        raise ModelMismatch("corpus embedded with ['other/model']")

    monkeypatch.setattr(answer_module, "search", boom)
    assert client.post("/ask", json={"question": "what is attention?"}).status_code == 500


@pytest.mark.parametrize(
    "payload",
    [
        {"question": "hi"},          # under min_length
        {"question": ""},
        {},                          # missing entirely
        {"question": "ok?", "k": 0},   # k below 1
        {"question": "ok?", "k": 99},  # k above the cap
    ],
)
def test_bad_requests_are_rejected_before_a_model_is_called(client, payload):
    assert client.post("/ask", json=payload).status_code == 422


def test_search_is_never_called_for_an_invalid_request(client, monkeypatch):
    called = False

    def spy(*args, **kwargs):
        nonlocal called
        called = True
        return [Result("1", "t", "a", "u", 0.1)]

    monkeypatch.setattr(answer_module, "search", spy)
    client.post("/ask", json={"question": "x"})
    assert not called, "validation ran after the expensive work"


def test_rate_limit_returns_429_with_a_retry_after(client, monkeypatch, fake_llm):
    """The limit exists because the deployed instance calls a paid model. It is on
    locally too, where answers are free — a limit first enabled in production is a limit
    that has never been exercised."""
    from app import limits

    fake_llm("An answer [1].")
    monkeypatch.setattr(settings, "rate_limit_per_minute", 3)
    limits._hits.clear()

    payload = {"question": "what is attention?"}
    codes = [client.post("/ask", json=payload).status_code for _ in range(4)]

    assert codes[:3] == [200, 200, 200]
    assert codes[3] == 429

    response = client.post("/ask", json=payload)
    assert "Retry-After" in response.headers


def test_rate_limit_can_be_switched_off(client, monkeypatch, fake_llm):
    from app import limits

    fake_llm("An answer [1].")
    monkeypatch.setattr(settings, "rate_limit_per_minute", 0)
    limits._hits.clear()

    codes = [client.post("/ask", json={"question": "what?"}).status_code for _ in range(6)]
    assert codes == [200] * 6, codes


def test_healthz_is_cheap_and_does_not_call_the_model(client, monkeypatch):
    """The Lambda adapter polls this before reporting the container ready. If it called
    the language model, readiness would depend on a third party and take seconds."""
    def boom(*args, **kwargs):
        raise AssertionError("/healthz called the language model")

    monkeypatch.setattr(llm, "complete", boom)
    assert client.get("/healthz").json() == {"status": "ok"}


def test_index_page_is_served_by_the_api(client):
    """One hostname for the page and the API, so there is no CORS preflight per question."""
    response = client.get("/")
    assert response.status_code == 200
    assert "PaperMind" in response.text
