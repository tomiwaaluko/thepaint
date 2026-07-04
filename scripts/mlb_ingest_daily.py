"""
Daily MLB data ingestion — cron-ready (not yet wired to a Railway service).

Intended schedule: 0 8 * * *  (8:00 AM UTC daily, after West Coast night games)

Steps:
  1. refresh_mlb_teams       — keep team metadata current (cheap, one call)
  2. ingest_yesterday_mlb    — yesterday's schedule + final-game boxscores
  3. seed_today_mlb_schedule — today's games (uncached; statuses are volatile)
  4. validate_row_counts     — warn-style sanity check on yesterday's logs

Exit code 0 when healthy, 1 when any step failed or validation flagged missing
logs — matching the scripts/railway_ingest.py contract.
"""
import asyncio
import sys
from datetime import datetime, timedelta, timezone

import structlog

log = structlog.get_logger()


async def main_async() -> bool:
    """Run all steps. Returns True if anything failed."""
    from chalk.db.session import async_session_factory
    from chalk.mlb.fetcher import (
        ingest_mlb_date,
        ingest_mlb_schedule,
        ingest_mlb_teams,
    )
    from chalk.mlb.validate import validate_mlb_row_counts

    now = datetime.now(timezone.utc)
    yesterday = (now - timedelta(days=1)).date()
    today = now.date()
    failed = False

    async def run_step(name, coro):
        nonlocal failed
        log.info("step_start", step=name)
        try:
            result = await coro
            log.info("step_done", step=name)
            return result
        except Exception as e:
            log.error("step_failed", step=name, error=str(e))
            failed = True
            return None

    # Each step gets its own session to avoid stale connections across retries
    async def with_session(coro_fn):
        async with async_session_factory() as session:
            return await coro_fn(session)

    await run_step(
        "refresh_mlb_teams",
        with_session(lambda s: ingest_mlb_teams(s, today.year)),
    )

    summary = await run_step(
        "ingest_yesterday_mlb",
        with_session(lambda s: ingest_mlb_date(s, yesterday)),
    )
    if summary is not None:
        log.info("mlb_yesterday_summary", date=str(yesterday), **summary)

    await run_step(
        "seed_today_mlb_schedule",
        with_session(lambda s: ingest_mlb_schedule(s, today, today, use_cache=False)),
    )

    healthy = await run_step(
        "validate_row_counts",
        with_session(lambda s: validate_mlb_row_counts(s, yesterday)),
    )
    if healthy is False:
        failed = True

    return failed


def main():
    failed = asyncio.run(main_async())
    log.info("mlb_daily_ingest_finished", failed=failed)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
