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

    postgres_user: str
    postgres_password: str
    postgres_db: str
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

    # Empty until step 5.
    openai_api_key: str = ""

    @property
    def database_url(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


settings = Settings()  # type: ignore[call-arg]  # values come from env/.env
