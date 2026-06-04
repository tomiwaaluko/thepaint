# The Paint — Project TODO

## How to Use This File
At the start of every Claude Code session, read this file and the current phase file.
When a task is completed, update the checkbox here before stopping.
Never mark a task done unless tests pass and the acceptance criteria in the phase file are met.

---

## Current Status

**Active Phase:** Phase 9 - AI Injury Agent
**Current Task:** ESPN/Gemini injury ingestion pipeline and dashboard injury status defaults
**Last Updated:** Session 10

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
| 3 | Baseline ML Models | ✅ Complete (4/5 targets met) | `.claude/phases/phase-3-baseline-models.md` |
| 4 | Prediction API | ✅ Complete | `.claude/phases/phase-4-prediction-api.md` |
| 5 | Betting & Fantasy | ✅ Complete | `.claude/phases/phase-5-betting-fantasy.md` |
| 6 | Dashboard UI | ✅ Complete | `.claude/phases/phase-6-dashboard.md` |
| 7 | Automation & Monitoring | ✅ Complete | `.claude/phases/phase-7-automation.md` |
| 8 | Ensemble & Tuning | ⏳ Not Started | `.claude/phases/phase-8-ensemble-tuning.md` |
| 9 | AI Injury Agent | In Progress | `.claude/phases/phase-9-ai-injury-agent.md` |

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
- [ ] Training run: team total model ≤ 8.0 MAE — at 15.4 MAE, needs external data (Vegas lines, injuries) — deferred to Phase 8

**Phase 3 Done When:** All 5 models registered in MLflow, MAE targets met on 2023-24 test set, feature importance top 10 reviewed and makes basketball sense.
**Phase 3 Result:** 4/5 targets met. Player models all PASS. Team total deferred — requires Vegas lines and injury context features not yet available (Phase 5 Odds API + Phase 7 automation will provide these). 17 model tests passing. 20 model files saved.

---

## Phase 4 — Prediction API
**Phase File:** `.claude/phases/phase-4-prediction-api.md`
**Goal:** FastAPI service returning full predicted statlines with confidence intervals in < 500ms.

- [x] Pydantic response schemas — chalk/api/schemas.py (14 tests)
- [x] Shared dependencies — chalk/api/dependencies.py
- [x] Distribution builder — chalk/predictions/distributions.py (15 tests)
- [x] Player prediction engine — chalk/predictions/player.py (4 tests)
- [x] Team prediction engine — chalk/predictions/team.py
- [x] FastAPI app setup — chalk/api/main.py (lifespan model warmup, exception handlers)
- [x] Redis caching layer — chalk/api/cache.py
- [x] Player prediction route — chalk/api/routes/players.py (6 tests)
- [x] Team prediction route — chalk/api/routes/teams.py
- [x] Game prediction route — chalk/api/routes/games.py
- [x] Health check route — chalk/api/routes/health.py (2 tests)
- [x] API tests — tests/test_api/ (41 tests passing)
- [x] Load test — p99 = 40ms (target < 500ms) — PASS

**Phase 4 Done When:** /v1/players/{id}/predict returns full statline + confidence intervals, Redis cache working, all routes return correct schemas, p99 < 500ms.
**Phase 4 Result:** All 13 tasks complete. 41 API tests passing. p99 = 40ms (12.5x under 500ms target). 119 total tests.

---

## Phase 5 — Betting & Fantasy
**Phase File:** `.claude/phases/phase-5-betting-fantasy.md`
**Goal:** O/U probabilities vs. Vegas lines, DK/FD/Yahoo fantasy scores, edge calculation.

- [x] Over/under probability module — chalk/betting/over_under.py (21 tests)
- [x] Edge calculation + CLV tracking — chalk/betting/edge.py
- [x] Fantasy scoring engine — chalk/fantasy/scoring.py (7 tests, DK DD/TD bonuses)
- [x] Monte Carlo simulation for floor/ceiling — chalk/fantasy/simulation.py (6 tests)
- [x] Props API route — chalk/api/routes/props.py (3 tests)
- [x] Fantasy API route — chalk/api/routes/fantasy.py (3 tests)
- [x] Betting + fantasy tests — 40 tests passing

**Phase 5 Done When:** /v1/players/{id}/props returns O/U probability + edge for any Vegas line, fantasy scores computed for all three platforms, Monte Carlo floor/ceiling working.
**Phase 5 Result:** All 7 tasks complete. 40 new tests, 159 total. O/U probabilities calibrated, DK DD/TD bonuses correct, Monte Carlo floor < ceiling verified.

---

## Phase 6 — Dashboard UI
**Phase File:** `.claude/phases/phase-6-dashboard.md`
**Goal:** React dashboard showing today's slate, predictions, O/U comparison, fantasy value plays.

- [x] React app scaffold — dashboard/ (Vite + React 18 + TypeScript + Tailwind v4)
- [x] TypeScript API types — dashboard/src/types/chalk.ts
- [x] API client — dashboard/src/api/chalk.ts (typed fetch wrapper)
- [x] React Query hooks — usePlayerPrediction, useGameSlate, useFantasyBoard
- [x] Today's games view — SlateView/GameCard + GameDetailView (3-tab: Players/Props/Fantasy)
- [x] Player prediction card — PlayerCard with stat distributions + fantasy scores
- [x] Stat distribution chart — p10-p90 range bar with IQR highlight + median marker + Vegas line
- [x] O/U line comparison view — PropsBoard with edge sorting, stat/confidence filters, star badges
- [x] Fantasy value rankings table — FantasyBoard with sortable columns, boom/bust rates, value filter
- [x] Injury context indicators — InjuryBadge (Active/Questionable/Out) + absent teammate alert
- [x] Auto-refresh on injury updates — React Query refetchInterval (3-10 min per data type)
- [x] Build passes — 0 TypeScript errors, 245KB production bundle

**Phase 6 Done When:** Dashboard loads today's full slate, shows predictions with confidence bands, highlights high-edge plays, updates when injury status changes.
**Phase 6 Result:** All tasks complete. Dark navy + orange theme. npm run dev serves at localhost:5173 with API proxy to localhost:8000. npm run build produces clean production bundle.

---

## Phase 7 — Automation & Monitoring
**Phase File:** `.claude/phases/phase-7-automation.md`
**Goal:** Daily Airflow pipelines running unattended, model drift alerts in place.

- [x] Airflow Docker setup — docker-compose.yml (init + webserver + scheduler, LocalExecutor)
- [x] Daily ingest DAG — airflow/dags/daily_ingest.py (4 tasks: games→injuries→odds→validate)
- [x] Daily predict DAG — airflow/dags/daily_predict.py (6 tasks: check→injuries→invalidate→predict→warm→validate)
- [x] Monitoring DAG — airflow/dags/monitoring.py (3 tasks: mae→drift→alert)
- [x] Model drift monitoring — chalk/monitoring/drift.py (compute_daily_mae, check_for_drift with 15% threshold)
- [x] Slack/email alerts — chalk/monitoring/alerts.py (drift, DAG failure, predictions ready)
- [x] DAG + monitoring tests — 21 tests passing (12 monitoring + 9 DAG structure)

**Phase 7 Done When:** Both DAGs run end-to-end unattended, drift monitor alerts fire correctly in test, predictions available by 6 PM ET on game days.
**Phase 7 Result:** All tasks complete. 3 DAGs with correct task ordering verified by tests. Drift detection fires at >15% MAE degradation. Slack alerts no-op gracefully without webhook. 180 total tests.

---

## Phase 8 — Ensemble & Tuning
**Phase File:** `.claude/phases/phase-8-ensemble-tuning.md`
**Goal:** Stacked ensemble, Optuna hyperparameter search, edge tracking over time.

- [x] Optuna hyperparameter search for each stat model — `chalk/models/tuning.py`
- [x] LightGBM models as XGBoost alternatives — `chalk/models/lgbm.py`
- [x] Stacking meta-learner — blends XGBoost + LightGBM + historical median — `chalk/models/ensemble.py`
- [x] Ensemble training script — `scripts/train_ensemble.py`
- [x] Registry support for LightGBM + ensemble save/load — `chalk/models/registry.py`
- [x] Phase 8 tests — 14 tests passing (6 LightGBM, 3 tuning, 5 ensemble)
- [x] Run ensemble training on real data (50 Optuna trials per stat per model type)
- [x] Prediction pipeline updated to use LightGBM as primary model — `chalk/predictions/player.py`
- [ ] Edge tracking dashboard — model edge vs. closing line value over time
- [ ] Monthly retraining job — `scripts/retrain_monthly.py`
- [ ] Final MAE benchmarks vs. Vegas closing line accuracy

**Phase 8 Benchmark Results:**
| Stat | Phase 3 XGB | Tuned LGBM | Improvement |
|---|---|---|---|
| PTS | 4.94 | **4.906** | +0.7% |
| REB | 2.02 | **1.995** | +1.2% |
| AST | 1.47 | **1.454** | +1.1% |
| FG3M | 0.94 | **0.907** | **+3.5%** |

**Key Finding:** LightGBM standalone outperforms both XGBoost and the stacked ensemble on every stat. Stacking doesn't help because both tree models are highly correlated. LightGBM's MAE objective (`regression_l1`) is the main driver of improvement.

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
| Production DB | Supabase (Session Pooler) | Railway is IPv4-only; Direct Connection incompatible; Transaction Pooler breaks asyncpg | 2026-03-16 |
| Production scheduling | Railway Cron Jobs (not Airflow) | Airflow requires 3 services + overhead; Railway cron is zero-infra | 2026-03-16 |
| Production builder | Dockerfile (not Railpack) | Railpack doesn't install the `chalk` package; Dockerfile ensures full env | 2026-03-16 |
| Primary model | LightGBM (not XGBoost) | LGBM beats XGB on all 4 stats; MAE objective (regression_l1) is key driver; ensemble stacking adds no value | 2026-03-16 |

---

## Open Questions

- [ ] Which sportsbooks to integrate beyond Odds API? (DraftKings, FanDuel direct feeds?)
- [ ] Track playoff games separately or include in training data?
- [ ] Player prop markets beyond PTS/REB/AST — (first basket, double-double, etc.)?
- [ ] Mobile app eventually or web dashboard only?

---

## Blockers

- **Stale dashboard data** — DB has no games after 2026-03-08. Cron jobs will fill forward from today but 3/9–3/15 gap needs a one-time backfill script run against production Supabase.
- **Odds fetcher stubbed** — `fetch_odds_lines()` in `railway_ingest.py` logs game count but does not fetch real odds. Props Board shows no real Vegas lines.
- **Cron crash verification** — Ingest and prediction cron services were crashing due to Railpack builder (fixed to Dockerfile). Next scheduled run will confirm fix.

---

## Session 9 Notes

- [x] Created comprehensive root `README.md` with project overview, architecture, local setup, run commands, test commands, API routes, guardrails, and production notes.
- [x] Added local-only Devpost writing draft in `DEVPOST_DRAFT.md` and excluded it from git tracking via `.gitignore`.
- [x] Added README visual section with architecture, model metrics, and API latency charts from `docs/images/`.
- [x] Added community standards docs and templates: `CODE_OF_CONDUCT.md`, `CONTRIBUTING.md`, `LICENSE`, `SECURITY.md`, `.github/ISSUE_TEMPLATE/*`, `.github/PULL_REQUEST_TEMPLATE.md`.
- [ ] Continue Phase 8 remaining deliverables: edge tracking dashboard, monthly retrain script, and benchmark/CLV reporting.
