"""Tests for props route."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from chalk.api.dependencies import get_db, get_redis
from chalk.api.main import app
from chalk.api.schemas import (
    FantasyScores,
    InjuryContext,
    PlayerPredictionResponse,
    StatPrediction,
)


def _make_prediction():
    return PlayerPredictionResponse(
        player_id=2544,
        player_name="LeBron James",
        game_id="0022300001",
        opponent_team="GSW",
        as_of_ts=datetime(2024, 1, 15, tzinfo=timezone.utc),
        model_version="v1",
        predictions=[
            StatPrediction(stat="pts", p10=15.0, p25=20.0, p50=25.0, p75=30.0, p90=35.0, confidence="medium"),
            StatPrediction(stat="reb", p10=3.0, p25=5.0, p50=7.0, p75=9.0, p90=11.0, confidence="medium"),
            StatPrediction(stat="ast", p10=3.0, p25=5.0, p50=7.0, p75=9.0, p90=11.0, confidence="medium"),
            StatPrediction(stat="fg3m", p10=0.5, p25=1.0, p50=2.0, p75=3.0, p90=4.0, confidence="medium"),
        ],
        fantasy_scores=FantasyScores(draftkings=45.0, fanduel=42.0, yahoo=42.5),
        injury_context=InjuryContext(),
    )


def _mock_redis():
    r = AsyncMock()
    r.get = AsyncMock(return_value=None)
    r.setex = AsyncMock()
    r.aclose = AsyncMock()
    return r


@pytest.fixture
def override_deps():
    redis = _mock_redis()
    mock_session = AsyncMock()
    # Mock the betting lines query to return empty (no Vegas lines)
    mock_result = AsyncMock()
    mock_result.scalars = lambda: AsyncMock(all=lambda: [])
    mock_session.execute = AsyncMock(return_value=mock_result)

    async def fake_db():
        yield mock_session

    async def fake_redis():
        yield redis

    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[get_redis] = fake_redis
    yield
    app.dependency_overrides.clear()


@pytest.mark.asyncio
@patch("chalk.api.routes.props.predict_player")
async def test_props_returns_list_of_over_under(mock_predict, override_deps):
    mock_predict.return_value = _make_prediction()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/v1/players/2544/props?game_id=0022300001")

    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 4  # pts, reb, ast, fg3m

    for item in data:
        assert "stat" in item
        assert "over_probability" in item
        assert "under_probability" in item
        assert "edge" in item
        assert "confidence" in item


@pytest.mark.asyncio
@patch("chalk.api.routes.props.predict_player")
async def test_props_probabilities_sum_to_one(mock_predict, override_deps):
    mock_predict.return_value = _make_prediction()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/v1/players/2544/props?game_id=0022300001")

    for item in resp.json():
        total = item["over_probability"] + item["under_probability"]
        assert abs(total - 1.0) < 0.01


@pytest.mark.asyncio
@patch("chalk.api.routes.props.predict_player")
async def test_props_404_unknown_player(mock_predict, override_deps):
    from chalk.exceptions import PredictionError
    mock_predict.side_effect = PredictionError("not found")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/v1/players/9999999/props?game_id=0022300001")

    assert resp.status_code == 404
