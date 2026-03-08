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
    # Set to "*" or a specific Railway/Vercel frontend URL in production.
    ALLOWED_ORIGINS: str = "*"

    model_config = {"env_file": ".env"}


settings = Settings()
