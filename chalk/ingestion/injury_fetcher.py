import re
import unicodedata
from datetime import date
from difflib import SequenceMatcher, get_close_matches
from typing import TypedDict

import httpx
import structlog
from nba_api.stats.static import players as nba_players_static
from nba_api.stats.static import teams as nba_teams_static
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from chalk.db.models import Injury, Player
from chalk.exceptions import IngestError

log = structlog.get_logger()

ESPN_INJURY_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries"
FUZZY_MATCH_CUTOFF = 0.92
SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v", "vi"}

# Persistent known mismatches between source provider strings and player table naming.
PLAYER_NAME_ALIASES: dict[str, str] = {
    "cj mccollum": "c j mccollum",
    "pj washington": "p j washington",
    "tj mcconnell": "t j mcconnell",
}


def _normalize_text(value: str) -> str:
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    ascii_value = ascii_value.replace("-", " ")
    ascii_value = re.sub(r"[^\w\s]", " ", ascii_value.lower())
    ascii_value = re.sub(r"\s+", " ", ascii_value).strip()
    return ascii_value


def _canonical_player_name(name: str) -> str:
    normalized = _normalize_text(name)
    if not normalized:
        return ""
    tokens = normalized.split()
    while tokens and tokens[-1] in SUFFIXES:
        tokens.pop()
    canonical = " ".join(tokens)
    return PLAYER_NAME_ALIASES.get(canonical, canonical)


STATIC_PLAYER_CANONICAL_TO_ID: dict[str, int] = {}
for _player in nba_players_static.get_players():
    _canonical = _canonical_player_name(_player["full_name"])
    if _canonical and _canonical not in STATIC_PLAYER_CANONICAL_TO_ID:
        STATIC_PLAYER_CANONICAL_TO_ID[_canonical] = _player["id"]

TEAM_NAME_TO_ID: dict[str, int] = {}
for _team in nba_teams_static.get_teams():
    _team_id = _team["id"]
    _team_names = {
        _team.get("full_name", ""),
        _team.get("nickname", ""),
        f"{_team.get('city', '')} {_team.get('nickname', '')}".strip(),
    }
    for _name in _team_names:
        _canonical = _normalize_text(_name)
        if _canonical:
            TEAM_NAME_TO_ID[_canonical] = _team_id


class PlayerLookupCache(TypedDict):
    exact: dict[str, int]
    canonical: dict[str, int]
    canonical_names: tuple[str, ...]
    player_ids: set[int]


async def _build_player_lookup(session: AsyncSession) -> PlayerLookupCache:
    result = await session.execute(select(Player.player_id, Player.name))
    rows = result.all()
    exact: dict[str, int] = {}
    canonical: dict[str, int] = {}
    player_ids: set[int] = set()

    for player_id, name in rows:
        exact[name] = player_id
        canonical.setdefault(_canonical_player_name(name), player_id)
        player_ids.add(player_id)

    return {
        "exact": exact,
        "canonical": canonical,
        "canonical_names": tuple(canonical.keys()),
        "player_ids": player_ids,
    }


def _resolve_player_id_from_static(display_name: str) -> int | None:
    canonical_name = _canonical_player_name(display_name)
    if not canonical_name:
        return None

    direct = STATIC_PLAYER_CANONICAL_TO_ID.get(canonical_name)
    if direct is not None:
        return direct

    match = get_close_matches(
        canonical_name,
        STATIC_PLAYER_CANONICAL_TO_ID.keys(),
        n=1,
        cutoff=FUZZY_MATCH_CUTOFF,
    )
    if not match:
        return None
    return STATIC_PLAYER_CANONICAL_TO_ID[match[0]]


async def resolve_player_id(
    session: AsyncSession,
    display_name: str,
    lookup_cache: PlayerLookupCache | None = None,
    *,
    log_missing: bool = True,
) -> int | None:
    """Resolve player_id from display_name using exact, normalized, then fuzzy matching."""
    if not display_name:
        return None

    cache = lookup_cache or await _build_player_lookup(session)
    exact = cache["exact"].get(display_name)
    if exact is not None:
        return exact

    canonical_name = _canonical_player_name(display_name)
    canonical_hit = cache["canonical"].get(canonical_name)
    if canonical_hit is not None:
        log.info(
            "player_name_normalized_match",
            name=display_name,
            canonical_name=canonical_name,
            player_id=canonical_hit,
        )
        return canonical_hit

    fuzzy = get_close_matches(
        canonical_name,
        cache["canonical_names"],
        n=1,
        cutoff=FUZZY_MATCH_CUTOFF,
    )
    if fuzzy:
        matched_name = fuzzy[0]
        player_id = cache["canonical"][matched_name]
        score = SequenceMatcher(a=canonical_name, b=matched_name).ratio()
        log.info(
            "player_name_fuzzy_match",
            name=display_name,
            matched_name=matched_name,
            player_id=player_id,
            score=round(score, 3),
        )
        return player_id

    if log_missing:
        log.warning("player_not_found", name=display_name, canonical_name=canonical_name)
    return None


async def _ensure_player_exists(
    session: AsyncSession,
    player_id: int,
    display_name: str,
    team_name: str,
    lookup_cache: PlayerLookupCache,
) -> bool:
    """Create/update missing player records for successful static-ID fallback resolution."""
    if player_id in lookup_cache["player_ids"]:
        return False

    team_id = TEAM_NAME_TO_ID.get(_normalize_text(team_name))
    if team_id is None:
        log.warning(
            "player_seed_skipped_unknown_team",
            name=display_name,
            player_id=player_id,
            team_name=team_name,
        )
        return False

    stmt = pg_insert(Player).values(
        player_id=player_id,
        name=display_name,
        team_id=team_id,
        position="N/A",
        is_active=True,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["player_id"],
        set_={
            "name": stmt.excluded.name,
            "team_id": stmt.excluded.team_id,
            "is_active": True,
        },
    )
    await session.execute(stmt)

    lookup_cache["player_ids"].add(player_id)
    lookup_cache["exact"][display_name] = player_id
    lookup_cache["canonical"][_canonical_player_name(display_name)] = player_id
    lookup_cache["canonical_names"] = tuple(lookup_cache["canonical"].keys())
    return True


async def upsert_injuries(session: AsyncSession, rows: list[dict]) -> int:
    """Upsert injury rows. Returns count of rows affected."""
    if not rows:
        return 0

    stmt = pg_insert(Injury).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["player_id", "report_date"],
        set_={
            "status": stmt.excluded.status,
            "description": stmt.excluded.description,
            "source": stmt.excluded.source,
        },
    )
    result = await session.execute(stmt)
    await session.commit()
    return result.rowcount


async def ingest_injuries(session: AsyncSession) -> int:
    """Fetch current NBA injuries from ESPN and upsert into DB."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(ESPN_INJURY_URL, timeout=10.0)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as exc:
        raise IngestError(f"Failed to fetch injuries from ESPN: {exc}") from exc

    lookup_cache = await _build_player_lookup(session)
    rows = []
    total_players = 0
    matched_players = 0
    static_resolved = 0
    seeded_players = 0

    for team_entry in data.get("injuries", []):
        team_name = team_entry.get("team", {}).get("displayName", "")
        for injury in team_entry.get("injuries", []):
            athlete = injury.get("athlete", {})
            display_name = athlete.get("displayName", "")
            if not display_name:
                continue

            total_players += 1
            player_id = await resolve_player_id(
                session,
                display_name,
                lookup_cache=lookup_cache,
                log_missing=False,
            )

            if player_id is None:
                static_player_id = _resolve_player_id_from_static(display_name)
                if static_player_id is not None:
                    seeded = await _ensure_player_exists(
                        session,
                        static_player_id,
                        display_name,
                        team_name,
                        lookup_cache,
                    )
                    if seeded:
                        seeded_players += 1
                    player_id = static_player_id
                    static_resolved += 1
                    log.info(
                        "player_resolved_from_static",
                        name=display_name,
                        player_id=player_id,
                        team_name=team_name,
                        seeded=seeded,
                    )

            if player_id is None:
                log.warning(
                    "player_not_found",
                    name=display_name,
                    canonical_name=_canonical_player_name(display_name),
                )
                continue

            matched_players += 1
            rows.append({
                "player_id": player_id,
                "report_date": date.today(),
                "status": injury.get("status", "Unknown"),
                "description": injury.get("details", {}).get("detail", ""),
                "source": "espn",
            })

    written = await upsert_injuries(session, rows)
    match_rate = round((matched_players / total_players), 3) if total_players else 1.0
    log.info(
        "injury_match_summary",
        matched=matched_players,
        total=total_players,
        unmatched=total_players - matched_players,
        match_rate=match_rate,
        resolved_db=matched_players - static_resolved,
        resolved_static=static_resolved,
        players_seeded=seeded_players,
        injuries_written=written,
    )
    return written


async def get_player_status(
    session: AsyncSession, player_id: int, game_date: date
) -> str:
    """Return most recent injury status for a player on or before game_date."""
    result = await session.execute(
        select(Injury.status)
        .where(Injury.player_id == player_id, Injury.report_date <= game_date)
        .order_by(Injury.report_date.desc())
        .limit(1)
    )
    status = result.scalar_one_or_none()
    return status or "Active"
