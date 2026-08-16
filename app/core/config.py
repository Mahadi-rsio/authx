from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings.

    Values are read from the process environment (case-insensitive) and,
    when present, an ``.env``/``.env.local`` file. Field names map to
    environment variables directly, e.g. ``DATABASE_URL`` -> ``database_url``.
    """

    model_config = SettingsConfigDict(
        env_file=(".env", ".env.local"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "authx"
    app_env: str = "development"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"

    database_url: str = "postgresql+asyncpg://authx:authx@localhost:5432/authx"
    database_echo: bool = False
    database_pool_size: int = 5
    database_max_overflow: int = 10

    redis_url: str = "redis://localhost:6379/0"

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"


@lru_cache
def get_settings() -> Settings:
    """Return a cached ``Settings`` instance.

    Cached so that all import-time consumers share one configuration.
    """
    return Settings()
