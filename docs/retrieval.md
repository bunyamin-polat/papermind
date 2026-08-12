# Retrieval

`retrieval/search(question, k)` embeds the question with the same model as the corpus and returns the
k nearest papers, closest first. A hit is a whole paper — nothing was chunked, so nothing has to be
stitched back together, and every result already is the unit a reader would open.

```console
$ uv run python -m scripts.ask "what is an attention mechanism in neural networks"

1. [0.160] Understanding Attention: In Minds and Machines
   https://arxiv.org/abs/2012.02659
2. [0.175] Understanding More about Human and Machine Attention in Deep Neural Networks
   https://arxiv.org/abs/1906.08764
3. [0.203] Thank you for Attention: A survey on Attention-based Artificial Neural Networks...
   https://arxiv.org/abs/2102.07259
4. [0.208] Are Sixteen Heads Really Better than One?
   https://arxiv.org/abs/1905.10650
```

### Where semantic search loses to keyword search

Two failures, both reproduced against this corpus rather than quoted from a blog post:

**Exact identifiers.** Asked for `2406.06538` — a paper that *is* in the corpus — semantic search does
not return it in the top 20. It answers with unrelated optimisation papers at distance 0.52, because
an identifier carries no meaning to embed. A keyword index finds it in one lookup.

**Negation.** Asked for "papers that do NOT use transformers", the second result is *Simplifying
Transformer Blocks*. Embeddings have no representation for negation: "not X" lands next to "X".

Both are the standard argument for hybrid retrieval. Neither is hypothetical here — they are what
this corpus actually does — so hybrid retrieval is a required part of the single release rather than
a later version.

**The release answers them with Elasticsearch beside pgvector, not instead of it.** Dense retrieval
stays in Postgres; a lexical BM25 index goes into Elasticsearch; the two ranked lists fuse with
Reciprocal Rank Fusion. Fusion happens on **ranks, not scores** — a cosine distance and a BM25 score
are different units and averaging them is meaningless.

The alternative was Postgres' own full-text search, which would have kept everything in one
datastore. It was not chosen: a real lexical engine is what production systems put in front of this
problem, `2406.06538` is exactly the query BM25 exists for, and running the two engines side by side
is what makes the comparison publishable — dense alone, lexical alone, and fused, over the same
questions. A hybrid result without the two arms measured separately is an assertion. This work is
done and accepted locally before the cloud image is rebuilt and deployed.

### Two safeguards

**The corpus and the query must share an embedding model.** Using different ones returns neighbours
that mean nothing, with no error anywhere, so the retriever checks which model produced the stored
vectors and raises `ModelMismatch` if it disagrees with the configuration.

**`hnsw.ef_search` is set per connection, never left to the default** — see below for why that matters
more than it should.
