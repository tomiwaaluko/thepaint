"""Tests for the rate-limiting middleware and cache-bypass token gate."""
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from chalk.api import ratelimit
from chalk.api.dependencies import get_db, get_redis
from chalk.api.main import app
from chalk.config import settings


class FakeRedisCounter:
    """Minimal in-memory stand-in for the Redis commands the limiter uses."""

    def __init__(self):
        self.counts: dict[str, int] = {}

    async def set(self, key: str, value: int, ex: int | None = None, nx: bool = False) -> bool | None:
        if nx and key in self.counts:
            return None
        self.counts[key] = int(value)
        return True

    async def incr(self, key: str) -> int:
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]


def _mock_db_empty():
    """DB session whose queries return no rows."""
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    result.scalar.return_value = None
    result.scalar_one_or_none.return_value = None
    db = AsyncMock()
    db.execute = AsyncMock(return_value=result)
    return db


def _mock_redis():
    r = AsyncMock()
    r.get = AsyncMock(return_value=None)
    r.set = AsyncMock(return_value=True)
    r.setex = AsyncMock()
    r.delete = AsyncMock(return_value=1)
    r.aclose = AsyncMock()
    return r


@pytest.fixture
def api_client_factory(monkeypatch):
    """Override app dependencies with mocks and yield a client factory."""
    db = _mock_db_empty()
    redis = _mock_redis()

    async def fake_db():
        yield db

    async def fake_redis():
        yield redis

    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[get_redis] = fake_redis
    # Avoid outbound NBA API calls from the /today auto-ingest fallback.
    monkeypatch.setattr(
        "chalk.api.routes.games.ingest_today_scoreboard", AsyncMock(return_value=0)
    )

    def make():
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    yield make
    app.dependency_overrides.clear()


@pytest.fixture
def limiter_on(monkeypatch):
    """Enable rate limiting against an in-memory counter."""
    fake = FakeRedisCounter()
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(ratelimit, "_get_redis", lambda: fake)
    return fake


async def test_returns_429_after_limit(api_client_factory, limiter_on, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_PER_MINUTE", 3)
    async with api_client_factory() as client:
        for _ in range(3):
            resp = await client.get("/v1/games/today")
            assert resp.status_code == 200
        resp = await client.get("/v1/games/today")
    assert resp.status_code == 429
    assert "Retry-After" in resp.headers


async def test_predict_paths_use_stricter_limit(api_client_factory, limiter_on, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_PER_MINUTE", 100)
    monkeypatch.setattr(settings, "RATE_LIMIT_PREDICT_PER_MINUTE", 1)
    async with api_client_factory() as client:
        resp1 = await client.get("/v1/games/0042500401/predict")
        resp2 = await client.get("/v1/games/0042500401/predict")
    # First request passes the limiter (404: game not in mocked DB), second is throttled.
    assert resp1.status_code == 404
    assert resp2.status_code == 429


async def test_health_is_exempt(api_client_factory, limiter_on, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_PER_MINUTE", 1)
    async with api_client_factory() as client:
        for _ in range(5):
            resp = await client.get("/v1/health")
            assert resp.status_code == 200


async def test_fails_open_when_redis_unavailable(api_client_factory, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(settings, "RATE_LIMIT_PER_MINUTE", 1)

    def broken():
        raise ConnectionError("redis down")

    monkeypatch.setattr(ratelimit, "_get_redis", broken)
    async with api_client_factory() as client:
        for _ in range(3):
            resp = await client.get("/v1/games/today")
            assert resp.status_code == 200


async def test_nocache_without_token_is_rejected(api_client_factory, monkeypatch):
    monkeypatch.setattr(settings, "CACHE_INVALIDATION_TOKEN", "sekrit")
    async with api_client_factory() as client:
        resp = await client.get("/v1/games/0042500401/predict?nocache=true")
    assert resp.status_code == 403


async def test_nocache_with_wrong_token_is_rejected(api_client_factory, monkeypatch):
    monkeypatch.setattr(settings, "CACHE_INVALIDATION_TOKEN", "sekrit")
    async with api_client_factory() as client:
        resp = await client.get(
            "/v1/games/0042500401/predict?nocache=true",
            headers={"X-Invalidation-Token": "wrong"},
        )
    assert resp.status_code == 403


async def test_nocache_disabled_when_no_token_configured(api_client_factory, monkeypatch):
    monkeypatch.setattr(settings, "CACHE_INVALIDATION_TOKEN", "")
    async with api_client_factory() as client:
        resp = await client.get(
            "/v1/games/0042500401/predict?nocache=true",
            headers={"X-Invalidation-Token": "anything"},
        )
    assert resp.status_code == 403


async def test_nocache_with_valid_token_bypasses_cache(api_client_factory, monkeypatch):
    monkeypatch.setattr(settings, "CACHE_INVALIDATION_TOKEN", "sekrit")
    async with api_client_factory() as client:
        # Game not in mocked DB → 404 proves the request passed the token gate.
        resp = await client.get(
            "/v1/games/0042500401/predict?nocache=true",
            headers={"X-Invalidation-Token": "sekrit"},
        )
    assert resp.status_code == 404


async def test_today_auto_ingest_skipped_when_lock_held(monkeypatch):
    """When another worker holds the ingest lock, no outbound fetch happens."""
    db = _mock_db_empty()
    redis = _mock_redis()
    redis.set = AsyncMock(return_value=None)  # lock not acquired

    async def fake_db():
        yield db

    async def fake_redis():
        yield redis

    mock_ingest = AsyncMock(return_value=0)
    monkeypatch.setattr("chalk.api.routes.games.ingest_today_scoreboard", mock_ingest)

    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[get_redis] = fake_redis
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/v1/games/today")
        assert resp.status_code == 200
        mock_ingest.assert_not_awaited()
    finally:
        app.dependency_overrides.clear()
