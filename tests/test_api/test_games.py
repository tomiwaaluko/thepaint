"""Tests for the /v1/games/today endpoint."""
from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from chalk.api.dependencies import get_db, get_redis
from chalk.api.main import app
from chalk.api.routes.games import ET_TZ

INGEST_PATCH = "chalk.api.routes.games.ingest_today_scoreboard"


def _today_et() -> date:
    """The date the route considers "today".

    The route works in US Eastern (the NBA's scheduling zone), not in the
    process's local zone. Asserting against date.today() passes on a developer
    machine in ET and fails on a UTC CI runner for the four to five hours
    between 8 PM ET and midnight ET, when UTC has already rolled over.
    """
    return datetime.now(ET_TZ).date()


def _make_redis():
    """Return a mock Redis that has no cached data."""
    r = AsyncMock()
    r.get = AsyncMock(return_value=None)
    r.setex = AsyncMock()
    r.aclose = AsyncMock()
    return r


def _make_empty_result():
    """Mock result where scalars().all() returns [] and scalar() returns None."""
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    result.scalar.return_value = None
    return result


def _make_games_result(games):
    """Mock result where scalars().all() returns the given games."""
    result = MagicMock()
    result.scalars.return_value.all.return_value = games
    result.scalar.return_value = None
    return result


@pytest.mark.asyncio
@patch(INGEST_PATCH, new_callable=AsyncMock, return_value=0)
async def test_today_games_returns_empty_list_when_no_games(mock_ingest):
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_make_empty_result())
    redis = _make_redis()

    async def fake_db():
        yield db

    async def fake_redis():
        yield redis

    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[get_redis] = fake_redis
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/v1/games/today")
        assert resp.status_code == 200
        data = resp.json()
        assert "date" in data
        assert "games" in data
        assert isinstance(data["games"], list)
        assert len(data["games"]) == 0
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_today_games_returns_game_list():
    mock_game = MagicMock()
    mock_game.game_id = "0022500100"
    mock_game.date = _today_et()
    mock_game.home_team_id = 1
    mock_game.away_team_id = 2
    mock_game.status = "scheduled"

    mock_home = MagicMock()
    mock_home.abbreviation = "BOS"
    mock_away = MagicMock()
    mock_away.abbreviation = "LAL"

    db = AsyncMock()
    db.execute = AsyncMock(return_value=_make_games_result([mock_game]))
    db.get = AsyncMock(
        side_effect=lambda model, tid: mock_home if tid == 1 else mock_away
    )

    redis = _make_redis()

    async def fake_db():
        yield db

    async def fake_redis():
        yield redis

    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[get_redis] = fake_redis
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/v1/games/today")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["games"]) >= 1
        game = data["games"][0]
        assert game["game_id"] == "0022500100"
        assert game["home_team"] == "BOS"
        assert game["away_team"] == "LAL"
        assert game["status"] == "scheduled"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
@patch(INGEST_PATCH, new_callable=AsyncMock, return_value=0)
async def test_today_games_response_schema(mock_ingest):
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_make_empty_result())
    redis = _make_redis()

    async def fake_db():
        yield db

    async def fake_redis():
        yield redis

    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[get_redis] = fake_redis
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/v1/games/today")
        data = resp.json()
        assert "date" in data
        assert "games" in data
        date.fromisoformat(data["date"])
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
@patch(INGEST_PATCH, new_callable=AsyncMock, return_value=0)
async def test_today_games_no_stale_fallback(mock_ingest):
    """When no current slate exists, return empty list rather than stale games."""

    empty = _make_empty_result()

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[empty, empty])

    redis = _make_redis()

    async def fake_db():
        yield db

    async def fake_redis():
        yield redis

    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[get_redis] = fake_redis
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/v1/games/today")
        assert resp.status_code == 200
        data = resp.json()
        assert data["date"] == str(_today_et())
        assert data["games"] == []
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_today_games_auto_ingest_fallback():
    """When no games in DB, auto-ingest from NBA API fetches them."""
    mock_game = MagicMock()
    mock_game.game_id = "0022500921"
    mock_game.date = _today_et()
    mock_game.home_team_id = 1
    mock_game.away_team_id = 2
    mock_game.status = "scheduled"

    mock_home = MagicMock()
    mock_home.abbreviation = "CLE"
    mock_away = MagicMock()
    mock_away.abbreviation = "BOS"

    empty = _make_empty_result()
    after_ingest = _make_games_result([mock_game])
    tomorrow_empty = _make_empty_result()

    db = AsyncMock()
    # 1=today (empty), 2=today after ingest (has game), 3=tomorrow (empty)
    db.execute = AsyncMock(side_effect=[empty, after_ingest, tomorrow_empty])
    db.get = AsyncMock(
        side_effect=lambda model, tid: mock_home if tid == 1 else mock_away
    )

    redis = _make_redis()

    async def fake_db():
        yield db

    async def fake_redis():
        yield redis

    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[get_redis] = fake_redis
    try:
        with patch(INGEST_PATCH, new_callable=AsyncMock, return_value=1):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/v1/games/today")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["games"]) == 1
        assert data["games"][0]["game_id"] == "0022500921"
    finally:
        app.dependency_overrides.clear()
