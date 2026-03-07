"""Tests for player prediction routes."""
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

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


def _make_prediction_response() -> PlayerPredictionResponse:
    return PlayerPredictionResponse(
        player_id=2544,
        player_name="LeBron James",
        game_id="0022300001",
        opponent_team="GSW",
        as_of_ts=datetime(2024, 1, 15, tzinfo=timezone.utc),
        model_version="20240115_120000",
        predictions=[
            StatPrediction(stat="pts", p10=15.0, p25=20.0, p50=25.0, p75=30.0, p90=35.0, confidence="high"),
            StatPrediction(stat="reb", p10=3.0, p25=5.0, p50=7.0, p75=9.0, p90=11.0, confidence="medium"),
            StatPrediction(stat="ast", p10=3.0, p25=5.0, p50=7.0, p75=9.0, p90=11.0, confidence="medium"),
            StatPrediction(stat="fg3m", p10=0.5, p25=1.0, p50=2.0, p75=3.0, p90=4.0, confidence="medium"),
            StatPrediction(stat="stl", p10=0.3, p25=0.6, p50=1.2, p75=1.5, p90=2.0, confidence="medium"),
            StatPrediction(stat="blk", p10=0.1, p25=0.3, p50=0.8, p75=1.0, p90=1.5, confidence="medium"),
            StatPrediction(stat="to_committed", p10=1.0, p25=1.5, p50=2.5, p75=3.0, p90=4.0, confidence="medium"),
        ],
        fantasy_scores=FantasyScores(draftkings=45.5, fanduel=42.0, yahoo=42.5),
        injury_context=InjuryContext(
            player_status="active",
            absent_teammates=["Anthony Davis"],
            opportunity_adjustment=1.05,
        ),
    )


def _mock_redis_no_cache():
    """Redis mock that returns no cache hit."""
    r = AsyncMock()
    r.get = AsyncMock(return_value=None)
    r.setex = AsyncMock()
    r.aclose = AsyncMock()
    return r


def _mock_redis_with_cache(response: PlayerPredictionResponse):
    """Redis mock that returns a cached response."""
    r = AsyncMock()
    r.get = AsyncMock(return_value=response.model_dump_json())
    r.aclose = AsyncMock()
    return r


@pytest.fixture
def override_deps_with_prediction():
    """Override deps and mock predict_player."""
    redis = _mock_redis_no_cache()

    async def fake_db():
        yield AsyncMock()

    async def fake_redis():
        yield redis

    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[get_redis] = fake_redis
    yield redis
    app.dependency_overrides.clear()


@pytest.fixture
def override_deps_cached():
    """Override deps with cached response in Redis."""
    resp = _make_prediction_response()
    redis = _mock_redis_with_cache(resp)

    async def fake_db():
        yield AsyncMock()

    async def fake_redis():
        yield redis

    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[get_redis] = fake_redis
    yield redis
    app.dependency_overrides.clear()


@pytest.mark.asyncio
@patch("chalk.api.routes.players.predict_player")
async def test_predict_player_returns_correct_schema(mock_predict, override_deps_with_prediction):
    mock_predict.return_value = _make_prediction_response()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/v1/players/2544/predict?game_id=0022300001")

    assert resp.status_code == 200
    data = resp.json()
    assert data["player_id"] == 2544
    assert data["player_name"] == "LeBron James"
    assert len(data["predictions"]) == 7
    assert data["fantasy_scores"]["draftkings"] == 45.5
    assert data["injury_context"]["player_status"] == "active"


@pytest.mark.asyncio
@patch("chalk.api.routes.players.predict_player")
async def test_predict_player_all_stats_present(mock_predict, override_deps_with_prediction):
    mock_predict.return_value = _make_prediction_response()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/v1/players/2544/predict?game_id=0022300001")

    stats = {p["stat"] for p in resp.json()["predictions"]}
    assert stats == {"pts", "reb", "ast", "fg3m", "stl", "blk", "to_committed"}


@pytest.mark.asyncio
async def test_predict_player_cache_hit(override_deps_cached):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/v1/players/2544/predict?game_id=0022300001")

    assert resp.status_code == 200
    data = resp.json()
    assert data["player_id"] == 2544
    # predict_player should NOT have been called — served from cache


@pytest.mark.asyncio
@patch("chalk.api.routes.players.predict_player")
async def test_predict_player_caches_result(mock_predict, override_deps_with_prediction):
    mock_predict.return_value = _make_prediction_response()
    redis = override_deps_with_prediction

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.get("/v1/players/2544/predict?game_id=0022300001")

    # Verify setex was called to cache the result
    redis.setex.assert_called_once()


@pytest.mark.asyncio
@patch("chalk.api.routes.players.predict_player")
async def test_predict_player_404_on_unknown_player(mock_predict, override_deps_with_prediction):
    from chalk.exceptions import PredictionError
    mock_predict.side_effect = PredictionError("Player 9999999 not found")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/v1/players/9999999/predict?game_id=0022300001")

    assert resp.status_code == 404


@pytest.mark.asyncio
@patch("chalk.api.routes.players.predict_player")
async def test_predict_player_injury_context_populated(mock_predict, override_deps_with_prediction):
    mock_predict.return_value = _make_prediction_response()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/v1/players/2544/predict?game_id=0022300001")

    ctx = resp.json()["injury_context"]
    assert "Anthony Davis" in ctx["absent_teammates"]
    assert ctx["opportunity_adjustment"] == 1.05
