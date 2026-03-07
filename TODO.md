# The Paint — Project TODO

## How to Use This File
At the start of every Claude Code session, read this file and the current phase file.
When a task is completed, update the checkbox here before stopping.
Never mark a task done unless tests pass and the acceptance criteria in the phase file are met.

---

## Current Status

**Active Phase:** Phase 3 — Baseline ML Models
**Current Task:** Training runs (Steps 1-8 code complete, running model training)
**Last Updated:** Session 5

---

## Session Kickoff Prompt

Paste this at the start of every Claude Code session:

```
Read CLAUDE.md, TODO.md, and the current phase file listed in TODO.md.
Continue from the current task. When you finish a task, mark it complete
in TODO.md and run any relevant tests before stopping.
```

---

## Phase Overview

| Phase | Name | Status | Phase File |
|---|---|---|---|
| 1 | Data Infrastructure | ✅ Complete | `.claude/phases/phase-1-data-infrastructure.md` |
| 2 | Feature Engineering | ✅ Complete | `.claude/phases/phase-2-feature-engineering.md` |
| 3 | Baseline ML Models | 🔄 In Progress | `.claude/phases/phase-3-baseline-models.md` |
| 4 | Prediction API | ⏳ Not Started | `.claude/phases/phase-4-prediction-api.md` |
| 5 | Betting & Fantasy | ⏳ Not Started | `.claude/phases/phase-5-betting-fantasy.md` |
| 6 | Dashboard UI | ⏳ Not Started | `.claude/phases/phase-6-dashboard.md` |
| 7 | Automation & Monitoring | ⏳ Not Started | `.claude/phases/phase-7-automation.md` |
| 8 | Ensemble & Tuning | ⏳ Not Started | `.claude/phases/phase-8-ensemble-tuning.md` |

---

## Phase 1 — Data Infrastructure
**Phase File:** `.claude/phases/phase-1-data-infrastructure.md`
**Goal:** PostgreSQL DB running, nba_api ingestion working, 2015–2025 data backfilled.

- [x] Repo scaffold — pyproject.toml, Dockerfile, docker-compose.yml, .env.example
- [x] Database session setup — chalk/db/session.py
- [x] ORM models — chalk/db/models.py
- [x] Alembic migrations — initial schema
- [x] Custom exceptions — chalk/exceptions.py
- [x] App config — chalk/config.py
- [x] NBAFetcher — chalk/ingestion/nba_fetcher.py
- [x] Player game log ingestion — ingest_player_season()
- [x] Team game log ingestion — ingest_team_season()
- [x] Injury feed ingestion — chalk/ingestion/injury_fetcher.py
- [x] Odds API ingestion — chalk/ingestion/odds_fetcher.py
- [x] Backfill script — scripts/backfill.py
- [x] Ingestion tests — tests/test_ingestion/ (25 tests passing)
- [x] Validate backfill — complete (127,171 player rows, 23,958 team rows, 11,979 games, 450 players, 30 teams). Query perf: 0.312ms for last-30-games (target <100ms). All 5300/5300 player-season requests done.

**Phase 1 Done When:** `docker compose up` works, migrations run clean, backfill script populates all tables, any player's last 30 game logs queryable in < 100ms.

---

## Phase 2 — Feature Engineering
**Phase File:** `.claude/phases/phase-2-feature-engineering.md`
**Goal:** generate_features(player_id, game_id, as_of_date) returns a validated 80+ feature dict.

- [x] Rolling window averages — chalk/features/rolling.py (15 tests passing)
- [x] Opponent defensive features — chalk/features/opponent.py (11 tests passing)
- [x] Situational features — chalk/features/situational.py
- [x] Roster/injury context features — chalk/features/roster.py
- [x] Usage & role features — chalk/features/usage.py
- [x] Master feature pipeline — chalk/features/pipeline.py (74 features, as_of_date gated)
- [x] Feature tests — tests/test_features/ (34 tests passing, incl. as_of_date gate tests)
- [x] Feature validation script — scripts/validate_features.py

**Phase 2 Done When:** generate_features() returns 80+ float features with zero None values, as_of_date leakage tests pass, feature matrix builds for 150 players across 2023-24 season in < 5 minutes.

---

## Phase 3 — Baseline ML Models
**Phase File:** `.claude/phases/phase-3-baseline-models.md`
**Goal:** Trained XGBoost models for pts, reb, ast, fg3m hitting MAE targets on 2023-24 holdout.

- [x] Base trainer class — chalk/models/base.py
- [x] Walk-forward CV utility — chalk/models/validation.py
- [x] Player stat models — chalk/models/player.py
- [x] Team total model — chalk/models/team.py
- [x] MLflow experiment setup — chalk/models/registry.py
- [x] Quantile models for pts, reb, ast — chalk/models/quantile.py
- [x] Full training script — scripts/train_all.py
- [x] Model tests — tests/test_models/ (17 tests passing)
- [x] Training run: pts model ≤ 5.0 MAE — achieved 4.94 test MAE
- [x] Training run: reb model ≤ 2.5 MAE — achieved 2.02 test MAE
- [x] Training run: ast model ≤ 2.0 MAE — achieved 1.47 test MAE
- [x] Training run: fg3m model ≤ 1.2 MAE — achieved 0.94 test MAE
- [ ] Training run: team total model ≤ 8.0 MAE — at 15.4 MAE, needs external data (Vegas lines, injuries)

**Phase 3 Done When:** All 5 models registered in MLflow, MAE targets met on 2023-24 test set, feature importance top 10 reviewed and makes basketball sense.

---

## Phase 4 — Prediction API
**Phase File:** `.claude/phases/phase-4-prediction-api.md`
**Goal:** FastAPI service returning full predicted statlines with confidence intervals in < 500ms.

- [ ] FastAPI app setup — the_paint/api/main.py
- [ ] Shared dependencies — the_paint/api/dependencies.py
- [ ] Pydantic response schemas — the_paint/api/schemas.py
- [ ] Player prediction engine — the_paint/predictions/player.py
- [ ] Team prediction engine — the_paint/predictions/team.py
- [ ] Distribution builder — the_paint/predictions/distributions.py
- [ ] Player prediction route — the_paint/api/routes/players.py
- [ ] Team prediction route — the_paint/api/routes/teams.py
- [ ] Game prediction route — the_paint/api/routes/games.py
- [ ] Health check route — the_paint/api/routes/health.py
- [ ] Redis caching layer
- [ ] API tests — tests/test_api/
- [ ] Load test — p99 latency < 500ms

**Phase 4 Done When:** /v1/players/{id}/predict returns full statline + confidence intervals, Redis cache working, all routes return correct schemas, p99 < 500ms.

---

## Phase 5 — Betting & Fantasy
**Phase File:** `.claude/phases/phase-5-betting-fantasy.md`
**Goal:** O/U probabilities vs. Vegas lines, DK/FD/Yahoo fantasy scores, edge calculation.

- [ ] Over/under probability module — the_paint/betting/over_under.py
- [ ] Edge calculation vs. implied odds — the_paint/betting/edge.py
- [ ] Fantasy scoring engine — the_paint/fantasy/scoring.py
- [ ] Monte Carlo simulation for floor/ceiling — the_paint/fantasy/simulation.py
- [ ] Props API route — the_paint/api/routes/props.py
- [ ] Fantasy API route — the_paint/api/routes/fantasy.py
- [ ] Betting + fantasy tests

**Phase 5 Done When:** /v1/players/{id}/props returns O/U probability + edge for any Vegas line, fantasy scores computed for all three platforms, Monte Carlo floor/ceiling working.

---

## Phase 6 — Dashboard UI
**Phase File:** `.claude/phases/phase-6-dashboard.md`
**Goal:** React dashboard showing today's slate, predictions, O/U comparison, fantasy value plays.

- [ ] React app scaffold — dashboard/
- [ ] Today's games view
- [ ] Player prediction card component
- [ ] Stat distribution chart (p10–p90 range bar)
- [ ] O/U line comparison view
- [ ] Fantasy value rankings table
- [ ] Injury context indicators
- [ ] Auto-refresh on injury updates

**Phase 6 Done When:** Dashboard loads today's full slate, shows predictions with confidence bands, highlights high-edge plays, updates when injury status changes.

---

## Phase 7 — Automation & Monitoring
**Phase File:** `.claude/phases/phase-7-automation.md`
**Goal:** Daily Airflow pipelines running unattended, model drift alerts in place.

- [ ] Daily ingest DAG — airflow/dags/daily_ingest.py
- [ ] Daily predict DAG — airflow/dags/daily_predict.py
- [ ] Model drift monitoring — checks MAE on rolling 30-day window
- [ ] Slack/email alert on drift > 15%
- [ ] Airflow Docker setup in docker-compose.yml
- [ ] DAG tests

**Phase 7 Done When:** Both DAGs run end-to-end unattended, drift monitor alerts fire correctly in test, predictions available by 6 PM ET on game days.

---

## Phase 8 — Ensemble & Tuning
**Phase File:** `.claude/phases/phase-8-ensemble-tuning.md`
**Goal:** Stacked ensemble, Optuna hyperparameter search, edge tracking over time.

- [ ] Optuna hyperparameter search for each stat model
- [ ] LightGBM models as XGBoost alternatives
- [ ] Stacking meta-learner — blends XGBoost + LightGBM + historical median
- [ ] Edge tracking dashboard — model edge vs. closing line value over time
- [ ] Monthly retraining job
- [ ] Final MAE benchmarks vs. Vegas closing line accuracy

**Phase 8 Done When:** Ensemble MAE improves ≥ 2% over best single model, edge tracking shows positive CLV on held-out games.

---

## Decisions Log

Track every significant architectural decision here so future sessions don't re-litigate them.

| Decision | Choice | Reason | Date |
|---|---|---|---|
| ML framework | XGBoost + LightGBM | Best-in-class for tabular sports data, interpretable | Pre-build |
| Validation strategy | Walk-forward time-series CV | Prevents future data leakage | Pre-build |
| DB | PostgreSQL + TimescaleDB | Time-series optimized, free | Pre-build |
| API framework | FastAPI async | Performance, async-native | Pre-build |
| Model structure | One model per stat | Easier debugging, independent feature sets | Pre-build |
| Project name | The Paint | Betting slang for the court / paint area; clean brand | Pre-build |

---

## Open Questions

- [ ] Which sportsbooks to integrate beyond Odds API? (DraftKings, FanDuel direct feeds?)
- [ ] Track playoff games separately or include in training data?
- [ ] Player prop markets beyond PTS/REB/AST — (first basket, double-double, etc.)?
- [ ] Mobile app eventually or web dashboard only?

---

## Blockers

None currently.
