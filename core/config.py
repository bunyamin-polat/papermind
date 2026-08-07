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

    # Empty until step 5.
    openai_api_key: str = ""

    @property
    def database_url(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


settings = Settings()  # type: ignore[call-arg]  # values come from env/.env
