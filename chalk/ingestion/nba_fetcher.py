import asyncio
import hashlib
import json
import random
from datetime import UTC, date, datetime
from pathlib import Path

import structlog
from nba_api.stats.endpoints import leaguegamelog, playergamelog
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from chalk.config import settings
from chalk.db.models import PlayerGameLog, TeamGameLog
from chalk.exceptions import IngestError

log = structlog.get_logger()

CACHE_DIR = Path(settings.NBA_API_CACHE_DIR)
MAX_RETRIES = 5
BASE_DELAY = 2.0


def _cache_path(endpoint: str, params: dict) -> Path:
    key = hashlib.md5(f"{endpoint}{sorted(params.items())}".encode()).hexdigest()
    return CACHE_DIR / endpoint / f"{key}.json"


async def _fetch_with_backoff(endpoint_cls, params: dict, endpoint_name: str) -> dict:
    """Call nba_api with exponential backoff + disk caching."""
    cache_file = _cache_path(endpoint_name, params)
    cache_file.parent.mkdir(parents=True, exist_ok=True)

    if cache_file.exists():
        log.debug("cache_hit", endpoint=endpoint_name, params=params)
        return json.loads(cache_file.read_text())

    for attempt in range(MAX_RETRIES):
        try:
            loop = asyncio.get_event_loop()
            endpoint = await loop.run_in_executor(
                None, lambda: endpoint_cls(**params)
            )
            data = endpoint.get_normalized_dict()
            cache_file.write_text(json.dumps(data))
            log.info("fetch_success", endpoint=endpoint_name, attempt=attempt)
            return data
        except Exception as exc:
            delay = BASE_DELAY * (2 ** attempt) + random.uniform(0, 1)
            log.warning(
                "fetch_retry", endpoint=endpoint_name,
                attempt=attempt, error=str(exc), delay=delay,
            )
            if attempt == MAX_RETRIES - 1:
                raise IngestError(
                    f"Permanent failure: {endpoint_name} after {MAX_RETRIES} attempts"
                ) from exc
            await asyncio.sleep(delay)

    # Unreachable, but satisfies type checkers
    raise IngestError(f"Permanent failure: {endpoint_name}")  # pragma: no cover


def _parse_minutes(min_str: str | None) -> float:
    """Convert '32:14' or '32' to 32.23."""
    if not min_str:
        return 0.0
    if ":" in min_str:
        parts = min_str.split(":")
        return int(parts[0]) + int(parts[1]) / 60
    return float(min_str)


async def upsert_player_game_logs(session: AsyncSession, rows: list[dict]) -> int:
    """Upsert player game log rows. Returns count of rows affected."""
    if not rows:
        return 0

    stmt = pg_insert(PlayerGameLog).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["game_id", "player_id"],
        set_={
            "team_id": stmt.excluded.team_id,
            "game_date": stmt.excluded.game_date,
            "season": stmt.excluded.season,
            "min_played": stmt.excluded.min_played,
            "pts": stmt.excluded.pts,
            "reb": stmt.excluded.reb,
            "ast": stmt.excluded.ast,
            "stl": stmt.excluded.stl,
            "blk": stmt.excluded.blk,
            "to_committed": stmt.excluded.to_committed,
            "fg3m": stmt.excluded.fg3m,
            "fg3a": stmt.excluded.fg3a,
            "fgm": stmt.excluded.fgm,
            "fga": stmt.excluded.fga,
            "ftm": stmt.excluded.ftm,
            "fta": stmt.excluded.fta,
            "plus_minus": stmt.excluded.plus_minus,
            "starter": stmt.excluded.starter,
            "updated_at": datetime.now(UTC),
        },
    )
    result = await session.execute(stmt)
    await session.commit()
    return result.rowcount


async def upsert_team_game_logs(session: AsyncSession, rows: list[dict]) -> int:
    """Upsert team game log rows. Returns count of rows affected."""
    if not rows:
        return 0

    stmt = pg_insert(TeamGameLog).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["game_id", "team_id"],
        set_={
            "game_date": stmt.excluded.game_date,
            "season": stmt.excluded.season,
            "pts": stmt.excluded.pts,
            "pace": stmt.excluded.pace,
            "off_rtg": stmt.excluded.off_rtg,
            "def_rtg": stmt.excluded.def_rtg,
            "ts_pct": stmt.excluded.ts_pct,
            "ast": stmt.excluded.ast,
            "to_committed": stmt.excluded.to_committed,
            "oreb": stmt.excluded.oreb,
            "dreb": stmt.excluded.dreb,
            "fg3a_rate": stmt.excluded.fg3a_rate,
        },
    )
    result = await session.execute(stmt)
    await session.commit()
    return result.rowcount


def _parse_matchup(matchup: str) -> tuple[bool, str]:
    """Parse 'LAL vs. GSW' or 'LAL @ GSW' into (is_home, opponent_abbr)."""
    if " vs. " in matchup:
        parts = matchup.split(" vs. ")
        return True, parts[1].strip()
    parts = matchup.split(" @ ")
    return False, parts[1].strip()


async def ingest_player_season(
    session: AsyncSession,
    player_id: int,
    season: str,
    team_id: int = 0,
) -> int:
    """Ingest all game logs for a player-season. Returns rows upserted."""
    data = await _fetch_with_backoff(
        playergamelog.PlayerGameLog,
        {"player_id": player_id, "season": season, "season_type_all_star": "Regular Season"},
        endpoint_name="PlayerGameLog",
    )

    rows = []
    for entry in data.get("PlayerGameLog", []):
        game_date = datetime.strptime(entry["GAME_DATE"], "%b %d, %Y").date()
        is_home, _ = _parse_matchup(entry.get("MATCHUP", ""))
        rows.append({
            "game_id": entry["Game_ID"],
            "player_id": player_id,
            "team_id": team_id or entry.get("TEAM_ID", 0),
            "game_date": game_date,
            "season": season,
            "min_played": _parse_minutes(entry.get("MIN")),
            "pts": entry["PTS"] or 0,
            "reb": entry["REB"] or 0,
            "ast": entry["AST"] or 0,
            "stl": entry["STL"] or 0,
            "blk": entry["BLK"] or 0,
            "to_committed": entry.get("TOV", 0) or 0,
            "fg3m": entry.get("FG3M", 0) or 0,
            "fg3a": entry.get("FG3A", 0) or 0,
            "fgm": entry.get("FGM", 0) or 0,
            "fga": entry.get("FGA", 0) or 0,
            "ftm": entry.get("FTM", 0) or 0,
            "fta": entry.get("FTA", 0) or 0,
            "plus_minus": entry.get("PLUS_MINUS", 0) or 0,
            "starter": False,  # nba_api PlayerGameLog doesn't include starter info
        })

    return await upsert_player_game_logs(session, rows)


async def ingest_team_season(session: AsyncSession, season: str) -> int:
    """Ingest team game logs for an entire season. Returns rows upserted."""
    data = await _fetch_with_backoff(
        leaguegamelog.LeagueGameLog,
        {"season": season, "player_or_team_abbreviation": "T"},
        endpoint_name="LeagueGameLog_Teams",
    )

    rows = []
    for entry in data.get("LeagueGameLog", []):
        game_date_str = entry.get("GAME_DATE", "")
        try:
            game_date = datetime.strptime(game_date_str, "%b %d, %Y").date()
        except ValueError:
            game_date = date.fromisoformat(game_date_str)

        rows.append({
            "game_id": entry["GAME_ID"],
            "team_id": entry["TEAM_ID"],
            "game_date": game_date,
            "season": season,
            "pts": entry.get("PTS", 0) or 0,
            "pace": 0.0,  # Not in LeagueGameLog, computed later
            "off_rtg": 0.0,
            "def_rtg": 0.0,
            "ts_pct": 0.0,
            "ast": entry.get("AST", 0) or 0,
            "to_committed": entry.get("TOV", 0) or 0,
            "oreb": entry.get("OREB", 0) or 0,
            "dreb": entry.get("DREB", 0) or 0,
            "fg3a_rate": 0.0,
        })

    return await upsert_team_game_logs(session, rows)
