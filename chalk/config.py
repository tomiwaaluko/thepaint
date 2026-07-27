from pathlib import Path

from pydantic import Field
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
    # NOTE: the localhost entry is a development convenience that ships as a
    # default. It is harmless today (credentials are not allowed, and the API
    # carries no session), but it means production runs with a dev origin
    # trusted unless ALLOWED_ORIGINS is set explicitly. Set it in Railway.
    ALLOWED_ORIGINS: str = "https://thepaint-production.up.railway.app,http://localhost:5173"
    # Optional token required to call DELETE /games/{id}/cache and to use the
    # nocache query param on prediction endpoints. Leave unset to disable both.
    CACHE_INVALIDATION_TOKEN: str = ""
    # Per-client (IP) rate limiting. Counters live in Redis; if Redis is
    # unavailable the limiter degrades to a per-process counter rather than
    # failing open.
    RATE_LIMIT_ENABLED: bool = True
    # Number of proxies in front of this service that append to
    # X-Forwarded-For. The client address is read as the Nth entry from the
    # right; entries to its left are caller-supplied and must not be trusted.
    # Railway's edge is one hop. Set to 0 when nothing is in front, which makes
    # the limiter use the socket peer and ignore the header entirely.
    # Bounded: a value larger than the real hop count selects an entry the
    # CALLER wrote, which is worse than having no limiter at all.
    TRUSTED_PROXY_HOPS: int = Field(default=1, ge=0, le=4)
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
