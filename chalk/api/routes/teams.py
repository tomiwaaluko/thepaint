"""Team prediction routes."""
from datetime import date, datetime

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from chalk.api.cache import get_cached, set_cached
from chalk.api.dependencies import get_db, get_redis
from chalk.api.schemas import TeamPredictionResponse
from chalk.exceptions import PredictionError
from chalk.predictions.team import predict_team

router = APIRouter(prefix="/v1/teams", tags=["teams"])


@router.get("/{team_id}/predict", response_model=TeamPredictionResponse)
async def predict_team_stats(
    team_id: int,
    game_id: str = Query(..., description="NBA game ID"),
    as_of: datetime | None = Query(None, description="Prediction as-of datetime"),
    session: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> TeamPredictionResponse:
    cache_key = f"pred:team:{team_id}:game:{game_id}"
    cached = await get_cached(redis, cache_key, TeamPredictionResponse)
    if cached:
        return cached

    as_of_date = as_of.date() if as_of else date.today()

    try:
        response = await predict_team(session, team_id, game_id, as_of_date)
    except PredictionError as e:
        raise HTTPException(status_code=404, detail=str(e))

    await set_cached(redis, cache_key, response)
    return response
