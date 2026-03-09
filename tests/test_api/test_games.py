"""Tests for the /v1/games/today endpoint."""
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from chalk.api.dependencies import get_db, get_redis
from chalk.api.main import app


def _make_db_returning(games):
    """Return a mock session whose execute always returns the given game list."""
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = games
    session.execute = AsyncMock(return_value=result_mock)
    return session


def _make_redis():
    """Return a mock Redis that has no cached data."""
    r = AsyncMock()
    r.get = AsyncMock(return_value=None)
    r.setex = AsyncMock()
    r.aclose = AsyncMock()
    return r


@pytest.mark.asyncio
async def test_today_games_returns_empty_list_when_no_games():
    db = _make_db_returning([])
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
    mock_game.date = date.today()
    mock_game.home_team_id = 1
    mock_game.away_team_id = 2
    mock_game.status = "scheduled"

    mock_home = MagicMock()
    mock_home.abbreviation = "BOS"
    mock_away = MagicMock()
    mock_away.abbreviation = "LAL"

    db = _make_db_returning([mock_game])
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
async def test_today_games_response_schema():
    db = _make_db_returning([])
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
        # Verify response matches TodayGamesResponse schema
        assert "date" in data
        assert "games" in data
        # date should be a valid ISO date string
        date.fromisoformat(data["date"])
    finally:
        app.dependency_overrides.clear()
