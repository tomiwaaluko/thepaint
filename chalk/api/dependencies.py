"""Shared FastAPI dependencies — DB session and Redis client."""
from collections.abc import AsyncGenerator

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from chalk.config import settings
from chalk.db.session import async_session_factory

# Module-level client, matching the pattern already used by
# chalk/api/ratelimit.py.
#
# This used to build a NEW client per request and aclose() it in the finally
# block, so every request that touched Redis paid a full TCP connect and
# teardown against redis.railway.internal - one Redis connection per anonymous
# HTTP request, and a handshake in the critical path of a service with a
# sub-500ms p99 target. redis.asyncio clients are pool-backed and designed to be
# shared across an event loop; creating one per request throws the pool away.
_redis_client: aioredis.Redis | None = None


def get_redis_client() -> aioredis.Redis:
    """Return the shared Redis client, creating it on first use."""
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
        )
    return _redis_client


async def close_redis_client() -> None:
    """Close the shared client. Called from the app's lifespan shutdown."""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session."""
    async with async_session_factory() as session:
        yield session


async def get_redis() -> AsyncGenerator[aioredis.Redis, None]:
    """Yield the shared Redis client.

    Deliberately does not close it - the client outlives the request and is
    torn down once, in the lifespan shutdown.
    """
    yield get_redis_client()
