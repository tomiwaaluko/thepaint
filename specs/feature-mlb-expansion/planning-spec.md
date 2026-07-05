# Planning Spec — MLB Expansion: Data Foundation

> Requirements only. No file paths, no code, no schema — those live in the design and
> implementation specs. Owned by phase 1 (`/chalk-brainstorm`).

| | |
|---|---|
| **Branch** | `feature/mlb-expansion` |
| **Prefix rationale** | New capability (a second sport) that does not change existing NBA behavior |
| **Base** | `railway` |
| **Date** | 2026-07-04 |
| **Author** | Claude Code (with tomiwaaluko) |

## Baseline
- `pytest tests/ -v` result at branch start: **PASS (255 passed, 5 warnings)**
- Frontend (if touched) `npm run build` / `lint`: **N/A** (dashboard out of scope for this slice)

## Problem statement
Tha Paint predicts statlines for exactly one sport. The NBA season runs October–June,
so the system sits idle (no games to predict, no betting/fantasy value) for roughly
four months a year, and the project's reach is capped at one market. MLB was chosen
over NFL because its daily cadence matches the existing ingest/predict rhythm, its
per-player sample sizes are far larger (162 games/season), and the batter-vs-pitcher
matchup decomposes cleanly into the per-stat modeling approach the system already
uses. Nothing in the codebase today can store, ingest, or validate MLB data — that
foundation must exist before any MLB feature engineering or modeling can start.

## Affected modules
- **ingestion** — new MLB data ingestion (teams, players, games, batter/pitcher game logs)
- **db** — new MLB tables and migrations alongside the existing NBA tables
- (scripts/backfill tooling as the runner surface for the above)

Explicitly *not* in this slice: features, models, predictions, betting, fantasy, api,
dashboard.

## Why now
- The user has decided to expand the product to a second sport and picked MLB
  (2026-07-04 session decision).
- It is early July: the 2026 MLB season is mid-flight and the NBA playoffs are ending —
  the ideal window to backfill history and validate live daily ingestion before the
  NBA off-season, so features/models can be built against real data next.
- Sliced delivery decision: **data foundation first** (this branch), features → models
  → API/betting/fantasy as follow-up branches.

## Success criteria
This slice has no MAE targets (no models yet). It succeeds when:
1. **Historical coverage:** batter and pitcher game logs for the **2018 through
   current (2026) MLB seasons** are ingestible, including postseason, with the 2020
   shortened season handled without special-casing by callers.
2. **Idempotency proven:** running any MLB ingestion job twice in a row produces an
   identical database state (verified by test, mirroring the NBA upsert standard).
3. **Isolation proven:** the full existing test suite still passes unchanged
   (255-passed baseline); no NBA table, route, cron, or model artifact is modified.
4. **Daily-run ready:** a single command can ingest "yesterday's MLB games" and is
   safe to wire into a Railway cron later (exit codes and structured logs consistent
   with the existing ingest cron conventions).
5. **Validation gates:** row-count sanity checks exist for MLB ingests (warn-style,
   consistent with `validate_row_counts` behavior on the NBA side).
6. **Tested:** every new public function has a pytest test; external MLB API calls are
   mocked in tests (never hit the real API), matching the repo testing standard.

## Scope
**In:**
- MLB reference data: teams, players (both batters and pitchers), season schedules/games.
- MLB per-game statlines: batter game logs (core counting stats needed for future
  prop/fantasy markets) and pitcher game logs (starts and relief appearances).
- Postseason games included and distinguishable from regular season (the MLB analog of
  the NBA `is_playoffs` handling).
- Historical backfill capability for 2018→present, resumable and idempotent.
- A "yesterday + today" incremental ingest path suitable for a future daily cron.
- Documentation of the chosen upstream MLB data source and its rate-limit/backoff
  behavior.

**Out (explicitly):**
- Any restructuring of existing NBA code (the Option A `core`/`nba`/`mlb` package
  split is the agreed *target* layout, but moving NBA code is deferred to a later
  `/chalk-refactor` branch — this slice is **additive only**).
- Feature engineering (rolling windows, park factors, batter-vs-pitcher profiles).
- Model training, predictions, probability distributions.
- Betting lines / odds ingestion for MLB, fantasy scoring, API routes, dashboard UI.
- Injury-report ingestion for MLB (future slice; noted as a known follow-up).
- Production Railway cron registration for MLB (the runner must be *ready* for it,
  but wiring the cron service happens when predictions exist to justify it).
- Statcast pitch-level data (per-pitch granularity is not needed for game-level
  statline prediction and would multiply storage ~300x).

## Constraints
- **as_of_date leakage rule:** not directly exercised in this slice (no features), but
  every stored MLB fact must carry the timestamps/dates needed so future feature code
  *can* enforce `game_date < as_of_date`. Nothing may be stored in a form that hides
  when it became known.
- **Idempotent ingestion:** all writes are upserts; re-runs converge to the same state.
- **Async all the way down:** MLB DB access uses the existing async SQLAlchemy
  session; no sync DB calls in anything that could reach the hot path.
- **Walk-forward validation only** (future constraint): season boundaries must be
  first-class in the stored data so later training can split by season cleanly.
- **One model per stat** (future constraint): logs must store discrete per-stat
  columns (not blobs) so per-stat models can be trained later.
- **Data availability:** must use a free, publicly accessible MLB data source with
  retry/backoff (exponential, jittered, max 5) like the NBA fetchers; source choice is
  a design decision, but licensing must permit this use.
- **Production posture:** Supabase Postgres via session pooler; migrations must be
  additive-only so deploying to the shared DB cannot affect the live NBA tables. All
  work merges to `railway`, never `main`.
- **MLB domain quirks the requirements must absorb:** doubleheaders (two games, same
  teams, same date — game identity cannot be date+teams alone); the 2020 60-game
  season; ties are impossible but suspended/postponed games exist; two-way players
  (one player can produce both a batter line and a pitcher line in the same game).

## Risks & unknowns
- **Upstream API stability:** the free MLB data source may throttle heavy backfills
  (~19k games for 2018–2026). Mitigation requirement: resumable backfill + caching so
  a failed run continues rather than restarts.
- **Player identity across sources:** future odds/fantasy slices will need to join on
  player names; MLB name collisions (e.g., multiple players with identical names) are
  more common than NBA. Requirement: store the upstream's stable numeric player ID as
  the primary identity from day one.
- **Doubleheader/suspended-game edge cases** could silently violate idempotency if
  game identity is modeled wrong — called out as a mandatory test scenario.
- **Two-way players** (batter+pitcher same game) could violate uniqueness constraints
  if logs assume one line per player-game — mandatory test scenario.
- **Shared production DB:** a bad migration hits the same Supabase instance the live
  NBA product uses. Mitigation: additive-only migration, reviewed against the live
  schema before merge.
- **Scope creep:** the temptation to "just add one feature" mid-slice. The off-ramps
  in this workflow and the Out list above are the guard.

## Alternatives considered
1. **NFL instead of MLB** — rejected: 17-game seasons give brutally small per-player
   samples, weekly cadence mismatches the daily cron architecture, and position
   fragmentation (QB/RB/WR/TE/K/DST) would fragment the one-model-per-stat design.
2. **Separate repository for MLB** — rejected: would duplicate ingestion/backoff,
   training harness, API, and deploy infrastructure, then let the copies drift; the
   monorepo shares fixes across sports.
3. **Restructure NBA code into `core`/`nba` packages in this same branch** — rejected
   for this slice: the MLB data layer shares only db-session/config/exception plumbing
   with NBA code, so the refactor buys nothing yet and would balloon the PR; deferred
   to a dedicated refactor branch once real duplication appears (target layout is
   unchanged).
4. **Full-stack MLB slice (through models/API) in one branch** — rejected: weeks-long
   PR against a live production branch; sliced delivery de-risks review and merge.
5. **Statcast pitch-level ingestion now** — rejected: game-level statlines don't need
   per-pitch rows; storage and backfill cost ~300x for no slice-1 benefit.
