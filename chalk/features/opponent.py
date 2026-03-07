"""Opponent defensive profile features."""
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from chalk.db.models import Player, PlayerGameLog, TeamGameLog

DEFAULT_WINDOW = 15


async def get_opp_def_rtg(
    session: AsyncSession,
    team_id: int,
    as_of_date: date,
    window: int = DEFAULT_WINDOW,
) -> float:
    """Rolling average defensive rating for a team."""
    subq = (
        select(TeamGameLog.def_rtg)
        .where(TeamGameLog.team_id == team_id)
        .where(TeamGameLog.game_date < as_of_date)  # as_of_date gate
        .order_by(TeamGameLog.game_date.desc())
        .limit(window)
    ).subquery()

    result = await session.execute(select(func.avg(subq.c.def_rtg)))
    val = result.scalar()
    return float(val) if val is not None else 0.0


async def get_opp_pace(
    session: AsyncSession,
    team_id: int,
    as_of_date: date,
    window: int = DEFAULT_WINDOW,
) -> float:
    """Rolling average pace for a team."""
    subq = (
        select(TeamGameLog.pace)
        .where(TeamGameLog.team_id == team_id)
        .where(TeamGameLog.game_date < as_of_date)  # as_of_date gate
        .order_by(TeamGameLog.game_date.desc())
        .limit(window)
    ).subquery()

    result = await session.execute(select(func.avg(subq.c.pace)))
    val = result.scalar()
    return float(val) if val is not None else 0.0


async def get_opp_pts_allowed_by_position(
    session: AsyncSession,
    team_id: int,
    position: str,
    as_of_date: date,
    window: int = DEFAULT_WINDOW,
) -> float:
    """Average points scored by players at `position` against this team."""
    # Find games where this team played, then look at opponent player logs
    subq = (
        select(PlayerGameLog.pts)
        .join(Player, Player.player_id == PlayerGameLog.player_id)
        .where(PlayerGameLog.game_date < as_of_date)  # as_of_date gate
        .where(Player.position == position)
        # Opponent scored against this team: the player's team_id != our team_id
        # but the game involves our team. We filter by: player is NOT on this team
        # but played in a game against this team.
        .where(PlayerGameLog.team_id != team_id)
        .where(
            PlayerGameLog.game_id.in_(
                select(TeamGameLog.game_id)
                .where(TeamGameLog.team_id == team_id)
                .where(TeamGameLog.game_date < as_of_date)  # as_of_date gate
                .order_by(TeamGameLog.game_date.desc())
                .limit(window)
            )
        )
    ).subquery()

    result = await session.execute(select(func.avg(subq.c.pts)))
    val = result.scalar()
    return float(val) if val is not None else 0.0


async def get_opp_fg3a_rate_allowed(
    session: AsyncSession,
    team_id: int,
    as_of_date: date,
    window: int = DEFAULT_WINDOW,
) -> float:
    """Fraction of opponent FGA that are 3-pointers against this defense."""
    subq = (
        select(TeamGameLog.fg3a_rate)
        .where(TeamGameLog.team_id == team_id)
        .where(TeamGameLog.game_date < as_of_date)  # as_of_date gate
        .order_by(TeamGameLog.game_date.desc())
        .limit(window)
    ).subquery()

    result = await session.execute(select(func.avg(subq.c.fg3a_rate)))
    val = result.scalar()
    return float(val) if val is not None else 0.0


async def get_opp_stl_rate(
    session: AsyncSession,
    team_id: int,
    as_of_date: date,
    window: int = DEFAULT_WINDOW,
) -> float:
    """Average steals per game by this team (proxy for steal rate)."""
    subq = (
        select(
            func.sum(PlayerGameLog.stl).label("game_stl"),
            func.max(PlayerGameLog.game_date).label("gdate"),
        )
        .where(PlayerGameLog.team_id == team_id)
        .where(PlayerGameLog.game_date < as_of_date)  # as_of_date gate
        .group_by(PlayerGameLog.game_id)
        .order_by(func.max(PlayerGameLog.game_date).desc())
        .limit(window)
    ).subquery()

    result = await session.execute(select(func.avg(subq.c.game_stl)))
    val = result.scalar()
    return float(val) if val is not None else 0.0


async def get_opp_blk_rate(
    session: AsyncSession,
    team_id: int,
    as_of_date: date,
    window: int = DEFAULT_WINDOW,
) -> float:
    """Average blocks per game by this team (proxy for block rate)."""
    subq = (
        select(
            func.sum(PlayerGameLog.blk).label("game_blk"),
            func.max(PlayerGameLog.game_date).label("gdate"),
        )
        .where(PlayerGameLog.team_id == team_id)
        .where(PlayerGameLog.game_date < as_of_date)  # as_of_date gate
        .group_by(PlayerGameLog.game_id)
        .order_by(func.max(PlayerGameLog.game_date).desc())
        .limit(window)
    ).subquery()

    result = await session.execute(select(func.avg(subq.c.game_blk)))
    val = result.scalar()
    return float(val) if val is not None else 0.0


async def get_all_opponent_features(
    session: AsyncSession,
    opponent_team_id: int,
    player_position: str,
    as_of_date: date,
) -> dict[str, float]:
    """Compute all opponent features. Returns flat dict."""
    return {
        "opp_def_rtg_15g": await get_opp_def_rtg(session, opponent_team_id, as_of_date),
        "opp_pace_15g": await get_opp_pace(session, opponent_team_id, as_of_date),
        f"opp_pts_allowed_{player_position.lower()}": await get_opp_pts_allowed_by_position(
            session, opponent_team_id, player_position, as_of_date
        ),
        "opp_fg3a_rate_allowed_15g": await get_opp_fg3a_rate_allowed(session, opponent_team_id, as_of_date),
        "opp_stl_rate_15g": await get_opp_stl_rate(session, opponent_team_id, as_of_date),
        "opp_blk_rate_15g": await get_opp_blk_rate(session, opponent_team_id, as_of_date),
    }
