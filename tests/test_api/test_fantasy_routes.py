"""Tests for fantasy routes."""
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


def _make_prediction(player_id=2544, name="LeBron James"):
    return PlayerPredictionResponse(
        player_id=player_id,
        player_name=name,
        game_id="0022300001",
        opponent_team="GSW",
        as_of_ts=datetime(2024, 1, 15, tzinfo=timezone.utc),
        model_version="v1",
        predictions=[
            StatPrediction(stat="pts", p10=15.0, p25=20.0, p50=25.0, p75=30.0, p90=35.0, confidence="medium"),
            StatPrediction(stat="reb", p10=3.0, p25=5.0, p50=7.0, p75=9.0, p90=11.0, confidence="medium"),
            StatPrediction(stat="ast", p10=3.0, p25=5.0, p50=7.0, p75=9.0, p90=11.0, confidence="medium"),
            StatPrediction(stat="fg3m", p10=0.5, p25=1.0, p50=2.0, p75=3.0, p90=4.0, confidence="medium"),
            StatPrediction(stat="stl", p10=0.3, p25=0.6, p50=1.2, p75=1.5, p90=2.0, confidence="medium"),
            StatPrediction(stat="blk", p10=0.1, p25=0.3, p50=0.8, p75=1.0, p90=1.5, confidence="medium"),
            StatPrediction(stat="to_committed", p10=1.0, p25=1.5, p50=2.5, p75=3.0, p90=4.0, confidence="medium"),
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

    async def fake_db():
        yield AsyncMock()

    async def fake_redis():
        yield redis

    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[get_redis] = fake_redis
    yield redis
    app.dependency_overrides.clear()


@pytest.mark.asyncio
@patch("chalk.api.routes.fantasy.predict_player")
async def test_player_fantasy_returns_projection(mock_predict, override_deps):
    mock_predict.return_value = _make_prediction()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/v1/players/2544/fantasy?game_id=0022300001&platform=draftkings")

    assert resp.status_code == 200
    data = resp.json()
    assert data["player_id"] == 2544
    assert data["platform"] == "draftkings"
    assert data["floor"] < data["ceiling"]
    assert data["mean"] > 0
    assert 0 <= data["boom_rate"] <= 1
    assert 0 <= data["bust_rate"] <= 1
    assert data["fantasy_scores"]["draftkings"] > 0


@pytest.mark.asyncio
@patch("chalk.api.routes.fantasy.predict_player")
async def test_player_fantasy_caches_result(mock_predict, override_deps):
    mock_predict.return_value = _make_prediction()
    redis = override_deps

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.get("/v1/players/2544/fantasy?game_id=0022300001")

    redis.setex.assert_called_once()


@pytest.mark.asyncio
@patch("chalk.api.routes.fantasy.predict_player")
async def test_player_fantasy_404_unknown(mock_predict, override_deps):
    from chalk.exceptions import PredictionError
    mock_predict.side_effect = PredictionError("not found")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/v1/players/9999999/fantasy?game_id=0022300001")

    assert resp.status_code == 404
