---
name: data-ingestion
description: Use this skill whenever writing, modifying, or debugging any data ingestion code in Chalk. Covers nba_api usage patterns, rate limiting, exponential backoff, response caching, idempotent upserts into PostgreSQL, and the Odds API / injury feed integrations. Always use this skill when touching chalk/ingestion/, writing backfill scripts, or building Airflow DAGs that pull external data.
---

# Data Ingestion Skill

## Core Principles

1. **Idempotent always** — every write is an upsert. Re-running any job must produce identical DB state.
2. **Cache raw responses** — never hit nba_api twice for the same data. Cache JSON to disk before parsing.
3. **Backoff on every external call** — nba_api is flaky. Always wrap in retry logic.
4. **Fail loudly** — raise `IngestError` on permanent failures. Never silently skip rows.

---

## NBAFetcher Pattern (`ingestion/nba_fetcher.py`)

```python
import asyncio
import json
import hashlib
from pathlib import Path
from datetime import datetime, date
from nba_api.stats.endpoints import playergamelog, leaguegamelog, commonplayerinfo
from chalk.exceptions import IngestError
from chalk.config import settings
import structlog

log = structlog.get_logger()

CACHE_DIR = Path(settings.NBA_API_CACHE_DIR)
MAX_RETRIES = 5
BASE_DELAY = 2.0  # seconds


def _cache_path(endpoint: str, params: dict) -> Path:
    key = hashlib.md5(f"{endpoint}{sorted(params.items())}".encode()).hexdigest()
    return CACHE_DIR / endpoint / f"{key}.json"


async def _fetch_with_backoff(endpoint_cls, params: dict, endpoint_name: str) -> dict:
    """Call nba_api with exponential backoff + disk caching."""
    cache_file = _cache_path(endpoint_name, params)
    cache_file.parent.mkdir(parents=True, exist_ok=True)

    # Return cached response if exists
    if cache_file.exists():
        log.debug("cache_hit", endpoint=endpoint_name, params=params)
        return json.loads(cache_file.read_text())

    for attempt in range(MAX_RETRIES):
        try:
            # nba_api is synchronous — run in thread pool
            loop = asyncio.get_event_loop()
            endpoint = await loop.run_in_executor(
                None, lambda: endpoint_cls(**params)
            )
            data = endpoint.get_normalized_dict()
            cache_file.write_text(json.dumps(data))
            log.info("fetch_success", endpoint=endpoint_name, attempt=attempt)
            return data

        except Exception as exc:
            delay = BASE_DELAY * (2 ** attempt) + (random.uniform(0, 1))
            log.warning("fetch_retry", endpoint=endpoint_name, attempt=attempt, error=str(exc), delay=delay)
            if attempt == MAX_RETRIES - 1:
                raise IngestError(f"Permanent failure: {endpoint_name} after {MAX_RETRIES} attempts") from exc
            await asyncio.sleep(delay)
```

---

## Upsert Pattern

Never use plain INSERT. Always use PostgreSQL upsert.

```python
from sqlalchemy.dialects.postgresql import insert as pg_insert

async def upsert_player_game_logs(session: AsyncSession, rows: list[dict]) -> int:
    """Upsert player game log rows. Returns count of rows inserted/updated."""
    if not rows:
        return 0

    stmt = pg_insert(PlayerGameLog).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["game_id", "player_id"],  # unique constraint
        set_={
            "pts": stmt.excluded.pts,
            "reb": stmt.excluded.reb,
            "ast": stmt.excluded.ast,
            # ... all mutable columns
            "updated_at": datetime.utcnow(),
        }
    )
    result = await session.execute(stmt)
    await session.commit()
    return result.rowcount
```

---

## Player Game Log Ingestion

```python
async def ingest_player_season(
    session: AsyncSession,
    player_id: int,
    season: str,  # e.g. "2023-24"
) -> int:
    """Ingest all game logs for a player-season. Returns rows upserted."""
    data = await _fetch_with_backoff(
        playergamelog.PlayerGameLog,
        {"player_id": player_id, "season": season, "season_type_all_star": "Regular Season"},
        endpoint_name="PlayerGameLog",
    )

    rows = []
    for entry in data.get("PlayerGameLog", []):
        rows.append({
            "game_id": entry["Game_ID"],
            "player_id": player_id,
            "game_date": datetime.strptime(entry["GAME_DATE"], "%b %d, %Y").date(),
            "pts": entry["PTS"],
            "reb": entry["REB"],
            "ast": entry["AST"],
            "stl": entry["STL"],
            "blk": entry["BLK"],
            "to_committed": entry["TOV"],
            "fg3m": entry["FG3M"],
            "fg3a": entry["FG3A"],
            "fgm": entry["FGM"],
            "fga": entry["FGA"],
            "min_played": _parse_minutes(entry["MIN"]),
        })

    return await upsert_player_game_logs(session, rows)


def _parse_minutes(min_str: str) -> float:
    """Convert '32:14' to 32.23"""
    parts = min_str.split(":")
    return int(parts[0]) + int(parts[1]) / 60
```

---

## Backfill Script Pattern (`scripts/backfill.py`)

```python
SEASONS = ["2015-16", "2016-17", "2017-18", "2018-19", "2019-20",
           "2020-21", "2021-22", "2022-23", "2023-24", "2024-25"]

# Rate limiting: nba_api allows ~30 requests/minute safely
INTER_REQUEST_DELAY = 2.5  # seconds between requests

async def backfill_all(session: AsyncSession):
    players = await get_active_players(session)  # top 300 by minutes
    total = len(players) * len(SEASONS)
    completed = 0

    for player in players:
        for season in SEASONS:
            try:
                count = await ingest_player_season(session, player.player_id, season)
                completed += 1
                log.info("backfill_progress", completed=completed, total=total,
                         player=player.name, season=season, rows=count)
            except IngestError as e:
                log.error("backfill_skip", player=player.name, season=season, error=str(e))
                # Continue with next player — don't abort entire backfill
            await asyncio.sleep(INTER_REQUEST_DELAY)
```

---

## Team Game Log Ingestion

Use `leaguegamelog.LeagueGameLog` for efficient bulk team ingestion (one call per season vs. one per team).

```python
async def ingest_team_season(session: AsyncSession, season: str) -> int:
    data = await _fetch_with_backoff(
        leaguegamelog.LeagueGameLog,
        {"season": season, "player_or_team_abbreviation": "T"},
        endpoint_name="LeagueGameLog_Teams",
    )
    # Parse and upsert to team_game_logs
    ...
```

---

## Injury Feed Ingestion (`ingestion/injury_fetcher.py`)

Pull from ESPN's public injury endpoint. Run every 2 hours during game days.

```python
ESPN_INJURY_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries"

async def ingest_injuries(session: AsyncSession) -> int:
    async with httpx.AsyncClient() as client:
        resp = await client.get(ESPN_INJURY_URL, timeout=10.0)
        resp.raise_for_status()
        data = resp.json()

    rows = []
    for team in data.get("injuries", []):
        for injury in team.get("injuries", []):
            rows.append({
                "player_id": await resolve_player_id(session, injury["athlete"]["displayName"]),
                "report_date": date.today(),
                "status": injury["status"],  # "Questionable", "Out", "Day-To-Day"
                "description": injury.get("details", {}).get("detail", ""),
                "source": "espn",
            })

    return await upsert_injuries(session, rows)
```

---

## Odds API Integration (`ingestion/odds_fetcher.py`)

```python
ODDS_API_BASE = "https://api.the-odds-api.com/v4"

async def fetch_player_props(session: AsyncSession, game_date: date) -> int:
    """Fetch NBA player prop lines for a given date."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{ODDS_API_BASE}/sports/basketball_nba/events",
            params={
                "apiKey": settings.ODDS_API_KEY,
                "dateFormat": "iso",
                "commenceTimeFrom": f"{game_date}T00:00:00Z",
                "commenceTimeTo": f"{game_date}T23:59:59Z",
            },
            timeout=15.0,
        )
        resp.raise_for_status()
    # Parse + upsert to betting_lines
    ...
```

---

## Airflow DAG Structure

Daily pipeline runs in two DAGs:

**`daily_ingest` (8:00 AM ET):**
`ingest_yesterday_games → ingest_injuries → fetch_odds_lines → validate_row_counts`

**`daily_predict` (6:00 PM ET, after lineup lock):**
`refresh_injuries → generate_todays_features → run_predictions → cache_to_redis → notify`

---

## Testing Ingestion Code

Always mock nba_api — never hit real endpoints in tests:

```python
@pytest.fixture
def mock_player_game_log(mocker):
    mocker.patch(
        "chalk.ingestion.nba_fetcher._fetch_with_backoff",
        return_value={"PlayerGameLog": [SAMPLE_LOG_ROW]}
    )

async def test_ingest_player_season_upserts_correctly(session, mock_player_game_log):
    count = await ingest_player_season(session, player_id=2544, season="2023-24")
    assert count == 1
    log = await session.get(PlayerGameLog, {"player_id": 2544, ...})
    assert log.pts == SAMPLE_LOG_ROW["PTS"]
```
