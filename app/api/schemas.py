"""The wire contract.

This shape is the most expensive thing in step 7 to get wrong: the UI at step 8 and
anything built after it are stuck with whatever is chosen here. Three decisions are
deliberate.

**`retrieved` is returned alongside `sources`.** `sources` is what the answer cited;
`retrieved` is everything that went into the prompt. A consumer can then show "5
papers consulted, 2 cited", and a developer can see whether a wrong answer came from
bad retrieval or bad grounding. Returning only citations hides which of the two
failed — and that distinction is what steps 4 and 5 spent their time on.

**The models that produced the answer are named in the response.** Which embedding
model and which generator answered is not metadata for logs; it is part of the
answer's meaning. A response is not comparable to another unless you know both.

**`marker` is the citation number the answer text actually uses.** The UI turns `[1]`
in the prose into a link without re-parsing anything.
"""

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1000)
    k: int = Field(default=5, ge=1, le=20)


class Source(BaseModel):
    marker: int = Field(description="the [n] used in the answer text")
    paper_id: str
    title: str
    url: str
    #: Cosine distance, or null. A paper the lexical arm found and the dense arm
    #: did not has no distance — BM25 does not produce one, and computing it after
    #: the fact would mean an extra embedding lookup per hit to fill in a number
    #: nothing ranks by. Null is the honest value.
    distance: float | None = None


class RetrievedPaper(BaseModel):
    paper_id: str
    title: str
    url: str
    #: Cosine distance, or null. A paper the lexical arm found and the dense arm
    #: did not has no distance — BM25 does not produce one, and computing it after
    #: the fact would mean an extra embedding lookup per hit to fill in a number
    #: nothing ranks by. Null is the honest value.
    distance: float | None = None


class Models(BaseModel):
    embedding: str
    generation: str


class AskResponse(BaseModel):
    question: str
    answer: str
    refused: bool = Field(description="the corpus did not support an answer")
    sources: list[Source] = Field(description="papers the answer cited, in citation order")
    retrieved: list[RetrievedPaper] = Field(description="everything that went into the prompt")
    models: Models
    latency_ms: float


class Health(BaseModel):
    status: str
    backend: str = Field(description="postgres in development, memory when deployed")
    papers: int
    embeddings: int
    embedding_model: str
    generation_model: str
    llm_reachable: bool
