import asyncio
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from chalk.config import settings
from chalk.db.models import Base


@pytest.fixture(autouse=True)
def _disable_rate_limiting(monkeypatch):
    """Keep the rate limiter out of unrelated tests.

    Without this, running the suite on a machine with a live local Redis
    would share one fixed-window counter across every API test and fail
    randomly. Rate-limit tests re-enable it explicitly.
    """
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", False)


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def engine():
    """Create an async SQLite engine for testing."""
    eng = create_async_engine("sqlite+aiosqlite:///", echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await eng.dispose()


@pytest_asyncio.fixture
async def session(engine) -> AsyncGenerator[AsyncSession, None]:
    """Yield an async session for tests, rolled back after each test."""
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as sess:
        yield sess
