"""Daily data ingestion DAG — pulls yesterday's games, injuries, and odds."""
import asyncio
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.exceptions import AirflowException

default_args = {
    "owner": "chalk",
    "depends_on_past": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}

dag = DAG(
    dag_id="daily_ingest",
    default_args=default_args,
    description="Ingest yesterday's game data, injuries, and betting lines",
    schedule="0 8 * * *",  # 8:00 AM ET daily
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["chalk", "ingestion"],
)


def _run_async(coro):
    """Helper to run async code in Airflow's sync context."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def ingest_yesterday_games(**context):
    """Ingest player and team game logs from yesterday."""
    from sqlalchemy import select, func
    from chalk.db.session import async_session_factory
    from chalk.db.models import Game, PlayerGameLog, TeamGameLog
    from chalk.ingestion.nba_fetcher import NBAFetcher

    yesterday = (datetime.utcnow() - timedelta(days=1)).date()

    async def _ingest():
        fetcher = NBAFetcher()
        async with async_session_factory() as session:
            # Find games played yesterday
            result = await session.execute(
                select(Game).where(Game.date == yesterday)
            )
            games = result.scalars().all()

            if not games:
                print(f"No games found for {yesterday}")
                return 0

            player_count = 0
            team_count = 0

            for game in games:
                for team_id in [game.home_team_id, game.away_team_id]:
                    try:
                        tc = await fetcher.ingest_team_season(
                            session, team_id, game.season
                        )
                        team_count += tc
                    except Exception as e:
                        print(f"Team ingest failed for {team_id}: {e}")

                    try:
                        # Get players who played in this game
                        result = await session.execute(
                            select(PlayerGameLog.player_id)
                            .where(PlayerGameLog.game_id == game.game_id)
                            .where(PlayerGameLog.team_id == team_id)
                        )
                        player_ids = [r[0] for r in result.all()]
                        for pid in player_ids:
                            try:
                                pc = await fetcher.ingest_player_season(
                                    session, pid, game.season
                                )
                                player_count += pc
                            except Exception as e:
                                print(f"Player ingest failed for {pid}: {e}")
                    except Exception as e:
                        print(f"Player lookup failed: {e}")

            await session.commit()
            print(f"Ingested {player_count} player rows, {team_count} team rows for {yesterday}")
            return player_count

    return _run_async(_ingest())


def ingest_injuries(**context):
    """Pull latest injury reports."""
    from chalk.db.session import async_session_factory
    from chalk.ingestion.injury_fetcher import ingest_injuries as _ingest

    async def _run():
        async with async_session_factory() as session:
            count = await _ingest(session)
            await session.commit()
            print(f"Ingested {count} injury reports")
            return count

    return _run_async(_run())


def fetch_odds_lines(**context):
    """Fetch betting lines for today's games."""
    from sqlalchemy import select
    from chalk.db.session import async_session_factory
    from chalk.db.models import Game

    today = datetime.utcnow().date()

    async def _run():
        async with async_session_factory() as session:
            result = await session.execute(
                select(Game).where(Game.date == today)
            )
            games = result.scalars().all()

            if not games:
                print(f"No games today ({today}), skipping odds fetch")
                return 0

            print(f"Found {len(games)} games today, would fetch odds")
            # Odds API integration is stubbed — requires ODDS_API_KEY
            return len(games)

    return _run_async(_run())


def validate_row_counts(**context):
    """Validate that ingestion produced data."""
    from sqlalchemy import select, func
    from chalk.db.session import async_session_factory
    from chalk.db.models import PlayerGameLog, Game

    yesterday = (datetime.utcnow() - timedelta(days=1)).date()

    async def _run():
        async with async_session_factory() as session:
            # Check if there were games yesterday
            game_result = await session.execute(
                select(func.count()).select_from(Game).where(Game.date == yesterday)
            )
            game_count = game_result.scalar()

            if game_count == 0:
                print(f"No games on {yesterday} — validation skipped")
                return

            # Check player game logs exist
            log_result = await session.execute(
                select(func.count())
                .select_from(PlayerGameLog)
                .where(PlayerGameLog.game_date == yesterday)
            )
            log_count = log_result.scalar()

            if log_count == 0:
                raise AirflowException(
                    f"Games existed on {yesterday} but 0 player_game_logs ingested"
                )

            print(f"Validation passed: {log_count} player logs for {game_count} games on {yesterday}")

    return _run_async(_run())


# Task definitions
t_ingest_games = PythonOperator(
    task_id="ingest_yesterday_games",
    python_callable=ingest_yesterday_games,
    dag=dag,
)

t_ingest_injuries = PythonOperator(
    task_id="ingest_injuries",
    python_callable=ingest_injuries,
    dag=dag,
)

t_fetch_odds = PythonOperator(
    task_id="fetch_odds_lines",
    python_callable=fetch_odds_lines,
    dag=dag,
)

t_validate = PythonOperator(
    task_id="validate_row_counts",
    python_callable=validate_row_counts,
    dag=dag,
)

# Task dependencies
t_ingest_games >> t_ingest_injuries >> t_fetch_odds >> t_validate
