"""Shared FastAPI dependencies — DB session and Redis client."""
from collections.abc import AsyncGenerator

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from chalk.config import settings
from chalk.db.session import async_session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session."""
    async with async_session_factory() as session:
        yield session


async def get_redis() -> AsyncGenerator[aioredis.Redis, None]:
    """Yield a Redis client, closed after request."""
    client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        yield client
    finally:
        await client.aclose()
