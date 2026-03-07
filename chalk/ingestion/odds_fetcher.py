from datetime import date, datetime

import httpx
import structlog
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from chalk.config import settings
from chalk.db.models import BettingLine
from chalk.exceptions import IngestError

log = structlog.get_logger()

ODDS_API_BASE = "https://api.the-odds-api.com/v4"


async def _fetch_odds(endpoint: str, params: dict) -> dict:
    """Fetch from the Odds API with error handling."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{ODDS_API_BASE}/{endpoint}",
                params={"apiKey": settings.ODDS_API_KEY, **params},
                timeout=15.0,
            )
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPError as exc:
        raise IngestError(f"Odds API request failed: {exc}") from exc


async def upsert_betting_lines(session: AsyncSession, rows: list[dict]) -> int:
    """Upsert betting line rows. Returns count of rows affected."""
    if not rows:
        return 0

    stmt = pg_insert(BettingLine).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["game_id", "market"],
        set_={
            "line": stmt.excluded.line,
            "over_odds": stmt.excluded.over_odds,
            "under_odds": stmt.excluded.under_odds,
            "timestamp": stmt.excluded.timestamp,
        },
    )
    result = await session.execute(stmt)
    await session.commit()
    return result.rowcount


async def fetch_player_props(session: AsyncSession, game_date: date) -> int:
    """Fetch NBA player prop lines for a given date. Returns rows upserted."""
    data = await _fetch_odds(
        "sports/basketball_nba/events",
        {
            "dateFormat": "iso",
            "commenceTimeFrom": f"{game_date}T00:00:00Z",
            "commenceTimeTo": f"{game_date}T23:59:59Z",
        },
    )

    rows = []
    now = datetime.utcnow()
    for event in data if isinstance(data, list) else []:
        game_id = event.get("id", "")
        for bookmaker in event.get("bookmakers", []):
            sportsbook = bookmaker.get("key", "")
            for market in bookmaker.get("markets", []):
                market_key = market.get("key", "")
                for outcome in market.get("outcomes", []):
                    rows.append({
                        "game_id": game_id,
                        "player_id": None,
                        "sportsbook": sportsbook,
                        "market": market_key,
                        "line": outcome.get("point", 0.0),
                        "over_odds": outcome.get("price") if outcome.get("name") == "Over" else None,
                        "under_odds": outcome.get("price") if outcome.get("name") == "Under" else None,
                        "timestamp": now,
                    })

    return await upsert_betting_lines(session, rows)


async def fetch_game_totals(session: AsyncSession, game_date: date) -> int:
    """Fetch game total (over/under) lines. Returns rows upserted."""
    data = await _fetch_odds(
        "sports/basketball_nba/odds",
        {
            "regions": "us",
            "markets": "totals",
            "dateFormat": "iso",
            "commenceTimeFrom": f"{game_date}T00:00:00Z",
            "commenceTimeTo": f"{game_date}T23:59:59Z",
        },
    )

    rows = []
    now = datetime.utcnow()
    for event in data if isinstance(data, list) else []:
        game_id = event.get("id", "")
        for bookmaker in event.get("bookmakers", []):
            sportsbook = bookmaker.get("key", "")
            for market in bookmaker.get("markets", []):
                over_odds = None
                under_odds = None
                line = 0.0
                for outcome in market.get("outcomes", []):
                    if outcome.get("name") == "Over":
                        over_odds = outcome.get("price")
                        line = outcome.get("point", 0.0)
                    elif outcome.get("name") == "Under":
                        under_odds = outcome.get("price")

                rows.append({
                    "game_id": game_id,
                    "player_id": None,
                    "sportsbook": sportsbook,
                    "market": "game_total",
                    "line": line,
                    "over_odds": over_odds,
                    "under_odds": under_odds,
                    "timestamp": now,
                })

    return await upsert_betting_lines(session, rows)
