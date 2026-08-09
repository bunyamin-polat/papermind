"""FastAPI entrypoint.

Run:  uv run uvicorn app.main:app --reload
      open http://localhost:8000/docs
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from app.api.routes import router
from retrieval.retriever import _model

STATIC = Path(__file__).parent / "static"

DESCRIPTION = """Ask a question about AI research and get an answer grounded in
arXiv abstracts, with the papers it came from — or an honest refusal when the corpus
does not support one."""


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load the embedding model at startup, not on the first request.
    #
    # It takes roughly eight seconds. Left lazy, the first caller pays for it and
    # sees an 11-second response where every later caller sees three — which reads
    # as an intermittent fault rather than a warm-up. Worse, on scale-to-zero
    # compute every cold start becomes that first caller.
    _model()
    yield


app = FastAPI(
    title="PaperMind",
    description=DESCRIPTION,
    version="0.1.0",
    lifespan=lifespan,
)
app.include_router(router)


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    """One page, no build step, served by the same process as the API.

    Streamlit stays for local use but cannot be deployed here: it needs a websocket,
    and a Lambda Function URL has none. A static page also means one hostname serves
    both the page and `/ask`, which removes CORS and a preflight on every question.
    """
    return FileResponse(STATIC / "index.html")
