from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://chalk:chalk@localhost:5432/chalk"
    REDIS_URL: str = "redis://localhost:6379/0"
    ODDS_API_KEY: str = ""
    gemini_api_key: str | None = None
    MLFLOW_TRACKING_URI: str = "http://localhost:5000"
    LOG_LEVEL: str = "INFO"
    NBA_API_CACHE_DIR: Path = Path(".cache/nba_api")
    # Comma-separated list of allowed CORS origins.
    # Override in production via ALLOWED_ORIGINS env var.
    ALLOWED_ORIGINS: str = "https://thepaint-production.up.railway.app,http://localhost:5173"
    # Optional token required to call DELETE /games/{id}/cache.
    # Leave unset to disable the endpoint entirely.
    CACHE_INVALIDATION_TOKEN: str = ""
    # Optional HTTP proxy URL for outbound NBA API requests.
    # Use this when Railway datacenter IPs are blocked by stats.nba.com.
    # Format: "http://user:pass@host:port" or "http://host:port"
    NBA_PROXY_URL: str = ""
    # nba_api request timeout in seconds (default 30).
    NBA_API_TIMEOUT: int = 30
    # nba_api max retry attempts before permanent failure (default 3).
    NBA_API_MAX_RETRIES: int = 3

    model_config = {"env_file": ".env"}


settings = Settings()
