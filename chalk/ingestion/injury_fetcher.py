from datetime import date, datetime
import re
from functools import lru_cache
import unicodedata

import httpx
import structlog
from nba_api.stats.static import players as nba_static_players
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from chalk.db.models import Injury, Player
from chalk.exceptions import IngestError

log = structlog.get_logger()

ESPN_INJURY_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries"
_SUFFIX_TOKENS = {"jr", "sr", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x"}
_HARDCODED_PLAYER_ID_FALLBACKS = {
    # Newly drafted players that can lag in nba_api's static player list.
    "lj cryer": 1641940,
    "adama bal": 1642380,
}


def _normalize_player_name(name: str) -> str:
    """Normalize player names for resilient matching across punctuation/suffix variants."""
    name = unicodedata.normalize("NFKD", name)
    name = "".join(c for c in name if not unicodedata.combining(c))
    cleaned = re.sub(r"[^a-z0-9\s]", "", name.lower())
    tokens = [token for token in cleaned.split() if token not in _SUFFIX_TOKENS]
    return " ".join(tokens)


@lru_cache(maxsize=1)
def _get_static_player_lookup() -> dict[str, tuple[int, str]]:
    """
    Build a normalized-name -> (player_id, full_name) map from nba_api static players.
    Prefer active players when duplicate normalized names exist.
    """
    lookup: dict[str, tuple[int, str]] = {}
    for player in nba_static_players.get_players():
        normalized = _normalize_player_name(player["full_name"])
        if not normalized:
            continue

        existing = lookup.get(normalized)
        if existing is None or player.get("is_active", False):
            lookup[normalized] = (int(player["id"]), player["full_name"])
    return lookup


async def resolve_player_id(session: AsyncSession, display_name: str) -> int | None:
    """Look up player_id by name using DB first, then nba_api static fallback."""
    result = await session.execute(
        select(Player.player_id).where(Player.name == display_name)
    )
    row = result.scalar_one_or_none()
    if row is not None:
        return row

    normalized_name = _normalize_player_name(display_name)
    static_match = _get_static_player_lookup().get(normalized_name)
    if static_match is not None:
        player_id, matched_name = static_match
        log.info(
            "player_resolved_from_static",
            name=display_name,
            matched_name=matched_name,
            player_id=player_id,
        )
        return player_id

    hardcoded_player_id = _HARDCODED_PLAYER_ID_FALLBACKS.get(normalized_name)
    if hardcoded_player_id is not None:
        log.info(
            "player_resolved_from_hardcoded",
            name=display_name,
            normalized_name=normalized_name,
            player_id=hardcoded_player_id,
        )
        return hardcoded_player_id

    log.warning("player_not_found", name=display_name)
    return None


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

    rows = []
    for team_entry in data.get("injuries", []):
        for injury in team_entry.get("injuries", []):
            athlete = injury.get("athlete", {})
            display_name = athlete.get("displayName", "")
            player_id = await resolve_player_id(session, display_name)
            if player_id is None:
                continue

            rows.append({
                "player_id": player_id,
                "report_date": date.today(),
                "status": injury.get("status", "Unknown"),
                "description": injury.get("details", {}).get("detail", ""),
                "source": "espn",
            })

    return await upsert_injuries(session, rows)


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
