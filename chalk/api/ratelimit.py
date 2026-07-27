"""Per-client rate limiting middleware backed by Redis.

Fixed-window counters (one window per minute) keyed by client IP. Expensive
prediction endpoints get a tighter limit than general reads.

When Redis is unreachable the limiter degrades to an in-process counter rather
than failing open. Failing open was the previous behaviour and it is worse than
it sounds here: the ingest stampede lock in ``routes/games.py`` also defaults to
"acquired" on a Redis error, so a single Redis outage removed BOTH abuse
controls at the same moment -- exactly when the backend is least able to absorb
load. The local counter is per-process and therefore approximate behind multiple
replicas, but it keeps a ceiling in place.
"""
import ipaddress
import time
from collections import defaultdict
from threading import Lock

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

# In-process fallback counters, used only while Redis is unavailable.
# Keyed the same way as the Redis keys, so behaviour is identical apart from
# not being shared between replicas. Bounded by _MAX_LOCAL_KEYS so a caller
# rotating identifiers cannot grow it without limit.
_MAX_LOCAL_KEYS = 10_000
# Returned for a new key once the map is full: larger than any configured
# per-minute limit, so the request is throttled rather than admitted.
_OVERFLOW_COUNT = 1_000_000
_local_counts: dict[str, int] = defaultdict(int)
_local_window: int | None = None
_local_lock = Lock()


def _local_incr(key: str, window: int) -> int:
    """Increment the in-process counter for ``key``, returning the new count.

    Returns a deliberately over-limit sentinel when the map is full and ``key``
    is new.
    """
    global _local_window
    with _local_lock:
        # Fixed windows: drop everything when the minute rolls over.
        if _local_window != window:
            _local_window = window
            _local_counts.clear()

        if key not in _local_counts and len(_local_counts) >= _MAX_LOCAL_KEYS:
            # Fail CLOSED on overflow rather than clearing the map.
            #
            # Clearing was the obvious way to bound memory, but it made the
            # ceiling resettable by the party it constrains: flush the map with
            # 10k distinct keys, spend your allowance, flush again. Worse, the
            # flush also zeroed every legitimate caller's counter - so the
            # fallback gave its weakest guarantee under exactly the distributed
            # load it exists to survive. Throttling unknown keys once the map is
            # full keeps memory bounded without handing anyone a reset.
            return _OVERFLOW_COUNT

        _local_counts[key] += 1
        return _local_counts[key]


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


def _is_ip_address(value: str) -> bool:
    """True if ``value`` parses as an IPv4/IPv6 address.

    Handles the bracketed-with-port form some proxies emit (``[::1]:443``).
    """
    candidate = value
    if candidate.startswith("["):
        candidate = candidate[1:].split("]", 1)[0]
    elif candidate.count(":") == 1:
        # host:port for IPv4; a bare IPv6 address has more than one colon.
        candidate = candidate.rsplit(":", 1)[0]
    try:
        ipaddress.ip_address(candidate)
    except ValueError:
        return False
    return True


_peer_fallback_warned = False


def _warn_peer_fallback(reason: str, hops: int, entry_count: int) -> None:
    """Log once per process when the header is rejected in favour of the peer.

    Worth a log line because the usual cause is a TRUSTED_PROXY_HOPS that does
    not match the deployment, and the symptom otherwise - every caller sharing
    one bucket and the API throttling globally - looks nothing like its cause.
    """
    global _peer_fallback_warned
    if not _peer_fallback_warned:
        _peer_fallback_warned = True
        log.warning(
            "rate_limit_peer_fallback",
            reason=reason,
            trusted_proxy_hops=hops,
            xff_entries=entry_count,
            hint="check TRUSTED_PROXY_HOPS matches the number of proxies in front of this service",
        )


def _client_ip(request: Request) -> str:
    """Best-effort client identifier for rate-limit bucketing.

    X-Forwarded-For is a list that each proxy appends to, so only the entries
    written by hops we actually control are trustworthy. With
    ``TRUSTED_PROXY_HOPS`` proxies in front of us, the client address is the
    Nth entry from the right; everything to its left was supplied by the
    caller and can be anything they like.

    The previous version took ``[-1]`` unconditionally, with the hop count
    implied rather than stated. Making it explicit matters because the right
    entry depends entirely on the deployment, and getting it wrong fails in
    both directions: too far left and callers pick their own bucket, too far
    right and everyone shares one.

    Residual limitation, stated plainly: with one configured hop a single-entry
    header is indistinguishable from a legitimate one-hop request, so it is
    trusted. That is safe on Railway because the public URL always traverses
    the edge -- a caller who prepends a value produces ``<fake>, <real>`` and
    still lands in their own bucket. It would NOT be safe if the container were
    directly reachable; set ``TRUSTED_PROXY_HOPS=0`` in that case, which ignores
    the header entirely and uses the socket peer.
    """
    hops = settings.TRUSTED_PROXY_HOPS
    peer = request.client.host if request.client is not None else "unknown"

    if hops <= 0:
        return peer

    forwarded = request.headers.get("x-forwarded-for")
    if not forwarded:
        return peer

    entries = [part.strip() for part in forwarded.split(",") if part.strip()]
    if len(entries) < hops:
        # Fewer hops than configured means the request did not traverse the
        # expected chain. Trust the socket rather than a caller-supplied value.
        _warn_peer_fallback("xff_shorter_than_configured_hops", hops, len(entries))
        return peer

    candidate = entries[-hops]

    # The selected entry must actually be an IP address.
    #
    # If TRUSTED_PROXY_HOPS is set HIGHER than the real hop count, the entry at
    # that position is one the caller wrote - and without this check it could be
    # any string at all, letting them mint a fresh bucket per request while
    # honest traffic (which sends no header, falls short of the hop count, and
    # lands on the shared proxy `peer`) collapses into a single bucket. That is
    # strictly worse than having no limiter. Requiring a parseable IP does not
    # make a misconfiguration correct, but it removes the arbitrary-string
    # bypass and leaves the failure symmetric.
    if not _is_ip_address(candidate):
        _warn_peer_fallback("xff_entry_not_an_ip", hops, len(entries))
        return peer

    return candidate


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
            # Create the key with its TTL before incrementing so a failure
            # between the two calls can never leave a counter without expiry.
            await redis.set(key, 0, ex=90, nx=True)
            count = await redis.incr(key)
        except Exception as e:
            # Degrade to the in-process counter rather than failing open, so a
            # Redis outage does not remove the only limit on the expensive
            # inference endpoints. Requests are still served; they are just
            # counted per-process.
            log.warning("rate_limit_degraded_to_local", error=str(e))
            count = _local_incr(key, window)

        if count > limit:
            retry_after = max(1, int((window + 1) * 60 - now))
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Slow down and retry shortly."},
                headers={"Retry-After": str(retry_after)},
            )

        return await call_next(request)
