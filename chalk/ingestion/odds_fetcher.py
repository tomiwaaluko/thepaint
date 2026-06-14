from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx
import structlog
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from chalk.config import settings
from chalk.db.models import BettingLine, Game, PlayerGameLog, Team
from chalk.exceptions import IngestError
from chalk.ingestion.injury_fetcher import resolve_player_id

log = structlog.get_logger()

ODDS_API_BASE = "https://api.the-odds-api.com/v4"
NBA_SPORT_KEY = "basketball_nba"
BETTING_LINE_CONFLICT_COLUMNS = ["game_id", "player_id", "market", "sportsbook"]
NBA_TZ = ZoneInfo("America/New_York")
PLAYER_PROP_MARKETS = [
    "player_points",
    "player_rebounds",
    "player_assists",
    "player_threes",
    "player_blocks",
    "player_steals",
    "player_turnovers",
]
STAT_TO_MARKET = {
    "pts": "player_points",
    "reb": "player_rebounds",
    "ast": "player_assists",
    "fg3m": "player_threes",
    "blk": "player_blocks",
    "stl": "player_steals",
    "to_committed": "player_turnovers",
}
MARKET_TO_STAT = {market: stat for stat, market in STAT_TO_MARKET.items()}
TEAM_NAME_ALIASES = {
    "la clippers": "los angeles clippers",
    "ny knicks": "new york knicks",
    "gs warriors": "golden state warriors",
}


def _normalize_lookup(value: str | None) -> str:
    return "".join(ch for ch in (value or "").lower() if ch.isalnum())


def _date_window_utc(game_date: date) -> tuple[str, str]:
    start_local = datetime.combine(game_date, time.min, tzinfo=NBA_TZ)
    end_local = start_local + timedelta(days=1)
    start_utc = start_local.astimezone(timezone.utc).replace(microsecond=0)
    end_utc = end_local.astimezone(timezone.utc).replace(microsecond=0)
    return (
        start_utc.isoformat().replace("+00:00", "Z"),
        end_utc.isoformat().replace("+00:00", "Z"),
    )


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _event_game_date(event: dict) -> date | None:
    commence_time = event.get("commence_time")
    if not commence_time:
        return None
    try:
        dt = datetime.fromisoformat(commence_time.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.astimezone(NBA_TZ).date()


async def _team_lookup(session: AsyncSession) -> dict[str, int]:
    result = await session.execute(select(Team))
    lookup: dict[str, int] = {}
    for team in result.scalars().all():
        names = {
            team.name,
            team.abbreviation,
            team.city,
            f"{team.city} {team.name}",
        }
        for name in names:
            key = _normalize_lookup(TEAM_NAME_ALIASES.get((name or "").lower(), name))
            if key:
                lookup[key] = team.team_id
    for alias, canonical in TEAM_NAME_ALIASES.items():
        canonical_id = lookup.get(_normalize_lookup(canonical))
        if canonical_id:
            lookup[_normalize_lookup(alias)] = canonical_id
    return lookup


async def _resolve_event_game_id(
    session: AsyncSession,
    event: dict,
    team_lookup: dict[str, int],
) -> str | None:
    game_date = _event_game_date(event)
    if game_date is None:
        log.warning("odds_event_missing_commence_time", event_id=event.get("id"))
        return None

    home_team_id = team_lookup.get(_normalize_lookup(event.get("home_team")))
    away_team_id = team_lookup.get(_normalize_lookup(event.get("away_team")))
    if not home_team_id or not away_team_id:
        log.warning(
            "odds_event_team_unresolved",
            event_id=event.get("id"),
            home_team=event.get("home_team"),
            away_team=event.get("away_team"),
        )
        return None

    log_count = func.count(PlayerGameLog.log_id)
    result = await session.execute(
        select(Game.game_id, log_count.label("player_log_count"))
        .outerjoin(PlayerGameLog, PlayerGameLog.game_id == Game.game_id)
        .where(Game.date == game_date)
        .where(Game.home_team_id == home_team_id)
        .where(Game.away_team_id == away_team_id)
        .group_by(Game.game_id)
        .order_by(log_count.desc(), Game.game_id.asc())
        .limit(1)
    )
    row = result.first()
    game_id = row[0] if row else None
    if game_id is None:
        log.warning(
            "odds_event_game_unresolved",
            event_id=event.get("id"),
            game_date=str(game_date),
            home_team_id=home_team_id,
            away_team_id=away_team_id,
        )
    return game_id


def _merge_outcome(rows_by_key: dict[tuple, dict], row: dict, side: str, odds: int | None) -> None:
    key = (row["game_id"], row["player_id"], row["sportsbook"], row["market"])
    existing = rows_by_key.setdefault(row_key := key, row)
    if side == "over":
        existing["over_odds"] = odds
    elif side == "under":
        existing["under_odds"] = odds
    rows_by_key[row_key] = existing


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
        index_elements=BETTING_LINE_CONFLICT_COLUMNS,
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
    start_utc, end_utc = _date_window_utc(game_date)
    events = await _fetch_odds(
        f"sports/{NBA_SPORT_KEY}/events",
        {
            "dateFormat": "iso",
            "commenceTimeFrom": start_utc,
            "commenceTimeTo": end_utc,
        },
    )

    team_lookup = await _team_lookup(session)
    rows_by_key: dict[tuple, dict] = {}
    now = _utcnow_naive()
    for event in events if isinstance(events, list) else []:
        game_id = await _resolve_event_game_id(session, event, team_lookup)
        if game_id is None:
            continue

        odds_data = await _fetch_odds(
            f"sports/{NBA_SPORT_KEY}/events/{event.get('id')}/odds",
            {
                "regions": "us",
                "markets": ",".join(PLAYER_PROP_MARKETS),
                "oddsFormat": "american",
                "dateFormat": "iso",
            },
        )

        for bookmaker in odds_data.get("bookmakers", []):
            sportsbook = bookmaker.get("key", "")
            for market in bookmaker.get("markets", []):
                market_key = market.get("key", "")
                if market_key not in PLAYER_PROP_MARKETS:
                    continue
                for outcome in market.get("outcomes", []):
                    outcome_name = (outcome.get("name") or "").strip().lower()
                    if outcome_name not in {"over", "under"}:
                        continue
                    player_name = outcome.get("description")
                    if not player_name:
                        continue
                    player_id = await resolve_player_id(session, player_name)
                    if player_id is None:
                        log.warning("odds_player_unresolved", player_name=player_name, market=market_key)
                        continue
                    price = outcome.get("price")
                    odds = int(price) if price is not None else None
                    row = {
                        "game_id": game_id,
                        "player_id": player_id,
                        "sportsbook": sportsbook,
                        "market": MARKET_TO_STAT.get(market_key, market_key),
                        "line": outcome.get("point", 0.0),
                        "over_odds": None,
                        "under_odds": None,
                        "timestamp": now,
                    }
                    _merge_outcome(rows_by_key, row, outcome_name, odds)

    return await upsert_betting_lines(session, list(rows_by_key.values()))


async def fetch_game_totals(session: AsyncSession, game_date: date) -> int:
    """Fetch game total (over/under) lines. Returns rows upserted."""
    start_utc, end_utc = _date_window_utc(game_date)
    data = await _fetch_odds(
        f"sports/{NBA_SPORT_KEY}/odds",
        {
            "regions": "us",
            "markets": "totals",
            "oddsFormat": "american",
            "dateFormat": "iso",
            "commenceTimeFrom": start_utc,
            "commenceTimeTo": end_utc,
        },
    )

    rows = []
    now = _utcnow_naive()
    team_lookup = await _team_lookup(session)
    for event in data if isinstance(data, list) else []:
        game_id = await _resolve_event_game_id(session, event, team_lookup)
        if game_id is None:
            continue
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
