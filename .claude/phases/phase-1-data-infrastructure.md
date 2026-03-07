# Phase 1 — Data Infrastructure

## Goal
PostgreSQL database running with TimescaleDB, all ORM models defined, nba_api ingestion
working with backoff and caching, historical data backfilled 2015–2025, any player's
last 30 game logs queryable in under 100ms.

## Depends On
Nothing. This is the foundation of the entire system.

## Unlocks
Phase 2 (Feature Engineering) — needs populated player_game_logs and team_game_logs tables.

## Skill Files to Read First
- `CLAUDE.md` — DB schema, naming conventions, environment variables
- `.claude/skills/data-ingestion/SKILL.md` — nba_api patterns, backoff, upserts

---

## Step 1 — Repo Scaffold

### Files to Create

**`pyproject.toml`**
```toml
[project]
name = "chalk"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.110.0",
    "uvicorn[standard]>=0.29.0",
    "sqlalchemy[asyncio]>=2.0.0",
    "asyncpg>=0.29.0",
    "alembic>=1.13.0",
    "pydantic-settings>=2.2.0",
    "xgboost>=2.0.0",
    "lightgbm>=4.3.0",
    "scikit-learn>=1.4.0",
    "pandas>=2.2.0",
    "polars>=0.20.0",
    "numpy>=1.26.0",
    "nba_api>=1.4.0",
    "httpx>=0.27.0",
    "redis[asyncio]>=5.0.0",
    "mlflow>=2.10.0",
    "optuna>=3.6.0",
    "structlog>=24.1.0",
    "mapie>=0.8.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "pytest-mock>=3.12.0",
    "httpx>=0.27.0",
    "factory-boy>=3.3.0",
]
```

**`docker-compose.yml`**
```yaml
services:
  db:
    image: timescale/timescaledb:latest-pg15
    environment:
      POSTGRES_USER: chalk
      POSTGRES_PASSWORD: chalk
      POSTGRES_DB: chalk
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  mlflow:
    image: ghcr.io/mlflow/mlflow:v2.10.0
    ports:
      - "5000:5000"
    environment:
      MLFLOW_BACKEND_STORE_URI: postgresql://chalk:chalk@db:5432/mlflow
      MLFLOW_DEFAULT_ARTIFACT_ROOT: /mlflow/artifacts
    volumes:
      - mlflow_artifacts:/mlflow/artifacts
    depends_on:
      - db
    command: >
      mlflow server
      --host 0.0.0.0
      --port 5000
      --backend-store-uri postgresql://chalk:chalk@db:5432/mlflow
      --default-artifact-root /mlflow/artifacts

  api:
    build: .
    ports:
      - "8000:8000"
    environment:
      DATABASE_URL: postgresql+asyncpg://chalk:chalk@db:5432/chalk
      REDIS_URL: redis://redis:6379/0
      MLFLOW_TRACKING_URI: http://mlflow:5000
    depends_on:
      - db
      - redis
    command: uvicorn chalk.api.main:app --host 0.0.0.0 --port 8000 --reload
    volumes:
      - .:/app
    working_dir: /app

volumes:
  postgres_data:
  mlflow_artifacts:
```

**`Dockerfile`**
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml .
RUN pip install -e ".[dev]"
COPY . .
```

**`.env.example`**
```
DATABASE_URL=postgresql+asyncpg://chalk:chalk@localhost:5432/chalk
REDIS_URL=redis://localhost:6379/0
ODDS_API_KEY=your_key_here
MLFLOW_TRACKING_URI=http://localhost:5000
LOG_LEVEL=INFO
NBA_API_CACHE_DIR=.cache/nba_api
```

**Acceptance Criteria:**
- `docker compose up` starts all services without errors
- `docker compose ps` shows db, redis, mlflow, api all healthy

---

## Step 2 — App Config

### `chalk/config.py`
Use pydantic-settings to load from environment variables.

```python
from pydantic_settings import BaseSettings
from pathlib import Path

class Settings(BaseSettings):
    DATABASE_URL: str
    REDIS_URL: str = "redis://localhost:6379/0"
    ODDS_API_KEY: str = ""
    MLFLOW_TRACKING_URI: str = "http://localhost:5000"
    LOG_LEVEL: str = "INFO"
    NBA_API_CACHE_DIR: Path = Path(".cache/nba_api")

    class Config:
        env_file = ".env"

settings = Settings()
```

---

## Step 3 — Custom Exceptions

### `chalk/exceptions.py`
```python
class ChalkError(Exception): ...
class IngestError(ChalkError): ...
class FeatureError(ChalkError): ...
class PredictionError(ChalkError): ...
class ModelNotFoundError(ChalkError): ...
```

---

## Step 4 — Database Session

### `chalk/db/session.py`
- Create async SQLAlchemy engine from `settings.DATABASE_URL`
- Create `async_session_factory` using `async_sessionmaker`
- Export `AsyncSession` type alias
- Include a `get_db()` async generator for FastAPI dependency injection

**Pattern:**
```python
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

engine = create_async_engine(settings.DATABASE_URL, echo=False, pool_size=10)
async_session_factory = async_sessionmaker(engine, expire_on_commit=False)
```

---

## Step 5 — ORM Models

### `chalk/db/models.py`
Create SQLAlchemy ORM classes for all tables. Use `mapped_column` and `Mapped` (SQLAlchemy 2.0 style).

**Tables to define:**

**`Player`**
```
player_id: int (PK, from nba_api)
name: str
team_id: int (FK → Team)
position: str  # PG, SG, SF, PF, C
height_inches: int | None
weight_lbs: int | None
birth_date: date | None
is_active: bool (default True)
```

**`Team`**
```
team_id: int (PK, from nba_api)
name: str
abbreviation: str
conference: str
division: str
arena: str | None
city: str
```

**`Game`**
```
game_id: str (PK, nba_api format e.g. "0022301234")
date: date
season: str  # e.g. "2023-24"
home_team_id: int (FK → Team)
away_team_id: int (FK → Team)
is_playoffs: bool (default False)
status: str  # "scheduled", "live", "final"
```

**`PlayerGameLog`**
```
log_id: int (PK, autoincrement)
game_id: str (FK → Game)
player_id: int (FK → Player)
team_id: int (FK → Team)
game_date: date  # denormalized for fast filtering
season: str      # denormalized for fast filtering
min_played: float
pts: int
reb: int
ast: int
stl: int
blk: int
to_committed: int
fg3m: int
fg3a: int
fgm: int
fga: int
ftm: int
fta: int
plus_minus: int
starter: bool
created_at: datetime (default utcnow)
updated_at: datetime (default utcnow)

UniqueConstraint: (game_id, player_id)
Index: (player_id, game_date)  ← critical for feature query performance
Index: (team_id, game_date)
```

**`TeamGameLog`**
```
log_id: int (PK, autoincrement)
game_id: str (FK → Game)
team_id: int (FK → Team)
game_date: date  # denormalized
season: str      # denormalized
pts: int
pace: float
off_rtg: float
def_rtg: float
ts_pct: float
ast: int
to_committed: int
oreb: int
dreb: int
fg3a_rate: float
created_at: datetime

UniqueConstraint: (game_id, team_id)
Index: (team_id, game_date)
```

**`Injury`**
```
injury_id: int (PK, autoincrement)
player_id: int (FK → Player)
report_date: date
game_id: str | None (FK → Game)
status: str  # "Active", "Day-To-Day", "Out", "Questionable"
description: str | None
source: str  # "espn", "nba_api"
created_at: datetime

Index: (player_id, report_date)
```

**`BettingLine`**
```
line_id: int (PK, autoincrement)
game_id: str (FK → Game)
player_id: int | None (FK → Player, null for game totals)
sportsbook: str
market: str  # "player_points", "player_rebounds", "game_total", etc.
line: float
over_odds: int | None  # American odds e.g. -110
under_odds: int | None
timestamp: datetime

Index: (game_id, market)
```

**`Prediction`**
```
pred_id: int (PK, autoincrement)
game_id: str (FK → Game)
player_id: int | None (FK → Player)
model_version: str
as_of_ts: datetime
stat: str
p10: float
p25: float
p50: float
p75: float
p90: float
created_at: datetime

Index: (game_id, player_id, stat)
```

**Acceptance Criteria:**
- All models importable without error
- Relationships defined correctly (backref where useful)
- All indexes defined

---

## Step 6 — Alembic Migrations

```bash
alembic init alembic
# Edit alembic/env.py to use async engine and import chalk.db.models
alembic revision --autogenerate -m "initial_schema"
alembic upgrade head
```

**Acceptance Criteria:**
- `alembic upgrade head` runs clean against a fresh DB
- `alembic downgrade -1` works without error
- All tables and indexes exist in the DB after upgrade

---

## Step 7 — NBAFetcher

### `chalk/ingestion/nba_fetcher.py`

Build following the pattern in `.claude/skills/data-ingestion/SKILL.md`.

**Key functions to implement:**

`_cache_path(endpoint, params) → Path`
- MD5 hash of endpoint + params
- Returns path under `settings.NBA_API_CACHE_DIR`

`_fetch_with_backoff(endpoint_cls, params, endpoint_name) → dict`
- Check disk cache first
- If miss: call nba_api in thread pool executor (it's synchronous)
- Exponential backoff: delay = 2.0 * (2 ** attempt) + jitter, max 5 retries
- Cache successful response to disk
- Raise `IngestError` on permanent failure

`ingest_player_season(session, player_id, season) → int`
- Fetches PlayerGameLog from nba_api
- Parses all rows into dicts matching PlayerGameLog ORM columns
- Calls `upsert_player_game_logs(session, rows)`
- Returns row count

`ingest_team_season(session, season) → int`
- Fetches LeagueGameLog (team flavor) — one call covers all teams for a season
- Parses and upserts to team_game_logs
- Returns row count

`upsert_player_game_logs(session, rows) → int`
- pg_insert with `on_conflict_do_update` on `(game_id, player_id)`
- Updates all mutable columns + `updated_at`

`upsert_team_game_logs(session, rows) → int`
- pg_insert with `on_conflict_do_update` on `(game_id, team_id)`

**Acceptance Criteria:**
- Calling `ingest_player_season()` twice produces identical DB state
- Re-running with cached response doesn't hit nba_api
- `IngestError` raised (not swallowed) on repeated failures

---

## Step 8 — Injury Fetcher

### `chalk/ingestion/injury_fetcher.py`

**Key functions:**

`ingest_injuries(session) → int`
- GET `https://site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries`
- Parse each player injury entry
- Match player name to player_id via fuzzy name lookup in DB
- Upsert to injuries table
- Return row count

`get_player_status(session, player_id, game_date) → str`
- Returns most recent injury status for a player on or before game_date
- Returns "Active" if no injury record found

---

## Step 9 — Odds Fetcher

### `chalk/ingestion/odds_fetcher.py`

**Key functions:**

`fetch_player_props(session, game_date) → int`
- Calls Odds API for NBA player props on given date
- Markets to fetch: `player_points`, `player_rebounds`, `player_assists`, `player_threes`
- Upserts to betting_lines table
- Returns row count

`fetch_game_totals(session, game_date) → int`
- Fetches game total (over/under) lines
- Upserts to betting_lines with `player_id = None`

---

## Step 10 — Backfill Script

### `scripts/backfill.py`

```
Usage: python scripts/backfill.py [--seasons 2015-16 2016-17 ...] [--players all|top150]
```

**Logic:**
1. Load list of active + historical players (top 300 by career minutes)
2. For each player × season combination:
   - Skip if row count in DB already matches expected (idempotent check)
   - Call `ingest_player_season()`
   - Sleep 2.5 seconds between requests
   - Log progress: `{completed}/{total} — {player} {season} ({rows} rows)`
3. After player logs: call `ingest_team_season()` for each season
4. Write final summary: total rows inserted, any skipped players

**Progress tracking:**
- Write progress to `.cache/backfill_progress.json` so backfill can be resumed if interrupted

**Acceptance Criteria:**
- Backfill runs to completion without crashing
- Re-running produces identical row counts (idempotent)
- Any player's last 30 game logs return in < 100ms via:
  ```sql
  SELECT * FROM player_game_logs
  WHERE player_id = 2544
  ORDER BY game_date DESC
  LIMIT 30;
  ```

---

## Step 11 — Tests

### `tests/test_ingestion/test_nba_fetcher.py`

- `test_ingest_player_season_upserts_correctly` — mock nba_api, verify rows in DB
- `test_ingest_player_season_is_idempotent` — run twice, verify same row count
- `test_fetch_with_backoff_uses_cache` — verify nba_api not called on second request
- `test_fetch_with_backoff_raises_after_max_retries` — mock repeated failures, verify IngestError

### `tests/test_ingestion/test_injury_fetcher.py`

- `test_ingest_injuries_upserts_correctly` — mock ESPN endpoint
- `test_get_player_status_returns_active_when_no_record`

### `tests/conftest.py`

- `session` fixture — creates test DB, runs migrations, yields session, tears down
- `mock_nba_api` fixture — patches `_fetch_with_backoff`

---

## Phase 1 Completion Checklist

- [ ] `docker compose up` — all services healthy
- [ ] `alembic upgrade head` — all tables and indexes created
- [ ] `pytest tests/test_ingestion/` — all tests pass
- [ ] `python scripts/backfill.py` — completes without error
- [ ] Row count validation:
  - `player_game_logs` ≥ 800,000 rows
  - `team_game_logs` ≥ 25,000 rows
- [ ] Query performance: last 30 logs for any player < 100ms
- [ ] `TODO.md` updated — all Phase 1 checkboxes marked done
- [ ] Phase 2 file read and understood before stopping
