# Running it

```bash
ollama serve &                       # generation, on the host — see below
ollama pull qwen3:4b-instruct
docker compose up -d                 # Postgres, API on :8000, UI on :8501
```

Then load the corpus once. It is **not** baked into the image — 287 MB of data belongs in a volume,
not in a layer that goes stale:

```bash
uv run python -m ingestion.fetch --limit 2000   # ~3 min, enough to try it
uv run python -m ingestion.clean
uv run python -m ingestion.embed
```

Drop `--limit` for the full 90,088-paper corpus: about an hour of arXiv fetching (their API allows
one request every three seconds) plus 31 minutes of embedding.

**Ollama stays on the host, deliberately.** Docker on macOS cannot reach Metal, so a containerised
Ollama silently falls back to CPU and answers take minutes instead of seconds — the demo appears hung
rather than slow. The API reaches back out via `host.docker.internal`, with `extra_hosts` making that
name resolve on Linux too.

### Image size: 19.4 GB → 3.08 GB

The first build was 19.4 GB. Two causes, both invisible until the number was looked at:

| Cause | Cost |
|---|--:|
| PyPI's default `torch` on Linux bundles CUDA — 2.9 GB of `nvidia` packages, 652 MB of triton | ~4.5 GB |
| A single `RUN chown -R`, which rewrites every file's metadata and duplicates the tree into a new layer | 6.16 GB |

The container has no GPU and never will: embedding is CPU-only and generation happens in Ollama on
the host. `pyproject.toml` therefore resolves `torch` from PyTorch's CPU index on Linux while macOS
keeps the default MPS wheel. Ownership is now set by `COPY --chown` as files are written, so nothing
is rewritten afterwards.

The UI reaches the API over HTTP and never imports from it — `tests/test_ui.py` asserts that by
parsing the imports. It is an easy boundary to erase by accident, and erasing it would make the API
decorative: untested by anything a user touches, and at step 9 a container with two entrypoints
pretending to be one.

**What the UI shows that most AI demos do not.** Every answer carries the papers consulted, how close
each one was, which models produced it, and how long it took. A refusal is rendered as information
rather than as an error, with the five consulted papers still listed — because "consulted five, none
answered" is a different statement from "something broke", and only one of them is true. All of it is
free to display, because the API already returns it.
