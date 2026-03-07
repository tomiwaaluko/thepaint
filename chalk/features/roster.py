"""Roster and injury context features."""
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chalk.db.models import Injury, Player, PlayerGameLog
from chalk.features.rolling import get_rolling_avg


async def get_absent_players(
    session: AsyncSession,
    team_id: int,
    game_date: date,
) -> list[Player]:
    """Players with status 'Out' or 'Doubtful' on the given date."""
    result = await session.execute(
        select(Player)
        .join(Injury, Injury.player_id == Player.player_id)
        .where(Player.team_id == team_id)
        .where(Injury.report_date == game_date)
        .where(Injury.status.in_(["Out", "Doubtful"]))
    )
    return list(result.scalars().all())


async def get_roster_features(
    session: AsyncSession,
    player_id: int,
    team_id: int,
    opponent_team_id: int,
    game_id: str,
    as_of_date: date,
) -> dict[str, float]:
    """Compute roster/injury context features."""
    absent_teammates = await get_absent_players(session, team_id, as_of_date)
    absent_opp = await get_absent_players(session, opponent_team_id, as_of_date)

    # Filter out the player themselves from absent teammates
    absent_teammates = [p for p in absent_teammates if p.player_id != player_id]

    # Sum usage proxies for absent teammates (pts avg as proxy for usage)
    usage_values = [
        await get_rolling_avg(session, p.player_id, "pts", 10, as_of_date)
        for p in absent_teammates
    ]
    absent_usage_sum = sum(usage_values)

    # Star teammate out: any absent teammate averaging > 20 pts
    star_out = any(v > 20 for v in usage_values)

    # Key opponent defender out: top scorer among absent opponents
    opp_usage_values = [
        await get_rolling_avg(session, p.player_id, "pts", 10, as_of_date)
        for p in absent_opp
    ]
    key_defender_out = any(v > 15 for v in opp_usage_values)

    return {
        "absent_teammate_count": float(len(absent_teammates)),
        "absent_teammate_usage_sum": float(absent_usage_sum),
        "star_teammate_out": 1.0 if star_out else 0.0,
        "absent_opp_player_count": float(len(absent_opp)),
        "key_opp_defender_out": 1.0 if key_defender_out else 0.0,
    }
