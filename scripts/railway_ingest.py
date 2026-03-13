"""
Railway cron job — daily data ingestion.

Schedule: 0 7 * * *  (7:00 AM UTC daily)

Configure in Railway:
  Start command: python scripts/railway_ingest.py
  Cron schedule: 0 7 * * *
"""
import asyncio
import sys
from datetime import datetime, timedelta

import structlog

log = structlog.get_logger()


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def ingest_yesterday_games() -> int:
    from sqlalchemy import select

    from chalk.db.models import Game, PlayerGameLog
    from chalk.db.session import async_session_factory
    from chalk.ingestion.nba_fetcher import NBAFetcher

    yesterday = (datetime.utcnow() - timedelta(days=1)).date()

    async def _run_ingest():
        fetcher = NBAFetcher()
        async with async_session_factory() as session:
            result = await session.execute(select(Game).where(Game.date == yesterday))
            games = result.scalars().all()

            if not games:
                log.info("no_games_yesterday", date=str(yesterday))
                return 0

            player_count = 0
            team_count = 0

            for game in games:
                for team_id in [game.home_team_id, game.away_team_id]:
                    try:
                        tc = await fetcher.ingest_team_season(session, team_id, game.season)
                        team_count += tc
                    except Exception as e:
                        log.error("team_ingest_failed", team_id=team_id, error=str(e))

                    try:
                        result = await session.execute(
                            select(PlayerGameLog.player_id)
                            .where(PlayerGameLog.game_id == game.game_id)
                            .where(PlayerGameLog.team_id == team_id)
                        )
                        player_ids = [r[0] for r in result.all()]
                        for pid in player_ids:
                            try:
                                pc = await fetcher.ingest_player_season(session, pid, game.season)
                                player_count += pc
                            except Exception as e:
                                log.error("player_ingest_failed", player_id=pid, error=str(e))
                    except Exception as e:
                        log.error("player_lookup_failed", game_id=game.game_id, error=str(e))

            await session.commit()
            log.info("games_ingested", player_rows=player_count, team_rows=team_count, date=str(yesterday))
            return player_count

    return _run(_run_ingest())


def ingest_injuries() -> int:
    from chalk.db.session import async_session_factory
    from chalk.ingestion.injury_fetcher import ingest_injuries as _ingest

    async def _run_ingest():
        async with async_session_factory() as session:
            count = await _ingest(session)
            await session.commit()
            log.info("injuries_ingested", count=count)
            return count

    return _run(_run_ingest())


def fetch_odds_lines() -> int:
    from sqlalchemy import select

    from chalk.db.models import Game
    from chalk.db.session import async_session_factory

    today = datetime.utcnow().date()

    async def _run_fetch():
        async with async_session_factory() as session:
            result = await session.execute(select(Game).where(Game.date == today))
            games = result.scalars().all()

            if not games:
                log.info("no_games_today_odds_skipped", date=str(today))
                return 0

            log.info("odds_fetch", game_count=len(games), date=str(today))
            return len(games)

    return _run(_run_fetch())


def validate_row_counts() -> None:
    from sqlalchemy import func, select

    from chalk.db.models import Game, PlayerGameLog
    from chalk.db.session import async_session_factory

    yesterday = (datetime.utcnow() - timedelta(days=1)).date()

    async def _run_validate():
        async with async_session_factory() as session:
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
                raise RuntimeError(
                    f"Games existed on {yesterday} but 0 player_game_logs ingested"
                )

            log.info("validation_passed", player_logs=log_count, games=game_count, date=str(yesterday))

    _run(_run_validate())


def main():
    steps = [
        ("ingest_yesterday_games", ingest_yesterday_games),
        ("ingest_injuries", ingest_injuries),
        ("fetch_odds_lines", fetch_odds_lines),
        ("validate_row_counts", validate_row_counts),
    ]

    failed = False
    for name, fn in steps:
        try:
            log.info("step_start", step=name)
            fn()
            log.info("step_done", step=name)
        except Exception as e:
            log.error("step_failed", step=name, error=str(e))
            failed = True
            # Continue remaining steps so we get full picture of failures

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
