"""Player prediction routes."""
from datetime import date, datetime, timezone

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chalk.api.cache import get_cached, set_cached
from chalk.api.dependencies import get_db, get_redis
from chalk.api.schemas import PlayerPredictionResponse
from chalk.db.models import Player, PlayerGameLog
from chalk.exceptions import FeatureError, PredictionError
from chalk.ingestion.injury_fetcher import get_player_status
from chalk.predictions.player import predict_player

router = APIRouter(prefix="/v1/players", tags=["players"])


async def _with_latest_injury_status(
    session: AsyncSession,
    response: PlayerPredictionResponse,
    as_of_date: date,
) -> PlayerPredictionResponse:
    status = await get_player_status(session, response.player_id, as_of_date)
    injury_context = response.injury_context.model_copy(
        update={"player_status": status}
    )
    return response.model_copy(update={"injury_context": injury_context})


@router.get("/{player_id}/predict", response_model=PlayerPredictionResponse)
async def predict_player_statline(
    player_id: int = Path(..., gt=0, description="Player ID"),
    game_id: str = Query(..., description="NBA game ID", pattern=r"^[0-9]{10}$"),
    as_of: datetime | None = Query(None, description="Prediction as-of datetime (default: now)"),
    session: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> PlayerPredictionResponse:
    # Check cache
    cache_key = f"pred:player:{player_id}:game:{game_id}"
    as_of_date = as_of.date() if as_of else date.today()
    if as_of_date > date.today():
        raise HTTPException(status_code=400, detail="as_of date cannot be in the future")

    cached = await get_cached(redis, cache_key, PlayerPredictionResponse)
    if cached:
        return await _with_latest_injury_status(session, cached, as_of_date)

    try:
        response = await predict_player(session, player_id, game_id, as_of_date)
    except PredictionError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except FeatureError as e:
        raise HTTPException(status_code=422, detail=str(e))

    response = await _with_latest_injury_status(session, response, as_of_date)
    await set_cached(redis, cache_key, response)
    return response


@router.get("/{player_id}/history")
async def player_history(
    player_id: int = Path(..., gt=0, description="Player ID"),
    limit: int = Query(10, ge=1, le=50),
    session: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Return recent game logs for a player."""
    player = await session.get(Player, player_id)
    if not player:
        raise HTTPException(status_code=404, detail=f"Player {player_id} not found")

    result = await session.execute(
        select(PlayerGameLog)
        .where(PlayerGameLog.player_id == player_id)
        .order_by(PlayerGameLog.game_date.desc())
        .limit(limit)
    )
    logs = result.scalars().all()

    return [
        {
            "game_id": log.game_id,
            "game_date": log.game_date.isoformat(),
            "pts": log.pts,
            "reb": log.reb,
            "ast": log.ast,
            "stl": log.stl,
            "blk": log.blk,
            "to_committed": log.to_committed,
            "fg3m": log.fg3m,
            "min_played": log.min_played,
        }
        for log in logs
    ]
