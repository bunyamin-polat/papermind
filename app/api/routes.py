"""POST /ask and GET /health.

Error handling is the part that matters here. `LLMError` and `ModelMismatch` are
different kinds of broken and must not look alike to a caller: one is a dependency
being down and worth retrying, the other is this service being misconfigured and
never worth retrying. A 500 with a stack trace says neither.
"""

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.schemas import AskRequest, AskResponse, Health, Models, RetrievedPaper, Source
from app.limits import enforce
from core import llm
from core.config import settings
from retrieval import retriever
from retrieval.answer import ask
from retrieval.prompt import cited_indices
from retrieval.retriever import ArtifactMismatch, ArtifactMissing, ModelMismatch

router = APIRouter()


def _generation_model() -> str:
    return settings.ollama_model if settings.llm_provider == "ollama" else settings.openai_model


def rate_limit(request: Request) -> None:
    enforce(request)


@router.post("/ask", response_model=AskResponse, dependencies=[Depends(rate_limit)])
def post_ask(request: AskRequest) -> AskResponse:
    try:
        answer = ask(request.question, k=request.k)
    except (ModelMismatch, ArtifactMismatch, ArtifactMissing) as exc:
        # Misconfiguration. Retrying will not help and the caller should not be
        # told to try again.
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except llm.LLMError as exc:
        # A dependency is unreachable. 503 is the honest code, and the message says
        # what to start rather than where the stack unwound.
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    markers = cited_indices(answer.text, len(answer.retrieved))
    return AskResponse(
        question=answer.question,
        answer=answer.text,
        refused=answer.refused,
        sources=[
            Source(
                marker=marker,
                paper_id=source.paper_id,
                title=" ".join(source.title.split()),
                url=source.url,
                distance=round(source.distance, 4) if source.distance is not None else None,
            )
            for marker, source in zip(markers, answer.sources, strict=True)
        ],
        retrieved=[
            RetrievedPaper(
                paper_id=r.paper_id,
                title=" ".join(r.title.split()),
                url=r.url,
                distance=round(r.distance, 4) if r.distance is not None else None,
            )
            for r in answer.retrieved
        ],
        models=Models(embedding=settings.embedding_model, generation=_generation_model()),
        latency_ms=round(answer.latency_ms, 1),
    )


@router.get("/healthz", include_in_schema=False)
def get_healthz() -> dict:
    """Liveness only, and deliberately cheap.

    The Lambda Web Adapter polls this before reporting the container ready. `/health`
    below calls the language model, which would make readiness depend on a third party
    and take seconds — the two checks answer different questions and must stay separate.
    """
    return {"status": "ok"}


@router.get("/health", response_model=Health)
def get_health() -> Health:
    """Deep enough to be worth having. A health check that only proves the process is
    alive tells you nothing the open port did not — and it was a deep check that caught
    the container being handed a database URL pointing at itself."""
    try:
        state = retriever.health()
    except Exception as exc:  # noqa: BLE001 — any backend failure is a 503 to the caller
        raise HTTPException(status_code=503, detail=f"retrieval unavailable: {exc}") from exc

    papers, embeddings = state["papers"], state["embeddings"]

    try:
        llm.complete("Reply with the single word: ok")
        reachable = True
    except llm.LLMError:
        reachable = False

    # Degraded rather than down: retrieval still works without a generator, and
    # saying so is more useful than a binary.
    status = "ok" if papers and embeddings == papers and reachable else "degraded"
    return Health(
        status=status,
        backend=state["backend"],
        papers=papers,
        embeddings=embeddings,
        embedding_model=settings.embedding_model,
        generation_model=_generation_model(),
        llm_reachable=reachable,
    )
