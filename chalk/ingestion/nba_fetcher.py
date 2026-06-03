import asyncio
import hashlib
import json
import random
import re
import unicodedata
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

import structlog
from nba_api.stats.endpoints import leaguegamelog, playergamelog, scoreboardv2
from nba_api.stats.static import players as nba_players_static
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from chalk.config import settings
from chalk.db.models import Game, Player, PlayerGameLog, TeamGameLog
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
CDN_REQUEST_TIMEOUT = 10
ESPN_SCOREBOARD_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
)
ESPN_SUMMARY_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary"
)
ESPN_TEAM_ABBR_ALIASES = {
    "BKN": "BKN",
    "GS": "GSW",
    "NY": "NYK",
    "NO": "NOP",
    "SA": "SAS",
    "UTAH": "UTA",
    "WSH": "WAS",
}

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


def _is_nba_game_id(game_id: str) -> bool:
    """True for canonical 10-digit NBA stats game IDs (``002…`` / ``004…``)."""
    return len(game_id) == 10 and game_id.isdigit() and game_id.startswith("00")


def _espn_event_is_playoffs(event: dict) -> bool:
    """Detect postseason from ESPN scoreboard event metadata."""
    for season in (
        event.get("season") or {},
        ((event.get("competitions") or [{}])[0]).get("season") or {},
    ):
        season_type = season.get("type")
        if season_type is not None:
            try:
                if int(season_type) == 3:
                    return True
                if int(season_type) == 2:
                    return False
            except (TypeError, ValueError):
                pass
        slug = str(season.get("slug") or "").lower()
        if "post" in slug or "playoff" in slug:
            return True
    return "playoff" in str(event.get("name") or "").lower()


def _parse_espn_scoreboard_events(payload: dict) -> list[dict]:
    """Parse ESPN scoreboard JSON into internal game header dicts."""
    results: list[dict] = []
    for event in payload.get("events", []):
        competition = (event.get("competitions") or [{}])[0]
        competitors = competition.get("competitors") or []
        home = next((c for c in competitors if c.get("homeAway") == "home"), None)
        away = next((c for c in competitors if c.get("homeAway") == "away"), None)
        if not home or not away:
            continue
        home_team_id = _team_id_from_any_abbr(home.get("team", {}).get("abbreviation", ""))
        away_team_id = _team_id_from_any_abbr(away.get("team", {}).get("abbreviation", ""))
        if not home_team_id or not away_team_id:
            continue
        espn_event_id = str(event["id"])
        results.append({
            "GAME_ID": espn_event_id,
            "ESPN_EVENT_ID": espn_event_id,
            "HOME_TEAM_ID": home_team_id,
            "VISITOR_TEAM_ID": away_team_id,
            "IS_PLAYOFFS": _espn_event_is_playoffs(event),
            "STATUS": competition.get("status", {}).get("type", {}).get("description", "scheduled"),
        })
    return results


async def _nba_game_id_for_matchup(
    session: AsyncSession,
    game_date: date,
    home_team_id: int,
    away_team_id: int,
) -> str | None:
    """Return an existing NBA-format game_id for this matchup, if already ingested."""
    result = await session.execute(
        select(Game.game_id).where(
            Game.date == game_date,
            Game.home_team_id == home_team_id,
            Game.away_team_id == away_team_id,
        )
    )
    for (game_id,) in result.all():
        if _is_nba_game_id(game_id):
            return game_id
    return None


async def _reconcile_espn_scoreboard_games(
    session: AsyncSession,
    game_date: date,
    espn_games: list[dict],
) -> list[dict]:
    """Prefer NBA game IDs when the same matchup already exists in the DB."""
    reconciled: list[dict] = []
    for g in espn_games:
        nba_id = await _nba_game_id_for_matchup(
            session,
            game_date,
            g["HOME_TEAM_ID"],
            g["VISITOR_TEAM_ID"],
        )
        game_id = nba_id or g["ESPN_EVENT_ID"]
        if nba_id and nba_id != g["ESPN_EVENT_ID"]:
            log.debug(
                "espn_game_id_reconciled",
                espn_event_id=g["ESPN_EVENT_ID"],
                nba_game_id=nba_id,
            )
        reconciled.append({**g, "GAME_ID": game_id})
    return reconciled


def _normalize_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]", "", ascii_only.lower())


def _team_id_from_any_abbr(abbr: str) -> int:
    normalized = ESPN_TEAM_ABBR_ALIASES.get((abbr or "").upper(), (abbr or "").upper())
    return team_id_from_abbr(normalized)


async def _player_lookup_by_name(session: AsyncSession) -> dict[tuple[int, str], int]:
    result = await session.execute(select(Player.player_id, Player.team_id, Player.name))
    return {
        (team_id, _normalize_name(name)): player_id
        for player_id, team_id, name in result.all()
    }


async def _fetch_scoreboard_espn(game_date: date) -> list[dict]:
    """Fetch a date's NBA slate from ESPN as a fallback source."""
    url = f"{ESPN_SCOREBOARD_URL}?dates={game_date:%Y%m%d}&limit=100"
    loop = asyncio.get_event_loop()

    def _do_fetch() -> list[dict]:
        req = urllib.request.Request(url, headers={"User-Agent": NBA_HEADERS["User-Agent"]})
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            payload = json.loads(resp.read().decode())
        return _parse_espn_scoreboard_events(payload)

    return await loop.run_in_executor(None, _do_fetch)


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


async def _fetch_boxscore_cdn(game_id: str) -> dict:
    """Fetch one game boxscore from the NBA CDN."""
    cdn_url = (
        "https://cdn.nba.com/static/json/liveData/boxscore/"
        f"boxscore_{game_id}.json"
    )
    loop = asyncio.get_event_loop()

    def _do_fetch() -> dict:
        req = urllib.request.Request(
            cdn_url,
            headers={"User-Agent": NBA_HEADERS["User-Agent"]},
        )
        with urllib.request.urlopen(req, timeout=CDN_REQUEST_TIMEOUT) as resp:
            return json.loads(resp.read().decode())

    return await loop.run_in_executor(None, _do_fetch)


def _parse_live_minutes(min_val: str | int | float | None) -> float:
    """Convert NBA liveData minutes values such as PT32M14.00S or 32:14."""
    if min_val is None:
        return 0.0
    if isinstance(min_val, (int, float)):
        return float(min_val)

    min_str = str(min_val).strip()
    if not min_str:
        return 0.0

    iso_match = re.fullmatch(r"PT(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?", min_str)
    if iso_match:
        minutes = int(iso_match.group(1) or 0)
        seconds = float(iso_match.group(2) or 0)
        return minutes + seconds / 60

    return _parse_minutes(min_str)


def _safe_int(value) -> int:
    if value in (None, ""):
        return 0
    return int(value)


def _parse_made_attempted(value) -> tuple[int, int]:
    if not value:
        return 0, 0
    made, _, attempted = str(value).partition("-")
    return _safe_int(made), _safe_int(attempted)


def _safe_bool(value) -> bool:
    return value in (True, 1, "1", "true", "True")


def _build_rows_from_live_boxscore(
    payload: dict,
    game_date: date,
    season: str,
) -> tuple[list[dict], list[dict]]:
    """Build TeamGameLog and PlayerGameLog rows from one NBA liveData boxscore."""
    game = payload.get("game", {})
    game_id = game.get("gameId")
    if not game_id:
        return [], []

    team_rows: list[dict] = []
    player_rows: list[dict] = []

    for side in ("homeTeam", "awayTeam"):
        team = game.get(side) or {}
        team_id = team.get("teamId")
        if not team_id:
            continue

        stats = team.get("statistics") or {}
        fga = _safe_int(stats.get("fieldGoalsAttempted"))
        fg3a = _safe_int(stats.get("threePointersAttempted"))

        team_rows.append({
            "game_id": game_id,
            "team_id": team_id,
            "game_date": game_date,
            "season": season,
            "pts": _safe_int(team.get("score") or stats.get("points")),
            "pace": 0.0,
            "off_rtg": 0.0,
            "def_rtg": 0.0,
            "ts_pct": 0.0,
            "ast": _safe_int(stats.get("assists")),
            "to_committed": _safe_int(stats.get("turnovers")),
            "oreb": _safe_int(stats.get("reboundsOffensive")),
            "dreb": _safe_int(stats.get("reboundsDefensive")),
            "fg3a_rate": (fg3a / fga) if fga else 0.0,
        })

        for player in team.get("players") or []:
            player_stats = player.get("statistics") or {}
            minutes = _parse_live_minutes(player_stats.get("minutes"))
            if minutes == 0 and _safe_int(player_stats.get("points")) == 0:
                # Validation should reflect players who logged time, not DNPs.
                continue

            player_id = player.get("personId")
            if not player_id:
                continue

            player_rows.append({
                "game_id": game_id,
                "player_id": player_id,
                "team_id": team_id,
                "game_date": game_date,
                "season": season,
                "min_played": minutes,
                "pts": _safe_int(player_stats.get("points")),
                "reb": _safe_int(player_stats.get("reboundsTotal")),
                "ast": _safe_int(player_stats.get("assists")),
                "stl": _safe_int(player_stats.get("steals")),
                "blk": _safe_int(player_stats.get("blocks")),
                "to_committed": _safe_int(player_stats.get("turnovers")),
                "fg3m": _safe_int(player_stats.get("threePointersMade")),
                "fg3a": _safe_int(player_stats.get("threePointersAttempted")),
                "fgm": _safe_int(player_stats.get("fieldGoalsMade")),
                "fga": _safe_int(player_stats.get("fieldGoalsAttempted")),
                "ftm": _safe_int(player_stats.get("freeThrowsMade")),
                "fta": _safe_int(player_stats.get("freeThrowsAttempted")),
                "plus_minus": _safe_int(player_stats.get("plusMinusPoints")),
                "starter": _safe_bool(player.get("starter")),
            })

    return team_rows, player_rows


async def ingest_game_boxscores_cdn(session: AsyncSession, games) -> tuple[int, int]:
    """Ingest team and player rows for specific games via NBA CDN boxscores."""
    team_rows: list[dict] = []
    player_rows: list[dict] = []

    for game in games:
        try:
            payload = await _fetch_boxscore_cdn(game.game_id)
            game_team_rows, game_player_rows = _build_rows_from_live_boxscore(
                payload,
                game.date,
                game.season,
            )
            team_rows.extend(game_team_rows)
            player_rows.extend(game_player_rows)
        except Exception as exc:
            log.warning("boxscore_cdn_fetch_failed", game_id=game.game_id, error=str(exc))

    for row in player_rows:
        name = _PLAYER_ID_TO_NAME.get(row["player_id"], str(row["player_id"]))
        await upsert_player(session, row["player_id"], name, row["team_id"])

    team_count = await upsert_team_game_logs(session, team_rows)
    player_count = await upsert_player_game_logs(session, player_rows)

    if team_count or player_count:
        log.info(
            "boxscore_cdn_ingested",
            games=len(games),
            team_rows=team_count,
            player_rows=player_count,
        )

    return team_count, player_count


async def _fetch_boxscore_espn(event_id: str) -> dict:
    url = f"{ESPN_SUMMARY_URL}?event={event_id}"
    loop = asyncio.get_event_loop()

    def _do_fetch() -> dict:
        req = urllib.request.Request(url, headers={"User-Agent": NBA_HEADERS["User-Agent"]})
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            return json.loads(resp.read().decode())

    return await loop.run_in_executor(None, _do_fetch)


def _espn_stats_map(entry: dict, keys: list[str]) -> dict[str, str]:
    stats = entry.get("stats") or []
    return {key: stats[i] for i, key in enumerate(keys) if i < len(stats)}


def _build_rows_from_espn_boxscore(
    payload: dict,
    game_id: str,
    game_date: date,
    season: str,
    lookup: dict[tuple[int, str], int],
) -> tuple[list[dict], list[dict]]:
    boxscore = payload.get("boxscore", {})
    team_rows: list[dict] = []
    player_rows: list[dict] = []

    team_totals_by_abbr: dict[str, dict[str, int | float]] = {}
    for team in boxscore.get("teams", []):
        abbr = team.get("team", {}).get("abbreviation", "")
        stats = {s.get("name"): s.get("displayValue") for s in team.get("statistics", [])}
        fgm = _safe_int(stats.get("fieldGoalsMade"))
        fga = _safe_int(stats.get("fieldGoalsAttempted"))
        fg3a = _safe_int(stats.get("threePointFieldGoalsAttempted"))
        team_totals_by_abbr[abbr] = {
            "pts": _safe_int(stats.get("points")),
            "ast": _safe_int(stats.get("assists")),
            "reb": _safe_int(stats.get("rebounds")),
            "to_committed": _safe_int(stats.get("turnovers")),
            "fg3a_rate": (fg3a / fga) if fga else 0.0,
            "ts_pct": (fgm / fga) if fga else 0.0,
        }

    for team_box in boxscore.get("players", []):
        team_info = team_box.get("team", {})
        team_abbr = team_info.get("abbreviation", "")
        team_id = _team_id_from_any_abbr(team_abbr)
        if not team_id:
            continue

        totals = team_totals_by_abbr.get(team_abbr, {})
        team_rows.append({
            "game_id": game_id,
            "team_id": team_id,
            "game_date": game_date,
            "season": season,
            "pts": _safe_int(totals.get("pts")),
            "pace": 0.0,
            "off_rtg": 0.0,
            "def_rtg": 0.0,
            "ts_pct": float(totals.get("ts_pct") or 0.0),
            "ast": _safe_int(totals.get("ast")),
            "to_committed": _safe_int(totals.get("to_committed")),
            "oreb": 0,
            "dreb": _safe_int(totals.get("reb")),
            "fg3a_rate": float(totals.get("fg3a_rate") or 0.0),
        })

        for group in team_box.get("statistics", []):
            keys = group.get("keys") or []
            athletes = group.get("athletes") or []
            for idx, entry in enumerate(athletes):
                athlete = entry.get("athlete") or {}
                name = athlete.get("displayName", "")
                player_id = lookup.get((team_id, _normalize_name(name)))
                if not player_id:
                    log.warning("espn_player_unmapped", name=name, team_id=team_id)
                    continue
                stats = _espn_stats_map(entry, keys)
                minutes = _parse_minutes(stats.get("minutes"))
                if minutes <= 0:
                    continue
                fgm, fga = _parse_made_attempted(stats.get("fieldGoalsMade-fieldGoalsAttempted"))
                fg3m, fg3a = _parse_made_attempted(stats.get("threePointFieldGoalsMade-threePointFieldGoalsAttempted"))
                ftm, fta = _parse_made_attempted(stats.get("freeThrowsMade-freeThrowsAttempted"))
                player_rows.append({
                    "game_id": game_id,
                    "player_id": player_id,
                    "team_id": team_id,
                    "game_date": game_date,
                    "season": season,
                    "min_played": minutes,
                    "pts": _safe_int(stats.get("points")),
                    "reb": _safe_int(stats.get("rebounds")),
                    "ast": _safe_int(stats.get("assists")),
                    "stl": _safe_int(stats.get("steals")),
                    "blk": _safe_int(stats.get("blocks")),
                    "to_committed": _safe_int(stats.get("turnovers")),
                    "fg3m": fg3m,
                    "fg3a": fg3a,
                    "fgm": fgm,
                    "fga": fga,
                    "ftm": ftm,
                    "fta": fta,
                    "plus_minus": _safe_int(stats.get("plusMinus")),
                    "starter": idx < 5,
                })

    return team_rows, player_rows


async def ingest_game_boxscores_espn(session: AsyncSession, games) -> tuple[int, int]:
    """Ingest team and player rows via ESPN summary API.

    Uses ESPN event IDs for fetch; rows are stored under ``game.game_id`` (NBA ID when
    the matchup was reconciled on scoreboard ingest).
    """
    lookup = await _player_lookup_by_name(session)
    team_rows: list[dict] = []
    player_rows: list[dict] = []

    event_map: dict[tuple[int, int], str] = {}
    if games and any(_is_nba_game_id(g.game_id) for g in games):
        espn_games = await _fetch_scoreboard_espn(games[0].date)
        event_map = {
            (g["HOME_TEAM_ID"], g["VISITOR_TEAM_ID"]): g["ESPN_EVENT_ID"]
            for g in espn_games
        }

    for game in games:
        if _is_nba_game_id(game.game_id):
            event_id = event_map.get((game.home_team_id, game.away_team_id))
            if not event_id:
                log.warning(
                    "boxscore_espn_skipped_nba_game",
                    game_id=game.game_id,
                    home_team_id=game.home_team_id,
                    away_team_id=game.away_team_id,
                )
                continue
        else:
            event_id = game.game_id

        try:
            payload = await _fetch_boxscore_espn(event_id)
            game_team_rows, game_player_rows = _build_rows_from_espn_boxscore(
                payload,
                game.game_id,
                game.date,
                game.season,
                lookup,
            )
            team_rows.extend(game_team_rows)
            player_rows.extend(game_player_rows)
        except Exception as exc:
            log.warning(
                "boxscore_espn_fetch_failed",
                game_id=game.game_id,
                espn_event_id=event_id,
                error=str(exc),
            )

    team_count = await upsert_team_game_logs(session, team_rows)
    player_count = await upsert_player_game_logs(session, player_rows)
    if team_count or player_count:
        log.info(
            "boxscore_espn_ingested",
            games=len(games),
            team_rows=team_count,
            player_rows=player_count,
        )
    return team_count, player_count


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

    # ESPN fallback when NBA endpoints are unavailable from the runtime IP.
    if not headers_list:
        try:
            espn_games = await _fetch_scoreboard_espn(game_date)
            if espn_games:
                headers_list = await _reconcile_espn_scoreboard_games(
                    session,
                    game_date,
                    espn_games,
                )
                log.info("scoreboard_espn_fallback_used", date=date_str, games=len(headers_list))
        except Exception as espn_err:
            log.warning("scoreboard_espn_fallback_failed", date=date_str, error=str(espn_err))

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
            "is_playoffs": bool(g.get("IS_PLAYOFFS")) or _is_playoff_game_id(gid),
            "status": str(g.get("STATUS") or "scheduled").lower(),
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
