from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://chalk:chalk@localhost:5432/chalk"
    REDIS_URL: str = "redis://localhost:6379/0"
    ODDS_API_KEY: str = ""
    gemini_api_key: str | None = None
    GEMINI_MODEL: str = "gemini-2.5-flash"
    MLFLOW_TRACKING_URI: str = "http://localhost:5000"
    LOG_LEVEL: str = "INFO"
    NBA_API_CACHE_DIR: Path = Path(".cache/nba_api")
    # Comma-separated list of allowed CORS origins.
    # Override in production via ALLOWED_ORIGINS env var.
    ALLOWED_ORIGINS: str = "https://thepaint-production.up.railway.app,http://localhost:5173"
    # Optional token required to call DELETE /games/{id}/cache and to use the
    # nocache query param on prediction endpoints. Leave unset to disable both.
    CACHE_INVALIDATION_TOKEN: str = ""
    # Per-client (IP) rate limiting. Counters live in Redis; the limiter fails
    # open if Redis is unavailable.
    RATE_LIMIT_ENABLED: bool = True
    # Requests per minute for general endpoints.
    RATE_LIMIT_PER_MINUTE: int = 120
    # Requests per minute for model-inference endpoints (/predict, /props, /fantasy).
    RATE_LIMIT_PREDICT_PER_MINUTE: int = 30
    # Optional HTTP proxy URL for outbound NBA API requests.
    # Use this when Railway datacenter IPs are blocked by stats.nba.com.
    # Format: "http://user:pass@host:port" or "http://host:port"
    NBA_PROXY_URL: str = ""
    # nba_api request timeout in seconds (default 30).
    NBA_API_TIMEOUT: int = 30
    # nba_api max retry attempts before permanent failure (default 3).
    NBA_API_MAX_RETRIES: int = 3
    # When true, missing player logs for a day with games make the ingest cron exit non-zero.
    INGEST_STRICT_VALIDATION: bool = False
    # MLB StatsAPI (statsapi.mlb.com) — keyless public API.
    MLB_API_CACHE_DIR: Path = Path(".cache/mlb_api")
    MLB_API_TIMEOUT: int = 30
    MLB_API_MAX_RETRIES: int = 5

    model_config = {"env_file": ".env"}


settings = Settings()
