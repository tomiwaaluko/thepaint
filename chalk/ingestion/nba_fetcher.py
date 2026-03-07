import asyncio
import hashlib
import json
import random
from datetime import date, datetime, timezone
from pathlib import Path

import structlog
from nba_api.stats.endpoints import leaguegamelog, playergamelog
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from chalk.config import settings
from chalk.db.models import PlayerGameLog, TeamGameLog
from chalk.exceptions import IngestError
from chalk.ingestion.seed import team_id_from_abbr, upsert_games, upsert_player

log = structlog.get_logger()

CACHE_DIR = Path(settings.NBA_API_CACHE_DIR)
MAX_RETRIES = 5
BASE_DELAY = 2.0
BATCH_SIZE = 500  # asyncpg has 32767 param limit; 500 rows × ~15 cols = safe


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


def _parse_minutes(min_val: str | int | float | None) -> float:
    """Convert '32:14' or 32 or 32.5 to float minutes."""
    if min_val is None:
        return 0.0
    if isinstance(min_val, (int, float)):
        return float(min_val)
    min_str = str(min_val).strip()
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

    total = 0
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        stmt = pg_insert(PlayerGameLog).values(batch)
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
                "updated_at": datetime.now(timezone.utc).replace(tzinfo=None),
            },
        )
        result = await session.execute(stmt)
        total += result.rowcount
    await session.commit()
    return total


async def upsert_team_game_logs(session: AsyncSession, rows: list[dict]) -> int:
    """Upsert team game log rows. Returns count of rows affected."""
    if not rows:
        return 0

    total = 0
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        stmt = pg_insert(TeamGameLog).values(batch)
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
        total += result.rowcount
    await session.commit()
    return total


def _parse_matchup(matchup: str) -> tuple[str, str, bool]:
    """Parse 'LAL vs. GSW' or 'LAL @ GSW' into (team_abbr, opponent_abbr, is_home)."""
    if " vs. " in matchup:
        parts = matchup.split(" vs. ")
        return parts[0].strip(), parts[1].strip(), True
    if " @ " in matchup:
        parts = matchup.split(" @ ")
        return parts[0].strip(), parts[1].strip(), False
    return matchup.strip(), "", False


async def ingest_player_season(
    session: AsyncSession,
    player_id: int,
    season: str,
    team_id: int = 0,
    player_name: str = "",
) -> int:
    """Ingest all game logs for a player-season. Returns rows upserted."""
    data = await _fetch_with_backoff(
        playergamelog.PlayerGameLog,
        {"player_id": player_id, "season": season, "season_type_all_star": "Regular Season"},
        endpoint_name="PlayerGameLog",
    )

    entries = data.get("PlayerGameLog", [])
    if not entries:
        return 0

    # Resolve team_id from matchup of first entry if not provided
    first_matchup = entries[0].get("MATCHUP", "")
    first_team_abbr, _, _ = _parse_matchup(first_matchup)
    effective_team_id = team_id if team_id > 0 else team_id_from_abbr(first_team_abbr)

    # Upsert the player record (FK: players)
    await upsert_player(session, player_id, player_name or str(player_id), effective_team_id)

    # Build game records and game log rows
    game_rows = []
    seen_games = set()
    rows = []
    for entry in entries:
        game_date = datetime.strptime(entry["GAME_DATE"], "%b %d, %Y").date()
        game_id = entry["Game_ID"]
        matchup = entry.get("MATCHUP", "")
        team_abbr, opp_abbr, is_home = _parse_matchup(matchup)
        entry_team_id = team_id_from_abbr(team_abbr) or effective_team_id
        opp_team_id = team_id_from_abbr(opp_abbr) or effective_team_id

        # Create game record if we haven't seen this game_id yet
        if game_id not in seen_games:
            seen_games.add(game_id)
            game_rows.append({
                "game_id": game_id,
                "date": game_date,
                "season": season,
                "home_team_id": entry_team_id if is_home else opp_team_id,
                "away_team_id": opp_team_id if is_home else entry_team_id,
            })

        rows.append({
            "game_id": game_id,
            "player_id": player_id,
            "team_id": entry_team_id,
            "game_date": game_date,
            "season": season,
            "min_played": _parse_minutes(entry.get("MIN")),
            "pts": entry.get("PTS") or 0,
            "reb": entry.get("REB") or 0,
            "ast": entry.get("AST") or 0,
            "stl": entry.get("STL") or 0,
            "blk": entry.get("BLK") or 0,
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

    # Upsert game records first (FK: games), then game logs
    await upsert_games(session, game_rows)
    await session.commit()
    return await upsert_player_game_logs(session, rows)


async def ingest_team_season(session: AsyncSession, season: str) -> int:
    """Ingest team game logs for an entire season. Returns rows upserted."""
    data = await _fetch_with_backoff(
        leaguegamelog.LeagueGameLog,
        {"season": season, "player_or_team_abbreviation": "T"},
        endpoint_name="LeagueGameLog_Teams",
    )

    entries = data.get("LeagueGameLog", [])
    if not entries:
        return 0

    # Build game records from team logs (each game appears twice — once per team)
    game_rows = []
    seen_games = {}  # game_id -> {teams seen}
    rows = []

    for entry in entries:
        game_date_str = entry.get("GAME_DATE", "")
        try:
            game_date = datetime.strptime(game_date_str, "%b %d, %Y").date()
        except ValueError:
            game_date = date.fromisoformat(game_date_str)

        game_id = entry["GAME_ID"]
        entry_team_id = entry["TEAM_ID"]
        matchup = entry.get("MATCHUP", "")
        is_home = " vs. " in matchup

        # Track teams per game to build proper home/away game records
        if game_id not in seen_games:
            seen_games[game_id] = {
                "date": game_date, "home": None, "away": None,
            }
        if is_home:
            seen_games[game_id]["home"] = entry_team_id
        else:
            seen_games[game_id]["away"] = entry_team_id

        rows.append({
            "game_id": game_id,
            "team_id": entry_team_id,
            "game_date": game_date,
            "season": season,
            "pts": entry.get("PTS", 0) or 0,
            "pace": 0.0,
            "off_rtg": 0.0,
            "def_rtg": 0.0,
            "ts_pct": 0.0,
            "ast": entry.get("AST", 0) or 0,
            "to_committed": entry.get("TOV", 0) or 0,
            "oreb": entry.get("OREB", 0) or 0,
            "dreb": entry.get("DREB", 0) or 0,
            "fg3a_rate": 0.0,
        })

    # Build game records with proper home/away
    for gid, info in seen_games.items():
        home = info["home"] or (info["away"] or 0)
        away = info["away"] or (info["home"] or 0)
        game_rows.append({
            "game_id": gid,
            "date": info["date"],
            "season": season,
            "home_team_id": home,
            "away_team_id": away,
        })

    # Upsert games first, then team logs
    await upsert_games(session, game_rows)
    await session.commit()
    return await upsert_team_game_logs(session, rows)
