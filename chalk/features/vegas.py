"""Vegas betting line features."""
from datetime import date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from chalk.db.models import BettingLine

STAT_TO_MARKET = {
    "pts": "player_points",
    "reb": "player_rebounds",
    "ast": "player_assists",
    "fg3m": "player_threes",
    "blk": "player_blocks",
    "stl": "player_steals",
    "to_committed": "player_turnovers",
}
VEGAS_PROP_STATS = ["pts", "reb", "ast", "fg3m"]


def _as_of_cutoff(as_of_date: date | datetime) -> datetime:
    if isinstance(as_of_date, datetime):
        return as_of_date
    return datetime.combine(as_of_date + timedelta(days=1), time.min)


async def get_player_prop_line(
    session: AsyncSession,
    player_id: int,
    game_id: str,
    stat: str,
    as_of_date: date | datetime,
) -> float:
    """Consensus player prop line for a player/stat before the as-of cutoff."""
    cutoff = _as_of_cutoff(as_of_date)
    markets = {stat}
    market_key = STAT_TO_MARKET.get(stat)
    if market_key:
        markets.add(market_key)

    result = await session.execute(
        select(func.avg(BettingLine.line))
        .where(BettingLine.game_id == game_id)
        .where(BettingLine.player_id == player_id)
        .where(BettingLine.market.in_(markets))
        .where(BettingLine.timestamp < cutoff)
    )
    value = result.scalar()
    return float(value) if value is not None else 0.0


async def get_game_total_line(
    session: AsyncSession,
    game_id: str,
    as_of_date: date | datetime,
) -> float:
    """Consensus game total line before the as-of cutoff."""
    cutoff = _as_of_cutoff(as_of_date)
    result = await session.execute(
        select(func.avg(BettingLine.line))
        .where(BettingLine.game_id == game_id)
        .where(BettingLine.player_id.is_(None))
        .where(BettingLine.market == "game_total")
        .where(BettingLine.timestamp < cutoff)
    )
    value = result.scalar()
    return float(value) if value is not None else 0.0


async def get_vegas_features(
    session: AsyncSession,
    player_id: int,
    game_id: str,
    as_of_date: date | datetime,
) -> dict[str, float]:
    """Return sparse Vegas-line features for model input."""
    features = {}
    has_line = 0.0
    for stat in VEGAS_PROP_STATS:
        line = await get_player_prop_line(session, player_id, game_id, stat, as_of_date)
        features[f"vegas_{stat}_line"] = line
        if line > 0.0:
            has_line = 1.0

    game_total = await get_game_total_line(session, game_id, as_of_date)
    features["vegas_game_total"] = game_total
    features["vegas_has_line"] = 1.0 if has_line or game_total > 0.0 else 0.0
    return features
