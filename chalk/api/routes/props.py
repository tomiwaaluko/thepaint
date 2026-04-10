"""Player props routes — over/under probabilities vs. Vegas lines."""
from datetime import date, datetime

import redis.asyncio as aioredis
import structlog
from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chalk.api.cache import get_cached, set_cached
from chalk.api.dependencies import get_db, get_redis
from chalk.api.schemas import OverUnderResponse
from chalk.betting.over_under import (
    american_to_implied_probability,
    calculate_edge,
    edge_confidence,
    over_probability,
    remove_vig,
)
from chalk.db.models import BettingLine, Game, Player, PlayerGameLog
from chalk.exceptions import PredictionError
from chalk.predictions.player import predict_player

log = structlog.get_logger()

router = APIRouter(prefix="/v1/players", tags=["props"])

DEFAULT_STATS = ["pts", "reb", "ast", "fg3m"]
ALLOWED_STATS = frozenset({"pts", "reb", "ast", "fg3m", "stl", "blk", "to_committed"})


@router.get("/{player_id}/props", response_model=list[OverUnderResponse])
async def player_props(
    player_id: int = Path(..., gt=0, description="Player ID"),
    game_id: str = Query(..., description="NBA game ID", pattern=r"^[0-9]{10}$"),
    stats: list[str] = Query(default=DEFAULT_STATS),
    session: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> list[OverUnderResponse]:
    """Return O/U probability + edge for each stat vs. Vegas lines."""
    invalid = [s for s in stats if s not in ALLOWED_STATS]
    if invalid:
        raise HTTPException(status_code=422, detail=f"Invalid stats: {invalid}. Allowed: {sorted(ALLOWED_STATS)}")
    stats_key = ",".join(sorted(stats))
    cache_key = f"props:player:{player_id}:game:{game_id}:stats:{stats_key}"
    cached = await get_cached(redis, cache_key, list)
    # list won't deserialize properly, handle manually
    try:
        raw = await redis.get(cache_key)
        if raw:
            import json
            data = json.loads(raw)
            return [OverUnderResponse(**item) for item in data]
    except Exception:
        pass

    as_of_date = date.today()

    # Get player prediction
    try:
        prediction = await predict_player(session, player_id, game_id, as_of_date)
    except PredictionError as e:
        raise HTTPException(status_code=404, detail=str(e))

    pred_map = {p.stat: p for p in prediction.predictions}

    # Get betting lines for this player+game
    result = await session.execute(
        select(BettingLine)
        .where(BettingLine.game_id == game_id)
        .where(BettingLine.player_id == player_id)
    )
    lines = result.scalars().all()
    line_map: dict[str, BettingLine] = {}
    for bl in lines:
        if bl.market not in line_map or bl.timestamp > line_map[bl.market].timestamp:
            line_map[bl.market] = bl

    responses = []
    for stat in stats:
        sp = pred_map.get(stat)
        if not sp:
            continue

        bl = line_map.get(stat)
        if bl:
            line_val = bl.line
            sportsbook = bl.sportsbook
            over_imp = american_to_implied_probability(bl.over_odds) if bl.over_odds else 0.5
            under_imp = american_to_implied_probability(bl.under_odds) if bl.under_odds else 0.5
            true_over_imp, _ = remove_vig(over_imp, under_imp)
        else:
            # No Vegas line available — use p50 as synthetic line
            line_val = sp.p50
            sportsbook = "model"
            true_over_imp = 0.5

        over_prob = over_probability(line_val, sp.p10, sp.p25, sp.p50, sp.p75, sp.p90)
        edge = calculate_edge(over_prob, true_over_imp)

        responses.append(OverUnderResponse(
            player_id=player_id,
            player_name=prediction.player_name,
            stat=stat,
            line=line_val,
            sportsbook=sportsbook,
            over_probability=round(over_prob, 3),
            under_probability=round(1.0 - over_prob, 3),
            implied_over_prob=round(true_over_imp, 3),
            edge=edge,
            confidence=edge_confidence(edge),
        ))

    # Cache response
    try:
        import json
        await redis.setex(cache_key, 900, json.dumps([r.model_dump() for r in responses]))
    except Exception:
        pass

    return responses
