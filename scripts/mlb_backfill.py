"""MLB historical data backfill runner.

Usage: python scripts/mlb_backfill.py [--start-season 2018] [--end-season 2026]

Resumable: completed gamePks are persisted to a progress file periodically
(every PROGRESS_FLUSH_EVERY games and at season end), so a failed run continues
near where it left off. One failed boxscore is skipped and logged, never
aborting the season; re-ingestion of the small unflushed tail is idempotent.
"""
import argparse
import asyncio
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import structlog
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from chalk.db.session import async_session_factory
from chalk.exceptions import IngestError
from chalk.mlb.fetcher import (
    game_is_final,
    ingest_mlb_boxscore,
    ingest_mlb_schedule,
    ingest_mlb_teams,
)
from chalk.mlb.models import MlbGame

log = structlog.get_logger()

DEFAULT_START_SEASON = 2018
INTER_REQUEST_DELAY = 1.0  # seconds between StatsAPI boxscore calls
PROGRESS_FILE = Path(".cache/mlb_backfill_progress.json")
PROGRESS_FLUSH_EVERY = 25  # games between progress-file rewrites

# The MLB calendar (spring reporting through the World Series) fits inside
# Feb 15 – Nov 30 (cushion for postseason slippage); schedule ingestion
# filters to regular season + postseason game types.
SEASON_START = (2, 15)
SEASON_END = (11, 30)


def season_windows(season: int, window_days: int = 30) -> list[tuple[date, date]]:
    """Contiguous ~30-day date windows covering one season's calendar."""
    start = date(season, *SEASON_START)
    end = date(season, *SEASON_END)
    windows = []
    cursor = start
    while cursor <= end:
        window_end = min(cursor + timedelta(days=window_days - 1), end)
        windows.append((cursor, window_end))
        cursor = window_end + timedelta(days=1)
    return windows


def load_progress() -> set[int]:
    """Load completed gamePks from the progress file."""
    if PROGRESS_FILE.exists():
        data = json.loads(PROGRESS_FILE.read_text())
        return set(data.get("completed", []))
    return set()


def save_progress(completed: set[int]) -> None:
    """Persist completed gamePks."""
    PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
    PROGRESS_FILE.write_text(json.dumps({"completed": sorted(completed)}))


async def backfill_season(session, season: int, completed: set[int]) -> tuple[int, int]:
    """Backfill one season. Returns (games_ingested, games_skipped_on_error)."""
    await ingest_mlb_teams(session, season)
    today = datetime.now(timezone.utc).date()
    for start, end in season_windows(season):
        # Windows that touch today/the future have volatile statuses — caching
        # them would permanently hide games from every future resume.
        await ingest_mlb_schedule(session, start, end, use_cache=end < today)
        await asyncio.sleep(INTER_REQUEST_DELAY)

    result = await session.execute(
        select(MlbGame).where(MlbGame.season == str(season)).order_by(MlbGame.date)
    )
    # Snapshot plain gamePks: a mid-loop rollback expires ORM instances, and
    # touching an expired attribute would force a lazy refresh mid-iteration.
    final_pks = [g.game_pk for g in result.scalars().all() if game_is_final(g)]

    done = 0
    skipped = 0
    for game_pk in final_pks:
        if game_pk in completed:
            continue
        try:
            batters, pitchers = await ingest_mlb_boxscore(session, game_pk)
            completed.add(game_pk)
            done += 1
            log.info(
                "mlb_backfill_progress",
                season=season, game_pk=game_pk,
                batters=batters, pitchers=pitchers,
                completed_total=len(completed),
            )
        except (IngestError, SQLAlchemyError) as e:
            # DB-level failures are also per-game skips; roll back so the
            # session stays usable for the rest of the season.
            await session.rollback()
            skipped += 1
            log.error("mlb_backfill_skip", game_pk=game_pk, error=str(e))
        if (done + skipped) % PROGRESS_FLUSH_EVERY == 0:
            save_progress(completed)
        await asyncio.sleep(INTER_REQUEST_DELAY)

    save_progress(completed)
    return done, skipped


async def backfill(start_season: int, end_season: int) -> None:
    completed = load_progress()
    log.info(
        "mlb_backfill_start",
        start_season=start_season, end_season=end_season,
        already_completed=len(completed),
    )
    for season in range(start_season, end_season + 1):
        async with async_session_factory() as session:
            done, skipped = await backfill_season(session, season, completed)
        log.info("mlb_backfill_season_done", season=season, done=done, skipped=skipped)
    log.info("mlb_backfill_complete", total_completed=len(completed))


def main():
    current_year = datetime.now(timezone.utc).year
    parser = argparse.ArgumentParser(description="Backfill MLB data")
    parser.add_argument("--start-season", type=int, default=DEFAULT_START_SEASON)
    parser.add_argument("--end-season", type=int, default=current_year)
    args = parser.parse_args()

    asyncio.run(backfill(args.start_season, args.end_season))


if __name__ == "__main__":
    main()
