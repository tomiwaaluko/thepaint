"""
Railway cron job — daily prediction generation.

Schedule: 0 18 * * *  (6:00 PM UTC daily)

Required env var:
  API_INTERNAL_URL — Railway private network URL for the API service,
                     e.g. http://web.railway.internal:8000
                     Leave unset to skip cache warming (predictions still generate).
"""
import asyncio
import os
import sys
from datetime import datetime, time
from urllib.parse import urlparse

import structlog

log = structlog.get_logger()

_raw_api_url = os.getenv("API_INTERNAL_URL", "")
_ALLOWED_API_HOSTS = {"web.railway.internal", "localhost", "127.0.0.1"}
if _raw_api_url:
    _parsed = urlparse(_raw_api_url)
    if _parsed.scheme not in {"http", "https"}:
        raise ValueError(f"API_INTERNAL_URL scheme '{_parsed.scheme}' must be 'http' or 'https'")
    if not _parsed.netloc:
        raise ValueError("API_INTERNAL_URL must be an absolute URL with a host")
    if _parsed.hostname not in _ALLOWED_API_HOSTS:
        raise ValueError(f"API_INTERNAL_URL hostname '{_parsed.hostname}' not in allowed list: {_ALLOWED_API_HOSTS}")
API_INTERNAL_URL = _raw_api_url


async def main_async() -> bool:
    from sqlalchemy import func, select

    from chalk.db.models import Game, Player, Prediction
    from chalk.db.session import async_session_factory
    from chalk.ingestion.injury_fetcher import ingest_injuries
    from chalk.predictions.player import predict_player

    today = datetime.utcnow().date()
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

    async def with_session(coro_fn):
        async with async_session_factory() as session:
            return await coro_fn(session)

    # 0. Early exit if no games today
    async def check_todays_games(session):
        result = await session.execute(
            select(func.count()).select_from(Game).where(Game.date == today)
        )
        count = result.scalar()
        log.info("todays_games", count=count, date=str(today))
        return count

    game_count = await with_session(check_todays_games)
    if not game_count:
        log.info("no_games_today_exiting")
        sys.exit(0)

    # 1. Refresh injuries right before generating predictions
    async def do_refresh_injuries(session):
        count = await ingest_injuries(session)
        await session.commit()
        log.info("injuries_refreshed", count=count)
        return count

    await run_step("refresh_injuries", with_session(do_refresh_injuries))

    # 2. Invalidate stale Redis cache
    async def invalidate_stale_cache():
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

    await run_step("invalidate_stale_cache", invalidate_stale_cache())

    # 3. Generate predictions for every active player in today's games
    async def generate_todays_predictions(session):
        result = await session.execute(select(Game).where(Game.date == today))
        games = result.scalars().all()

        if not games:
            log.info("no_games_today_predictions_skipped")
            return 0

        total = 0
        for game in games:
            # Query active players by team roster — NOT by future game logs
            # (today's game hasn't been played yet, so player_game_logs won't have it)
            p_result = await session.execute(
                select(Player.player_id)
                .where(Player.team_id.in_([game.home_team_id, game.away_team_id]))
                .where(Player.is_active == True)
            )
            player_ids = [r[0] for r in p_result.all()]

            successful_pids = []
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
                            p90=sp.p90,
                        )
                        session.add(db_pred)
                    successful_pids.append(pid)
                except Exception as e:
                    log.error("prediction_failed", player_id=pid, error=str(e))

            try:
                await session.commit()
                total += len(successful_pids)
            except Exception as e:
                log.error("prediction_failed", player_id=None, error=str(e))

        log.info("predictions_generated", player_count=total)
        return total

    await run_step("generate_todays_predictions", with_session(generate_todays_predictions))

    # 4. Warm API cache by hitting game prediction endpoints
    async def warm_api_cache(session):
        if not API_INTERNAL_URL:
            log.info("cache_warm_skipped", reason="API_INTERNAL_URL not set")
            return

        import httpx

        result = await session.execute(select(Game.game_id).where(Game.date == today))
        game_ids = [r[0] for r in result.all()]

        async with httpx.AsyncClient(base_url=API_INTERNAL_URL, timeout=60) as client:
            for gid in game_ids:
                try:
                    resp = await client.get(f"/v1/games/{gid}/predict")
                    log.info("cache_warmed", game_id=gid, status=resp.status_code)
                except Exception as e:
                    log.error("cache_warm_failed", game_id=gid, error=str(e))

    await run_step("warm_api_cache", with_session(warm_api_cache))

    # 5. Spot-check prediction quality
    async def validate_predictions(session):
        result = await session.execute(
            select(Prediction)
            .where(Prediction.as_of_ts >= datetime.combine(today, time.min))
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

    await run_step("validate_predictions", with_session(validate_predictions))

    return failed


def main():
    failed = asyncio.run(main_async())
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
