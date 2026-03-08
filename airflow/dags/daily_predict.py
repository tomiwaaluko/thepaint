"""Daily prediction DAG — generates predictions for today's games."""
import asyncio
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.exceptions import AirflowException

default_args = {
    "owner": "chalk",
    "depends_on_past": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=10),
}

dag = DAG(
    dag_id="daily_predict",
    default_args=default_args,
    description="Generate player predictions for today's games",
    schedule="0 18 * * *",  # 6:00 PM ET daily
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["chalk", "predictions"],
)


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def check_todays_games(**context):
    """Check if there are games today. Short-circuit if none."""
    from sqlalchemy import select, func
    from chalk.db.session import async_session_factory
    from chalk.db.models import Game

    today = datetime.utcnow().date()

    async def _run():
        async with async_session_factory() as session:
            result = await session.execute(
                select(func.count()).select_from(Game).where(Game.date == today)
            )
            count = result.scalar()
            print(f"Found {count} games for {today}")
            return count

    count = _run_async(_run())
    context["ti"].xcom_push(key="game_count", value=count)
    return count


def refresh_injuries(**context):
    """Re-pull injury updates from the last 2 hours."""
    from chalk.db.session import async_session_factory
    from chalk.ingestion.injury_fetcher import ingest_injuries

    async def _run():
        async with async_session_factory() as session:
            count = await ingest_injuries(session)
            await session.commit()
            print(f"Refreshed {count} injury reports")
            return count

    return _run_async(_run())


def invalidate_stale_cache(**context):
    """Clear Redis prediction cache to force fresh predictions."""
    import redis

    from chalk.config import settings

    r = redis.from_url(settings.REDIS_URL)
    keys = r.keys("pred:*")
    if keys:
        deleted = r.delete(*keys)
        print(f"Invalidated {deleted} cached predictions")
    else:
        print("No cached predictions to invalidate")
    r.close()


def generate_todays_predictions(**context):
    """Generate predictions for all players in today's games."""
    from sqlalchemy import select
    from chalk.db.session import async_session_factory
    from chalk.db.models import Game, PlayerGameLog, Prediction
    from chalk.predictions.player import predict_player

    today = datetime.utcnow().date()

    async def _run():
        async with async_session_factory() as session:
            result = await session.execute(
                select(Game).where(Game.date == today)
            )
            games = result.scalars().all()

            if not games:
                print("No games today — skipping predictions")
                return 0

            total_predictions = 0
            for game in games:
                # Get players for both teams
                result = await session.execute(
                    select(PlayerGameLog.player_id)
                    .where(PlayerGameLog.game_id == game.game_id)
                    .distinct()
                )
                player_ids = [r[0] for r in result.all()]

                for pid in player_ids:
                    try:
                        pred = await predict_player(session, pid, game.game_id, today)

                        # Store predictions in DB
                        for sp in pred.predictions:
                            db_pred = Prediction(
                                game_id=game.game_id,
                                player_id=pid,
                                model_version=pred.model_version,
                                as_of_ts=datetime.utcnow(),
                                stat=sp.stat,
                                p10=sp.p10,
                                p25=sp.p25,
                                p50=sp.p50,
                                p75=sp.p75,
                                p90=sp.ceiling,
                            )
                            session.add(db_pred)
                        total_predictions += 1
                    except Exception as e:
                        print(f"Prediction failed for player {pid}: {e}")

                await session.commit()

            print(f"Generated predictions for {total_predictions} players")
            return total_predictions

    count = _run_async(_run())
    context["ti"].xcom_push(key="player_count", value=count)
    return count


def warm_api_cache(**context):
    """Pre-populate Redis cache with today's predictions via API calls."""
    import httpx

    from sqlalchemy import select
    from chalk.db.session import async_session_factory
    from chalk.db.models import Game

    today = datetime.utcnow().date()

    async def _run():
        async with async_session_factory() as session:
            result = await session.execute(
                select(Game.game_id).where(Game.date == today)
            )
            game_ids = [r[0] for r in result.all()]

        # Hit the game prediction endpoint to warm cache
        async with httpx.AsyncClient(base_url="http://api:8000", timeout=60) as client:
            for gid in game_ids:
                try:
                    resp = await client.get(f"/v1/games/{gid}/predict")
                    print(f"Warmed cache for game {gid}: {resp.status_code}")
                except Exception as e:
                    print(f"Cache warm failed for {gid}: {e}")

    _run_async(_run())


def validate_predictions(**context):
    """Spot-check today's predictions for sanity."""
    from sqlalchemy import select
    from chalk.db.session import async_session_factory
    from chalk.db.models import Prediction

    today = datetime.utcnow().date()

    async def _run():
        async with async_session_factory() as session:
            result = await session.execute(
                select(Prediction)
                .where(Prediction.as_of_ts >= datetime.combine(today, datetime.min.time()))
                .limit(10)
            )
            preds = result.scalars().all()

            if not preds:
                print("No predictions to validate (may be no games today)")
                return

            errors = []
            for p in preds:
                if not (p.p10 <= p.p50 <= p.p90):
                    errors.append(f"Quantile ordering violated for pred {p.pred_id}: p10={p.p10}, p50={p.p50}, p90={p.p90}")

                if p.stat == "pts" and not (0 <= p.p50 <= 70):
                    errors.append(f"PTS out of bounds for pred {p.pred_id}: p50={p.p50}")

                if p.stat == "reb" and not (0 <= p.p50 <= 30):
                    errors.append(f"REB out of bounds for pred {p.pred_id}: p50={p.p50}")

            if errors:
                raise AirflowException(
                    f"Prediction validation failed:\n" + "\n".join(errors)
                )

            print(f"Validated {len(preds)} predictions — all passed")

    _run_async(_run())


# Task definitions
t_check = PythonOperator(task_id="check_todays_games", python_callable=check_todays_games, dag=dag)
t_injuries = PythonOperator(task_id="refresh_injuries", python_callable=refresh_injuries, dag=dag)
t_invalidate = PythonOperator(task_id="invalidate_stale_cache", python_callable=invalidate_stale_cache, dag=dag)
t_predict = PythonOperator(task_id="generate_todays_predictions", python_callable=generate_todays_predictions, dag=dag)
t_warm = PythonOperator(task_id="warm_api_cache", python_callable=warm_api_cache, dag=dag)
t_validate = PythonOperator(task_id="validate_predictions", python_callable=validate_predictions, dag=dag)

# Dependencies
t_check >> t_injuries >> t_invalidate >> t_predict >> t_warm >> t_validate
