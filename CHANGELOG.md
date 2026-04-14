# Changelog

## 2026-04-14 (Injury Unicode + Rookie Fallback Fix)

### Done
- Updated `chalk/ingestion/injury_fetcher.py::_normalize_player_name` to strip Unicode diacritics via `unicodedata.normalize("NFKD", ...)` before punctuation/suffix cleanup, so names like `Dončić`, `Vučević`, and `Jović` normalize to ASCII equivalents.
- Added hardcoded rookie fallback IDs for unresolved 2025 names currently missing from `nba_api` static list resolution (`LJ Cryer`, `Adama Bal`) after DB + static lookup miss.
- Added resolver test coverage for diacritic-insensitive static matching (`Luka Dončić` vs `Luka Doncic`) and hardcoded rookie fallback behavior.

### Metrics
- `pytest tests/test_ingestion/test_injury_fetcher.py -v` passed: 7/7 tests.

### Pending
- Monitor production ingest logs for any additional 2025 rookies still hitting `player_not_found`.

### Next
- Extend `_HARDCODED_PLAYER_ID_FALLBACKS` if new rookies appear before `nba_api` static data catches up.

---

## 2026-04-14 (Injury Ingest Name Resolution Fix)

### Done
- Restored fallback player resolution in `chalk/ingestion/injury_fetcher.py` using `nba_api.stats.static.players` when direct DB name match fails.
- Added normalized name matching (lowercase, punctuation stripped, Jr./III-style suffix removal) to resolve variants such as `Jimmy Butler III`, `T.J. McConnell`, and `Day'Ron Sharpe`.
- Added `player_resolved_from_static` logging when static fallback resolves a player; `player_not_found` now only logs after both DB and static lookup fail.
- Follow-up refinement: clarified `resolve_player_id` no-match return to explicit `None` and strengthened fallback tests to patch `nba_static_players.get_players` (exercising real lookup-building + cache behavior).
- Added/updated tests in `tests/test_ingestion/test_injury_fetcher.py` for DB-first resolution, static fallback resolution, and no-match behavior.

### Metrics
- `pytest tests/test_ingestion/test_injury_fetcher.py -v` passed: 6/6 tests.

### Pending
- Validate the next production ingest run to confirm `player_not_found` noise is eliminated for known NBA players.

### Next
- If any remaining misses appear in production logs, extend normalization rules for additional edge-case suffix/name patterns.

---

## 2026-04-14

### Done
- Reverted the `railway` branch back to commit `3b88695d0d1f31f07e03415216e9af09eebb5dd5` (security hardening baseline) due to post-deploy crashes.
- Rolled back all subsequent API, ingestion, dashboard, model, script, and test changes introduced after that commit.

### Metrics
- Attempted `git revert --no-commit 3b88695d0d1f31f07e03415216e9af09eebb5dd5..HEAD`; it failed on a merge commit requiring mainline selection.
- Completed equivalent merge-aware no-commit reverts for the same range, resulting in a single rollback commit target.

### Pending
- Validate Railway redeploy and run production smoke checks after push.

### Next
- Isolate the post-deploy crash root cause from reverted commits and reintroduce fixes incrementally.

---

## 2026-03-16 (Session 8)

### Done
- Implemented Optuna hyperparameter search with walk-forward CV and MedianPruner trial pruning (`chalk/models/tuning.py`)
- Built LGBMStatModel as drop-in LightGBM alternative to BaseStatModel (`chalk/models/lgbm.py`)
- Built StackedEnsemble meta-learner blending XGBoost + LightGBM + historical median via Ridge regression (`chalk/models/ensemble.py`)
- Created full Phase 8 training pipeline script (`scripts/train_ensemble.py`) with `--tune-only`, `--skip-tune`, `--n-trials` options
- Extended model registry with `save/load_lgbm_model` and `save/load_ensemble_model` functions
- Added 14 new tests: 6 LightGBM, 3 Optuna tuning, 5 stacking ensemble
- Ran full Optuna tuning (50 trials per stat per model type = 400 total trials) on real data
- Updated prediction pipeline to use LightGBM as primary model for pts/reb/ast/fg3m (`chalk/predictions/player.py`)

### Metrics
- 198 tests passing (14 new Phase 8 + 184 existing), 1 pre-existing scaffold test failure (Supabase URL vs local URL assertion)
- Optuna best CV MAEs: pts_lgbm=4.9745, reb_lgbm=2.0807, ast_lgbm=1.4393, fg3m_lgbm=0.8608
- LightGBM test MAEs: pts=4.906 (+0.7%), reb=1.995 (+1.2%), ast=1.454 (+1.1%), fg3m=0.907 (+3.5%)
- Stacking ensemble did NOT improve over standalone LightGBM — XGB and LGBM too correlated
- LightGBM now the primary model in production prediction pipeline

### Pending
- Edge tracking dashboard not yet built
- Monthly retraining job not yet created
- Same blockers from previous session (stale dashboard data, stubbed odds fetcher)

### Next
- Build edge tracking dashboard (model edge vs. closing line)
- Create monthly retraining script (`scripts/retrain_monthly.py`)
- Explore feature engineering improvements to push PTS/REB/AST past 2% threshold

---

## 2026-03-16

### Done
- Added Railway deployment configuration (`railway.json`, `railway.ingest.json`, `railway.predict.json`)
- Wrote standalone cron scripts (`scripts/railway_ingest.py`, `scripts/railway_predict.py`) that replicate Airflow DAG logic without Airflow dependency
- Confirmed TimescaleDB features are NOT used in migrations — Supabase (plain PostgreSQL) is fully compatible
- Confirmed model `.joblib` files are committed to git and baked into the Docker image — no ephemeral storage issue
- Set up `ingest` and `prediction` cron services on Railway (7 AM UTC and 6 PM UTC daily)
- Fixed builder from Railpack to Dockerfile on both cron services
- Clarified Supabase connection: Session Pooler (port 5432) is correct for asyncpg; Direct Connection is IPv4-incompatible on Railway
- Added `railway-deployment` skill to `.claude/skills/`
- Added `ensemble-tuning` skill to `.claude/skills/` for Phase 8
- Updated CLAUDE.md tech stack and added Production Deployment section
- Added Session Rules section to CLAUDE.md

### Metrics
- Cron services deployed and confirmed running (crash = script error, not infra issue)
- `web` API health check: `{"status":"ok","checks":{"database":"ok","redis":"ok"}}`
- Dashboard still showing stale 3/8 data — DB gap not yet resolved

### Pending
- Cron services still crashing (`No module named 'chalk'` was root cause — fixed by switching to Dockerfile builder, but latest run needs verification)
- Dashboard showing games from 2026-03-08 — needs backfill of 3/9 through 3/15
- Odds fetcher (`fetch_odds_lines`) is stubbed — does not actually fetch odds
- MLflow not deployed in production — experiment tracking disabled in prod
- Phase 8 (Ensemble & Tuning) not started

### Next
- Verify cron services succeed on next scheduled run (ingest at 07:00 UTC, predict at 18:00 UTC)
- Run one-time backfill to populate missing game data from 3/9–3/15
- Implement actual odds fetching in `scripts/railway_ingest.py` / `chalk/ingestion/odds_fetcher.py`
- Begin Phase 8: Optuna hyperparameter search starting with `pts` model
