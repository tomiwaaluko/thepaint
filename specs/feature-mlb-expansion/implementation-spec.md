# Implementation Spec — MLB Expansion: Data Foundation

> The buildable plan, including **API spec**, **DB spec**, and **security rules**.
> Owned by phase 2 (`/chalk-plan`); executed by phase 4 (`/chalk-work`).

| | |
|---|---|
| **Branch** | `feature/mlb-expansion` |
| **Date** | 2026-07-04 |
| **Design spec** | ./design-spec.md |

## Task breakdown

Bite-sized tasks. One commit per task (or per tight group). TDD: each task's test
is written RED first where a public surface exists.

- [ ] **T1** — `chalk/config.py` + `.env.example` — add `MLB_API_CACHE_DIR`
      (default `.cache/mlb_api`), `MLB_API_TIMEOUT` (30), `MLB_API_MAX_RETRIES`
      (5) — verify: `pytest tests/ -q` still green (settings defaults only).
- [ ] **T2** — `chalk/mlb/__init__.py` + `chalk/mlb/models.py` — 5 ORM tables on
      shared `Base`: `MlbTeam`, `MlbPlayer`, `MlbGame`, `MlbBatterGameLog`,
      `MlbPitcherGameLog` (columns per DB spec below) — verify:
      `pytest tests/test_mlb/test_models.py -v` (create rows in sqlite,
      uniqueness constraints enforced, doubleheader legs coexist, two-way player
      has a row in both log tables).
- [ ] **T3** — `tests/test_mlb/fixtures/` — trimmed real-shape StatsAPI JSON:
      `teams.json`, `schedule_single.json`, `schedule_doubleheader.json`
      (includes one spring-training game to prove filtering),
      `boxscore_regular.json` (includes a two-way player),
      `boxscore_postseason.json` — verify: fixtures load as JSON.
- [ ] **T4** — `chalk/mlb/fetcher.py` — `_fetch_json(path, params)` with disk
      cache (md5 key like `nba_fetcher._cache_path`, path-traversal-safe),
      exponential backoff + jitter, max `MLB_API_MAX_RETRIES` → `IngestError` —
      verify: `pytest tests/test_mlb/test_fetcher.py -v -k cache_or_backoff`
      (cache hit skips HTTP; retries then raises `IngestError`; mocked
      transport, no real network).
- [ ] **T5** — `chalk/mlb/fetcher.py` — `ingest_mlb_teams(session, season)`
      parse + upsert (`ON CONFLICT (team_id) DO UPDATE`) — verify: idempotency
      test (run twice → same row count and values).
- [ ] **T6** — `chalk/mlb/fetcher.py` — `ingest_mlb_schedule(session, start,
      end)`: filter `gameType` to `R/F/D/L/W`, derive `is_postseason`, upsert
      `mlb_games` on `game_pk` — verify: doubleheader fixture yields 2 distinct
      games same date/teams; spring game excluded; postseason flag set; run
      twice → identical state.
- [ ] **T7** — `chalk/mlb/fetcher.py` — boxscore parsers:
      `_build_batter_rows(payload, ...)` / `_build_pitcher_rows(payload, ...)`
      including `outs_recorded` from upstream `outs`; missing counting stats
      default 0 — verify: parser unit tests incl. two-way player producing one
      batter row + one pitcher row.
- [ ] **T8** — `chalk/mlb/fetcher.py` — `ingest_mlb_boxscore(session, game_pk)`:
      opportunistic team/player upserts, then batter/pitcher log upserts on
      `(game_pk, player_id)`; returns `(batter_rows, pitcher_rows)` — verify:
      idempotency (twice → same state); FK integrity (players/teams exist
      before logs).
- [ ] **T9** — `chalk/mlb/fetcher.py` — `ingest_mlb_date(session, game_date)`:
      schedule for the date → boxscores for games with `status == "Final"`;
      returns summary dict; empty date (no games) returns zeros without error —
      verify: composed test on fixtures; no-games day logs `no_mlb_games` and
      succeeds.
- [ ] **T10** — `chalk/mlb/validate.py` — `validate_mlb_row_counts(session,
      game_date)`: games exist for date but zero batter+pitcher logs → log
      `validation_failed_no_mlb_logs` warning, return `False`; healthy or
      no-games → `True`; never raises — verify: three-case test.
- [ ] **T11** — `alembic/env.py` — add `import chalk.mlb.models  # noqa: F401`
      after the `Base` import — verify: `alembic revision --autogenerate` sees
      the 5 tables (or offline check: `Base.metadata.tables` contains
      `mlb_teams` etc. via test).
- [ ] **T12** — `alembic/versions/<rev>_add_mlb_tables.py` — hand-written
      additive migration: `upgrade()` creates 5 tables + indexes,
      `downgrade()` drops them in FK-safe order; **touches no existing table**
      — verify: `alembic upgrade head` + `alembic downgrade -1` round-trip on a
      scratch sqlite/postgres URL.
- [ ] **T13** — `scripts/mlb_backfill.py` — seasons 2018→current: per-season
      schedule ingest, then boxscore ingest per game; progress file
      `.cache/mlb_backfill_progress.json` (completed `game_pk`s), resume skips
      completed; `INTER_REQUEST_DELAY` politeness sleep; `IngestError` on one
      game skips + logs, doesn't abort — verify:
      `pytest tests/test_mlb/test_backfill.py -v` (resume logic, skip-on-error)
      with mocked ingest functions.
- [ ] **T14** — `scripts/mlb_ingest_daily.py` — steps: `ingest_mlb_date(yesterday)`
      → `ingest_mlb_schedule(today, today)` → `validate_mlb_row_counts(yesterday)`;
      per-step sessions, `run_step` isolation, structlog step logs; exit 0
      healthy / 1 if any step failed or validation returned False — verify:
      `pytest tests/test_mlb/test_ingest_daily.py -v` (exit-code matrix with
      mocked steps).
- [ ] **T15** — Full-suite gate + docs — `pytest tests/ -q` all green (255
      baseline + new); update `TODO.md`; `CHANGELOG.md` entry per session rules
      — verify: suite output pasted into `testing-spec.md`.

---

## API spec

**No API changes.** This slice ends at the database. No routes, no Pydantic
response schemas, no Redis caching. (Future slices add `/v1/mlb/...` routes.)

---

## DB spec

- **Tables touched:** 5 **new** tables only — no existing table modified.

**`mlb_teams`**
| column | type | nullable | notes |
|---|---|---|---|
| team_id | Integer PK | no | upstream StatsAPI team id |
| name | String(100) | no | |
| abbreviation | String(5) | no | |
| league | String(20) | no | AL / NL |
| division | String(30) | no | e.g. "AL East" |
| venue | String(100) | yes | |
| city | String(50) | no | locationName |

**`mlb_players`**
| column | type | nullable | notes |
|---|---|---|---|
| player_id | Integer PK | no | upstream StatsAPI person id |
| name | String(100) | no | fullName |
| team_id | FK mlb_teams | yes | last-seen team; null tolerated |
| position | String(5) | no | primary position abbrev |
| bats | String(1) | yes | L/R/S |
| throws | String(1) | yes | L/R |
| birth_date | Date | yes | |
| is_active | Boolean default True | no | |

**`mlb_games`** — `UniqueConstraint(date, home_team_id, away_team_id,
game_number)` (doubleheader-safe)
| column | type | nullable | notes |
|---|---|---|---|
| game_pk | Integer PK | no | upstream gamePk |
| date | Date | no | official game date |
| season | String(4) | no | "2018" |
| game_type | String(1) | no | R/F/D/L/W |
| is_postseason | Boolean default False | no | derived from game_type |
| doubleheader | String(1) default "N" | no | N/Y/S |
| game_number | Integer default 1 | no | 1 or 2 |
| home_team_id | FK mlb_teams | no | |
| away_team_id | FK mlb_teams | no | |
| status | String(30) default "scheduled" | no | |
| venue | String(100) | yes | |

**`mlb_batter_game_logs`** — `UniqueConstraint(game_pk, player_id)`;
`Index(player_id, game_date)`, `Index(team_id, game_date)`
| column | type | notes |
|---|---|---|
| log_id | Integer PK autoincr | |
| game_pk | FK mlb_games | |
| player_id | FK mlb_players | |
| team_id | FK mlb_teams | |
| game_date | Date | |
| season | String(4) | |
| ab, r, h, doubles, triples, hr, rbi, bb, so, sb, cs, hbp, total_bases, plate_appearances | Integer NOT NULL (default 0 at parse) | per-stat columns for future one-model-per-stat |
| batting_order | String(3) nullable | upstream slot encoding, stored as-is |
| position | String(5) | position played this game |
| created_at / updated_at | DateTime server_default now / onupdate now | |

**`mlb_pitcher_game_logs`** — `UniqueConstraint(game_pk, player_id)`;
`Index(player_id, game_date)`, `Index(team_id, game_date)`
| column | type | notes |
|---|---|---|
| log_id | Integer PK autoincr | |
| game_pk / player_id / team_id / game_date / season | as above | |
| is_starter | Boolean NOT NULL | from gamesStarted |
| outs_recorded | Integer NOT NULL | exact; IP is base-3 so never stored as float |
| h, r, er, bb, so, hr, batters_faced, pitches_thrown | Integer NOT NULL (default 0) | |
| win, loss, save, hold | Boolean NOT NULL default False | decision flags |
| created_at / updated_at | DateTime | |

- **Migration:** `alembic/versions/<rev>_add_mlb_tables.py` — `upgrade()`
  creates the 5 tables + 4 log indexes; `downgrade()` drops
  logs → games → players → teams (FK-safe). Purely additive; safe on the shared
  Supabase production DB.
- **Indexes / TimescaleDB:** plain B-tree indexes as listed (matches NBA log
  tables); no hypertable in this slice.
- **Idempotency:** every write is `INSERT … ON CONFLICT … DO UPDATE` via
  `sqlalchemy.dialects.postgresql.insert` (works on sqlite for tests, as the
  existing suite already relies on):
  - `mlb_teams` → conflict target `(team_id)`
  - `mlb_players` → `(player_id)`
  - `mlb_games` → `(game_pk)`
  - `mlb_batter_game_logs` / `mlb_pitcher_game_logs` → `(game_pk, player_id)`

---

## Security rules

- **Secrets:** none required — MLB StatsAPI is keyless. New settings are
  non-secret operational knobs via `pydantic-settings`/`.env`. No tokens in
  code, tests, or fixtures.
- **Input validation:** all upstream JSON parsed defensively (missing keys →
  defaults/skip with structured log, mirroring `_safe_int` style); DB writes go
  through SQLAlchemy Core/ORM — parameterized only, no string SQL.
- **Cache path safety:** `_fetch_json` sanitizes cache-key path segments
  exactly like `nba_fetcher._cache_path` (alphanumeric+underscore only) to
  prevent path traversal.
- **CORS / origins:** untouched (no API changes).
- **Leakage-as-integrity:** no feature functions in this slice; the gate list
  is empty. Enabler obligation: `game_date`, `season`, `created_at`,
  `updated_at` present on all log rows so future `as_of_date` gates are
  enforceable.
- **PII / least privilege:** only public professional-athlete data (name,
  birth date, handedness) — same class as existing NBA `players`.
- **Dependencies:** **none added.** `httpx>=0.27.0` already pinned in
  `pyproject.toml`.

---

## Execution notes

- Order: T1→T2 unblock everything; T3 (fixtures) before T4–T10; migration
  (T11–T12) after models stabilize; runners (T13–T14) last.
- Test DB: reuse the repo's sqlite+aiosqlite conftest pattern
  (`tests/conftest.py`) — MLB tables share `Base`, so `create_all` picks them up.
- Fixture policy: fixtures are *trimmed real payload shapes* (a handful of
  players), never full dumps; committed under `tests/test_mlb/fixtures/`.
- Backfill is NOT run in CI or by the PR; it ships as a runner the user
  executes against production (`python scripts/mlb_backfill.py`), same posture
  as the NBA `scripts/backfill.py`.
- No Railway cron registration in this branch (per planning spec Out list);
  `scripts/mlb_ingest_daily.py` is written to the same contract so wiring a
  `railway.mlb_ingest.json` later is a one-file follow-up.
