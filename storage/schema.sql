-- The corpus, one row per paper. Chunks and their embeddings arrive at step 2.
CREATE TABLE IF NOT EXISTS papers (
    -- The real arXiv identifier (e.g. 2103.00020). Using it as the primary key
    -- means re-running ingestion cannot create duplicates.
    id          TEXT PRIMARY KEY,
    title       TEXT        NOT NULL,
    abstract    TEXT        NOT NULL,
    authors     TEXT,
    categories  TEXT        NOT NULL,
    -- Submission date (YYYY-MM-DD). Kept because "how recent is this corpus" is a
    -- question the README has to answer honestly, and because retrieval may want
    -- to prefer recent work later.
    published   DATE,
    -- Derived, never stored by hand: a citation that cannot drift from its id.
    url         TEXT GENERATED ALWAYS AS ('https://arxiv.org/abs/' || id) STORED,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Retrieval at step 3 filters by category often enough to earn an index.
CREATE INDEX IF NOT EXISTS papers_categories_idx ON papers (categories);

-- One embedding per paper, not per chunk.
--
-- Chunking was measured and rejected: with a 512-token window, 3,999 of 4,000
-- abstracts fit whole (median 206 tokens, p99 394). Splitting a 206-token abstract
-- would cut apart context that belongs together and buy nothing. The earlier plan
-- assumed all-MiniLM-L6-v2, whose 256-token window truncated 26% of abstracts
-- silently — that was the real problem, and a wider model solved it.
--
-- `model` is part of the key so two models can be embedded side by side, which is
-- what makes the configuration comparison at step 4 possible without dropping data.
CREATE TABLE IF NOT EXISTS embeddings (
    paper_id   TEXT        NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    model      TEXT        NOT NULL,
    embedding  vector(768) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (paper_id, model)
);

-- Vector index. HNSW over IVFFlat, measured with scripts/bench_index.py on 30k
-- vectors: at full recall@5, HNSW/ef_search=64 ran 3.7ms against IVFFlat/probes=40
-- at 4.2ms, versus 70.5ms unindexed. The margin is small; the deciding factor is
-- that IVFFlat clusters around the data present when it is built and degrades as
-- rows are added, while this corpus is designed to be refreshed.
--
-- WATCH OUT: at hnsw.ef_search = 40 the planner silently chooses a sequential scan
-- — 19x slower, identical results, no error. 40 is pgvector 0.8.6's own default, so
-- leaving the setting untouched selects the one value that fails. The cost estimate
-- is non-monotonic: it climbs steeply to ~1230 at ef=40 (just past the ~1217 seq-scan
-- estimate), then resets to ~347 at ef=50 and stays nearly flat. Every other value
-- tested (5-30, 50-200) uses the index. core/config.py pins it to 100.
CREATE INDEX IF NOT EXISTS embeddings_hnsw_idx
    ON embeddings USING hnsw (embedding vector_cosine_ops);
