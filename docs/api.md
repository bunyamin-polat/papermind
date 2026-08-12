# API

```bash
uv run uvicorn app.main:app --reload    # http://localhost:8000/docs
```

```console
$ curl -s localhost:8000/health
{"status":"ok","papers":90088,"embeddings":90088,
 "embedding_model":"BAAI/bge-base-en-v1.5","generation_model":"qwen3:4b-instruct",
 "llm_reachable":true}
```

```console
$ curl -s -X POST localhost:8000/ask -H 'Content-Type: application/json' \
    -d '{"question":"how can learned noise protect private data sent to a cloud service?"}'
{
  "answer": "Learned noise can protect private data by adding distributions that reduce the
             information content of the communicated data [1]. ...",
  "refused": false,
  "sources":   [{"marker":1,"paper_id":"1905.11814","title":"Shredder: Learning Noise ...",
                 "url":"https://arxiv.org/abs/1905.11814","distance":0.1856}],
  "retrieved": [ ...5 papers with distances... ],
  "models":    {"embedding":"BAAI/bge-base-en-v1.5","generation":"qwen3:4b-instruct"},
  "latency_ms": 3782.3
}
```

**`retrieved` is returned next to `sources`.** `sources` is what the answer cited; `retrieved` is
everything that went into the prompt. A refusal therefore returns five papers and zero sources —
"consulted five, none answered" is a different statement from "found nothing", and only one of them
is true. It is also the difference between diagnosing bad retrieval and bad grounding.

**The response names the models that produced it.** Which embedder and which generator answered is
part of what the answer means; two responses are not comparable without it.

**Failure modes are distinguished.** Ollama unreachable is `503` — a dependency is down, retrying may
work. A corpus embedded with a different model is `500` — this service is misconfigured and retrying
never helps. Both carry a message that names what to fix.

**The embedding model loads at startup, not on first request.** It costs about eight seconds; left
lazy, the first caller sees eleven seconds where everyone else sees three, which reads as an
intermittent fault rather than a warm-up.
