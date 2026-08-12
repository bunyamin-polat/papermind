# Generation

```console
$ uv run python -m retrieval.answer "how can learned noise protect private data sent to a cloud inference service"

Learned noise can protect private data sent to a cloud inference service by adding noise
distributions that reduce the information content of the communicated data [1]. Shredder, an
end-to-end framework, learns these distributions through an offline process that balances
inference accuracy against information degradation [1]. Experiments show a 74.70% reduction in
mutual information between the input and the communicated data [1].

Sources:
  [1] Shredder: Learning Noise Distributions to Protect Inference Privacy
      https://arxiv.org/abs/1905.11814
```

### The model is never shown an identifier

It cites sources by their **position** in the list it was given — `[1]`, `[2]` — and code maps
those positions back to papers. Ask a model to write `arXiv:2406.06538` and sooner or later it
writes a plausible identifier for a paper that does not exist, with nothing in the text to reveal
it. A position cannot be inflated into something real: `[9]` in a list of five is detectably wrong,
so it is dropped and counted rather than shown.

Across 68 generated answers, **zero invented citations**.

### Refusal is one exact sentence

`The provided sources do not answer this question.` — not "say you don't know". An exact string is
testable; an instruction to be honest is not.

### What it costs, per local model

**Measured against the previous corpus** — 30,061 papers, 24 answerable and 6 unanswerable
hand-written questions. The corpus is now 90,088 and the questions are regenerated, so these
have not been re-taken. They are kept because the *shape* of the finding survives a corpus
change; the digits do not.

Same prompt, same corpus:

| | `qwen3:4b-instruct` | `gpt-oss:20b` |
|---|--:|--:|
| Cites the expected paper | 83% | **92%** |
| False refusals (answerable, refused) | 3 / 24 | 1 / 24 |
| Out-of-corpus refused | **100%** | **100%** |
| Invented citations | 0 | 0 |
| Latency (median / max) | **3.2s / 12.3s** | 5.5s / 37.3s |
| Download | **2.5 GB** | 13.8 GB |

The larger model closes the gap to the retrieval ceiling — 92% end to end against 92% hit-rate,
meaning generation loses nothing — **and it does so without spending any refusal discipline.** Both
refuse every out-of-corpus question.

The 4B is the default anyway, because 2.5 GB is the difference between "clone and run" and "clone,
then find 14 GB and enough VRAM". Set `OLLAMA_MODEL=gpt-oss:20b` to trade 2.3 seconds for nine
points of coverage.

### The number most RAG projects do not publish

Retrieval hit-rate@5 is 92%. End-to-end citation accuracy with the small model is 83%. **The
nine-point gap is generation discarding papers retrieval had already found.** Two of the three false
refusals had the correct paper at rank 1, with the answer stated verbatim in the abstract — the
model simply declined. Reporting only the retrieval number would have hidden that entirely.
