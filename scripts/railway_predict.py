"""
Railway cron job — daily prediction generation.

Schedule: 0 18 * * *  (6:00 PM UTC daily)

Configure in Railway:
  Start command: python scripts/railway_predict.py
  Cron schedule: 0 18 * * *

Required env var:
  API_INTERNAL_URL — Railway private network URL for the API service,
                     e.g. http://chalk-api.railway.internal:8000
                     Leave unset to skip cache warming (predictions still generate).
"""
import asyncio
import os
import sys
from datetime import datetime

import structlog

log = structlog.get_logger()

# Railway private networking: http://<service-name>.railway.internal:<port>
# Set this to match your API service name in Railway.
API_INTERNAL_URL = os.getenv("API_INTERNAL_URL", "")


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def check_todays_games() -> int:
    from sqlalchemy import func, select

    from chalk.db.models import Game
    from chalk.db.session import async_session_factory

    today = datetime.utcnow().date()

    async def _run_check():
        async with async_session_factory() as session:
            result = await session.execute(
                select(func.count()).select_from(Game).where(Game.date == today)
            )
            count = result.scalar()
            log.info("todays_games", count=count, date=str(today))
            return count

    return _run(_run_check())


def refresh_injuries() -> int:
    from chalk.db.session import async_session_factory
    from chalk.ingestion.injury_fetcher import ingest_injuries

    async def _run_refresh():
        async with async_session_factory() as session:
            count = await ingest_injuries(session)
            await session.commit()
            log.info("injuries_refreshed", count=count)
            return count

    return _run(_run_refresh())


def invalidate_stale_cache() -> None:
    import redis

    from chalk.config import settings

    r = redis.from_url(settings.REDIS_URL)
    keys = r.keys("pred:*")
    if keys:
        deleted = r.delete(*keys)
        log.info("cache_invalidated", keys_deleted=deleted)
    else:
        log.info("cache_already_empty")
    r.close()


def generate_todays_predictions() -> int:
    from sqlalchemy import select

    from chalk.db.models import Game, PlayerGameLog, Prediction
    from chalk.db.session import async_session_factory
    from chalk.predictions.player import predict_player

    today = datetime.utcnow().date()

    async def _run_predict():
        async with async_session_factory() as session:
            result = await session.execute(select(Game).where(Game.date == today))
            games = result.scalars().all()

            if not games:
                log.info("no_games_today_predictions_skipped")
                return 0

            total = 0
            for game in games:
                result = await session.execute(
                    select(PlayerGameLog.player_id)
                    .where(PlayerGameLog.game_id == game.game_id)
                    .distinct()
                )
                player_ids = [r[0] for r in result.all()]

                for pid in player_ids:
                    try:
                        pred = await predict_player(session, pid, game.game_id, today)
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
                        total += 1
                    except Exception as e:
                        log.error("prediction_failed", player_id=pid, error=str(e))

                await session.commit()

            log.info("predictions_generated", player_count=total)
            return total

    return _run(_run_predict())


def warm_api_cache() -> None:
    """Pre-populate Redis by hitting the game prediction endpoints."""
    if not API_INTERNAL_URL:
        log.info("cache_warm_skipped", reason="API_INTERNAL_URL not set")
        return

    import httpx
    from sqlalchemy import select

    from chalk.db.models import Game
    from chalk.db.session import async_session_factory

    today = datetime.utcnow().date()

    async def _run_warm():
        async with async_session_factory() as session:
            result = await session.execute(select(Game.game_id).where(Game.date == today))
            game_ids = [r[0] for r in result.all()]

        async with httpx.AsyncClient(base_url=API_INTERNAL_URL, timeout=60) as client:
            for gid in game_ids:
                try:
                    resp = await client.get(f"/v1/games/{gid}/predict")
                    log.info("cache_warmed", game_id=gid, status=resp.status_code)
                except Exception as e:
                    log.error("cache_warm_failed", game_id=gid, error=str(e))

    _run(_run_warm())


def validate_predictions() -> None:
    from sqlalchemy import select

    from chalk.db.models import Prediction
    from chalk.db.session import async_session_factory

    today = datetime.utcnow().date()

    async def _run_validate():
        async with async_session_factory() as session:
            result = await session.execute(
                select(Prediction)
                .where(Prediction.as_of_ts >= datetime.combine(today, datetime.min.time()))
                .limit(10)
            )
            preds = result.scalars().all()

            if not preds:
                log.info("no_predictions_to_validate")
                return

            errors = []
            for p in preds:
                if not (p.p10 <= p.p50 <= p.p90):
                    errors.append(f"Quantile ordering violated: pred {p.pred_id}")
                if p.stat == "pts" and not (0 <= p.p50 <= 70):
                    errors.append(f"PTS out of bounds: pred {p.pred_id} p50={p.p50}")
                if p.stat == "reb" and not (0 <= p.p50 <= 30):
                    errors.append(f"REB out of bounds: pred {p.pred_id} p50={p.p50}")

            if errors:
                raise RuntimeError("Prediction validation failed:\n" + "\n".join(errors))

            log.info("predictions_validated", count=len(preds))

    _run(_run_validate())


def main():
    game_count = check_todays_games()
    if game_count == 0:
        log.info("no_games_today_exiting")
        sys.exit(0)

    steps = [
        ("refresh_injuries", refresh_injuries),
        ("invalidate_stale_cache", invalidate_stale_cache),
        ("generate_todays_predictions", generate_todays_predictions),
        ("warm_api_cache", warm_api_cache),
        ("validate_predictions", validate_predictions),
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

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
