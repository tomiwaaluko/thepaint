# Deployment Spec — MLB Expansion: Data Foundation

> How this ships. Owned by phase 6 (`/chalk-ship`).

| | |
|---|---|
| **Branch** | `feature/mlb-expansion` |
| **Date** | 2026-07-05 |
| **Merge target** | **`railway`** (never `main`) |
| **PR** | (filled after opening) |

## Migrations
- Alembic revisions run (in order): `f6a7b8c9d0e1_add_mlb_tables` (head after
  `e5f6a7b8c9d0`). Purely additive — creates `mlb_teams`, `mlb_players`,
  `mlb_games`, `mlb_batter_game_logs`, `mlb_pitcher_game_logs` + 4 indexes.
  **No existing table is touched**, so it is safe on the shared Supabase
  production DB. Apply with `alembic upgrade head` (Session Pooler URL).
- Down-path / rollback: `alembic downgrade e5f6a7b8c9d0` — drops the five MLB
  tables in FK-safe order. Verified round-trip on scratch DB.

## Railway services affected
| Service | Type | Change |
|---|---|---|
| `web` | FastAPI | **None** (no API routes in this slice) |
| `thepaint` | React frontend | **None** |
| `ingest` | Cron 07:00 UTC | **None** (NBA cron untouched) |
| `prediction` | Cron 18:00 UTC | **None** |
| `Redis` | add-on | **None** |

- Shared Docker image / start-command changes: none. `scripts/mlb_ingest_daily.py`
  is cron-*ready* but deliberately **not wired** to a Railway service yet (per
  planning-spec Out list); when MLB predictions exist, add a
  `railway.mlb_ingest.json` pointing at the same Docker image with start
  command `python scripts/mlb_ingest_daily.py` (suggested 08:00 UTC, after
  West Coast night games).
- Builder: **`DOCKERFILE`** for Python services (not Railpack) — unchanged.

## Config / env
- New env vars (all optional, sane defaults; added to `.env.example`):
  `MLB_API_CACHE_DIR` (default `.cache/mlb_api`), `MLB_API_TIMEOUT` (30),
  `MLB_API_MAX_RETRIES` (5). **No secrets** — MLB StatsAPI is keyless. Nothing
  needs to be set on any Railway service until the MLB cron is wired.
- Redis URL via `${{Redis.REDIS_URL}}`; DB via Supabase **Session Pooler** — unchanged.

## Model artifacts
None. No models trained in this slice; `models/` untouched.

## Rollout & verification
- Post-merge: run `alembic upgrade head` against Supabase (Session Pooler),
  then verify the five `mlb_*` tables exist and NBA tables are unchanged.
- Operator-run backfill (not CI): `python scripts/mlb_backfill.py` (2018→2026,
  resumable via `.cache/mlb_backfill_progress.json`; ~19k games at ~1 req/s —
  expect several hours; safe to interrupt and resume).
- Smoke the daily path once: `python scripts/mlb_ingest_daily.py` → exit 0,
  `mlb_yesterday_summary` log line with non-zero rows on a game day.
- **First-live-run check:** confirm `stats.pitching.wins/losses/saves/holds`
  in a real boxscore are per-game decision flags (fixtures model them as 0/1;
  could not verify from this environment — proxy blocks statsapi.mlb.com).
- Latency budget: N/A (no API surface added); p99 < 500ms unaffected.

## Rollback plan
- Revert the merge on `railway`; run `alembic downgrade e5f6a7b8c9d0`;
  no service redeploys needed (no service behavior changed).

## Pre-ship gate
- [x] `pytest tests/ -q` — **301 passed**; the single failure
  (`tests/test_api/test_games.py::test_today_games_no_stale_fallback`) is a
  **pre-existing timezone flake** unrelated to this diff: the NBA route's
  "today" vs the container's `date.today()` disagree in the ~4h window after
  midnight UTC. Passes outside that window; MLB + scaffold subset: 58 passed.
- [x] Frontend: N/A (not touched)
- [x] `TODO.md` + `CHANGELOG.md` updated
- [x] All five specs match final code

## Known follow-ups
- **Verify pitcher decision flags** (win/loss/save/hold) against the first
  real boxscore ingested — see Rollout above.
- **Timezone flake in `test_today_games_no_stale_fallback`** (pre-existing,
  NBA API test): compare against the route's own timezone, not naive
  `date.today()`. Candidate for a `/chalk-test` branch.
- **`mlb_players.bats/throws/birth_date`** are schema-ready but not populated
  (needs a `/people/{id}` enrichment pass — future slice, alongside features).
- **Matchup unique constraint vs extreme reschedules:** `uq_mlb_game_matchup`
  could collide if MLB renumbers a postponed game into an existing slot within
  one upsert batch — considered rare; revisit if ingest ever hits it.
- **Shared-helper extraction** deferred to the planned `core/` refactor branch:
  `_cache_path`, `_safe_int`, progress-file helpers, `run_step`/`with_session`
  cron scaffold are duplicated NBA↔MLB by the additive-first decision.
- **httpx client reuse** (one `AsyncClient` per run instead of per request) —
  micro-optimization masked by the 1 req/s throttle; do with the refactor.
- **Unbounded disk cache** under `.cache/mlb_api` after a full backfill
  (several GB of boxscore JSON) — acceptable locally, prune manually or add
  eviction later. Railway crons use ephemeral storage, so prod is unaffected.
