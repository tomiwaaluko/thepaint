from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://chalk:chalk@localhost:5432/chalk"
    REDIS_URL: str = "redis://localhost:6379/0"
    ODDS_API_KEY: str = ""
    MLFLOW_TRACKING_URI: str = "http://localhost:5000"
    LOG_LEVEL: str = "INFO"
    NBA_API_CACHE_DIR: Path = Path(".cache/nba_api")
    # Comma-separated list of allowed CORS origins.
    # Override in production via ALLOWED_ORIGINS env var.
    ALLOWED_ORIGINS: str = "https://thepaint-production.up.railway.app,http://localhost:5173"
    # Optional token required to call DELETE /games/{id}/cache.
    # Leave unset to disable the endpoint entirely.
    CACHE_INVALIDATION_TOKEN: str = ""

    model_config = {"env_file": ".env"}


settings = Settings()
