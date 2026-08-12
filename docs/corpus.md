# Corpus

arXiv abstracts in eight AI categories — `cs.AI`, `cs.CL`, `cs.CV`, `cs.IR`, `cs.LG`, `cs.MA`, `cs.NE`, `stat.ML` — sampled from 2015 onward, queried live from the [arXiv API](https://info.arxiv.org/help/api/user-manual.html).

**Why the API and not a dataset dump.** The obvious choice, HuggingFace's `gfissore/arxiv-abstracts-2021`, is a snapshot that ends in December 2021. A corpus frozen there cannot answer anything about work published since — most of what anyone would ask an AI-research assistant. Querying arXiv directly means the corpus reaches the present day and can be refreshed by re-running the fetch.

**Why these eight categories and not more.** They are arXiv's core AI set plus `cs.MA`. Broader categories such as `cs.RO` and `cs.CR` already reach the corpus through cross-listing — an ML-heavy robotics paper carries `cs.LG` as well — so adding them explicitly would only pull in the papers carrying *no* AI tag, which are by definition the least relevant. `cs.MA` is the exception: multi-agent work is under-represented by cross-listing and directly on topic.

**Sampling took three attempts.**

The arXiv API sorts only by submission date and truncates, so asking for "the newest N" of any window returns that window's tail:

| Scheme | What it actually produced |
|---|---|
| Newest N per year | Each year collapsed onto its final three weeks — "2018" meant 10-31 December |
| Newest N per month | Each month collapsed onto its final day; 98% of papers fell on days 22-31 |
| **Randomly-offset slice per month** | Current scheme — contiguous, but no longer always at the same end |

Narrowing the window was not the fix, because truncation simply moved down a level. The fix is to place the slice at a random offset inside each month, chosen from a fixed seed so the corpus stays reproducible.

| Year | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| Papers | 563 | 732 | 960 | 1,332 | 1,799 | 2,328 | 2,531 | 2,772 | 3,408 | 4,332 | 5,280 | 4,024 |

Papers carry an average of two categories, so the per-category counts overlap: `cs.LG` 13,945 ·
`cs.CV` 9,875 · `cs.AI` 9,176 · `cs.CL` 5,826 · `stat.ML` 3,902 · `cs.IR` 1,264 · `cs.NE` 804 ·
`cs.MA` 618. 2026 covers January to August, the year being incomplete.

**Known limit:** the sample is a fraction of what arXiv holds — 90,088 of roughly 590,000 AI
papers published since 2015. Any *specific* paper is therefore unlikely to be present. That is what
makes refusal a first-class outcome rather than an edge case, and why it gets its own build step and
its own test.

The corpus is **not committed to this repository**; it is fetched at setup time. ArXiv content remains under its authors' terms — see [arxiv.org/help/license](https://arxiv.org/help/license).
