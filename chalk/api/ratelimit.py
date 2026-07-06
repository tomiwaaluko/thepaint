"""Per-client rate limiting middleware backed by Redis.

Fixed-window counters (one window per minute) keyed by client IP. Expensive
prediction endpoints get a tighter limit than general reads. The limiter
fails open: if Redis is unreachable the request is allowed and a warning is
logged, so an infra hiccup never takes the API down.
"""
import time

import redis.asyncio as aioredis
import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from chalk.config import settings

log = structlog.get_logger()

# Paths that must never be throttled (health checks, API docs).
EXEMPT_PATHS = frozenset({"/v1/health", "/docs", "/redoc", "/openapi.json"})

# Route suffixes that trigger model inference and get the stricter limit.
EXPENSIVE_SUFFIXES = ("/predict", "/props", "/fantasy")

_redis: aioredis.Redis | None = None


def _get_redis() -> aioredis.Redis:
    """Lazily create the shared Redis client used for rate-limit counters."""
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=0.5,
            socket_timeout=0.5,
        )
    return _redis


def _client_ip(request: Request) -> str:
    """Best-effort client identifier.

    Behind the Railway edge proxy the real client IP is the last entry of
    X-Forwarded-For (appended by the trusted hop); earlier entries are
    client-controlled and spoofable.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[-1].strip()
    if request.client is not None:
        return request.client.host
    return "unknown"


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if (
            not settings.RATE_LIMIT_ENABLED
            or request.method == "OPTIONS"
            or request.url.path in EXEMPT_PATHS
        ):
            return await call_next(request)

        path = request.url.path
        if path.endswith(EXPENSIVE_SUFFIXES):
            scope, limit = "predict", settings.RATE_LIMIT_PREDICT_PER_MINUTE
        else:
            scope, limit = "default", settings.RATE_LIMIT_PER_MINUTE

        now = time.time()
        window = int(now // 60)
        key = f"rl:{scope}:{_client_ip(request)}:{window}"

        try:
            redis = _get_redis()
            count = await redis.incr(key)
            if count == 1:
                await redis.expire(key, 60)
        except Exception as e:
            # Fail open — rate limiting must never take the API down.
            log.warning("rate_limit_check_failed", error=str(e))
            return await call_next(request)

        if count > limit:
            retry_after = max(1, int((window + 1) * 60 - now))
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Slow down and retry shortly."},
                headers={"Retry-After": str(retry_after)},
            )

        return await call_next(request)
