# Tha Paint — NBA Statline Predictor — Project Overview

## Project Purpose

**Tha Paint** (Python package: `chalk`) is a machine learning system that predicts NBA player and team statlines for any given matchup. It powers four distinct outputs:

1. **Player stat predictions** — PTS, REB, AST, STL, BLK, TO, 3PM, FG% for a given player vs. a given opponent
2. **Team-level game projections** — total points, pace, offensive/defensive rating
3. **Over/under probability distributions** — for sports betting analysis, with edge calculations against posted lines
4. **Fantasy scoring projections** — DraftKings, FanDuel, and Yahoo formats

The system ingests raw data from the NBA API, live odds, and injury reports, runs it through scikit-learn feature pipelines, and serves predictions via a FastAPI REST API. A React dashboard with Recharts visualizes the outputs. The backend is deployed on Railway with cron-based scheduled ingestion; Apache Airflow is used locally.

---

## Tech Stack & Rationale

| Layer | Technology | Role |
|---|---|---|
| Language | Python 3.11+ | Entire backend, ML, and ingestion |
| Database | PostgreSQL 15 + TimescaleDB | Time-series player/game data with efficient range queries |
| ORM / Migrations | SQLAlchemy 2.0 + Alembic | Type-safe async ORM; Alembic for schema versioning |
| Data Processing | pandas + polars | pandas for exploratory/feature work; polars for high-throughput ingestion paths |
| Feature Pipelines | scikit-learn Pipelines | Composable, serializable feature transformers |
| ML Models | XGBoost + LightGBM | Gradient boosting; XGBoost for player models, LightGBM for team/pace models |
| Probabilistic Output | MAPIE + quantile regression | Generates calibrated confidence intervals for O/U probability distributions |
| Experiment Tracking | MLflow | Model registry, artifact storage, run comparison |
| Hyperparameter Tuning | Optuna | Bayesian optimization with pruning; `optuna.db` SQLite for local study persistence |
| API | FastAPI (async) | OpenAPI docs at `/docs`; `asynccontextmanager` lifespan for model warm-up on startup |
| Caching | Redis (asyncio) | Per-prediction and per-feature caching to avoid repeated NBA API calls |
| Task Scheduling | Railway Cron Jobs (prod) / Apache Airflow (local) | Daily ingestion, weekly retraining |
| Frontend | React + Recharts + Vite | Dashboard for visualizing predictions; TypeScript |
| Containerization | Docker + Docker Compose | Full-stack local dev; separate Railway service configs (`railway.ingest.json`, `railway.predict.json`) |
| Testing | pytest + pytest-asyncio | Async test support for SQLAlchemy sessions and API routes |

**Why XGBoost + LightGBM over deep learning:** NBA stat prediction is a tabular regression problem with moderate data volume (~30 seasons × 1,200 games). Gradient boosting is faster to train, more interpretable via feature importance, and less prone to overfitting than deep models on this data size. MAPIE is layered on top to produce prediction intervals rather than point estimates.

---

## Architecture Overview

```
thepaint/
├── chalk/                      # Main Python package
│   ├── api/
│   │   ├── main.py             # FastAPI entry point; lifespan model pre-load; CORS middleware
│   │   └── routes/
│   │       ├── health.py       # /health liveness probe
│   │       ├── players.py      # /players — stat predictions + distributions
│   │       ├── teams.py        # /teams — team projections
│   │       ├── games.py        # /games — upcoming matchup lookup
│   │       ├── props.py        # /props — O/U edge calculation
│   │       └── fantasy.py      # /fantasy — DK/FD/Yahoo scoring projections
│   ├── config.py               # pydantic-settings Settings class; reads env vars
│   ├── db/
│   │   ├── session.py          # Async SQLAlchemy engine + session factory
│   │   └── models.py           # ORM table definitions
│   ├── ingestion/
│   │   ├── nba_fetcher.py      # nba_api wrapper with exponential backoff + Redis caching
│   │   ├── odds_fetcher.py     # Odds API integration (posted lines)
│   │   └── injury_fetcher.py   # Injury report ingestion
│   ├── features/
│   │   ├── rolling.py          # Rolling window averages (3g, 5g, 10g, season)
│   │   ├── opponent.py         # Opponent defensive profile (pts allowed per position, DRTG)
│   │   ├── situational.py      # Rest days, home/away, back-to-back flags
│   │   ├── roster.py           # Injury/teammate availability impact features
│   │   ├── usage.py            # Usage rate and minute-share features
│   │   └── pipeline.py         # Master feature pipeline (chains all feature modules)
│   ├── models/
│   │   ├── base.py             # Abstract base trainer class
│   │   ├── player.py           # Per-stat player models (separate model per: pts, reb, ast, fg3m)
│   │   ├── team.py             # Team total / pace models
│   │   ├── ensemble.py         # Ensemble combiner (blends XGBoost + LightGBM outputs)
│   │   ├── lgbm.py             # LightGBM-specific trainer
│   │   ├── quantile.py         # Quantile regression for prediction intervals
│   │   ├── tuning.py           # Optuna-based hyperparameter search
│   │   ├── validation.py       # Cross-validation and backtesting utilities
│   │   └── registry.py         # MLflow model registry helpers (load_model, log_model)
│   ├── predictions/
│   │   ├── player.py           # Player prediction engine (features → model → distribution)
│   │   ├── team.py             # Team prediction engine
│   │   └── distributions.py    # Quantile outputs → calibrated O/U probability distributions
│   ├── betting/
│   │   └── over_under.py       # O/U probability + edge calculation vs. posted lines
│   ├── fantasy/                # DraftKings/FanDuel/Yahoo scoring formulas
│   └── monitoring/             # Prediction logging, accuracy tracking
├── dashboard/                  # React + Recharts + Vite frontend
│   ├── src/
│   └── dist/                   # Built assets
├── alembic/                    # Database migrations
│   └── versions/
├── scripts/                    # One-off ingestion and training scripts
├── tests/                      # pytest test suite
├── airflow/                    # Local DAG definitions (daily ingest, weekly retrain)
├── docker-compose.yml          # Full local stack (PostgreSQL + Redis + API + Dashboard)
├── Dockerfile                  # API service image
├── Procfile                    # Railway process declarations
├── railway.ingest.json         # Railway ingestion service config
├── railway.predict.json        # Railway prediction service config
└── pyproject.toml              # Package manifest (name: "chalk")
```

### API on Startup
`chalk/api/main.py` uses a `@asynccontextmanager` lifespan function that pre-loads all four stat models (`pts`, `reb`, `ast`, `fg3m`) into the in-process model registry cache before the API begins serving traffic. This eliminates cold-start latency on the first prediction request.

### Feature Pipeline
`chalk/features/pipeline.py` assembles a master scikit-learn `Pipeline` that chains all feature modules in sequence: rolling stats → opponent profile → situational context → roster availability → usage rates. The pipeline is fit once on training data and serialized with the model artifact in MLflow.

### Model Registry
`chalk/models/registry.py` wraps MLflow's model registry. `load_model(stat)` fetches the production-tagged model artifact for a given stat type. The lifespan hook calls this for all four stats at startup, storing them in a module-level dict so route handlers never hit MLflow at request time.

---

## Setup & Install Steps

### Prerequisites
- Python 3.11+, Docker + Docker Compose, Railway CLI (optional, for deployment)

### Local Development (Docker)

```bash
git clone https://github.com/tomiwaaluko/thepaint.git
cd thepaint
cp .env.example .env
# Fill in: DATABASE_URL, REDIS_URL, NBA_API_KEY, ODDS_API_KEY, MLFLOW_TRACKING_URI, ALLOWED_ORIGINS
docker compose up
# API: http://localhost:8000/docs
# Dashboard: http://localhost:5173
```

### Local Development (manual)

```bash
pip install -e ".[dev]"
# Start PostgreSQL + Redis locally, then:
alembic upgrade head          # apply DB migrations
uvicorn chalk.api.main:app --reload --port 8000
# Dashboard:
cd dashboard && npm install && npm run dev
```

### Running Ingestion

```bash
python -m chalk.ingestion.nba_fetcher     # ingest today's games + player logs
python -m chalk.ingestion.odds_fetcher    # ingest current O/U lines
```

### Training a Model

```bash
python scripts/train_player_model.py --stat pts
# Logs to MLflow; promotes best run to "production" in registry
```

### Running Tests

```bash
pytest tests/ -v
pytest tests/ --asyncio-mode=auto
```

---

## Notable Implementation Decisions

### Separate Railway services for ingestion and prediction
`railway.ingest.json` and `railway.predict.json` define two separate Railway services running from the same repo. The ingest service runs on a cron schedule (daily game logs, odds refresh) and has no HTTP port. The predict service runs the FastAPI app. This separation means the CPU-intensive data pipeline never shares process resources with the low-latency prediction API.

### Per-stat models rather than a single multi-output model
Each stat (pts, reb, ast, fg3m) has its own independently trained XGBoost/LightGBM model. A single multi-output model would be simpler but would share feature representations across stats that have very different predictors — assists are dominated by playmaker usage and lineup context, while 3PM is driven by shot selection and opponent perimeter defense. Independent models allow each to have its own hyperparameter search and feature subset.

### MAPIE for calibrated prediction intervals
Rather than reporting just a point estimate, the prediction engine produces an O/U probability distribution. MAPIE wraps the trained gradient boosting model and calibrates prediction intervals using conformal prediction theory. This allows the `/props` endpoint to report not just "predicted points: 24" but "80% confidence interval: [21, 27], implied over probability at line 23.5: 62%."

### Optuna with SQLite persistence
Hyperparameter tuning runs are stored in `optuna.db` (SQLite). This means tuning studies persist across sessions and can be resumed after interruption. In production, this would be migrated to a shared database, but for a solo project SQLite is sufficient and zero-ops.

### polars alongside pandas
`polars` is used specifically in the ingestion pipeline where large batches of game log rows need to be read and filtered quickly. `pandas` is used in the feature engineering and model training code where scikit-learn integration is needed (scikit-learn transformers don't accept polars DataFrames natively). The two coexist without conflict.

### Redis caching in `nba_fetcher.py`
The NBA API has aggressive rate limits and slow responses. `nba_fetcher.py` wraps every API call with a Redis cache keyed by the API endpoint + parameters. Cache TTL is set per endpoint type: player logs cache for 1 hour (updated nightly), static player/team metadata caches for 24 hours. This dramatically reduces API call volume during feature pipeline runs.

### Dashboard as a separate Vite app (not integrated into FastAPI)
The React dashboard lives in `dashboard/` and is built separately into `dist/`. In production, Railway serves the static files via its static-file hosting rather than embedding them in the FastAPI app. This keeps the API container lightweight and lets the dashboard deploy independently.
