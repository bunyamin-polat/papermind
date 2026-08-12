"""Settings, read from the environment once, in one place.

Nothing else in the codebase reads os.environ. That is the whole point: when a
value is wrong you look here, and when a new environment needs configuring you
have a single list of what it must provide.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # env_file is a development convenience. In production (step 10) the same
    # names arrive as real environment variables and this file simply isn't there.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Optional, because the deployed instance has no database — it serves the corpus
    # from memory. Required fields here crashed the first Lambda deploy at import time,
    # before a single line of application code ran. The Postgres backend validates them
    # when it is actually the backend in use, which is the only place their absence is
    # an error rather than a configuration.
    postgres_user: str = "papermind"
    postgres_password: str = ""
    postgres_db: str = "papermind"
    postgres_host: str = "localhost"
    postgres_port: int = 5434

    # Embedding. The dimension is not a free parameter — it must match the model,
    # and the `vector(N)` column is declared from it. Changing the model means a new
    # column width and a re-embed, which is why the model name is stored per row.
    embedding_model: str = "BAAI/bge-base-en-v1.5"
    embedding_dim: int = 768
    embedding_batch_size: int = 64

    # How hard HNSW searches. This is set explicitly because pgvector's default is
    # 40, and 40 is the single value at which the planner abandons the index for a
    # sequential scan — 19x slower, identical results, no warning. Measured in
    # scripts/bench_index.py; every other value tested uses the index.
    hnsw_ef_search: int = 100

    # Which retrieval strategy serves queries. Measured on the same 100 questions,
    # 90,088 papers — the default is the winner, not a preference:
    #
    #   hybrid   — RRF over the two below.        hit-rate@5 91%, MRR 0.744, 83 ms
    #   postgres — pgvector + HNSW, dense only.   hit-rate@5 86%, MRR 0.742, 58 ms
    #   lexical  — Elasticsearch BM25 only.       hit-rate@5 67%, MRR 0.529
    #   memory   — the corpus as a numpy array; dense, no database. At this size
    #              brute force is 2.9 ms against HNSW's 3.7 ms.
    #
    # Lexical alone is 19 points *worse* than dense and fusing them still gains 5
    # over dense. That is the whole argument for RRF: the two arms fail on
    # different questions, so agreement between them carries information that
    # neither ranking has on its own.
    #
    # `hybrid` needs Elasticsearch. `postgres` and `memory` do not, which is why
    # they remain the fallback rather than being deleted.
    #
    # See retrieval/backends/base.py and retrieval/backends/hybrid.py.
    retrieval_backend: str = "hybrid"
    artifact_dir: str = "data/artifact"

    # Generation. Ollama is the default so the repo runs with no API key and no
    # cost — which also means prompt iteration, the expensive part of step 5 in
    # wall-clock terms, is free.
    llm_provider: str = "ollama"  # "ollama" | "openai"
    ollama_host: str = "http://localhost:11434"
    # Measured at step 5 on 24 in-corpus + 6 out-of-corpus questions:
    #
    #   qwen3:4b-instruct  cites the expected paper 83%,  3 false refusals, 3.2s
    #   gpt-oss:20b        cites the expected paper 92%,  1 false refusal,  5.5s
    #
    # Both refuse 100% of out-of-corpus questions and neither invented a citation,
    # so the larger model buys answer coverage without spending refusal discipline.
    # The 4B is the default anyway: 2.5 GB against 13.8 GB is the difference between
    # "clone and run" and "clone, then find 14 GB and enough VRAM". Set
    # OLLAMA_MODEL=gpt-oss:20b to trade 2.3s of latency for 9 points of coverage.
    ollama_model: str = "qwen3:4b-instruct"
    openai_model: str = "gpt-4o-mini"
    openai_api_key: str = ""

    # Bounded on purpose. An unbounded generation loop over an eval set is how a
    # portfolio project produces a surprising bill or a hung terminal.
    llm_max_tokens: int = 600
    llm_temperature: float = 0.0  # grounded answers should not be creative
    llm_timeout_s: int = 120

    # Elasticsearch — the BM25 half of hybrid retrieval. Same shape as the
    # database settings: the host differs between the laptop and the compose
    # network, so it is configuration rather than a constant.
    elastic_host: str = "http://localhost:9200"
    elastic_timeout_s: int = 30

    # Questions per minute per caller. On by default, including locally where answers
    # are free — a limit first enabled in production is a limit never exercised.
    # 0 disables it.
    rate_limit_per_minute: int = 10

    @property
    def database_url(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


settings = Settings()  # type: ignore[call-arg]  # values come from env/.env
