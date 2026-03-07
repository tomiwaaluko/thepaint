"""Rolling window average features for player game logs."""
from datetime import date

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chalk.db.models import Game, PlayerGameLog

ROLLING_WINDOWS = [5, 10, 20]
ROLLING_STATS = [
    "pts", "reb", "ast", "stl", "blk", "to_committed",
    "fg3m", "fg3a", "fgm", "fga", "ftm", "fta", "min_played",
]
SPLIT_STATS = ["pts", "reb", "ast"]
TREND_STATS = ["pts", "reb", "ast"]
TREND_WINDOW = 10


async def get_rolling_avg(
    session: AsyncSession,
    player_id: int,
    stat: str,
    window: int,
    as_of_date: date,
) -> float:
    """Rolling average of `stat` over last `window` games before as_of_date."""
    col = getattr(PlayerGameLog, stat)
    subq = (
        select(col)
        .where(PlayerGameLog.player_id == player_id)
        .where(PlayerGameLog.game_date < as_of_date)  # as_of_date gate
        .order_by(PlayerGameLog.game_date.desc())
        .limit(window)
    ).subquery()

    result = await session.execute(select(subq.c[stat]))
    values = result.scalars().all()
    if not values:
        return 0.0
    return float(sum(values)) / len(values)


async def get_rolling_avg_split(
    session: AsyncSession,
    player_id: int,
    stat: str,
    window: int,
    as_of_date: date,
    location: str,
) -> float:
    """Rolling average filtered by home/away location."""
    col = getattr(PlayerGameLog, stat)

    # Join to Game to determine home/away
    if location == "home":
        location_filter = Game.home_team_id == PlayerGameLog.team_id
    else:
        location_filter = Game.away_team_id == PlayerGameLog.team_id

    subq = (
        select(col)
        .join(Game, Game.game_id == PlayerGameLog.game_id)
        .where(PlayerGameLog.player_id == player_id)
        .where(PlayerGameLog.game_date < as_of_date)  # as_of_date gate
        .where(location_filter)
        .order_by(PlayerGameLog.game_date.desc())
        .limit(window)
    ).subquery()

    result = await session.execute(select(subq.c[stat]))
    values = result.scalars().all()
    if not values:
        return 0.0
    return float(sum(values)) / len(values)


def compute_trend_slope(values: list[float]) -> float:
    """Linear regression slope over a sequence of values.

    Returns 0.0 if fewer than 3 values. Positive = improving, negative = declining.
    """
    if len(values) < 3:
        return 0.0
    x = np.arange(len(values), dtype=np.float64)
    y = np.array(values, dtype=np.float64)
    coeffs = np.polyfit(x, y, 1)
    return float(coeffs[0])


async def get_stat_trend(
    session: AsyncSession,
    player_id: int,
    stat: str,
    window: int,
    as_of_date: date,
) -> float:
    """Slope of `stat` over last `window` games (chronological order)."""
    col = getattr(PlayerGameLog, stat)
    subq = (
        select(col, PlayerGameLog.game_date)
        .where(PlayerGameLog.player_id == player_id)
        .where(PlayerGameLog.game_date < as_of_date)  # as_of_date gate
        .order_by(PlayerGameLog.game_date.desc())
        .limit(window)
    ).subquery()

    # Re-select in chronological order for slope computation
    result = await session.execute(
        select(subq.c[stat]).order_by(subq.c.game_date.asc())
    )
    values = [float(v) for v in result.scalars().all()]
    return compute_trend_slope(values)


async def get_all_rolling_features(
    session: AsyncSession,
    player_id: int,
    as_of_date: date,
) -> dict[str, float]:
    """Compute all rolling features. Returns flat dict."""
    features: dict[str, float] = {}

    # Basic rolling averages: stat × window
    for stat in ROLLING_STATS:
        for window in ROLLING_WINDOWS:
            features[f"{stat}_avg_{window}g"] = await get_rolling_avg(
                session, player_id, stat, window, as_of_date
            )

    # Home/away splits for key stats (window=10)
    for stat in SPLIT_STATS:
        for loc in ("home", "away"):
            features[f"{stat}_avg_10g_{loc}"] = await get_rolling_avg_split(
                session, player_id, stat, 10, as_of_date, loc
            )

    # Trend slopes for key stats
    for stat in TREND_STATS:
        features[f"{stat}_trend_{TREND_WINDOW}g"] = await get_stat_trend(
            session, player_id, stat, TREND_WINDOW, as_of_date
        )

    return features
