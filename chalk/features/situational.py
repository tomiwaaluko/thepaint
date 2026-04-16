"""Situational features: rest, location, season context."""
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from chalk.db.models import Game, Player, PlayerGameLog, TeamGameLog

# Denver Nuggets team_id — altitude affects performance
NUGGETS_TEAM_ID = 1610612743


async def get_previous_game_date(
    session: AsyncSession,
    player_id: int,
    as_of_date: date,
) -> date | None:
    """Date of player's most recent game before as_of_date."""
    result = await session.execute(
        select(PlayerGameLog.game_date)
        .where(PlayerGameLog.player_id == player_id)
        .where(PlayerGameLog.game_date < as_of_date)  # as_of_date gate
        .order_by(PlayerGameLog.game_date.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_game_number_in_season(
    session: AsyncSession,
    team_id: int,
    season: str,
    as_of_date: date,
) -> int:
    """Count of games played by team in season before as_of_date."""
    result = await session.execute(
        select(func.count())
        .select_from(TeamGameLog)
        .where(TeamGameLog.team_id == team_id)
        .where(TeamGameLog.season == season)
        .where(TeamGameLog.game_date < as_of_date)  # as_of_date gate
    )
    return result.scalar() or 0


def get_situational_features(
    game: Game,
    player: Player,
    previous_game_date: date | None,
    game_number: int = 0,
) -> dict[str, float]:
    """Compute situational features from game/player context."""
    # Rest days
    if previous_game_date is not None:
        days_rest = min((game.date - previous_game_date).days, 7)
    else:
        days_rest = 7  # No previous game → treat as well-rested

    is_home = game.home_team_id == player.team_id

    # Denver altitude check: playing AT Denver (opponent is home and is Nuggets)
    is_denver = (not is_home and game.home_team_id == NUGGETS_TEAM_ID) or \
                (is_home and game.home_team_id == NUGGETS_TEAM_ID)

    # Derive playoff round from game ID: position 5 encodes round (1-4)
    # Format: 004SSRGGGG where R = round number
    playoff_round = 0.0
    if game.is_playoffs and len(game.game_id) >= 6 and game.game_id[5].isdigit():
        playoff_round = float(game.game_id[5])
    elif game.is_playoffs:
        playoff_round = 1.0  # default if format is unexpected

    return {
        "days_rest": float(days_rest),
        "is_back_to_back": 1.0 if days_rest <= 1 else 0.0,
        "is_well_rested": 1.0 if days_rest >= 3 else 0.0,
        "is_home": 1.0 if is_home else 0.0,
        "is_away": 0.0 if is_home else 1.0,
        "is_denver": 1.0 if is_denver else 0.0,
        "game_number_in_season": float(game_number),
        "is_second_half_season": 1.0 if game_number > 41 else 0.0,
        "is_playoffs": 1.0 if game.is_playoffs else 0.0,
        "playoff_round": playoff_round,
    }
