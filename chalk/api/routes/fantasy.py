"""Fantasy scoring routes."""
from datetime import date, datetime

import redis.asyncio as aioredis
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chalk.api.cache import get_cached, set_cached
from chalk.api.dependencies import get_db, get_redis
from chalk.api.schemas import FantasyScores
from chalk.api.schemas_betting import FantasyProjectionResponse, SlateFantasyResponse
from chalk.db.models import Game, PlayerGameLog, Team
from chalk.exceptions import PredictionError
from chalk.fantasy.scoring import compute_all_fantasy_scores
from chalk.fantasy.simulation import simulate_fantasy_scores
from chalk.predictions.player import predict_player

log = structlog.get_logger()

router = APIRouter(prefix="/v1", tags=["fantasy"])


@router.get("/players/{player_id}/fantasy", response_model=FantasyProjectionResponse)
async def player_fantasy(
    player_id: int,
    game_id: str = Query(..., description="NBA game ID"),
    platform: str = Query("draftkings", description="Fantasy platform"),
    session: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> FantasyProjectionResponse:
    cache_key = f"fantasy:player:{player_id}:game:{game_id}:{platform}"
    cached = await get_cached(redis, cache_key, FantasyProjectionResponse)
    if cached:
        return cached

    as_of_date = date.today()
    try:
        prediction = await predict_player(session, player_id, game_id, as_of_date)
    except PredictionError as e:
        raise HTTPException(status_code=404, detail=str(e))

    # Compute fantasy scores from predicted p50 values
    stat_dict = {p.stat: p.p50 for p in prediction.predictions}
    fantasy = compute_all_fantasy_scores(stat_dict)

    # Run Monte Carlo simulation
    sim = simulate_fantasy_scores(prediction.predictions, platform)

    response = FantasyProjectionResponse(
        player_id=player_id,
        player_name=prediction.player_name,
        game_id=game_id,
        platform=platform,
        fantasy_scores=fantasy,
        floor=sim.floor,
        ceiling=sim.ceiling,
        mean=sim.mean,
        std=sim.std,
        boom_rate=sim.boom_rate,
        bust_rate=sim.bust_rate,
    )

    await set_cached(redis, cache_key, response)
    return response


@router.get("/games/{game_id}/fantasy", response_model=SlateFantasyResponse)
async def game_fantasy(
    game_id: str,
    platform: str = Query("draftkings", description="Fantasy platform"),
    session: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> SlateFantasyResponse:
    cache_key = f"fantasy:game:{game_id}:{platform}"
    cached = await get_cached(redis, cache_key, SlateFantasyResponse)
    if cached:
        return cached

    # Get game
    result = await session.execute(select(Game).where(Game.game_id == game_id))
    game = result.scalar_one_or_none()
    if not game:
        raise HTTPException(status_code=404, detail=f"Game {game_id} not found")

    as_of_date = game.date

    # Get all players in this game
    result = await session.execute(
        select(PlayerGameLog.player_id)
        .where(PlayerGameLog.game_id == game_id)
        .distinct()
    )
    player_ids = [row[0] for row in result.all()]

    projections: list[FantasyProjectionResponse] = []
    for pid in player_ids:
        try:
            prediction = await predict_player(session, pid, game_id, as_of_date)
            stat_dict = {p.stat: p.p50 for p in prediction.predictions}
            fantasy = compute_all_fantasy_scores(stat_dict)
            sim = simulate_fantasy_scores(prediction.predictions, platform)

            projections.append(FantasyProjectionResponse(
                player_id=pid,
                player_name=prediction.player_name,
                game_id=game_id,
                platform=platform,
                fantasy_scores=fantasy,
                floor=sim.floor,
                ceiling=sim.ceiling,
                mean=sim.mean,
                std=sim.std,
                boom_rate=sim.boom_rate,
                bust_rate=sim.bust_rate,
            ))
        except Exception as e:
            log.warning("fantasy_projection_skipped", player_id=pid, error=str(e))

    # Sort by mean projected score descending
    projections.sort(key=lambda p: p.mean, reverse=True)

    response = SlateFantasyResponse(
        game_id=game_id,
        platform=platform,
        projections=projections,
    )

    await set_cached(redis, cache_key, response)
    return response
