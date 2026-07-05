"""Row-count sanity checks for MLB ingestion — warn, don't raise."""
from datetime import date

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chalk.mlb.fetcher import game_is_final
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
    final_games = [g for g in games if game_is_final(g)]
    if not final_games:
        log.info("no_mlb_games_to_validate", date=str(game_date))
        return True

    # Per-game coverage, not a date-wide total: one covered game must not
    # mask nine uncovered ones.
    covered = set(
        (
            await session.execute(
                select(MlbBatterGameLog.game_pk)
                .where(MlbBatterGameLog.game_date == game_date)
                .union(
                    select(MlbPitcherGameLog.game_pk)
                    .where(MlbPitcherGameLog.game_date == game_date)
                )
            )
        ).scalars().all()
    )
    missing = sorted({g.game_pk for g in final_games} - covered)
    if missing:
        log.warning(
            "validation_failed_no_mlb_logs",
            date=str(game_date), final_games=len(final_games),
            missing_games=missing,
        )
        return False

    log.info(
        "mlb_validation_ok",
        date=str(game_date), final_games=len(final_games),
        covered_games=len(covered),
    )
    return True
