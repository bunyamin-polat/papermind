"""POST /ask and GET /health.

Error handling is the part that matters here. `LLMError` and `ModelMismatch` are
different kinds of broken and must not look alike to a caller: one is a dependency
being down and worth retrying, the other is this service being misconfigured and
never worth retrying. A 500 with a stack trace says neither.
"""

import psycopg
from fastapi import APIRouter, HTTPException

from app.api.schemas import AskRequest, AskResponse, Health, Models, RetrievedPaper, Source
from core import llm
from core.config import settings
from retrieval.answer import ask
from retrieval.prompt import cited_indices
from retrieval.retriever import ModelMismatch

router = APIRouter()


def _generation_model() -> str:
    return settings.ollama_model if settings.llm_provider == "ollama" else settings.openai_model


@router.post("/ask", response_model=AskResponse)
def post_ask(request: AskRequest) -> AskResponse:
    try:
        answer = ask(request.question, k=request.k)
    except ModelMismatch as exc:
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
                distance=round(source.distance, 4),
            )
            for marker, source in zip(markers, answer.sources, strict=True)
        ],
        retrieved=[
            RetrievedPaper(
                paper_id=r.paper_id,
                title=" ".join(r.title.split()),
                url=r.url,
                distance=round(r.distance, 4),
            )
            for r in answer.retrieved
        ],
        models=Models(embedding=settings.embedding_model, generation=_generation_model()),
        latency_ms=round(answer.latency_ms, 1),
    )


@router.get("/health", response_model=Health)
def get_health() -> Health:
    """Deep enough to be worth having. A health check that only proves the process
    is alive tells you nothing you could not get from the port being open."""
    try:
        with psycopg.connect(settings.database_url, connect_timeout=3) as conn:
            papers = conn.execute("SELECT count(*) FROM papers").fetchone()[0]
            embeddings = conn.execute(
                "SELECT count(*) FROM embeddings WHERE model = %s", (settings.embedding_model,)
            ).fetchone()[0]
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail=f"database unreachable: {exc}") from exc

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
        papers=papers,
        embeddings=embeddings,
        embedding_model=settings.embedding_model,
        generation_model=_generation_model(),
        llm_reachable=reachable,
    )
