# Changelog

## 2026-07-06 (later) — CHA-8: API error-response hardening

### Done
- Sanitized the app-level 500 handlers in `chalk/api/main.py`: `PredictionError`/`IngestError` now return a generic message + error type and log the real exception server-side (structlog `prediction_error`/`ingest_error` events with request path). Raw exception text (upstream URLs, hostnames, driver errors) no longer reaches anonymous callers. `FeatureError` (422) keeps meaningful input-related detail by design.
- The other two CHA-8 items (constant-time invalidation-token compare, `.env.example` CORS guidance) were already shipped in PR #34.

### Metrics
- Tests: 321 passed (318 + 3 new handler tests asserting no internal detail leaks); ruff clean.

### Pending
- Remaining audit tickets CHA-9…CHA-15.

### Next
- CHA-9 (shared Redis pool + SCAN) — same file neighborhood, natural follow-up.

## 2026-07-06 — Security audit: CI, dependency pinning, API abuse protection

### Done
- Full repo security/quality audit → 11 Linear tickets (CHA-5…CHA-15); implemented the three High-priority ones on `claude/repo-security-audit-ljdr3d`.
- **CI (CHA-6):** `.github/workflows/ci.yml` runs ruff + pytest (backend) and npm lint + build (dashboard) on every PR/push to `railway`/`main`; added `[tool.ruff]` config; fixed all 86 existing lint errors incl. dead cache-read in `props.py` and an eslint error in `dashboard/src/main.tsx`.
- **Dependency pinning (CHA-7):** committed `requirements.txt`/`requirements-dev.txt` lockfiles (uv pip compile); Dockerfile installs from the lockfile, pins `python:3.11.15-slim`, runs as non-root.
- **Abuse protection (CHA-5):** per-IP Redis rate limiting middleware (fail-open, health/docs exempt, stricter limit on inference routes); `nocache` cache bypass now requires the invalidation token (constant-time compare); Redis NX lock prevents `/v1/games/today` auto-ingest stampedes.

### Metrics
- Tests: 318 passed (309 baseline + 9 new rate-limit/nocache tests); ruff: 0 errors; dashboard lint/build: clean.
- All 18 committed model artifacts verified to load under the pinned dependency set; prod lockfile alone boots the API.

### Pending
- `ruff format` normalization deferred (would touch 104 files — separate mechanical PR).
- Docker image build not verifiable in the dev sandbox (no daemon); Railway deploy build is the verification.
- Remaining audit tickets CHA-8…CHA-15 (Medium/Low) unstarted.

### Next
- Merge PR into `railway` after CodeRabbit review; then pick up CHA-8 (error-response hardening) and CHA-9 (shared Redis pool) which touch the same files while context is fresh.

## 2026-07-05 (later) — MLB slice 1 merged & deployed
### Done
- Merged PR #28 (`feature/mlb-expansion` → `railway`, merge `c94b73b`).
- Applied migration `f6a7b8c9d0e1` to **production Supabase**: 5 `mlb_*` tables + 4 indexes created, RLS enabled to match the NBA tables, `alembic_version` advanced to `f6a7b8c9d0e1`. Verified NBA tables intact (154k player logs).
- Captured loop learnings in `docs/solutions/2026-07-05-feature-mlb-expansion.md`.
### Pending
- Operator backfill (`python scripts/mlb_backfill.py`) from an env that can reach statsapi.mlb.com — the tables are live but empty.
### Next
- Promote durable learnings (CLAUDE.md MLB-ingestion subsection, chalk-review checklist additions) as small follow-ups; then the MLB feature-engineering slice.

## 2026-07-05

### Done
- **MLB expansion, slice 1 (data foundation)** on `feature/mlb-expansion` via the new `/chalk-feature` workflow (brainstorm → plan → work → review → ship, five specs in `specs/feature-mlb-expansion/`).
- New additive `chalk/mlb/` package: 5 ORM tables on the shared `Base` (`mlb_teams`, `mlb_players`, `mlb_games`, `mlb_batter_game_logs`, `mlb_pitcher_game_logs`), MLB StatsAPI fetcher (keyless, httpx, disk cache + exponential backoff → `IngestError`), warn-style row-count validation.
- Domain correctness baked into the schema: gamePk identity (doubleheader-safe matchup uniqueness incl. `game_number`), separate batter/pitcher log tables (two-way players get one row in each), `outs_recorded` integer instead of base-3 IP floats, postseason flag from `gameType`, `abstract_state` (upstream Preview/Live/Final) as the canonical finality signal.
- Runners: resumable `scripts/mlb_backfill.py` (2018→present, progress file flushed every 25 games, per-game error isolation, live windows never disk-cached) and cron-ready `scripts/mlb_ingest_daily.py` (exit 0/1 contract mirroring `railway_ingest.py`; not yet wired to a Railway service by design).
- Additive Alembic migration `f6a7b8c9d0e1` (up/down round-trip verified; no existing table touched — safe on shared Supabase).
- Independent 8-angle review (line-by-line, removed-behavior, cross-file, reuse, simplification, efficiency, altitude, conventions) + fixes for all blocking findings.

### Metrics
- Full suite: **301 passed** (baseline 255 → +46 net new); `tests/test_mlb/` = 53 tests; new-module coverage 93% (fetcher 94%, models/validate 100%, backfill 81%, daily 90%).
- 1 known failure: pre-existing timezone flake `test_today_games_no_stale_fallback` (NBA games API test, unrelated to this diff — fails only in the ~4h window after midnight UTC).

### Pending
- PR into `railway` + CodeRabbit triage; post-merge `alembic upgrade head` on Supabase; operator-run backfill (~19k games at ~1 req/s).
- Verify pitcher win/loss/save/hold are per-game flags on first live ingest (proxy blocked statsapi.mlb.com from the dev environment).

### Next
- Slice 2: MLB feature engineering (rolling windows with the `as_of_date` gate, opposing-pitcher profiles, park factors) on a fresh `feature/` branch; `core/` refactor branch to de-duplicate NBA↔MLB helpers.


## 2026-07-04

### Done
- Added the **Chalk Dev Flow** — agentic, self-correcting Git workflows under `.claude/`, modeled on the Compound Engineering loop (brainstorm → plan → work → review → ship → compound) and adapted to Chalk.
- Restructured to a Windsurf-style two-layer design: **one self-contained slash command per branch type** (the orchestrators) + **reusable phase skills** they invoke.
  - 13 branch-type workflows: `.claude/commands/chalk-{feature,bugfix,hotfix,refactor,perf,experiment,chore,docs,test,style,ci,build,release}.md`.
  - 6 phase skills: `.claude/skills/chalk-{brainstorm,plan,work,review,ship,compound}/SKILL.md`.
  - 5 spec templates in `.claude/templates/` + an index `.claude/README.md`.
- Each workflow is self-contained with `## MCP Integration` (uses whatever MCP servers are connected — trackers, Git hosting, CI, quality gates — no specific one assumed), `## Resuming` (skip completed phases on restart), and `## Steps` with **loop-back error recovery** (later phase fails → return to `chalk-work`/`chalk-plan`) and **loop caps** (stop after 3 no-progress rounds and ask the user).
- Codified the branch-naming convention with the hard rule: all work branches off `railway`, PRs target `railway`, and `main` is touched only by the deliberate `railway → main` promotion inside `/chalk-release`.
- Each run scaffolds `specs/<branch-slug>/` with the five specs: planning, design, implementation (API + DB + security), testing, deployment.
- Added a CI enforcement of the golden branch rule: `.github/workflows/branch-guard.yml` fails PRs into `main` that don't come from `railway`/`release/*`, and PRs into `railway` whose branch lacks an approved `<prefix>/`.

### Metrics
- 13 workflow commands + 6 phase skills + 5 templates + 1 README = 25 markdown files, plus 1 CI workflow.
- No application code touched; test suite unaffected.

### Pending
- Dogfood on a real branch; tune per-type step lists and loop caps from usage.
- **Manual (admin):** make `branch-guard` a required status check on `main` and `railway` via branch protection (steps documented in `.claude/README.md`) — a workflow can't self-require.

### Next
- Run `/chalk-feature` on the next piece of work and refine the phase skills from what surfaces.

---

## 2026-04-16 (Phase 9 AI Injury Agent)

### Done
- Added Gemini-backed NBA injury ingestion from ESPN's public injury endpoint with structured JSON extraction, DB player matching, and upsert summaries.
- Wired Airflow injury refresh tasks to `fetch_and_store_injuries()` and kept compatibility wrappers for existing cron scripts.
- Added `GEMINI_API_KEY` configuration and documentation, plus a standalone manual injury-agent runner.
- Updated player prediction responses and the dashboard `InjuryBadge` to default missing statuses to `Active`.
- Expanded injury fetcher tests for ESPN parsing, Gemini JSON handling, player matching, missing API key behavior, and skip/error paths.

### Pending
- Run the manual script against real ESPN/Gemini credentials after `GEMINI_API_KEY` is configured locally or in Railway.

---

## 2026-04-16 (README + Devpost Draft)

### Done
- Replaced placeholder root `README.md` with a full project README covering overview, features, stack, repo layout, setup, run/test commands, key API routes, guardrails, and production notes
- Added `DEVPOST_DRAFT.md` with a complete submission draft (project story, built-with stack, links, and media checklist)
- Updated Devpost draft wording to first-person solo-project voice and simplified challenge explanations for non-technical readers
- Added `DEVPOST_DRAFT.md` to `.gitignore` so the draft remains local-only
- Updated `TODO.md` session notes and current status to reflect documentation work and remaining Phase 8 tasks
- Added a `Project Visuals` section in `README.md` with embedded architecture, model-metrics, and API-latency images plus short explanatory captions
- Added GitHub community standards files: `CODE_OF_CONDUCT.md`, `CONTRIBUTING.md`, `LICENSE` (MIT), `SECURITY.md`, issue templates, and a pull request template

### Metrics
- Documentation coverage expanded from a 1-line README to a complete onboarding and usage guide
- No runtime code changes; API/model/ingestion behavior remains unchanged

### Pending
- Finish Phase 8 items: edge tracking dashboard, monthly retraining automation, and final benchmark/CLV report
- Validate latest Railway cron runs and resolve remaining data freshness/odds ingestion blockers

### Next
- Implement real odds ingestion in production cron flow
- Build edge tracking visualization/reporting and wire monthly retrain execution
- Add quickstart screenshots/GIF to README for easier first-time onboarding

---

## 2026-04-19 (Playoff Feature & Prediction Context)

### Done
- Added `playoff_round` feature to `chalk/features/situational.py` — derived from game ID position 5 (NBA format `004SSRGGGG` where R=round 1-4), defaults to 1 for unexpected formats, 0 for non-playoff games
- Confirmed `is_playoffs` feature in `get_situational_features` already reads `game.is_playoffs` correctly from DB (set on ingest by previous commit)
- Added `prediction_context` warning log in `chalk/predictions/player.py` when generating predictions for playoff games — logs `season_type=playoff`, `model_trained_on=regular_season`, `accuracy_caveat=true`
- No model weights or training logic changed — context flagging only

### Metrics
- New feature `playoff_round` flows through pipeline automatically (dict merge in `generate_features`)
- Unseen by existing models (will be 0.0 via `_align_features` fallback) — no impact on current predictions

### Pending
- Models have not been retrained with playoff data — playoff_round feature is available but unused by current model weights
- Playoff prediction accuracy may differ from regular-season benchmarks

### Next
- Monitor playoff prediction logs for `prediction_context` warnings
- Consider retraining with historical playoff data once enough 2026 playoff games are ingested

---

## 2026-04-19 (Playoff Game Ingestion Support)

### Done
- `ingest_player_season` now fetches both "Regular Season" and "Playoffs" season types — previously hardcoded to Regular Season only, which excluded all playoff game logs
- `ingest_team_season` now fetches both season types as well
- Added `_is_playoff_game_id()` helper — detects playoff games from game ID prefix (`004` = playoffs, `002` = regular season)
- `ingest_today_scoreboard` now sets `is_playoffs` on game records based on game ID prefix (ScoreboardV2 and CDN fallback both return playoff games without filtering)
- `upsert_games` changed from `on_conflict_do_nothing` to `on_conflict_do_update` so `is_playoffs` flag can be corrected on re-ingest
- All game record creation paths (`ingest_today_scoreboard`, `ingest_player_season`, `ingest_team_season`) now include `is_playoffs` in game rows
- Confirmed no-games paths (`no_games_yesterday`, `no_games_today`, `validate_row_counts` with 0 games) already handle irregular playoff schedules gracefully
- Updated CLAUDE.md with playoff mode documentation

### Metrics
- No ML/prediction logic changed — ingestion-only fix
- Playoff game logs will now appear in `player_game_logs` and `team_game_logs` tables

### Pending
- Existing games already in DB still have `is_playoffs=False` — will be corrected on next re-ingest
- Models were trained on regular-season data only; playoff prediction accuracy may differ

### Next
- Monitor first playoff ingest run to confirm playoff game logs are captured
- Consider whether models need playoff-specific retraining or adjustments

---

## 2026-04-16 (Browser Headers + CDN Fallback)

### Done
- Added CDN fallback for ScoreboardV2: when stats.nba.com times out, fetches from `cdn.nba.com/static/json/liveData/scoreboard/todaysScoreboard_00.json` (no auth, no bot detection)
- Reduced default timeout from 60s to 30s (`NBA_API_TIMEOUT` setting) and retries from 5 to 3 (`NBA_API_MAX_RETRIES` setting) — configurable via env vars
- Both settings added to `chalk/config.py` as pydantic-settings fields
- Browser-like headers (`NBA_HEADERS`) with Sec-Fetch-* and x-nba-stats-* were already present; kept as-is
- Pre-request jitter (0.5–1.5s) already present in `_fetch_with_backoff`; kept as-is

### Metrics
- Worst-case per-endpoint failure time: ~1.5 min (was ~5 min with 60s × 5 retries)
- CDN fallback adds a reliable scoreboard seeding path that bypasses stats.nba.com entirely

### Pending
- Circuit breaker for player ingestion loop not yet on this branch (was in reverted commits)

### Next
- Re-apply circuit breaker pattern to `scripts/railway_ingest.py` to cap total cron runtime
- Monitor next ingest run for CDN fallback usage via `scoreboard_cdn_fallback_used` log event

---

## 2026-04-14 (Vite Allowed Hosts Fix)

### Done
- Updated `dashboard/vite.config.ts` to allow Railway staging and preview hostnames in both `server.allowedHosts` and `preview.allowedHosts`
- Added `thepaint-staging.up.railway.app` and `.up.railway.app` wildcard alongside the existing production host
- Fixes "Blocked request. This host is not allowed." error on `thepaint-staging.up.railway.app`

### Metrics
- No functional changes — host allowlist only

### Pending
- None

### Next
- Verify staging environment loads without blocked-host errors after deploy

---

## 2026-04-14 (Dashboard Player Name Display Fix)

### Done
- Fixed `PlayerCard`, `PropsBoard`, and `FantasyBoard` components to display `player_name` with a `|| String(player_id)` fallback when name is missing or empty
- Root cause: old ingest code stored `str(player_id)` as player name when no name was available; components now degrade gracefully instead of rendering blank headers
- Changes: `dashboard/src/components/PlayerCard/PlayerCard.tsx`, `PropsBoard/PropsBoard.tsx`, `FantasyBoard/FantasyBoard.tsx`

### Metrics
- No logic or styling changes — display-only fix

### Pending
- DB backfill needed: players ingested before `nba_fetcher.py` header/proxy fix still have numeric string names in the `players` table

### Next
- Backfill `players.name` using `nba_api.stats.static.players` lookup for any rows where `name` is all digits

---

## 2026-04-14 (Injury Ingest FK Crash Fix)

### Done
- Added `_filter_valid_player_ids()` to `chalk/ingestion/injury_fetcher.py` — queries `players` table before bulk upsert and drops rows whose `player_id` has no FK match
- Prevents `ForeignKeyViolationError` crash when hardcoded/static-resolved player IDs (e.g. LJ Cryer=1641940, Adama Bal=1642380) don't exist in `players`
- Added 2 tests for the FK filter (missing-player filtering, empty-input passthrough)
- Updated CLAUDE.md with production deployment notes (railway branch policy, Airflow local-only, injury fetcher tiers, ScoreboardV2 CDN fallback, validate_row_counts warn behavior)

### Metrics
- 9/9 injury fetcher tests pass

### Pending
- Players resolved from static/hardcoded fallback still won't have injury data tracked until they exist in `players` table

### Next
- Consider auto-inserting minimal `players` rows for fallback-resolved IDs so their injuries are captured

---

## 2026-04-14 (Railway Ingest Validation Crash Guard)

### Done
- Updated `scripts/railway_ingest.py::validate_row_counts` so `log_count == 0` now emits `validation_failed_no_player_logs` as a warning and returns, instead of raising a `RuntimeError` that crashes the service.
- Marked the ingest run as failed (`failed = True`) in that warning path so the cron still exits with status code `1` after completion.

### Metrics
- Validation behavior changed from exception-based crash to warning + failure flag for missing yesterday `player_game_logs`.

### Pending
- Verify the next Railway ingest cron run reports the warning and exits non-zero without mid-run service crash when stats ingestion is skipped/timeouts occur.

### Next
- Monitor `validation_failed_no_player_logs` frequency and pair with ScoreboardV2 timeout telemetry to reduce missed-stat ingest windows.

---

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
- Added `railway-deployment` skill to `.agents/skills/`
- Added `ensemble-tuning` skill to `.agents/skills/` for Phase 8
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
