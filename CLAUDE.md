# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Tha Paint** — an NBA Statline Predictor. A machine learning system that predicts NBA player and team statlines for any given matchup. It powers four outputs:
- Player stat predictions (PTS, REB, AST, STL, BLK, TO, 3PM, FG%)
- Team-level game projections (total points, pace, offensive/defensive rating)
- Over/under probability distributions for sports betting
- Fantasy scoring projections (DraftKings, FanDuel, Yahoo)

The full architecture and roadmap is documented in `NBA_Prediction_System_Roadmap.pdf`.

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.11+ |
| Database | PostgreSQL 15 + TimescaleDB |
| ORM / Migrations | SQLAlchemy 2.0 + Alembic |
| Data Processing | pandas + polars |
| Feature Pipelines | scikit-learn Pipelines |
| ML Models | XGBoost + LightGBM |
| Probabilistic Output | MAPIE + quantile regression |
| Experiment Tracking | MLflow |
| API | FastAPI (async) |
| Task Scheduling | Apache Airflow |
| Caching | Redis |
| Frontend | React + Recharts |
| Containerization | Docker + Docker Compose |
| Testing | pytest + pytest-asyncio |

## Repo Structure

```
tha_paint/
├── CLAUDE.md                        ← you are here
├── .claude/
│   └── skills/                      ← Claude Code skill files
│       ├── feature-engineering/
│       ├── mlflow-tracking/
│       ├── api-patterns/
│       ├── data-ingestion/
│       └── model-training/
├── alembic/                         ← database migrations
│   └── versions/
├── tha_paint/
│   ├── __init__.py
│   ├── config.py                    ← settings via pydantic-settings
│   ├── db/
│   │   ├── __init__.py
│   │   ├── session.py               ← async SQLAlchemy engine + session factory
│   │   └── models.py                ← ORM table definitions
│   ├── ingestion/
│   │   ├── __init__.py
│   │   ├── nba_fetcher.py           ← nba_api wrapper with backoff + caching
│   │   ├── odds_fetcher.py          ← Odds API integration
│   │   └── injury_fetcher.py        ← injury report ingestion
│   ├── features/
│   │   ├── __init__.py
│   │   ├── rolling.py               ← rolling window averages
│   │   ├── opponent.py              ← opponent defensive profile features
│   │   ├── situational.py           ← rest days, home/away, context features
│   │   ├── roster.py                ← injury/teammate availability features
│   │   └── pipeline.py              ← master feature pipeline
│   ├── models/
│   │   ├── __init__.py
│   │   ├── base.py                  ← base trainer class
│   │   ├── player.py                ← per-stat player models
│   │   ├── team.py                  ← team total / pace models
│   │   └── registry.py              ← MLflow model registry helpers
│   ├── predictions/
│   │   ├── __init__.py
│   │   ├── player.py                ← player prediction engine
│   │   ├── team.py                  ← team prediction engine
│   │   └── distributions.py         ← quantile → probability distributions
│   ├── betting/
│   │   ├── __init__.py
│   │   └── over_under.py            ← O/U probability + edge calculation
│   ├── fantasy/
│   │   ├── __init__.py
│   │   └── scoring.py               ← DK / FD / Yahoo score computation
│   └── api/
│       ├── __init__.py
│       ├── main.py                  ← FastAPI app entrypoint
│       ├── dependencies.py          ← shared FastAPI dependencies
│       └── routes/
│           ├── players.py
│           ├── teams.py
│           ├── games.py
│           └── health.py
├── airflow/
│   └── dags/
│       ├── daily_ingest.py
│       └── daily_predict.py
├── tests/
│   ├── conftest.py
│   ├── test_features/
│   ├── test_models/
│   └── test_api/
├── scripts/
│   ├── backfill.py                  ← historical data backfill runner
│   └── train_all.py                 ← full model training pipeline
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
└── .env.example
```

## Database Schema

### Core Tables

```sql
players         (player_id, name, team_id, position, height_inches, weight_lbs, birth_date, is_active)
teams           (team_id, name, abbreviation, conference, division, arena, city)
games           (game_id, date, season, home_team_id, away_team_id, is_playoffs, status)
player_game_logs (log_id, game_id, player_id, team_id, min_played, pts, reb, ast, stl, blk,
                  to_committed, fgm, fga, fg3m, fg3a, ftm, fta, plus_minus, starter)
team_game_logs  (log_id, game_id, team_id, pts, pace, off_rtg, def_rtg, ts_pct, ast,
                  to_committed, oreb, dreb, fg3a_rate, created_at)
injuries        (injury_id, player_id, report_date, game_id, status, description, source)
betting_lines   (line_id, game_id, player_id, sportsbook, market, line, over_odds,
                  under_odds, timestamp)
predictions     (pred_id, game_id, player_id, model_version, as_of_ts, stat, p10, p25,
                  p50, p75, p90, created_at)
```

## The Non-Negotiable Rules

### 1. The as_of_date Leakage Rule — NEVER VIOLATE THIS
Every function that generates features MUST accept an `as_of_date: datetime` parameter.
Features may ONLY use data where `game_date < as_of_date`.
This is the single most important correctness constraint in the entire codebase.
Violating it produces falsely optimistic MAE scores and broken live predictions.

```python
# CORRECT
def get_rolling_avg(player_id: int, stat: str, window: int, as_of_date: datetime) -> float:
    # Only query logs where game_date < as_of_date
    ...

# WRONG — never do this
def get_rolling_avg(player_id: int, stat: str, window: int) -> float:
    # No date gate = data leakage
    ...
```

### 2. Idempotent Ingestion
All ingestion jobs must use upsert (INSERT ... ON CONFLICT DO UPDATE), never plain INSERT.
Re-running any ingestion job must produce the same database state.

### 3. Async All the Way Down
Database access uses asyncpg via SQLAlchemy async sessions.
API endpoints are all async def.
Never use synchronous database calls in the hot path.

### 4. Time-Series Validation Only
Never use random k-fold cross-validation on any sports data.
Always use walk-forward validation: train on seasons N through Y, validate on Y+1.
Training cutoff seasons: 2015–2022. Validation: 2022–23. Test: 2023–24.

### 5. One Model Per Stat
Do not build a multi-output model. Train separate XGBoost regressors for:
pts, reb, ast, stl, blk, to_committed, fg3m — one model per stat.
This enables independent feature sets and easier debugging per stat.

## Architecture Notes

### Data Pipeline
1. **Ingest** raw game logs via nba_api into PostgreSQL (seasons 2015+)
2. **Feature engineering** produces 60+ features per player-game: rolling averages (5/10/20 game), opponent defensive profiles, injury context, usage/role features, situational context
3. **Training** uses time-series walk-forward validation (never leak future data)
4. **Serving** via FastAPI with Redis caching (15-min TTL, refreshed on injury updates)
5. **Scheduling** via Airflow DAGs: daily data pull at 8 AM ET, predictions at 6 PM ET

### Key Design Decisions
- XGBoost over deep learning: tabular regression on <1M rows favors gradient boosted trees
- Opportunity Score (projected minutes x usage rate) is the single most predictive feature — must be recalculated at prediction time using current injury news
- Weight recent games 3x vs older games in training to handle role/age changes

## Naming Conventions

- Files: `snake_case.py`
- Classes: `PascalCase`
- Functions / variables: `snake_case`
- Constants: `UPPER_SNAKE_CASE`
- DB columns: `snake_case`
- MLflow experiment names: `tha_paint/{stat}/{model_type}` e.g. `tha_paint/pts/xgboost`
- MLflow run names: `{player_last_name}_{season}` e.g. `james_2024`
- API routes: `/v1/{resource}/{id}/{action}` e.g. `/v1/players/2544/predict`

## Environment Variables (see .env.example)

```
DATABASE_URL=postgresql+asyncpg://tha_paint:tha_paint@localhost:5432/tha_paint
REDIS_URL=redis://localhost:6379/0
ODDS_API_KEY=
MLFLOW_TRACKING_URI=http://localhost:5000
LOG_LEVEL=INFO
NBA_API_CACHE_DIR=.cache/nba_api
```

## Error Handling Patterns

- Raise custom exceptions from `tha_paint/exceptions.py`: `IngestError`, `FeatureError`, `PredictionError`
- Never swallow exceptions silently — always log before re-raising
- Use `structlog` for all logging (structured JSON logs)
- Retry logic: exponential backoff with jitter, max 5 retries, for all external API calls

## Testing Standards

- Every public function gets a pytest test
- Feature functions: test that `as_of_date` gate works correctly (no future data leaks)
- Ingestion: test with mocked nba_api responses (never hit real API in tests)
- API: use `httpx.AsyncClient` with the FastAPI test client
- Minimum coverage target: 80%

## Key Reference Numbers

- Target PTS MAE: ≤ 5.0 (Vegas baseline ~4.5)
- Target REB MAE: ≤ 2.5
- Target AST MAE: ≤ 2.0
- Target 3PM MAE: ≤ 1.2
- Target Team Total MAE: ≤ 8.0
- API latency target: < 500ms p99
- Training data: 2015–2024 seasons (~9 seasons, ~1.2M player-game rows)
- Active players tracked: top 150 by minutes per game

## Skills Available

Read these before working on the relevant module:

- `.claude/skills/data-ingestion/SKILL.md` — nba_api patterns, backoff, caching, upserts
- `.claude/skills/feature-engineering/SKILL.md` — rolling windows, as_of_date gate, opponent features
- `.claude/skills/model-training/SKILL.md` — XGBoost setup, walk-forward CV, MLflow logging
- `.claude/skills/mlflow-tracking/SKILL.md` — experiment naming, artifact logging, model registry
- `.claude/skills/api-patterns/SKILL.md` — FastAPI route patterns, response schemas, caching

## Development Phases

The project follows 8 phases: (1) Data Infrastructure, (2) Feature Engineering Pipeline, (3) Baseline ML Models, (4) Prediction API, (5) Betting & Fantasy Modules, (6) Dashboard UI, (7) Automation & Monitoring, (8) Ensemble & Tuning.
