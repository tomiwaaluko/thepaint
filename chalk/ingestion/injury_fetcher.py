"""NBA injury ingestion via ESPN and Gemini structured extraction."""
from __future__ import annotations

import asyncio
import inspect
import json
import re
import unicodedata
from datetime import date, datetime
from functools import lru_cache
from typing import Any

import httpx
import structlog
from nba_api.stats.static import players as nba_static_players
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from chalk.config import settings
from chalk.db.models import Injury, Player
from chalk.exceptions import IngestError

try:
    import google.generativeai as genai
except ImportError:  # pragma: no cover - exercised when dependency is absent locally
    genai = None

log = structlog.get_logger()

ESPN_INJURY_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries"
INJURY_SOURCE = "ESPN/Gemini"
MISSING_GEMINI_KEY_MESSAGE = (
    "GEMINI_API_KEY not configured. Skipping injury ingestion.\n"
    "Set this in Railway environment variables and your local .env file.\n"
    "Get a free key at: https://aistudio.google.com/app/apikey"
)
GEMINI_SYSTEM_INSTRUCTION = """You extract NBA injury data into JSON. Return ONLY valid JSON with no
markdown, no backticks, no explanation. Use exactly this schema:
{
  "player_name": "string",
  "status": "Active" | "Questionable" | "Doubtful" | "Out",
  "injury_type": "string or null",
  "return_date": "YYYY-MM-DD or null",
  "notes": "string or null"
}
If return_date is uncertain, use null. Never guess dates."""

_VALID_STATUSES = {"Active", "Questionable", "Doubtful", "Out"}
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


def _clean_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_return_date(value: Any) -> date | None:
    text = _clean_optional_text(value)
    if text is None:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None


def _normalize_status(value: Any) -> str:
    if not isinstance(value, str):
        return "Active"
    normalized = value.strip().title()
    return normalized if normalized in _VALID_STATUSES else "Active"


def _parse_gemini_json(text: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        log.warning("injury_gemini_json_parse_failed", response=text[:500])
        return None

    if not isinstance(payload, dict):
        log.warning("injury_gemini_json_parse_failed", response=text[:500])
        return None

    return {
        "player_name": _clean_optional_text(payload.get("player_name")),
        "status": _normalize_status(payload.get("status")),
        "injury_type": _clean_optional_text(payload.get("injury_type")),
        "return_date": _parse_return_date(payload.get("return_date")),
        "notes": _clean_optional_text(payload.get("notes")),
    }


def _extract_espn_player_records(data: dict[str, Any]) -> list[dict[str, str]]:
    """Extract raw player injury records from ESPN's nested injury response."""
    records: list[dict[str, str]] = []
    for team_entry in data.get("injuries", []):
        team_data = team_entry.get("team") or {}
        team = (
            team_data.get("displayName")
            or team_data.get("name")
            or team_data.get("abbreviation")
            or ""
        )
        for injury in team_entry.get("injuries", []):
            athlete = injury.get("athlete") or {}
            full_name = athlete.get("displayName") or athlete.get("fullName") or ""
            if not full_name:
                continue

            details = injury.get("details") or {}
            raw_notes = (
                details.get("detail")
                or injury.get("shortComment")
                or injury.get("longComment")
                or injury.get("detail")
                or ""
            )
            records.append(
                {
                    "full_name": full_name,
                    "team": team,
                    "raw_status": str(injury.get("status") or ""),
                    "raw_notes": str(raw_notes or ""),
                }
            )
    return records


async def _fetch_espn_injuries() -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(ESPN_INJURY_URL)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPError as exc:
        raise IngestError(f"Failed to fetch injuries from ESPN API: {exc}") from exc


async def _match_player_id_by_name(session: AsyncSession, player_name: str) -> int | None:
    """Match Gemini's player name to the local players table case-insensitively."""
    result = await session.execute(
        select(Player.player_id).where(func.lower(Player.name) == player_name.lower())
    )
    player_id = result.scalar_one_or_none()
    if player_id is None:
        log.warning("player_not_found", name=player_name)
    return player_id


async def resolve_player_id(session: AsyncSession, display_name: str) -> int | None:
    """Look up player_id by name using DB first, then legacy nba_api static fallback."""
    result = await session.execute(select(Player.player_id).where(Player.name == display_name))
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


async def _filter_valid_player_ids(session: AsyncSession, rows: list[dict]) -> list[dict]:
    """Remove rows whose player_id does not exist in the players table."""
    if not rows:
        return rows
    unique_ids = {r["player_id"] for r in rows}
    result = await session.execute(
        select(Player.player_id).where(Player.player_id.in_(unique_ids))
    )
    existing_ids = {row[0] for row in result.fetchall()}
    missing_ids = unique_ids - existing_ids
    if missing_ids:
        for pid in missing_ids:
            log.warning("injury_skipped_missing_player", player_id=pid)
    return [r for r in rows if r["player_id"] in existing_ids]


async def upsert_injuries(session: AsyncSession, rows: list[dict]) -> int:
    """Upsert injury rows. Returns count of rows affected."""
    rows = await _filter_valid_player_ids(session, rows)
    if not rows:
        return 0
    write_rows = [
        {
            "player_id": row["player_id"],
            "report_date": row["report_date"],
            "status": row["status"],
            "injury_type": row.get("injury_type"),
            "return_date": row.get("return_date"),
            "notes": row.get("notes"),
            "source": row["source"],
        }
        for row in rows
    ]

    stmt = pg_insert(Injury).values(write_rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["player_id", "report_date"],
        set_={
            "status": stmt.excluded.status,
            "injury_type": stmt.excluded.injury_type,
            "return_date": stmt.excluded.return_date,
            "notes": stmt.excluded.notes,
            "source": stmt.excluded.source,
        },
    )
    result = await session.execute(stmt)
    await session.commit()
    return result.rowcount or 0


def _build_gemini_prompt(record: dict[str, str]) -> str:
    return (
        f"Player: {record['full_name']}\n"
        f"Team: {record['team']}\n"
        f"Status: {record['raw_status']}\n"
        f"Notes: {record['raw_notes']}"
    )


async def _extract_with_gemini(model: Any, record: dict[str, str]) -> dict[str, Any] | None:
    response = model.generate_content(_build_gemini_prompt(record))
    text = getattr(response, "text", "") or ""
    extracted = _parse_gemini_json(text)
    if extracted is not None and extracted["player_name"] is None:
        extracted["player_name"] = record["full_name"]
    return extracted


async def fetch_and_store_injuries(db: AsyncSession) -> dict:
    """Fetch ESPN injuries, extract structured fields with Gemini, and upsert them."""
    if settings.gemini_api_key is None:
        log.info(MISSING_GEMINI_KEY_MESSAGE)
        return {"processed": 0, "inserted": 0, "skipped": 0, "errors": 0}
    if genai is None:
        raise IngestError("google-generativeai is not installed")

    # TODO: Set GEMINI_API_KEY in .env (local) and Railway env vars (production)
    # Get a free key at: https://aistudio.google.com/app/apikey
    genai.configure(api_key=settings.gemini_api_key)
    model = genai.GenerativeModel(
        "gemini-1.5-flash",
        system_instruction=GEMINI_SYSTEM_INSTRUCTION,
    )

    data = await _fetch_espn_injuries()
    records = _extract_espn_player_records(data)
    rows: list[dict[str, Any]] = []
    summary = {"processed": len(records), "inserted": 0, "skipped": 0, "errors": 0}
    report_date = date.today()

    for record in records:
        try:
            extracted = await _extract_with_gemini(model, record)
            await asyncio.sleep(0.5)
            if extracted is None:
                summary["skipped"] += 1
                continue

            player_id = await _match_player_id_by_name(db, extracted["player_name"])
            if player_id is None:
                summary["skipped"] += 1
                continue

            notes = extracted["notes"]
            rows.append(
                {
                    "player_id": player_id,
                    "report_date": report_date,
                    "status": extracted["status"],
                    "injury_type": extracted["injury_type"],
                    "return_date": extracted["return_date"],
                    "notes": notes,
                    "source": INJURY_SOURCE,
                }
            )
        except Exception as exc:
            summary["errors"] += 1
            log.warning(
                "injury_player_extract_failed",
                player=record.get("full_name"),
                error=str(exc),
            )

    summary["inserted"] = await upsert_injuries(db, rows)
    return summary


async def ingest_injuries(session: AsyncSession) -> int:
    """Compatibility wrapper for older DAGs and Railway scripts."""
    summary = await fetch_and_store_injuries(session)
    return int(summary["inserted"])


async def get_player_status(session: AsyncSession, player_id: int, game_date: date) -> str:
    """Return most recent injury status for a player on or before game_date."""
    result = await session.execute(
        select(Injury.status)
        .where(Injury.player_id == player_id, Injury.report_date <= game_date)
        .order_by(Injury.report_date.desc())
        .limit(1)
    )
    status = result.scalar_one_or_none()
    if inspect.isawaitable(status):
        status = await status
    return status if isinstance(status, str) and status else "Active"
