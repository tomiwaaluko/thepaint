"""Row-count sanity checks for MLB ingestion — warn, don't raise."""
from datetime import date

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from chalk.mlb.fetcher import is_final_status
from chalk.mlb.models import MlbBatterGameLog, MlbGame, MlbPitcherGameLog

log = structlog.get_logger()


async def validate_mlb_row_counts(session: AsyncSession, game_date: date) -> bool:
    """True if healthy; logs a warning and returns False otherwise. Never raises.

    Unhealthy means final games exist for the date but zero batter+pitcher log
    rows landed (e.g. boxscore ingestion was skipped or timed out). A no-games
    day is healthy — playoff-style gaps in the schedule are normal.
    """
    games = (
        await session.execute(select(MlbGame).where(MlbGame.date == game_date))
    ).scalars().all()
    final_games = [g for g in games if is_final_status(g.status)]
    if not final_games:
        log.info("no_mlb_games_to_validate", date=str(game_date))
        return True

    batter_count = (
        await session.execute(
            select(func.count())
            .select_from(MlbBatterGameLog)
            .where(MlbBatterGameLog.game_date == game_date)
        )
    ).scalar_one()
    pitcher_count = (
        await session.execute(
            select(func.count())
            .select_from(MlbPitcherGameLog)
            .where(MlbPitcherGameLog.game_date == game_date)
        )
    ).scalar_one()

    if batter_count + pitcher_count == 0:
        log.warning(
            "validation_failed_no_mlb_logs",
            date=str(game_date), final_games=len(final_games),
        )
        return False

    log.info(
        "mlb_validation_ok",
        date=str(game_date), final_games=len(final_games),
        batter_logs=batter_count, pitcher_logs=pitcher_count,
    )
    return True
