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

**Exact identifiers — fixed by BM25.** An arXiv id carries no meaning to embed, so dense search
answers with unrelated papers at distance 0.52 and never returns the right one. With the lexical arm
indexing `id` as a keyword, asking for `1708.07367` returns that paper in the top three.

*(The original example here was `2406.06538`. It is no longer in the corpus: growing 30,061 → 90,088
redrew the sample rather than extending it, and the paper the claim rested on left with it. Recorded
because a documented example that quietly stops being true is the same failure the ledger tracks.)*

**Negation — not fixed, and BM25 makes it worse.** Asked for "papers that do NOT use transformers",
four of the top five are about transformers. Embeddings have no representation for negation, so "not
X" lands next to "X"; BM25 then matches the very token being excluded. Both arms fail in the same
direction, which is exactly when fusion cannot help. This needs query understanding rather than
retrieval, and is out of scope.

**Author queries — where fusion actively hurts.** BM25 alone answers `Yoshua Bengio` with three of
his papers in the top three. Fused, a paper by someone else takes first place: a name is
unembeddable, the dense arm returns noise, and RRF weights that noise equally with the arm that
worked. Hybrid is better *on average* and worse on this class, which is the argument for
query-dependent routing — measured, and not built.

**The release answers them with Elasticsearch beside pgvector, not instead of it.** Dense retrieval
stays in Postgres; a lexical BM25 index goes into Elasticsearch; the two ranked lists fuse with
Reciprocal Rank Fusion. Fusion happens on **ranks, not scores** — a cosine distance and a BM25 score
are different units and averaging them is meaningless.

The alternative was Postgres' own full-text search, which would have kept everything in one
datastore. It was not chosen: a real lexical engine is what production systems put in front of this
problem, an exact identifier is precisely the query BM25 exists for, and running the two engines side by side
is what makes the comparison publishable — dense alone, lexical alone, and fused, over the same
questions. A hybrid result without the two arms measured separately is an assertion. This work is
done and accepted locally before the cloud image is rebuilt and deployed.

### Two safeguards

**The corpus and the query must share an embedding model.** Using different ones returns neighbours
that mean nothing, with no error anywhere, so the retriever checks which model produced the stored
vectors and raises `ModelMismatch` if it disagrees with the configuration.

**`hnsw.ef_search` is set per connection, never left to the default** — see below for why that matters
more than it should.
