"""MLB StatsAPI ingestion — teams, schedule, and per-game batter/pitcher logs.

Source: https://statsapi.mlb.com/api/v1 (official, keyless, JSON). Calls go
through the single `_fetch_json` seam, which adds disk caching and exponential
backoff and raises `IngestError` on permanent failure. All writes are upserts.

Ordering contract: `ingest_mlb_boxscore` requires the game's `mlb_games` row to
exist (it supplies game_date/season), so schedule ingestion must run first —
`ingest_mlb_date` and the backfill runner do this. Team/player rows are
stub-upserted opportunistically from every payload so log writes are FK-safe;
full team metadata comes from `ingest_mlb_teams`.
"""
import asyncio
import hashlib
import json
import random
from datetime import date, datetime, timezone
from pathlib import Path

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from chalk.config import settings
from chalk.exceptions import IngestError
from chalk.mlb.models import (
    MlbBatterGameLog,
    MlbGame,
    MlbPitcherGameLog,
    MlbPlayer,
    MlbTeam,
)

log = structlog.get_logger()

MLB_API_BASE = "https://statsapi.mlb.com/api/v1"
CACHE_DIR: Path = settings.MLB_API_CACHE_DIR
REQUEST_TIMEOUT = settings.MLB_API_TIMEOUT
# Total attempts (not additional retries); floor of 1 so a misconfigured 0
# still makes one request instead of failing without ever fetching.
MAX_RETRIES = max(1, settings.MLB_API_MAX_RETRIES)
BASE_DELAY = 2.0

# F/D/L/W = postseason rounds; R = regular season. Spring training (S),
# exhibition (E), and All-Star (A) games are never ingested.
POSTSEASON_GAME_TYPES = {"F", "D", "L", "W"}
INGESTED_GAME_TYPES = POSTSEASON_GAME_TYPES | {"R"}

# detailedState prefixes that mean the game is over and has a final boxscore.
_FINAL_STATUS_PREFIXES = ("Final", "Game Over", "Completed")


def _cache_path(path: str, params: dict) -> Path:
    # Sanitize path segments to prevent traversal — keep only alphanumerics/underscores
    safe = "".join(c for c in path if c.isalnum() or c == "_")
    # Non-cryptographic use: md5 only derives a stable cache filename.
    key = hashlib.md5(
        f"{safe}{sorted(params.items())}".encode(), usedforsecurity=False
    ).hexdigest()
    return CACHE_DIR / safe / f"{key}.json"


async def _http_get_json(url: str, params: dict) -> dict:
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()


async def _fetch_json(path: str, params: dict | None = None, use_cache: bool = True) -> dict:
    """GET a StatsAPI path with disk caching and exponential backoff.

    Pass use_cache=False for volatile requests (e.g. today's schedule while
    games are live) so stale statuses are never served or persisted.
    """
    params = params or {}
    cache_file = _cache_path(path, params)
    if use_cache and cache_file.exists():
        log.debug("mlb_cache_hit", path=path, params=params)
        return json.loads(cache_file.read_text())

    url = f"{MLB_API_BASE}/{path}"
    for attempt in range(MAX_RETRIES):
        try:
            data = await _http_get_json(url, params)
            if use_cache:
                cache_file.parent.mkdir(parents=True, exist_ok=True)
                cache_file.write_text(json.dumps(data))
            log.info("mlb_fetch_success", path=path, attempt=attempt)
            return data
        # Transient classes only (network/HTTP via httpx, OS-level socket
        # errors, bad JSON bodies); programming errors fail fast instead of
        # burning MAX_RETRIES backoff cycles.
        except (httpx.HTTPError, OSError, ValueError) as exc:
            delay = BASE_DELAY * (2**attempt) + random.uniform(0, 1)  # noqa: S311 — jitter, not crypto
            log.warning(
                "mlb_fetch_retry", path=path,
                attempt=attempt, error=str(exc), delay=delay,
            )
            if attempt == MAX_RETRIES - 1:
                raise IngestError(
                    f"Permanent failure: MLB StatsAPI {path} after {MAX_RETRIES} attempts"
                ) from exc
            await asyncio.sleep(delay)

    # Unreachable, but satisfies type checkers
    raise IngestError(f"Permanent failure: MLB StatsAPI {path}")  # pragma: no cover


def _safe_int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


async def ingest_mlb_teams(session: AsyncSession, season: int) -> int:
    """Upsert all MLB teams for a season. Returns the number of teams."""
    data = await _fetch_json("teams", {"sportId": 1, "season": season})
    rows = [
        {
            "team_id": t["id"],
            "name": t["name"],
            "abbreviation": t.get("abbreviation", ""),
            "league": (t.get("league") or {}).get("name", ""),
            "division": (t.get("division") or {}).get("name", ""),
            "venue": (t.get("venue") or {}).get("name"),
            "city": t.get("locationName", ""),
        }
        for t in data.get("teams", [])
    ]
    if not rows:
        return 0

    stmt = pg_insert(MlbTeam).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["team_id"],
        set_={
            "name": stmt.excluded.name,
            "abbreviation": stmt.excluded.abbreviation,
            "league": stmt.excluded.league,
            "division": stmt.excluded.division,
            "venue": stmt.excluded.venue,
            "city": stmt.excluded.city,
        },
    )
    await session.execute(stmt)
    await session.commit()
    log.info("mlb_teams_ingested", season=season, count=len(rows))
    return len(rows)


async def _upsert_stub_teams(session: AsyncSession, teams: list[dict]) -> None:
    """FK-safety net: insert minimal team rows, never overwrite full metadata."""
    rows = [
        {
            "team_id": t["id"],
            "name": t.get("name", ""),
            "abbreviation": t.get("abbreviation", ""),
        }
        for t in teams
    ]
    if rows:
        stmt = pg_insert(MlbTeam).values(rows).on_conflict_do_nothing(
            index_elements=["team_id"]
        )
        await session.execute(stmt)


async def ingest_mlb_schedule(
    session: AsyncSession, start_date: date, end_date: date, use_cache: bool = True
) -> int:
    """Upsert games in [start_date, end_date]. Returns games upserted.

    Spring-training/exhibition/All-Star games are filtered out; postseason is
    flagged from gameType. Doubleheader legs are distinct gamePks.
    """
    data = await _fetch_json(
        "schedule",
        {
            "sportId": 1,
            "startDate": start_date.isoformat(),
            "endDate": end_date.isoformat(),
        },
        use_cache=use_cache,
    )

    stub_teams: dict[int, dict] = {}
    # Keyed by game_pk so a gamePk echoed twice in one payload (suspended/
    # resumed games, or a leg repeated across date entries) collapses to a
    # single row — Postgres rejects two rows sharing the ON CONFLICT key in
    # the same statement ("cannot affect row a second time"). Last leg wins.
    games_by_pk: dict[int, dict] = {}
    for day in data.get("dates", []):
        for g in day.get("games", []):
            if g.get("gameType") not in INGESTED_GAME_TYPES:
                continue
            try:
                home = g["teams"]["home"]["team"]
                away = g["teams"]["away"]["team"]
                row = {
                    "game_pk": g["gamePk"],
                    "date": date.fromisoformat(g["officialDate"]),
                    "season": str(g.get("season") or g["officialDate"][:4]),
                    "game_type": g["gameType"],
                    "is_postseason": g["gameType"] in POSTSEASON_GAME_TYPES,
                    "doubleheader": g.get("doubleHeader", "N"),
                    "game_number": g.get("gameNumber", 1),
                    "home_team_id": home["id"],
                    "away_team_id": away["id"],
                    "status": (g.get("status") or {}).get("detailedState", "scheduled"),
                    "abstract_state": (g.get("status") or {}).get("abstractGameState"),
                    "venue": (g.get("venue") or {}).get("name"),
                }
            except (KeyError, ValueError) as exc:
                # One malformed schedule entry must not sink the whole window.
                log.warning(
                    "mlb_schedule_game_malformed",
                    game_pk=g.get("gamePk"), error=str(exc),
                )
                continue
            stub_teams[home["id"]] = home
            stub_teams[away["id"]] = away
            games_by_pk[row["game_pk"]] = row

    games = list(games_by_pk.values())
    if not games:
        log.info("no_mlb_games", start=str(start_date), end=str(end_date))
        return 0

    await _upsert_stub_teams(session, list(stub_teams.values()))
    stmt = pg_insert(MlbGame).values(games)
    stmt = stmt.on_conflict_do_update(
        index_elements=["game_pk"],
        set_={
            "date": stmt.excluded.date,
            "season": stmt.excluded.season,
            "game_type": stmt.excluded.game_type,
            "is_postseason": stmt.excluded.is_postseason,
            "doubleheader": stmt.excluded.doubleheader,
            "game_number": stmt.excluded.game_number,
            "home_team_id": stmt.excluded.home_team_id,
            "away_team_id": stmt.excluded.away_team_id,
            "status": stmt.excluded.status,
            "abstract_state": stmt.excluded.abstract_state,
            "venue": stmt.excluded.venue,
        },
    )
    await session.execute(stmt)
    await session.commit()
    log.info(
        "mlb_schedule_ingested",
        start=str(start_date), end=str(end_date), games=len(games),
    )
    return len(games)


def _iter_boxscore_players(payload: dict):
    """Yield (team_id, player_entry) for both sides of a boxscore.

    Entries without a resolvable person id are skipped here (with a log) so no
    downstream consumer has to guard against them.
    """
    for side in ("away", "home"):
        side_data = (payload.get("teams") or {}).get(side) or {}
        team_id = (side_data.get("team") or {}).get("id")
        for entry in (side_data.get("players") or {}).values():
            if not (entry.get("person") or {}).get("id"):
                log.warning("mlb_boxscore_entry_missing_person", team_id=team_id)
                continue
            yield team_id, entry


def _build_batter_rows(payload: dict, game_date: date, season: str) -> list[dict]:
    """Batter log rows for every player with at least one plate appearance."""
    rows = []
    for team_id, entry in _iter_boxscore_players(payload):
        batting = (entry.get("stats") or {}).get("batting") or {}
        if not batting or _safe_int(batting.get("plateAppearances")) == 0:
            continue
        rows.append(
            {
                "player_id": entry["person"]["id"],
                "team_id": team_id,
                "game_date": game_date,
                "season": season,
                "ab": _safe_int(batting.get("atBats")),
                "r": _safe_int(batting.get("runs")),
                "h": _safe_int(batting.get("hits")),
                "doubles": _safe_int(batting.get("doubles")),
                "triples": _safe_int(batting.get("triples")),
                "hr": _safe_int(batting.get("homeRuns")),
                "rbi": _safe_int(batting.get("rbi")),
                "bb": _safe_int(batting.get("baseOnBalls")),
                "so": _safe_int(batting.get("strikeOuts")),
                "sb": _safe_int(batting.get("stolenBases")),
                "cs": _safe_int(batting.get("caughtStealing")),
                "hbp": _safe_int(batting.get("hitByPitch")),
                "total_bases": _safe_int(batting.get("totalBases")),
                "plate_appearances": _safe_int(batting.get("plateAppearances")),
                "batting_order": entry.get("battingOrder"),
                "position": (entry.get("position") or {}).get("abbreviation", ""),
            }
        )
    return rows


def _build_pitcher_rows(payload: dict, game_date: date, season: str) -> list[dict]:
    """Pitcher log rows for every player who faced a batter or recorded an out."""
    rows = []
    for team_id, entry in _iter_boxscore_players(payload):
        pitching = (entry.get("stats") or {}).get("pitching") or {}
        if not pitching:
            continue
        if _safe_int(pitching.get("battersFaced")) == 0 and _safe_int(pitching.get("outs")) == 0:
            continue
        rows.append(
            {
                "player_id": entry["person"]["id"],
                "team_id": team_id,
                "game_date": game_date,
                "season": season,
                "is_starter": _safe_int(pitching.get("gamesStarted")) > 0,
                "outs_recorded": _safe_int(pitching.get("outs")),
                "h": _safe_int(pitching.get("hits")),
                "r": _safe_int(pitching.get("runs")),
                "er": _safe_int(pitching.get("earnedRuns")),
                "bb": _safe_int(pitching.get("baseOnBalls")),
                "so": _safe_int(pitching.get("strikeOuts")),
                "hr": _safe_int(pitching.get("homeRuns")),
                "batters_faced": _safe_int(pitching.get("battersFaced")),
                "pitches_thrown": _safe_int(pitching.get("numberOfPitches")),
                "win": _safe_int(pitching.get("wins")) > 0,
                "loss": _safe_int(pitching.get("losses")) > 0,
                "save": _safe_int(pitching.get("saves")) > 0,
                "hold": _safe_int(pitching.get("holds")) > 0,
            }
        )
    return rows


async def _upsert_players(session: AsyncSession, payload: dict) -> int:
    """Opportunistically upsert every player appearing in a boxscore."""
    rows = [
        {
            "player_id": entry["person"]["id"],
            "name": entry["person"].get("fullName", ""),
            "team_id": team_id,
            "position": (entry.get("position") or {}).get("abbreviation", ""),
        }
        for team_id, entry in _iter_boxscore_players(payload)
    ]
    if not rows:
        return 0

    stmt = pg_insert(MlbPlayer).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["player_id"],
        set_={
            "name": stmt.excluded.name,
            # Last-seen team wins (players change teams mid-season).
            "team_id": stmt.excluded.team_id,
            "position": stmt.excluded.position,
        },
    )
    await session.execute(stmt)
    return len(rows)


async def _upsert_log_rows(session: AsyncSession, model, rows: list[dict]) -> int:
    if not rows:
        return 0
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    stmt = pg_insert(model).values(rows)
    update_cols = {
        c: getattr(stmt.excluded, c)
        for c in rows[0]
        if c not in ("game_pk", "player_id")
    }
    update_cols["updated_at"] = now
    stmt = stmt.on_conflict_do_update(
        index_elements=["game_pk", "player_id"], set_=update_cols
    )
    await session.execute(stmt)
    return len(rows)


async def ingest_mlb_boxscore(
    session: AsyncSession, game_pk: int, use_cache: bool = True
) -> tuple[int, int]:
    """Ingest one game's batter + pitcher logs. Returns (batter_rows, pitcher_rows).

    The game's `mlb_games` row must already exist (schedule ingest supplies the
    game_date/season the log rows carry). Pass use_cache=False when official
    scorer corrections may still land (the daily cron does), so re-ingests
    reconcile instead of replaying a stale cached payload forever.
    """
    game = (
        await session.execute(select(MlbGame).where(MlbGame.game_pk == game_pk))
    ).scalar_one_or_none()
    if game is None:
        log.error("mlb_game_not_found", game_pk=game_pk)
        raise IngestError(
            f"mlb_games row missing for game_pk={game_pk}; run schedule ingest first"
        )

    payload = await _fetch_json(f"game/{game_pk}/boxscore", use_cache=use_cache)

    side_teams = [
        (payload.get("teams") or {}).get(side, {}).get("team", {})
        for side in ("away", "home")
    ]
    await _upsert_stub_teams(session, [t for t in side_teams if t.get("id")])
    await _upsert_players(session, payload)

    batter_rows = _build_batter_rows(payload, game.date, game.season)
    pitcher_rows = _build_pitcher_rows(payload, game.date, game.season)
    for row in batter_rows + pitcher_rows:
        row["game_pk"] = game_pk

    batters = await _upsert_log_rows(session, MlbBatterGameLog, batter_rows)
    pitchers = await _upsert_log_rows(session, MlbPitcherGameLog, pitcher_rows)
    await session.commit()
    log.info("mlb_boxscore_ingested", game_pk=game_pk, batters=batters, pitchers=pitchers)
    return batters, pitchers


def is_final_status(status: str) -> bool:
    """Prefix fallback for rows that predate the abstract_state column."""
    return status.startswith(_FINAL_STATUS_PREFIXES)


def game_is_final(game: MlbGame) -> bool:
    """True when a game is over and its boxscore is authoritative.

    Prefers the upstream abstractGameState enum (Preview/Live/Final), which
    also covers oddball detailedStates like forfeits; falls back to the
    detailedState prefix check when abstract_state was never captured.
    """
    if game.abstract_state:
        return game.abstract_state == "Final"
    return is_final_status(game.status)


async def ingest_mlb_date(session: AsyncSession, game_date: date) -> dict[str, int]:
    """Schedule + boxscores for one date (the daily-cron unit of work).

    Uncached schedule fetch so live statuses are never stale. Only games whose
    status is final get boxscores; a no-games day returns zeros without error.
    """
    games = await ingest_mlb_schedule(session, game_date, game_date, use_cache=False)
    summary = {"games": games, "batter_rows": 0, "pitcher_rows": 0, "failed_games": 0}
    if games == 0:
        return summary

    rows = (
        await session.execute(select(MlbGame).where(MlbGame.date == game_date))
    ).scalars().all()
    for game in rows:
        if not game_is_final(game):
            log.info("mlb_game_not_final_skipped", game_pk=game.game_pk, status=game.status)
            continue
        try:
            batters, pitchers = await ingest_mlb_boxscore(
                session, game.game_pk, use_cache=False
            )
        except IngestError as exc:
            # One bad boxscore must not sink the rest of the day's games.
            summary["failed_games"] += 1
            log.error("mlb_boxscore_failed", game_pk=game.game_pk, error=str(exc))
            continue
        summary["batter_rows"] += batters
        summary["pitcher_rows"] += pitchers
    return summary
