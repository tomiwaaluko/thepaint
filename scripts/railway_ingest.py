"""
Railway cron job — daily data ingestion.

Schedule: 0 7 * * *  (7:00 AM UTC daily)

Steps:
  1. seed_yesterday_games   — create game records for yesterday via NBA scoreboard
  2. ingest_yesterday_stats — ingest team + player box scores for yesterday's games
  3. seed_today_games       — create game records for today (needed by prediction cron)
  4. ingest_injuries        — refresh injury report
  5. fetch_odds_lines       — stub (Odds API not yet wired)
  6. validate_row_counts    — sanity check: logs exist for yesterday's games
"""
import asyncio
import sys
from datetime import datetime, timedelta, timezone

import structlog

log = structlog.get_logger()


async def main_async() -> bool:
    from sqlalchemy import func, select

    from chalk.db.models import Game, Player, PlayerGameLog
    from chalk.db.session import async_session_factory
    from chalk.ingestion.injury_fetcher import ingest_injuries
    from chalk.ingestion.nba_fetcher import (
        ingest_player_season,
        ingest_team_season,
        ingest_today_scoreboard,
    )

    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).date()
    today = datetime.now(timezone.utc).date()
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

    # Each step gets its own session to avoid asyncpg state issues
    async def with_session(coro_fn):
        async with async_session_factory() as session:
            return await coro_fn(session)

    # 1. Seed game records for yesterday so subsequent steps can find them
    await run_step(
        "seed_yesterday_games",
        with_session(lambda s: ingest_today_scoreboard(s, yesterday)),
    )

    # 2. Ingest team + player box scores for yesterday's games
    # Uses fresh sessions per-call to avoid stale connections during long nba_api retries
    async def ingest_yesterday_stats(_unused_session):
        async with async_session_factory() as session:
            result = await session.execute(select(Game).where(Game.date == yesterday))
            games = result.scalars().all()

        if not games:
            log.info("no_games_yesterday", date=str(yesterday))
            return 0

        # Ingest full team season logs (one call per season covers all teams)
        seen_seasons: set[str] = set()
        for game in games:
            if game.season not in seen_seasons:
                seen_seasons.add(game.season)
                try:
                    async with async_session_factory() as session:
                        tc = await ingest_team_season(session, game.season)
                    log.info("team_season_ingested", season=game.season, rows=tc)
                except Exception as e:
                    log.error("team_season_failed", season=game.season, error=str(e))

        # Ingest player game logs — use active roster for each team playing yesterday
        player_count = 0
        team_ids: set[int] = set()
        for game in games:
            team_ids.add(game.home_team_id)
            team_ids.add(game.away_team_id)

        # All games on the same date share a season
        season = games[0].season

        async with async_session_factory() as session:
            p_result = await session.execute(
                select(Player.player_id)
                .where(Player.team_id.in_(team_ids))
                .where(Player.is_active == True)
            )
            player_ids = [r[0] for r in p_result.all()]

        # Circuit breaker: if N consecutive players fail, nba_api is likely
        # unreachable from this IP — skip remaining to avoid burning hours.
        CIRCUIT_BREAKER_THRESHOLD = 3
        consecutive_failures = 0

        for pid in player_ids:
            if consecutive_failures >= CIRCUIT_BREAKER_THRESHOLD:
                skipped = len(player_ids) - player_ids.index(pid)
                log.error(
                    "circuit_breaker_tripped",
                    consecutive_failures=consecutive_failures,
                    skipped_players=skipped,
                    msg="nba_api appears unreachable — skipping remaining players",
                )
                break

            try:
                async with async_session_factory() as session:
                    pc = await ingest_player_season(session, pid, season)
                player_count += pc
                consecutive_failures = 0  # reset on success
            except Exception as e:
                consecutive_failures += 1
                log.error("player_ingest_failed", player_id=pid, error=str(e),
                          consecutive_failures=consecutive_failures)

        log.info("yesterday_stats_done", player_rows=player_count, date=str(yesterday))
        return player_count

    await run_step("ingest_yesterday_stats", with_session(ingest_yesterday_stats))

    # 3. Seed today's game records so the prediction cron can find them
    await run_step(
        "seed_today_games",
        with_session(lambda s: ingest_today_scoreboard(s, today)),
    )

    # 4. Refresh injury report
    async def do_ingest_injuries(session):
        count = await ingest_injuries(session)
        await session.commit()
        log.info("injuries_ingested", count=count)
        return count

    await run_step("ingest_injuries", with_session(do_ingest_injuries))

    # 5. Fetch odds lines (stubbed — counts today's games)
    async def fetch_odds_lines(session):
        result = await session.execute(select(Game).where(Game.date == today))
        games = result.scalars().all()
        if not games:
            log.info("no_games_today_odds_skipped", date=str(today))
            return 0
        log.info("odds_fetch", game_count=len(games), date=str(today))
        return len(games)

    await run_step("fetch_odds_lines", with_session(fetch_odds_lines))

    # 6. Validate: if games existed yesterday, player logs must exist
    async def validate_row_counts(session):
        nonlocal failed
        game_result = await session.execute(
            select(func.count()).select_from(Game).where(Game.date == yesterday)
        )
        game_count = game_result.scalar()

        if game_count == 0:
            log.info("no_games_validation_skipped", date=str(yesterday))
            return

        log_result = await session.execute(
            select(func.count())
            .select_from(PlayerGameLog)
            .where(PlayerGameLog.game_date == yesterday)
        )
        log_count = log_result.scalar()

        if log_count == 0:
            log.warning(
                "validation_failed_no_player_logs",
                games=game_count,
                date=str(yesterday),
            )
            failed = True
            return

        log.info("validation_passed", player_logs=log_count, games=game_count, date=str(yesterday))

    await run_step("validate_row_counts", with_session(validate_row_counts))

    return failed


def main():
    failed = asyncio.run(main_async())
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
