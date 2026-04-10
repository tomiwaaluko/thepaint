"""Predictions recap routes — compare yesterday's predictions to actual stats."""
from collections import defaultdict
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import redis.asyncio as aioredis
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from chalk.api.cache import get_cached, set_cached
from chalk.api.dependencies import get_db, get_redis
from chalk.api.schemas_recap import (
    RecapGameEntry,
    RecapPlayerEntry,
    RecapResponse,
    RecapStatComparison,
    RecapSummary,
)
from chalk.db.models import Game, Player, PlayerGameLog, Prediction, Team, TeamGameLog

log = structlog.get_logger()

router = APIRouter(prefix="/v1/games", tags=["recap"])

ET_TZ = ZoneInfo("America/New_York")

ALL_STATS = ["pts", "reb", "ast", "fg3m", "stl", "blk", "to_committed"]
STAT_LABELS = {"fg3m": "3PM", "to_committed": "TO"}

RECAP_CACHE_TTL = 3600  # 1 hour — historical recaps are immutable


def _grade(actual: int | None, p10: float, p25: float, p75: float, p90: float) -> str:
    """Grade a prediction: hit (IQR), close (p10-p90), or miss."""
    if actual is None:
        return "miss"
    if p25 <= actual <= p75:
        return "hit"
    if p10 <= actual <= p90:
        return "close"
    return "miss"


@router.get("/recap", response_model=RecapResponse)
async def get_recap(
    recap_date: date | None = Query(None, alias="date", description="Date to recap (defaults to yesterday ET)"),
    session: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> RecapResponse:
    """Compare predictions to actual stats for a given date."""
    now_et = datetime.now(ET_TZ)
    target_date = recap_date or (now_et.date() - timedelta(days=1))

    if target_date > now_et.date():
        raise HTTPException(status_code=400, detail="Cannot recap future dates")

    # Check cache
    cache_key = f"recap:{target_date}"
    cached = await get_cached(redis, cache_key, RecapResponse)
    if cached:
        return cached

    # Single query: predictions joined with actuals
    result = await session.execute(
        select(
            Prediction.game_id,
            Prediction.player_id,
            Prediction.stat,
            Prediction.p10,
            Prediction.p25,
            Prediction.p50,
            Prediction.p75,
            Prediction.p90,
            PlayerGameLog.pts,
            PlayerGameLog.reb,
            PlayerGameLog.ast,
            PlayerGameLog.fg3m,
            PlayerGameLog.stl,
            PlayerGameLog.blk,
            PlayerGameLog.to_committed,
            Player.name.label("player_name"),
            Player.position,
            Team.abbreviation.label("team_abbr"),
        )
        .join(
            PlayerGameLog,
            and_(
                Prediction.game_id == PlayerGameLog.game_id,
                Prediction.player_id == PlayerGameLog.player_id,
            ),
        )
        .join(Player, Prediction.player_id == Player.player_id)
        .join(Team, PlayerGameLog.team_id == Team.team_id)
        .join(Game, Prediction.game_id == Game.game_id)
        .where(Game.date == target_date)
        .where(Prediction.stat.in_(ALL_STATS))
    )
    rows = result.all()

    if not rows:
        empty = RecapResponse(
            date=target_date,
            summary=RecapSummary(
                total_predictions=0,
                hit_rate=0.0,
                close_rate=0.0,
                miss_rate=0.0,
                mae_by_stat={},
                overall_mae=0.0,
            ),
            games=[],
        )
        return empty

    # Group by game_id → player_id → list of stat rows
    game_player_stats: dict[str, dict[int, list]] = defaultdict(lambda: defaultdict(list))
    player_info: dict[int, tuple[str, str, str]] = {}  # player_id → (name, position, team_abbr)

    for row in rows:
        game_id = row.game_id
        pid = row.player_id
        stat = row.stat
        actual = getattr(row, stat, None)
        if actual is None:
            continue
        grade = _grade(actual, row.p10, row.p25, row.p75, row.p90)

        game_player_stats[game_id][pid].append(
            RecapStatComparison(
                stat=stat,
                predicted=round(row.p50, 1),
                actual=actual,
                p10=round(row.p10, 1),
                p25=round(row.p25, 1),
                p75=round(row.p75, 1),
                p90=round(row.p90, 1),
                error=round(abs(actual - row.p50), 1),
                grade=grade,
            )
        )

        if pid not in player_info:
            player_info[pid] = (row.player_name, row.position, row.team_abbr)

    # Load game and score info
    game_ids = list(game_player_stats.keys())
    games_result = await session.execute(
        select(Game).where(Game.game_id.in_(game_ids))
    )
    games_by_id: dict[str, Game] = {g.game_id: g for g in games_result.scalars().all()}

    # Team scores from team_game_logs
    team_scores: dict[str, dict[int, int]] = defaultdict(dict)  # game_id → {team_id: pts}
    scores_result = await session.execute(
        select(TeamGameLog.game_id, TeamGameLog.team_id, TeamGameLog.pts)
        .where(TeamGameLog.game_id.in_(game_ids))
    )
    for score_row in scores_result.all():
        team_scores[score_row.game_id][score_row.team_id] = score_row.pts

    # Team abbreviations
    all_team_ids: set[int] = set()
    for g in games_by_id.values():
        all_team_ids.add(g.home_team_id)
        all_team_ids.add(g.away_team_id)
    teams_result = await session.execute(
        select(Team).where(Team.team_id.in_(all_team_ids))
    )
    teams_by_id: dict[int, Team] = {t.team_id: t for t in teams_result.scalars().all()}

    # Build response
    all_grades: list[str] = []
    all_errors: list[float] = []
    errors_by_stat: dict[str, list[float]] = defaultdict(list)
    game_entries: list[RecapGameEntry] = []

    for game_id, players_map in game_player_stats.items():
        game = games_by_id.get(game_id)
        if not game:
            continue

        home_abbr = teams_by_id[game.home_team_id].abbreviation if game.home_team_id in teams_by_id else "UNK"
        away_abbr = teams_by_id[game.away_team_id].abbreviation if game.away_team_id in teams_by_id else "UNK"
        home_score = team_scores.get(game_id, {}).get(game.home_team_id)
        away_score = team_scores.get(game_id, {}).get(game.away_team_id)

        game_grades: list[str] = []
        game_errors: list[float] = []
        player_entries: list[RecapPlayerEntry] = []

        for pid, stat_comps in players_map.items():
            name, position, team_abbr = player_info[pid]
            # Sort stats in canonical order
            stat_order = {s: i for i, s in enumerate(ALL_STATS)}
            stat_comps.sort(key=lambda sc: stat_order.get(sc.stat, 99))

            hits = sum(1 for sc in stat_comps if sc.grade == "hit")
            closes = sum(1 for sc in stat_comps if sc.grade == "close")
            misses = sum(1 for sc in stat_comps if sc.grade == "miss")

            for sc in stat_comps:
                game_grades.append(sc.grade)
                game_errors.append(sc.error)
                all_grades.append(sc.grade)
                all_errors.append(sc.error)
                errors_by_stat[sc.stat].append(sc.error)

            player_entries.append(
                RecapPlayerEntry(
                    player_id=pid,
                    player_name=name,
                    team_abbreviation=team_abbr,
                    position=position,
                    stats=stat_comps,
                    hit_count=hits,
                    close_count=closes,
                    miss_count=misses,
                )
            )

        # Sort players by total error descending (worst predictions first? or best first?)
        # Best predictions first is more encouraging
        player_entries.sort(key=lambda p: p.hit_count, reverse=True)

        game_mae = round(sum(game_errors) / len(game_errors), 2) if game_errors else 0.0
        game_hit_rate = round(game_grades.count("hit") / len(game_grades), 3) if game_grades else 0.0

        game_entries.append(
            RecapGameEntry(
                game_id=game_id,
                date=target_date,
                home_team=home_abbr,
                away_team=away_abbr,
                home_score=home_score,
                away_score=away_score,
                players=player_entries,
                game_mae=game_mae,
                game_hit_rate=game_hit_rate,
            )
        )

    # Build summary
    total = len(all_grades)
    summary = RecapSummary(
        total_predictions=total,
        hit_rate=round(all_grades.count("hit") / total, 3) if total else 0.0,
        close_rate=round(all_grades.count("close") / total, 3) if total else 0.0,
        miss_rate=round(all_grades.count("miss") / total, 3) if total else 0.0,
        mae_by_stat={
            stat: round(sum(errs) / len(errs), 2)
            for stat, errs in errors_by_stat.items()
            if errs
        },
        overall_mae=round(sum(all_errors) / len(all_errors), 2) if all_errors else 0.0,
    )

    response = RecapResponse(date=target_date, summary=summary, games=game_entries)
    await set_cached(redis, cache_key, response, ttl=RECAP_CACHE_TTL)
    return response
