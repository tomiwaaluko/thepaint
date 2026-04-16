import asyncio
import hashlib
import json
import random
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

import structlog
from nba_api.stats.endpoints import leaguegamelog, playergamelog, scoreboardv2
from nba_api.stats.static import players as nba_players_static
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from chalk.config import settings
from chalk.db.models import PlayerGameLog, TeamGameLog
from chalk.exceptions import IngestError
from chalk.ingestion.seed import team_id_from_abbr, upsert_games, upsert_player

# Static ID→name lookup for all active + historical players (avoids DB name fallback to ID)
_PLAYER_ID_TO_NAME: dict[int, str] = {
    p["id"]: p["full_name"] for p in nba_players_static.get_players()
}

log = structlog.get_logger()

CACHE_DIR = Path(settings.NBA_API_CACHE_DIR)
MAX_RETRIES = settings.NBA_API_MAX_RETRIES
BASE_DELAY = 2.0
BATCH_SIZE = 500  # asyncpg has 32767 param limit; 500 rows × ~15 cols = safe
REQUEST_TIMEOUT = settings.NBA_API_TIMEOUT

# Browser-like headers required by stats.nba.com.
# stats.nba.com is typically accessed via nba.com links, so Origin/Referer must
# be nba.com (not stats.nba.com). The Sec-Fetch-* headers are required by
# Cloudflare/WAF rules — omitting them causes requests from cloud IPs to hang.
# Do NOT include Host here — it's set automatically by the HTTP library.
NBA_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Encoding": "gzip, deflate, br",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
    "Origin": "https://www.nba.com",
    "Referer": "https://www.nba.com/",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-site",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/121.0.0.0 Safari/537.36"
    ),
    "x-nba-stats-origin": "stats",
    "x-nba-stats-token": "true",
}

# Optional proxy for bypassing IP-based blocks (configure via NBA_PROXY_URL env var).
# Format: "http://user:pass@host:port" — leave blank to disable.
_NBA_PROXY: str | None = settings.NBA_PROXY_URL or None


def _cache_path(endpoint: str, params: dict) -> Path:
    # Sanitize endpoint name to prevent path traversal — keep only alphanumerics/underscores
    safe_endpoint = "".join(c for c in endpoint if c.isalnum() or c == "_")
    key = hashlib.md5(f"{safe_endpoint}{sorted(params.items())}".encode()).hexdigest()
    return CACHE_DIR / safe_endpoint / f"{key}.json"


async def _fetch_with_backoff(endpoint_cls, params: dict, endpoint_name: str) -> dict:
    """Call nba_api with exponential backoff + disk caching."""
    cache_file = _cache_path(endpoint_name, params)
    cache_file.parent.mkdir(parents=True, exist_ok=True)

    if cache_file.exists():
        log.debug("cache_hit", endpoint=endpoint_name, params=params)
        return json.loads(cache_file.read_text())

    for attempt in range(MAX_RETRIES):
        # Small jitter before every request to avoid thundering-herd on retries
        await asyncio.sleep(random.uniform(0.5, 1.5))
        try:
            loop = asyncio.get_event_loop()
            kwargs: dict = {"headers": NBA_HEADERS, "timeout": REQUEST_TIMEOUT}
            if _NBA_PROXY:
                kwargs["proxy"] = _NBA_PROXY
            _params = params  # capture for lambda closure
            _kwargs = kwargs
            endpoint = await loop.run_in_executor(
                None,
                lambda: endpoint_cls(**_params, **_kwargs),
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


def _season_from_date(d: date) -> str:
    """Derive NBA season string from a date. NBA season starts in October."""
    year = d.year if d.month >= 10 else d.year - 1
    return f"{year}-{str(year + 1)[-2:]}"


def _is_playoff_game_id(game_id: str) -> bool:
    """Detect playoff game from NBA game ID prefix.

    NBA game IDs: ``00 2 SSNNNN`` = regular season, ``00 4 SSNNNN`` = playoffs.
    The third character (index 2) is the season-type digit.
    """
    return len(game_id) >= 3 and game_id[2] == "4"


async def _fetch_scoreboard_cdn(game_date: date) -> list[dict]:
    """Fallback: fetch today's scoreboard from the NBA CDN (no auth/bot detection).

    Returns a list of dicts with keys: GAME_ID, HOME_TEAM_ID, VISITOR_TEAM_ID.
    Only works for today's games (the CDN always serves the current day's slate).
    """
    cdn_url = "https://cdn.nba.com/static/json/liveData/scoreboard/todaysScoreboard_00.json"
    loop = asyncio.get_event_loop()

    def _do_fetch() -> list[dict]:
        req = urllib.request.Request(cdn_url, headers={"User-Agent": NBA_HEADERS["User-Agent"]})
        with urllib.request.urlopen(req, timeout=10) as resp:
            payload = json.loads(resp.read().decode())
        games_raw = payload.get("scoreboard", {}).get("games", [])
        results: list[dict] = []
        for g in games_raw:
            results.append({
                "GAME_ID": g["gameId"],
                "HOME_TEAM_ID": g["homeTeam"]["teamId"],
                "VISITOR_TEAM_ID": g["awayTeam"]["teamId"],
            })
        return results

    return await loop.run_in_executor(None, _do_fetch)


async def ingest_today_scoreboard(session: AsyncSession, game_date: date) -> int:
    """Fetch games from NBA ScoreboardV2 for the given date and upsert into games table.

    This is used as a fallback when today's games haven't been ingested yet by the
    daily Airflow DAG. It creates game records so the dashboard can show the slate.
    Falls back to the NBA CDN if ScoreboardV2 times out.
    """
    date_str = game_date.strftime("%m/%d/%Y")
    loop = asyncio.get_event_loop()
    headers_list: list[dict] | None = None

    # Primary path: ScoreboardV2 API
    try:
        _sb_kwargs: dict = {"headers": NBA_HEADERS, "timeout": REQUEST_TIMEOUT}
        if _NBA_PROXY:
            _sb_kwargs["proxy"] = _NBA_PROXY
        board = await loop.run_in_executor(
            None, lambda: scoreboardv2.ScoreboardV2(game_date=date_str, **_sb_kwargs)
        )
        data = board.get_normalized_dict()
        headers_list = data.get("GameHeader", [])
    except Exception as e:
        log.warning("scoreboard_fetch_failed", date=date_str, error=str(e))

    # CDN fallback when ScoreboardV2 fails or returns empty
    if not headers_list:
        try:
            cdn_games = await _fetch_scoreboard_cdn(game_date)
            if cdn_games:
                headers_list = cdn_games
                log.info("scoreboard_cdn_fallback_used", date=date_str, games=len(cdn_games))
        except Exception as cdn_err:
            log.warning("scoreboard_cdn_fallback_failed", date=date_str, error=str(cdn_err))

    if not headers_list:
        return 0

    season = _season_from_date(game_date)
    game_rows: list[dict] = []
    seen: set[str] = set()
    for g in headers_list:
        gid = g["GAME_ID"]
        if gid in seen:
            continue
        seen.add(gid)
        game_rows.append({
            "game_id": gid,
            "date": game_date,
            "season": season,
            "home_team_id": g["HOME_TEAM_ID"],
            "away_team_id": g["VISITOR_TEAM_ID"],
            "is_playoffs": _is_playoff_game_id(gid),
        })

    if game_rows:
        await upsert_games(session, game_rows)
        await session.commit()
        log.info("scoreboard_ingested", date=date_str, games=len(game_rows))

    return len(game_rows)


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
    """Ingest all game logs for a player-season. Returns rows upserted.

    Fetches both Regular Season and Playoffs so that playoff game logs are
    ingested alongside regular-season data.
    """
    # Fetch regular season
    reg_data = await _fetch_with_backoff(
        playergamelog.PlayerGameLog,
        {"player_id": player_id, "season": season, "season_type_all_star": "Regular Season"},
        endpoint_name="PlayerGameLog",
    )
    entries = list(reg_data.get("PlayerGameLog", []))

    # Fetch playoffs (may be empty during regular season — that's fine)
    try:
        playoff_data = await _fetch_with_backoff(
            playergamelog.PlayerGameLog,
            {"player_id": player_id, "season": season, "season_type_all_star": "Playoffs"},
            endpoint_name="PlayerGameLog_Playoffs",
        )
        entries.extend(playoff_data.get("PlayerGameLog", []))
    except Exception:
        # Playoff data may not exist yet — don't fail the whole ingest
        log.debug("playoff_gamelog_fetch_skipped", player_id=player_id, season=season)

    if not entries:
        return 0

    # Resolve team_id from matchup of first entry if not provided
    first_matchup = entries[0].get("MATCHUP", "")
    first_team_abbr, _, _ = _parse_matchup(first_matchup)
    effective_team_id = team_id if team_id > 0 else team_id_from_abbr(first_team_abbr)

    # Upsert the player record (FK: players)
    # Prefer: explicitly passed name → static NBA lookup → numeric ID as last resort
    effective_name = player_name or _PLAYER_ID_TO_NAME.get(player_id, "") or str(player_id)
    await upsert_player(session, player_id, effective_name, effective_team_id)

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
                "is_playoffs": _is_playoff_game_id(game_id),
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
    """Ingest team game logs for an entire season (regular + playoffs). Returns rows upserted."""
    # Fetch regular season
    reg_data = await _fetch_with_backoff(
        leaguegamelog.LeagueGameLog,
        {"season": season, "player_or_team_abbreviation": "T", "season_type_all_star": "Regular Season"},
        endpoint_name="LeagueGameLog_Teams",
    )
    entries = list(reg_data.get("LeagueGameLog", []))

    # Fetch playoffs
    try:
        playoff_data = await _fetch_with_backoff(
            leaguegamelog.LeagueGameLog,
            {"season": season, "player_or_team_abbreviation": "T", "season_type_all_star": "Playoffs"},
            endpoint_name="LeagueGameLog_Teams_Playoffs",
        )
        entries.extend(playoff_data.get("LeagueGameLog", []))
    except Exception:
        log.debug("playoff_team_gamelog_fetch_skipped", season=season)

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
            "is_playoffs": _is_playoff_game_id(gid),
        })

    # Upsert games first, then team logs
    await upsert_games(session, game_rows)
    await session.commit()
    return await upsert_team_game_logs(session, rows)
