# How this is verified

Fourteen defects have been found in this project so far. **Every one of them exited zero and printed
plausible output.** None raised an exception, logged a warning, or failed a test. A suite asserting
on results would have passed for all fourteen, because in every case the results were correct — the
corpus loaded, the search returned papers, the container answered.

What caught them was looking at something other than the result.

| What was wrong | What it looked like | What caught it |
|---|---|---|
| Sampling collapsed each month onto its final day | Right row count, all 12 months present | Day-of-month histogram — 98.3% fell in days 22-31 |
| The embedding model truncated 26% of abstracts | Vectors written, search returned sensible papers | Tokenising the corpus and comparing to the model's window |
| The query planner silently stopped using the HNSW index | Identical papers, identical order, 19× slower | `EXPLAIN` |
| The image shipped 4.5 GB of CUDA it cannot use, plus a 6.16 GB layer from one `chown -R` | Container built, started and answered correctly | Reading the image size, then `docker history` and `du` |
| Compose passed the host's `OLLAMA_HOST` into the container, where `localhost` is the container | All services up, ports mapped, `curl` returned 200 | `/health` reporting `degraded` — the check itself |
| A dependency override was ignored because the package was transitive | `uv lock` reported "Resolved 113 packages", twice | Grepping the lock for the index that should have been in it |
| Settings required database credentials at import, so the memory backend could not start without a database it never uses | Process exited before any application code ran; the error named Pydantic, not the cause | Starting the app with the database settings unset |

Three of the fourteen were in measurement code rather than product code. The instrument is as likely
to be wrong as the thing it measures: the index benchmark first reported `ef_search=40` as *slower*
than `ef_search=100` on the same index, which is impossible, and that contradiction is what exposed a
missing warm-up and a client-side timer.

### What this changes about the tests

Assertions are on mechanism and shape, not on success:

- [`test_query_plan_actually_uses_the_index`](tests/test_retriever.py) runs `EXPLAIN` and asserts the
  index appears. A sequential scan returns the same papers in the same order — output cannot reveal it.
- [`test_papers_are_spread_across_the_month`](tests/test_regressions.py) fails if any quarter of the
  month holds more than 45% of the corpus. Under the broken scheme it was 98.3%.
- [`test_lock_contains_no_cuda_packages`](tests/test_regressions.py) fails if CUDA returns to the
  dependency lock, which is the only visible sign that the CPU-wheel override stopped applying.
- [`test_compose_does_not_interpolate_the_host_ollama_url`](tests/test_regressions.py) fails if the
  container is handed a URL that resolves to itself.
- [`test_ui_never_imports_the_backend`](tests/test_ui.py) parses every file in `ui/` and fails on a
  direct import. The import would work — same repo, same interpreter — which is exactly why a comment
  saying "don't" was not enough.
- [`test_search_is_never_called_for_an_invalid_request`](tests/test_api.py) asserts something does
  *not* happen: that validation runs before the expensive work.
- [`test_settings_load_with_no_database_configuration`](tests/test_regressions.py) exercises the
  deployed image's import path, while
  [`test_postgres_backend_refuses_to_run_unconfigured`](tests/test_regressions.py) keeps the local
  backend strict when it is explicitly selected.

`GET /health` checks the database, the corpus, and whether the language model answers, rather than
returning `{"status":"ok"}` — which is how the container misconfiguration above was found rather than
shipped.
