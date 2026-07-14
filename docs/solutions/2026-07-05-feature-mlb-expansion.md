# Solution Log — MLB Expansion: Data Foundation

**Date:** 2026-07-05
**Branch:** `feature/mlb-expansion` → merged as PR #28 into `railway`
**Loop:** `/chalk-feature` (brainstorm → plan → work → review → ship → compound)

## Context

First slice of extending Chalk to a second sport. Decision (recorded with the
user): **MLB over NFL** — daily cadence matches the existing cron architecture,
162-game seasons give deep per-player samples, and the batter-vs-pitcher matchup
decomposes cleanly into the one-model-per-stat design. Delivery was **sliced**:
this branch is the data foundation only (schema + ingestion + resumable backfill +
a cron-ready daily runner). Features → models → API/betting/fantasy are later
branches. Layout is **Option A, additive-first**: a new `chalk/mlb/` package
alongside the NBA code, sharing `db`/`config`/`exceptions`; the NBA→`nba/` move
and a shared `core/` are deferred to a future `/chalk-refactor`.

Source: **MLB StatsAPI** (`https://statsapi.mlb.com/api/v1`) — official, keyless,
JSON, async-native via `httpx` (already a dependency). No `nba_api`-style
`run_in_executor` wrapping needed.

## What we learned

- **`gamePk` is the only safe game identity.** Doubleheaders play two games with
  the same date + same teams, so the NBA-style `(date, home, away)` matchup key is
  non-unique for MLB. Game identity must be the upstream numeric `gamePk`; the
  human-facing matchup uniqueness constraint has to include `game_number`.
- **Two-way players break the "one row per (game, player)" assumption.** Ohtani
  produces both a batting line and a pitching line in the same game. Modeling this
  as one wide table forces either two rows per player-game (breaking uniqueness) or
  ~30 nullable columns. Two separate tables (`mlb_batter_game_logs`,
  `mlb_pitcher_game_logs`), each unique on `(game_pk, player_id)`, keep per-stat
  columns NOT NULL and map onto the future per-stat models.
- **Innings pitched is base-3, not decimal.** "6.2 IP" means 6 innings + 2 outs,
  not 6.2. Storing it as a float silently corrupts any aggregation. Store
  `outs_recorded` as an integer; IP is derivable at read time.
- **`abstractGameState` beats string-matching `detailedState` for finality.**
  StatsAPI exposes a coarse `Preview`/`Live`/`Final` enum *and* a verbose
  `detailedState` ("Final", "Completed Early: Rain", "Forfeit", …). Deriving
  "is this game over" from a hand-maintained prefix list on `detailedState` misses
  oddballs (a forfeit is `Final` abstractly but its detailedState isn't in the
  list). Store both; decide finality on `abstract_state == "Final"`, keep the
  prefix check only as a fallback for legacy rows.
- **Upstream IDs must be `autoincrement=False`.** A single-column integer PK in
  SQLAlchemy/Postgres defaults to `SERIAL`. For `team_id`/`player_id`/`game_pk`
  (which come *from* StatsAPI) that would silently generate a local ID when the
  upstream value is missing, instead of failing loudly. (Caught in review.)
- **Live vs. historical caching must differ.** Disk-caching a schedule window that
  includes today/future permanently freezes "Scheduled"/"In Progress" statuses, so
  a later resume never sees those games go Final. Only cache windows strictly in
  the past; fetch live/near-term windows with `use_cache=False`. Boxscores must
  also be re-fetchable so late official-scorer stat corrections reconcile through
  the upsert path.
- **Per-game failure isolation belongs at every layer.** One 404/malformed
  boxscore should skip that game, not abort the day (daily runner) or the season
  (backfill). Backfill must catch `SQLAlchemyError` (with rollback) too, not just
  `IngestError` — a bad upsert/commit is also a per-game skip. And the isolated
  failure count (`failed_games`) has to propagate to the cron's exit code, or a
  partly-failed day exits 0 and looks healthy.
- **The dev proxy blocks `statsapi.mlb.com`.** All fetch tests mock the
  `_fetch_json` seam; the live API is unreachable from the agent sandbox (403 on
  CONNECT). The backfill is an operator step run from Railway or a dev machine.

## Reusable patterns

- **Single fetch seam** — `chalk/mlb/fetcher.py::_fetch_json`: one place for disk
  cache (path-traversal-safe md5 key), exponential backoff + jitter, and
  `IngestError` wrapping; one monkeypatch point for every test. Mirrors
  `nba_fetcher._fetch_with_backoff`.
- **Opportunistic stub upserts for FK safety** — `_upsert_stub_teams` /
  `_upsert_players` insert minimal rows (id + name) before log writes so foreign
  keys resolve without a separate roster crawl; full metadata comes from
  `ingest_mlb_teams`. Stub columns are nullable so a stub is an honest "not yet
  known", not an empty-string sentinel.
- **Warn-don't-raise validation** — `chalk/mlb/validate.py::validate_mlb_row_counts`
  returns `False` + logs instead of raising, matching the NBA `validate_row_counts`
  convention; the cron still exits non-zero. Now checks **per-game coverage**
  (union of batter/pitcher `game_pk`s vs. final games), not a date-wide total, so
  one covered game can't mask nine uncovered ones.
- **Resumable backfill** — `scripts/mlb_backfill.py`: progress file of completed
  `gamePk`s flushed every N games + at season end; iterate plain `gamePk`s (a
  mid-loop rollback expires ORM instances, so don't hold them across the boundary).

## Traps & gotchas

- **Leakage:** no feature functions in this slice, so the `as_of_date` gate isn't
  exercised yet — but every log row stores `game_date`, `season`, `created_at`,
  `updated_at` so the future feature layer *can* enforce `game_date < as_of_date`.
  Do not add a feature/rolling function in `chalk/mlb/` without the `as_of_date`
  parameter.
- **Idempotency:** every write is `INSERT … ON CONFLICT DO UPDATE`. The
  doubleheader and two-way-player cases are the ones that quietly break uniqueness
  if the schema is modeled wrong — both are mandatory test scenarios.
- **Shared-Base metadata drift:** MLB tables register on the same
  `chalk.db.models.Base`, so `alembic/env.py` must import `chalk.mlb.models` or
  autogenerate misses them. When relaxing a schema-parity test to a subset, keep an
  exhaustive union check somewhere (see `tests/test_mlb/test_models.py::
  test_metadata_is_exhaustive`) or stray tables sneak in silently.
- **Alembic vs. direct DDL on production:** the migration was applied to the shared
  Supabase DB via the Supabase MCP (dev proxy has no direct Postgres path). When
  doing that, the DDL, the RLS-enable (to match existing tables), and the
  `alembic_version` bump to the new revision must go in **one** migration, or
  Alembic and the DB disagree and the next `alembic upgrade head` collides.

## Guidance for the next loop

- **Slice 2 (MLB features):** every feature-generating function takes
  `as_of_date: datetime` and gates on `game_date < as_of_date` — non-negotiable.
  The opposing **pitcher** profile is the MLB analog of the NBA opponent-defense
  feature; park factors and batting-order slot are new inputs with no NBA parallel.
- **Player enrichment:** `mlb_players.bats` / `throws` / `birth_date` are
  schema-ready but not yet populated (boxscores don't carry them). A `/people/{id}`
  enrichment pass is a prerequisite for handedness-split features.
- **Verify pitcher decision flags on first live ingest:** `win`/`loss`/`save`/`hold`
  are read from `stats.pitching`; confirm against a real boxscore that these are
  per-game and not season-cumulative before trusting them in a model. (Couldn't be
  verified from the sandbox — proxy-blocked.)
- **When the daily job is justified,** wire an MLB ingest cron as a *new service in
  the same Railway project* (new `railway.mlb_ingest.json`, same Docker image,
  `python scripts/mlb_ingest_daily.py`). Do not create a new environment — the
  monorepo shares one project, one Supabase DB, one image.
- **Refactor trigger:** once slice 2 duplicates fetch/cache/progress helpers a
  third time, cut the `/chalk-refactor` branch to extract `core/` (`_cache_path`,
  `_safe_int`, progress-file helpers, the `run_step`/`with_session` cron scaffold).

## Promoted follow-ups (separate branches, not this doc)

These are candidates to lift out of this log into durable homes — each its own
small `docs/` or `chore/` change, never smuggled into a feature PR:

1. **`CLAUDE.md` — new "MLB ingestion behaviors" subsection** (mirroring the
   existing NBA "Ingestion Behaviors"): gamePk identity, two-way players, base-3
   IP, `abstractGameState` finality, live-vs-historical caching. *Durable domain
   rules — highest value to promote.*
2. **`chalk-review` checklist** — add "single-column integer PK from an upstream
   source → assert `autoincrement=False`" and "isolated per-item failure counts
   must reach the process exit code". Both were review misses this loop.
3. **`.agents/skills/data-ingestion/SKILL.md`** — note the live-vs-historical cache
   split and the warn-don't-raise validation pattern as cross-sport ingestion idioms.
