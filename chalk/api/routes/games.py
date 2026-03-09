"""Game prediction routes."""
import asyncio
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import redis.asyncio as aioredis
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from chalk.api.cache import get_cached, set_cached
from chalk.api.dependencies import get_db, get_redis
from chalk.api.schemas import (
    GamePredictionResponse,
    GameSummary,
    PlayerPredictionResponse,
    TodayGamesResponse,
)
from chalk.db.models import Game, Player, PlayerGameLog, Team
from chalk.exceptions import PredictionError
from chalk.ingestion.nba_fetcher import ingest_today_scoreboard
from chalk.predictions.player import predict_player

log = structlog.get_logger()

router = APIRouter(prefix="/v1/games", tags=["games"])

ET_TZ = ZoneInfo("America/New_York")


@router.get("/today", response_model=TodayGamesResponse)
async def get_today_games(
    session: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> TodayGamesResponse:
    """Return today's games (or tomorrow's if none today or after 11 PM ET)."""
    now_et = datetime.now(ET_TZ)
    today = now_et.date()
    tomorrow = today + timedelta(days=1)

    cache_key = f"games:today:{today}:{now_et.hour >= 23}"
    cached = await get_cached(redis, cache_key, TodayGamesResponse)
    if cached:
        return cached

    result = await session.execute(
        select(Game).where(Game.date == today).order_by(Game.game_id)
    )
    today_games = result.scalars().all()

    # If no games for today in DB, try fetching from NBA API
    if not today_games:
        try:
            count = await ingest_today_scoreboard(session, today)
            if count > 0:
                result = await session.execute(
                    select(Game).where(Game.date == today).order_by(Game.game_id)
                )
                today_games = result.scalars().all()
        except Exception as e:
            log.warning("auto_ingest_today_failed", error=str(e))

    result = await session.execute(
        select(Game).where(Game.date == tomorrow).order_by(Game.game_id)
    )
    tomorrow_games = result.scalars().all()

    if today_games and now_et.hour < 23:
        games, target_date = today_games, today
    elif tomorrow_games:
        games, target_date = tomorrow_games, tomorrow
    elif today_games:
        games, target_date = today_games, today
    else:
        # Fallback: show the most recent date that has games in the DB
        latest_date_result = await session.execute(
            select(func.max(Game.date))
        )
        latest_date = latest_date_result.scalar()
        if latest_date:
            result = await session.execute(
                select(Game).where(Game.date == latest_date).order_by(Game.game_id)
            )
            games = result.scalars().all()
            target_date = latest_date
        else:
            games, target_date = [], today

    summaries: list[GameSummary] = []
    for g in games:
        home_team = await session.get(Team, g.home_team_id)
        away_team = await session.get(Team, g.away_team_id)
        summaries.append(
            GameSummary(
                game_id=g.game_id,
                date=g.date,
                home_team_id=g.home_team_id,
                away_team_id=g.away_team_id,
                home_team=home_team.abbreviation if home_team else "UNK",
                away_team=away_team.abbreviation if away_team else "UNK",
                status=g.status,
            )
        )

    response = TodayGamesResponse(date=target_date, games=summaries)
    await set_cached(redis, cache_key, response, ttl=300)
    return response


@router.get("/{game_id}/predict", response_model=GamePredictionResponse)
async def predict_game(
    game_id: str,
    as_of: datetime | None = Query(None, description="Prediction as-of datetime"),
    session: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> GamePredictionResponse:
    cache_key = f"pred:game:{game_id}"
    cached = await get_cached(redis, cache_key, GamePredictionResponse)
    if cached:
        return cached

    # Load game
    result = await session.execute(select(Game).where(Game.game_id == game_id))
    game = result.scalar_one_or_none()
    if not game:
        raise HTTPException(status_code=404, detail=f"Game {game_id} not found")

    as_of_date = as_of.date() if as_of else game.date

    # Get team names
    home_team = await session.get(Team, game.home_team_id)
    away_team = await session.get(Team, game.away_team_id)
    home_name = home_team.abbreviation if home_team else "UNK"
    away_name = away_team.abbreviation if away_team else "UNK"

    # Find players who played in this game (from game logs)
    home_logs = await session.execute(
        select(PlayerGameLog.player_id)
        .where(PlayerGameLog.game_id == game_id)
        .where(PlayerGameLog.team_id == game.home_team_id)
    )
    away_logs = await session.execute(
        select(PlayerGameLog.player_id)
        .where(PlayerGameLog.game_id == game_id)
        .where(PlayerGameLog.team_id == game.away_team_id)
    )
    home_player_ids = [row[0] for row in home_logs.all()]
    away_player_ids = [row[0] for row in away_logs.all()]

    # Fallback for upcoming games: use each team's top rotation from recent logs
    if not home_player_ids:
        home_player_ids = await _get_recent_roster(session, game.home_team_id, as_of_date)
    if not away_player_ids:
        away_player_ids = await _get_recent_roster(session, game.away_team_id, as_of_date)

    # Predict each player (sequentially to avoid session conflicts with async sqlite)
    home_predictions = await _predict_players(session, home_player_ids, game_id, as_of_date)
    away_predictions = await _predict_players(session, away_player_ids, game_id, as_of_date)

    # Estimate total
    home_pts = sum(_get_pts(p) for p in home_predictions)
    away_pts = sum(_get_pts(p) for p in away_predictions)

    response = GamePredictionResponse(
        game_id=game_id,
        home_team=home_name,
        away_team=away_name,
        as_of_ts=datetime(as_of_date.year, as_of_date.month, as_of_date.day),
        predicted_total=round(home_pts + away_pts, 1),
        home_predictions=home_predictions,
        away_predictions=away_predictions,
    )

    # Only cache if we got predictions — don't cache empty results
    if home_predictions or away_predictions:
        await set_cached(redis, cache_key, response)
    return response


async def _get_recent_roster(
    session: AsyncSession, team_id: int, as_of_date: date, limit: int = 12,
) -> list[int]:
    """Find the team's top rotation players from recent game logs (last 30 days)."""
    cutoff = as_of_date - timedelta(days=30)
    result = await session.execute(
        select(PlayerGameLog.player_id)
        .where(PlayerGameLog.team_id == team_id)
        .where(PlayerGameLog.game_date >= cutoff)
        .where(PlayerGameLog.game_date < as_of_date)
        .group_by(PlayerGameLog.player_id)
        .order_by(func.avg(PlayerGameLog.min_played).desc())
        .limit(limit)
    )
    return [row[0] for row in result.all()]


async def _predict_players(
    session: AsyncSession,
    player_ids: list[int],
    game_id: str,
    as_of_date: date,
) -> list[PlayerPredictionResponse]:
    """Predict stats for a list of players, skipping failures."""
    results = []
    for pid in player_ids:
        try:
            pred = await predict_player(session, pid, game_id, as_of_date)
            results.append(pred)
        except Exception as e:
            log.warning("player_prediction_skipped", player_id=pid, error=str(e))
    return results


def _get_pts(pred: PlayerPredictionResponse) -> float:
    """Extract predicted points from a player prediction."""
    for sp in pred.predictions:
        if sp.stat == "pts":
            return sp.p50
    return 0.0
