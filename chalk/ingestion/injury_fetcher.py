from datetime import date, datetime

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from chalk.db.models import Injury, Player
from chalk.exceptions import IngestError

log = structlog.get_logger()

ESPN_INJURY_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries"


async def resolve_player_id(session: AsyncSession, display_name: str) -> int | None:
    """Look up player_id by name. Returns None if not found."""
    result = await session.execute(
        select(Player.player_id).where(Player.name == display_name)
    )
    row = result.scalar_one_or_none()
    if row is None:
        log.warning("player_not_found", name=display_name)
    return row


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
