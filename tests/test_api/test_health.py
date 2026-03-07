"""Tests for the health check endpoint."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from chalk.api.dependencies import get_db, get_redis
from chalk.api.main import app


def _mock_db_ok():
    """Return a mock session that succeeds on execute."""
    session = AsyncMock()
    session.execute = AsyncMock(return_value=MagicMock())
    return session


def _mock_redis_ok():
    """Return a mock Redis that succeeds on ping."""
    r = AsyncMock()
    r.ping = AsyncMock(return_value=True)
    r.aclose = AsyncMock()
    return r


def _mock_redis_down():
    """Return a mock Redis that fails on ping."""
    r = AsyncMock()
    r.ping = AsyncMock(side_effect=ConnectionError("Redis down"))
    r.aclose = AsyncMock()
    return r


@pytest.fixture
def override_deps_ok():
    """Override both deps with working mocks."""
    db = _mock_db_ok()
    redis = _mock_redis_ok()

    async def fake_db():
        yield db

    async def fake_redis():
        yield redis

    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[get_redis] = fake_redis
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def override_deps_redis_down():
    """Override deps with DB ok but Redis down."""
    db = _mock_db_ok()
    redis = _mock_redis_down()

    async def fake_db():
        yield db

    async def fake_redis():
        yield redis

    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[get_redis] = fake_redis
    yield
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_health_returns_ok_when_all_services_up(override_deps_ok):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["checks"]["database"] == "ok"
    assert data["checks"]["redis"] == "ok"
    assert "timestamp" in data


@pytest.mark.asyncio
async def test_health_returns_degraded_when_redis_down(override_deps_redis_down):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "degraded"
    assert data["checks"]["redis"] == "error"
    assert data["checks"]["database"] == "ok"
