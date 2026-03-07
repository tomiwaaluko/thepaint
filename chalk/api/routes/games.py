"""Game prediction routes."""
import asyncio
from datetime import date, datetime

import redis.asyncio as aioredis
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chalk.api.cache import get_cached, set_cached
from chalk.api.dependencies import get_db, get_redis
from chalk.api.schemas import GamePredictionResponse, PlayerPredictionResponse
from chalk.db.models import Game, Player, PlayerGameLog, Team
from chalk.exceptions import PredictionError
from chalk.predictions.player import predict_player

log = structlog.get_logger()

router = APIRouter(prefix="/v1/games", tags=["games"])


@router.get("/{game_id}/predict", response_model=GamePredictionResponse)
async def predict_game(
    game_id: str,
    as_of: datetime | None = Query(None, description="Prediction as-of datetime"),
    session: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> GamePredictionResponse:
    cache_key = f"pred:game:{game_id}"
    cached = await get_cached(redis, cache_key, GamePredictionResponse)
    if cached:
        return cached

    # Load game
    result = await session.execute(select(Game).where(Game.game_id == game_id))
    game = result.scalar_one_or_none()
    if not game:
        raise HTTPException(status_code=404, detail=f"Game {game_id} not found")

    as_of_date = as_of.date() if as_of else game.date

    # Get team names
    home_team = await session.get(Team, game.home_team_id)
    away_team = await session.get(Team, game.away_team_id)
    home_name = home_team.abbreviation if home_team else "UNK"
    away_name = away_team.abbreviation if away_team else "UNK"

    # Find players who played in this game (from game logs)
    home_logs = await session.execute(
        select(PlayerGameLog.player_id)
        .where(PlayerGameLog.game_id == game_id)
        .where(PlayerGameLog.team_id == game.home_team_id)
    )
    away_logs = await session.execute(
        select(PlayerGameLog.player_id)
        .where(PlayerGameLog.game_id == game_id)
        .where(PlayerGameLog.team_id == game.away_team_id)
    )
    home_player_ids = [row[0] for row in home_logs.all()]
    away_player_ids = [row[0] for row in away_logs.all()]

    # Predict each player (sequentially to avoid session conflicts with async sqlite)
    home_predictions = await _predict_players(session, home_player_ids, game_id, as_of_date)
    away_predictions = await _predict_players(session, away_player_ids, game_id, as_of_date)

    # Estimate total
    home_pts = sum(_get_pts(p) for p in home_predictions)
    away_pts = sum(_get_pts(p) for p in away_predictions)

    response = GamePredictionResponse(
        game_id=game_id,
        home_team=home_name,
        away_team=away_name,
        as_of_ts=datetime(as_of_date.year, as_of_date.month, as_of_date.day),
        predicted_total=round(home_pts + away_pts, 1),
        home_predictions=home_predictions,
        away_predictions=away_predictions,
    )

    await set_cached(redis, cache_key, response)
    return response


async def _predict_players(
    session: AsyncSession,
    player_ids: list[int],
    game_id: str,
    as_of_date: date,
) -> list[PlayerPredictionResponse]:
    """Predict stats for a list of players, skipping failures."""
    results = []
    for pid in player_ids:
        try:
            pred = await predict_player(session, pid, game_id, as_of_date)
            results.append(pred)
        except Exception as e:
            log.warning("player_prediction_skipped", player_id=pid, error=str(e))
    return results


def _get_pts(pred: PlayerPredictionResponse) -> float:
    """Extract predicted points from a player prediction."""
    for sp in pred.predictions:
        if sp.stat == "pts":
            return sp.p50
    return 0.0
