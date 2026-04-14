from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://chalk:chalk@localhost:5432/chalk"
    REDIS_URL: str = "redis://localhost:6379/0"
    ODDS_API_KEY: str = ""
    MLFLOW_TRACKING_URI: str = "http://localhost:5000"
    LOG_LEVEL: str = "INFO"
    NBA_API_CACHE_DIR: Path = Path(".cache/nba_api")
    NBA_PLAYER_DELAY_MIN_SECONDS: float = 3.0
    NBA_PLAYER_DELAY_MAX_SECONDS: float = 5.0
    NBA_SCOREBOARD_DELAY_MIN_SECONDS: float = 2.0
    NBA_SCOREBOARD_DELAY_MAX_SECONDS: float = 4.0
    NBA_API_REQUEST_TIMEOUT_SECONDS: int = 120
    NBA_SCOREBOARD_REQUEST_TIMEOUT_SECONDS: int = 30
    NBA_API_BACKOFF_BASE_SECONDS: float = 8.0
    NBA_API_MAX_BACKOFF_SECONDS: float = 120.0
    FAILED_PLAYER_INGEST_LOG: Path = Path(".cache/failed_player_ingest.jsonl")
    # Optional HTTP/HTTPS proxy URL for nba_api requests.
    # Set this on Railway's ingest service to route through a residential proxy
    # so stats.nba.com doesn't block datacenter IPs.
    # Example: "http://user:pass@proxy.example.com:8080"
    NBA_PROXY_URL: str = ""
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

    model_config = {"env_file": ".env"}


settings = Settings()
