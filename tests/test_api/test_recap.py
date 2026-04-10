"""Tests for the /v1/games/recap endpoint."""
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from chalk.api.dependencies import get_db, get_redis
from chalk.api.main import app
from chalk.api.routes.recap import _grade


def _make_redis():
    r = AsyncMock()
    r.get = AsyncMock(return_value=None)
    r.setex = AsyncMock()
    r.aclose = AsyncMock()
    return r


# ─── Unit tests for grading logic ───


class TestGradeFunction:
    def test_hit_within_iqr(self):
        assert _grade(actual=15, p10=8.0, p25=12.0, p75=18.0, p90=22.0) == "hit"

    def test_hit_at_p25_boundary(self):
        assert _grade(actual=12, p10=8.0, p25=12.0, p75=18.0, p90=22.0) == "hit"

    def test_hit_at_p75_boundary(self):
        assert _grade(actual=18, p10=8.0, p25=12.0, p75=18.0, p90=22.0) == "hit"

    def test_close_between_p10_and_p25(self):
        assert _grade(actual=10, p10=8.0, p25=12.0, p75=18.0, p90=22.0) == "close"

    def test_close_between_p75_and_p90(self):
        assert _grade(actual=20, p10=8.0, p25=12.0, p75=18.0, p90=22.0) == "close"

    def test_close_at_p10_boundary(self):
        assert _grade(actual=8, p10=8.0, p25=12.0, p75=18.0, p90=22.0) == "close"

    def test_close_at_p90_boundary(self):
        assert _grade(actual=22, p10=8.0, p25=12.0, p75=18.0, p90=22.0) == "close"

    def test_miss_below_p10(self):
        assert _grade(actual=5, p10=8.0, p25=12.0, p75=18.0, p90=22.0) == "miss"

    def test_miss_above_p90(self):
        assert _grade(actual=30, p10=8.0, p25=12.0, p75=18.0, p90=22.0) == "miss"


# ─── API endpoint tests ───


@pytest.mark.asyncio
async def test_recap_empty_when_no_predictions():
    """Returns 200 with empty games list when no predictions exist for the date."""
    db = AsyncMock()
    result_mock = MagicMock()
    result_mock.all.return_value = []
    db.execute = AsyncMock(return_value=result_mock)
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
            yesterday = (date.today() - timedelta(days=1)).isoformat()
            resp = await client.get(f"/v1/games/recap?date={yesterday}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["games"] == []
        assert data["summary"]["total_predictions"] == 0
        assert data["summary"]["hit_rate"] == 0.0
        assert data["summary"]["overall_mae"] == 0.0
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_recap_future_date_returns_400():
    """Future dates should be rejected."""
    db = AsyncMock()
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
            future = (date.today() + timedelta(days=5)).isoformat()
            resp = await client.get(f"/v1/games/recap?date={future}")
        assert resp.status_code == 400
        assert "future" in resp.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_recap_with_predictions_and_actuals():
    """Full flow: predictions joined with actuals produce correct grades and MAE."""
    # Build a fake row that looks like a SQLAlchemy result tuple
    # Simulates the joined query result
    class FakeRow:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

    # Player predicted 20 pts (p25=16, p75=24) and scored 22 → HIT
    row_hit = FakeRow(
        game_id="0022500100", player_id=101, stat="pts",
        p10=10.0, p25=16.0, p50=20.0, p75=24.0, p90=28.0,
        pts=22, reb=5, ast=3, fg3m=2, stl=1, blk=0, to_committed=2,
        player_name="Test Player", position="SG", team_abbr="BOS",
    )
    # Same player predicted 5 reb (p25=3, p75=7) and got 1 → MISS (below p10=2)
    row_miss = FakeRow(
        game_id="0022500100", player_id=101, stat="reb",
        p10=2.0, p25=3.0, p50=5.0, p75=7.0, p90=9.0,
        pts=22, reb=1, ast=3, fg3m=2, stl=1, blk=0, to_committed=2,
        player_name="Test Player", position="SG", team_abbr="BOS",
    )

    # Mock game
    mock_game = MagicMock()
    mock_game.game_id = "0022500100"
    mock_game.date = date.today() - timedelta(days=1)
    mock_game.home_team_id = 1
    mock_game.away_team_id = 2

    mock_home_team = MagicMock()
    mock_home_team.team_id = 1
    mock_home_team.abbreviation = "BOS"
    mock_away_team = MagicMock()
    mock_away_team.team_id = 2
    mock_away_team.abbreviation = "LAL"

    call_count = 0

    async def mock_execute(stmt):
        nonlocal call_count
        call_count += 1
        result = MagicMock()
        if call_count == 1:
            # Main joined query
            result.all.return_value = [row_hit, row_miss]
        elif call_count == 2:
            # Games query
            result.scalars.return_value.all.return_value = [mock_game]
        elif call_count == 3:
            # Team scores query
            result.all.return_value = []
        elif call_count == 4:
            # Teams query
            result.scalars.return_value.all.return_value = [mock_home_team, mock_away_team]
        else:
            result.all.return_value = []
            result.scalars.return_value.all.return_value = []
        return result

    db = AsyncMock()
    db.execute = mock_execute
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
            yesterday = (date.today() - timedelta(days=1)).isoformat()
            resp = await client.get(f"/v1/games/recap?date={yesterday}")
        assert resp.status_code == 200
        data = resp.json()

        assert data["summary"]["total_predictions"] == 2
        assert data["summary"]["hit_rate"] == 0.5  # 1 hit out of 2
        assert data["summary"]["miss_rate"] == 0.5  # 1 miss out of 2

        assert len(data["games"]) == 1
        game = data["games"][0]
        assert game["home_team"] == "BOS"
        assert game["away_team"] == "LAL"

        assert len(game["players"]) == 1
        player = game["players"][0]
        assert player["player_name"] == "Test Player"
        assert player["hit_count"] == 1
        assert player["miss_count"] == 1

        # Check individual stat grades
        stats_by_name = {s["stat"]: s for s in player["stats"]}
        assert stats_by_name["pts"]["grade"] == "hit"
        assert stats_by_name["pts"]["actual"] == 22
        assert stats_by_name["pts"]["predicted"] == 20.0
        assert stats_by_name["reb"]["grade"] == "miss"
        assert stats_by_name["reb"]["actual"] == 1
    finally:
        app.dependency_overrides.clear()
