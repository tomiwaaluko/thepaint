# Chalk - Project Overview

## Project Purpose

**Chalk is a machine learning system** for NBA player, team, prop, and fantasy projections. It ingests sports data, engineers time-aware prediction features, trains stat-specific models, and serves model outputs through a FastAPI backend and a Vite + React + TypeScript dashboard. The Python package is `chalk`; the frontend lives in `dashboard/`.

The current production-facing NBA surface supports:

1. **Player stat predictions** for PTS, REB, AST, STL, BLK, turnovers, and 3PM.
2. **Team and game projections** for matchup-level slate analysis.
3. **Over/under probability and edge views** against stored sportsbook lines.
4. **Fantasy projections** for DraftKings, FanDuel, and Yahoo-style scoring.
5. **Daily slate discovery** with cache-aware fallback ingestion for NBA scoreboard data.

The repository has also started a second-sport expansion. MLB slice 1 is implemented as a data foundation only: schema, StatsAPI fetcher, validation helpers, resumable backfill, and a cron-ready daily ingest runner. MLB feature engineering, models, API routes, betting views, and fantasy views are planned follow-up work.

## Current State

Chalk includes working machine learning and product foundations for:

- NBA data ingestion from `nba_api`, CDN scoreboard fallback, odds ingestion, and Gemini-backed injury ingestion.
- PostgreSQL schemas and Alembic migrations for NBA prediction data, betting lines, injury reports, predictions, and MLB data tables.
- Feature engineering with rolling, opponent, situational, roster, usage, and Vegas-line features.
- Per-stat model training with XGBoost/LightGBM, quantile outputs, ensemble and tuning modules, MLflow registry integration, and baseline evaluation tooling.
- FastAPI routes under `/v1` with Redis-backed response caching.
- React dashboard views for slate, player cards, stat distributions, prop edges, fantasy projections, and injury status.
- Railway deployment configs for the API/prediction and ingestion services, plus a separate dashboard deploy config.
- Local Airflow DAGs for daily ingest, prediction, and monitoring workflows.
- A pytest suite covering API behavior, ingestion, feature engineering, models, monitoring, DAG structure, betting/fantasy logic, and MLB ingestion foundations.

## Tech Stack

| Layer | Technology | Role |
| --- | --- | --- |
| Backend | Python 3.11+, FastAPI, pydantic-settings, structlog | API, config, service lifecycle, logging |
| Database | PostgreSQL, SQLAlchemy 2.0 async, Alembic | Relational storage, migrations, async data access |
| Cache | Redis asyncio | Prediction, slate, prop, fantasy, and API-response caching |
| Data ingestion | `nba_api`, `httpx`, ESPN injury data, Gemini, MLB StatsAPI | NBA logs/scoreboards, odds, injuries, MLB schedules and boxscores |
| Data processing | pandas, polars, numpy | Feature construction, ingestion transforms, model inputs |
| Modeling | scikit-learn, XGBoost, LightGBM, MAPIE, Optuna, MLflow | Training, intervals, tuning, registry/artifacts |
| Frontend | React, TypeScript, Vite, Recharts | Dashboard UI and visualization |
| Scheduling | Railway cron services, Apache Airflow | Production jobs and local orchestration |
| Testing | pytest, pytest-asyncio, httpx test client | Backend, async route, ingestion, and model tests |
| Deployment | Docker, Docker Compose, Railway | Local stack and production services |

## Repository Layout

```text
chalk/
  api/
    main.py                # FastAPI app, middleware, exception handlers, model warmup
    routes/                # health, players, teams, games, props, fantasy
    schemas.py             # API response/request models
    schemas_betting.py     # fantasy/betting response models
  betting/                 # edge and over/under probability utilities
  db/                      # shared SQLAlchemy Base, NBA tables, session factory
  fantasy/                 # platform scoring and fantasy simulations
  features/                # rolling, opponent, situational, roster, usage, Vegas features
  ingestion/               # NBA, odds, injury, seed ingestion
  mlb/                     # MLB StatsAPI fetcher, ORM models, validation
  models/                  # trainers, registry, quantile, ensemble, tuning, validation
  monitoring/              # drift and alert helpers
  predictions/             # player/team prediction engines and distributions

dashboard/
  src/                     # Vite + React + TypeScript dashboard
  public/chalk.svg         # dashboard asset
  railway.toml             # dashboard deploy config

tests/
  test_api/                # route and schema tests
  test_betting/            # prop edge tests
  test_dags/               # Airflow DAG structure tests
  test_fantasy/            # scoring tests
  test_features/           # feature generation tests
  test_ingestion/          # NBA, odds, injury, Railway ingestion tests
  test_mlb/                # MLB schema/fetcher/backfill/daily ingest tests
  test_models/             # trainers, tuning, validation, ensemble tests
  test_monitoring/         # drift and alert tests

scripts/                  # backfills, Railway jobs, training, evaluation, handoff helpers
airflow/dags/             # local daily ingest, daily predict, monitoring DAGs
alembic/versions/         # database migrations, including MLB tables
docs/                     # roadmap, handoff, accuracy plan, solution logs, images
models/                   # serialized model artifacts
specs/                    # branch/feature implementation specs
docker-compose.yml        # local full stack
Dockerfile                # backend service image
pyproject.toml            # package manifest, package name: chalk
```

## API Surface

The FastAPI app is created in `chalk/api/main.py`, with OpenAPI docs at `/docs`. Routes are versioned under `/v1` except the health route, which is included by its router configuration.

Key routes:

- `GET /v1/players/{player_id}/predict` - player statline prediction for a game.
- `GET /v1/players/{player_id}/history` - recent player game logs.
- `GET /v1/teams/{team_id}/predict` - team projection for a game.
- `GET /v1/games/today` - today's slate, with tomorrow fallback after 11 PM ET.
- `GET /v1/games/{game_id}/predict` - game-level prediction with roster fallback.
- `DELETE /v1/games/{game_id}/cache` - token-protected game cache invalidation.
- `GET /v1/players/{player_id}/props` - prop probabilities and edge against latest stored lines.
- `GET /v1/players/{player_id}/fantasy` - player fantasy projection.
- `GET /v1/games/{game_id}/fantasy` - game fantasy slate projection.

On startup, the API attempts to warm model artifacts for `pts`, `reb`, `ast`, `fg3m`, `stl`, `blk`, and `to_committed` through `chalk.models.registry.load_model`. Startup continues if a model is unavailable, but the condition is logged.

## Data Model

NBA tables live in `chalk/db/models.py`:

- `teams`, `players`, `games`
- `player_game_logs`, `team_game_logs`
- `injuries`
- `betting_lines`
- `predictions`

Recent NBA-specific schema behavior includes:

- `games` has a matchup uniqueness constraint on `(date, home_team_id, away_team_id)`.
- `games.is_playoffs` tracks playoff status from NBA game IDs.
- `betting_lines` uniqueness is scoped by game, player, market, and sportsbook so player props do not overwrite each other.
- injury rows include Gemini/ESPN extraction fields such as description/source context.

MLB tables live in `chalk/mlb/models.py` and share the same SQLAlchemy `Base`:

- `mlb_teams`, `mlb_players`, `mlb_games`
- `mlb_batter_game_logs`, `mlb_pitcher_game_logs`

MLB schema decisions already implemented:

- `game_pk` is the primary game identity because doubleheaders make date/team identity unsafe.
- `game_number` participates in matchup uniqueness for doubleheaders.
- batter and pitcher game logs are separate so two-way players can have one row in each table for the same game.
- pitcher innings are stored as integer `outs_recorded`, not decimal innings.
- `abstract_state` stores the canonical MLB finality signal.

## Ingestion and Jobs

NBA ingestion:

- `chalk/ingestion/nba_fetcher.py` handles NBA API calls, backoff, caching, scoreboard fallback, player/team logs, playoff support, and idempotent upserts.
- `chalk/ingestion/odds_fetcher.py` resolves and stores betting lines.
- `chalk/ingestion/injury_fetcher.py` uses ESPN injury data and Gemini extraction, then matches to database players before upsert.
- `scripts/railway_ingest.py` is the production-oriented ingest runner.

MLB ingestion:

- `chalk/mlb/fetcher.py` wraps MLB StatsAPI with async `httpx`, disk cache, retry/backoff, idempotent writes, and per-game failure isolation.
- `chalk/mlb/validate.py` provides warn-style row-count validation.
- `scripts/mlb_backfill.py` is a resumable historical backfill.
- `scripts/mlb_ingest_daily.py` is cron-ready but intentionally separate from the NBA ingest runner.

Training and evaluation:

- `scripts/train_all.py` trains the NBA model set.
- `scripts/train_ensemble.py` trains ensemble models.
- `scripts/evaluate_baseline.py` records baseline MAE/RMSE/bias before retraining.
- `scripts/validate_features.py` checks feature output behavior.

## Feature and Modeling Pipeline

`chalk/features/pipeline.py` builds player features from rolling history, opponent context, situational context, roster/injury availability, usage, and sparse Vegas-line context. The project guardrail is that prediction-time features must be gated by `as_of_date` and only use information available before the prediction point.

Modeling modules include:

- `base.py` for shared trainer behavior.
- `player.py` and `team.py` for core stat models.
- `lgbm.py` for LightGBM-specific training.
- `quantile.py` and `predictions/distributions.py` for interval and distribution outputs.
- `ensemble.py` for blended model outputs.
- `tuning.py` for Optuna search.
- `validation.py` for cross-validation/backtesting utilities.
- `registry.py` for MLflow artifact loading/logging.

The API and dashboard currently consume NBA predictions. MLB has data ingestion and persistence in place, but feature/model/API/dashboard work is still future scope.

## Frontend

The dashboard lives in `dashboard/` and is intentionally separate from the FastAPI app. It uses React, TypeScript, Vite, and Recharts.

Current UI modules include:

- landing/dashboard shell in `App.tsx` and `pages/LandingPage.tsx`
- slate views and game detail cards
- player prediction cards
- stat distribution charts
- props board
- fantasy board
- injury badge/status display
- typed API client and shared Chalk types

Production hosting keeps the dashboard separate from the backend API service.

## Local Development

### Backend

```bash
pip install -e ".[dev]"
copy .env.example .env
alembic upgrade head
uvicorn chalk.api.main:app --reload --port 8000
```

Open API docs at:

```text
http://localhost:8000/docs
```

### Frontend

```bash
cd dashboard
npm install
npm run dev
```

### Full Stack

```bash
docker compose up
```

## Common Commands

```bash
pytest tests/ -v
pytest tests/test_api/ -v
pytest tests/test_ingestion/ -v
pytest tests/test_features/ -v
pytest tests/test_mlb/ -v
```

```bash
cd dashboard
npm run lint
npm run build
```

```bash
python scripts/railway_ingest.py
python scripts/railway_predict.py
python scripts/mlb_ingest_daily.py
python scripts/evaluate_baseline.py --season 2024-25 --stats pts reb ast fg3m
```

## Deployment

Production deploy target is Railway.

Relevant configs:

- `railway.ingest.json` - NBA ingestion service.
- `railway.predict.json` - prediction/API service.
- `railway.mlb_ingest.json` - MLB daily ingest service config.
- `dashboard/railway.toml` - dashboard service config.
- `Dockerfile` - backend image.
- `Procfile` - process declaration compatibility.

The project currently uses separate services for user-facing prediction traffic and scheduled ingestion work so long-running data jobs do not share the API process.

## Testing Status

The test suite is broad and currently organized around:

- API routes and schemas
- betting/over-under logic
- fantasy scoring
- feature modules
- NBA ingestion
- MLB fetcher/schema/backfill/daily ingest behavior
- model trainers, validation, tuning, and ensembles
- monitoring/drift alerts
- Airflow DAG structure

Recent project notes report a full-suite baseline around the low 300s of passing tests after the MLB data-foundation slice, with one previously documented timezone-sensitive NBA slate test flake in a narrow post-midnight UTC window. Run the current suite locally before relying on that historical count.

## Implementation Decisions

### Separate prediction and ingestion services

Railway runs prediction/API traffic separately from cron-style ingestion. This keeps CPU-heavy backfill or refresh jobs from affecting API latency.

### Per-stat NBA models

Chalk keeps stat-specific models rather than one broad multi-output model. PTS, REB, AST, 3PM, steals, blocks, and turnovers have different predictive signals, so separate models allow targeted feature importance, tuning, and validation.

### `as_of_date` as a leakage boundary

Feature generation is expected to use only rows available before the prediction date. This is especially important for rolling windows, injury status, Vegas lines, and future MLB features.

### Additive MLB expansion

MLB was added under `chalk/mlb/` instead of moving existing NBA code into a new namespace. That keeps the first slice low-risk: shared DB/config/exceptions, new sport-specific package, and no disruption to active NBA prediction routes.

### Dashboard remains independent

The React dashboard is deployed separately from FastAPI. The API stays focused on JSON serving and model inference; the frontend can build and deploy independently.

## Resume Bullet Points

- Built Chalk, a full-stack NBA prediction platform using FastAPI, PostgreSQL, Redis, XGBoost/LightGBM, MLflow, and a React/TypeScript dashboard to deliver player stat, game, prop-edge, and fantasy projections.
- Engineered time-aware prediction features across rolling production, opponent matchup, situation, roster/injury context, usage, and Vegas lines, with an `as_of_date` guardrail to prevent data leakage.
- Implemented production-oriented ingestion and deployment workflows with Railway cron services, local Airflow DAGs, idempotent database upserts, Redis caching, and a broad pytest suite spanning API, ingestion, features, models, monitoring, fantasy, betting, and MLB data foundations.
- Added MLB expansion slice 1 with official StatsAPI ingestion, doubleheader-safe schema design, separate batter/pitcher logs for two-way players, resumable backfill, daily ingest runner, and validation coverage, ready for future MLB feature/model work.
