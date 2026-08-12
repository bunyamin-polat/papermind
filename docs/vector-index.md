# Vector index

Which index, measured rather than assumed — **30,061 vectors** (the corpus is now 90,088 and this
has not been re-measured; HNSW's advantage should have grown, since brute force is linear in the
row count and HNSW is not), top-5, timings taken server-side from
`EXPLAIN ANALYZE`, recall measured against exact search ([`scripts/bench_index.py`](scripts/bench_index.py)):

| Configuration | Median | p95 | recall@5 | Index used |
|---|--:|--:|--:|:-:|
| No index (exact) | 70.5 ms | 81.1 ms | 100% | — |
| HNSW `ef_search=40` | 69.7 ms | 72.2 ms | 100% | **0/12** |
| **HNSW `ef_search=64`** | **3.7 ms** | 4.9 ms | 100% | 12/12 |
| HNSW `ef_search=100` | 4.6 ms | 7.3 ms | 100% | 12/12 |
| IVFFlat `probes=10` | 1.2 ms | 1.4 ms | 93.3% | 12/12 |
| IVFFlat `probes=20` | 2.2 ms | 2.4 ms | 98.3% | 12/12 |
| IVFFlat `probes=40` | 4.2 ms | 4.8 ms | 100% | 12/12 |

**HNSW.** At full recall it is marginally faster than IVFFlat (3.7 ms against 4.2 ms), but the margin
alone would not decide it. IVFFlat clusters around whatever data exists when the index is built and
degrades as rows are added; this corpus is meant to be refreshed, so an index that tolerates
incremental inserts is worth 5× the build time (16.9 s against 3.3 s).

**One trap worth knowing.** At `hnsw.ef_search = 40` the planner abandons the index in every query
and falls back to a sequential scan — 19× slower, identical results, no error and no warning. **40 is
pgvector's own default**, so leaving the setting untouched picks the one value that fails.

The cause is a discontinuity in pgvector 0.8.6's cost estimate. Below 40 the estimated startup cost
climbs steeply — 348 at `ef=5`, 494 at 10, 754 at 20, 992 at 30 — and by 40 it has passed the
sequential-scan estimate of 1217, so the planner rejects the index. At `ef=50` it resets to 347 and
from there rises almost flat, reaching only 370 by `ef=400`. Two branches of the formula, meeting
badly, exactly at the default:

| `ef_search` | 5 | 10 | 20 | 30 | **40** | 50 | 64 | 100 | 200 |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| Median | 1.0 ms | 1.2 ms | 1.9 ms | 2.3 ms | **71.5 ms** | 3.4 ms | 3.7 ms | 4.7 ms | 7.3 ms |
| Plan | index | index | index | index | **seq scan** | index | index | index | index |

Recall@5 measured 100% at every value **on the 12 benchmark queries**, so the configured 100 buys
margin rather than accuracy. It is pinned in `core/config.py` rather than left to the default.

**That 100% was a property of the query set, not of the index.** Re-measured later against all 34
evaluation questions, HNSW agrees with exact search on 30 of 34 rankings and 33 of 34 top results —
96.5% overlap at k=5. HNSW is an approximate index and this is what approximate costs. It went
unnoticed because twelve queries were not enough to show it, which is the same mistake as reporting
a hit-rate from a small eval set and believing the third decimal place.
