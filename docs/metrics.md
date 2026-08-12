# Metrics

Measured by [`evaluation/run.py`](evaluation/run.py) against 108 questions: 100 answerable from the
corpus with the expected paper recorded, 6 the corpus provably cannot answer, and 2 targeting known
weak spots. The answerable questions are generated from the corpus by
[`evaluation/build_questions.py`](../evaluation/build_questions.py) and graded by a second model;
the other 8 are hand-written and survive a corpus change untouched.

| k | hit-rate | MRR |
|--:|--:|--:|
| 1 | 62% | 0.620 |
| 3 | 74% | 0.677 |
| **5** | **79%** | **0.688** |
| 10 | 85% | 0.696 |

| Metric | Value |
|---|---|
| Corpus size | 90,088 papers |
| Retrieval hit-rate@5 | 79% (100 questions) |
| Query latency | 52 ms median, 95 ms p95 |
| Cost per query | $0 — retrieval is entirely local |
| Refusal rate on out-of-corpus questions | 100% (6 questions) |

**hit-rate@5 79% against MRR 0.688** means the right paper is usually retrieved and usually not
first. That gap is what reranking exists to close, and it is measurable now in a way it was not at
the previous corpus size, where hit-rate@5 was 92% and there was almost nothing left to win.

**Out-of-corpus questions still separate cleanly.** The nearest paper for an answerable question sits
at cosine distance 0.091-0.265; for one the corpus cannot answer, 0.402-0.503. The gap survived the
corpus tripling, which is what makes a distance-based refusal threshold still viable.

## What these numbers replaced, and why

The previous set was 34 hand-written questions against 30,061 papers: hit-rate@5 92%, MRR 0.889,
39 ms median. Those numbers are not comparable to these and are not an earlier reading of the same
instrument — the instrument was rebuilt.

Growing the corpus drew a **different sample** rather than extending the old one, because each
month's slice offset moves with the per-year quota. 23 of the 26 expected papers no longer existed
in the corpus, and hit-rate@5 read 12%. Nothing errored; the story "3× the corpus, harder retrieval"
was plausible enough to publish. What exposed it was that the drop was too large to be physically
possible.

The questions are therefore generated from the corpus now, by `evaluation/build_questions.py`, and
regenerating them is part of changing the corpus rather than an optional follow-up.
