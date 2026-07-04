# Design Spec — MLB Expansion: Data Foundation

> The *shape* of the solution. Owned by phase 2 (`/chalk-plan`). Read the
> `planning-spec.md` first.

| | |
|---|---|
| **Branch** | `feature/mlb-expansion` |
| **Date** | 2026-07-04 |
| **Planning spec** | ./planning-spec.md |

## Approach

Additive sport package. All new code lives in a new `chalk/mlb/` package plus two
`scripts/mlb_*.py` runners; **zero existing NBA files change behavior** (the only
touches to existing files are registration-style: an import in `alembic/env.py`,
new settings fields in `chalk/config.py`, and `.env.example` entries).

**Upstream source: MLB StatsAPI** (`https://statsapi.mlb.com/api/v1`) called
directly with `httpx.AsyncClient` (already a runtime dependency). It is free,
keyless, official, JSON, and natively async-friendly — unlike the NBA path, no
`run_in_executor` wrapping is needed. Three endpoints cover the whole slice:

1. `GET /api/v1/teams?sportId=1&season={year}` → 30 teams
2. `GET /api/v1/schedule?sportId=1&startDate=..&endDate=..` → games with
   `gamePk` (stable numeric game ID), `gameType`, `doubleHeader`, `gameNumber`,
   `status`
3. `GET /api/v1/game/{gamePk}/boxscore` → per-game batting + pitching lines for
   every player on both teams, plus each player's id/name/position (used to
   upsert `mlb_players` opportunistically — no separate roster crawl needed)

The fetch seam mirrors `nba_fetcher._fetch_with_backoff`: one private
`_fetch_json(path, params)` with disk caching (keyed like `_cache_path`),
exponential backoff + jitter, max-retries → `IngestError`. Every public ingest
function is `async def`, takes an `AsyncSession` first, and writes via
`INSERT … ON CONFLICT DO UPDATE`.

**Game identity** is the upstream `gamePk` (numeric, unique per game including
each leg of a doubleheader) — never date+teams. The matchup-level uniqueness
constraint therefore includes `game_number` to admit doubleheaders.

**Two-way players** (batting and pitching in the same game) are handled
structurally: batter lines and pitcher lines live in **separate tables**, each
unique on `(game_pk, player_id)`, so one player can legally produce one row in
each.

**Game types**: regular season `R` and postseason `F`/`D`/`L`/`W` are ingested;
spring training `S`, exhibition `E`, and All-Star `A` are filtered out at the
schedule stage. `is_postseason` is derived from `gameType` (the MLB analog of
the NBA `_is_playoff_game_id` behavior).

**Season** is the calendar year as a string (`"2018"`), matching the upstream
`season` field; the 2020 short season needs no special casing — it is simply a
year with fewer rows.

## Component breakdown

| Path | New / Changed | Responsibility |
|---|---|---|
| `chalk/mlb/__init__.py` | New | Package marker |
| `chalk/mlb/models.py` | New | 5 ORM tables (`MlbTeam`, `MlbPlayer`, `MlbGame`, `MlbBatterGameLog`, `MlbPitcherGameLog`) subclassing the shared `chalk.db.models.Base` |
| `chalk/mlb/fetcher.py` | New | StatsAPI client (`_fetch_json` backoff+cache seam), parsers, and all ingest/upsert functions |
| `chalk/mlb/validate.py` | New | `validate_mlb_row_counts` — warn-style row-count sanity check for a date |
| `scripts/mlb_backfill.py` | New | Resumable 2018→present backfill runner (progress file, per-request delay), modeled on `scripts/backfill.py` |
| `scripts/mlb_ingest_daily.py` | New | Cron-ready "yesterday stats + today schedule" runner; exit codes + structlog conventions of `scripts/railway_ingest.py` |
| `alembic/versions/<rev>_add_mlb_tables.py` | New | Additive migration creating the 5 tables (down = drop them) |
| `alembic/env.py` | Changed | Import `chalk.mlb.models` so the tables register on `Base.metadata` |
| `chalk/config.py` | Changed | Add `MLB_API_CACHE_DIR`, `MLB_API_TIMEOUT`, `MLB_API_MAX_RETRIES` settings |
| `.env.example` | Changed | Document the new MLB settings |
| `tests/test_mlb/…` | New | Full test package with JSON fixtures (mocked `_fetch_json`; never hits the real API) |

## Data flow

One batter line, end to end (this slice stops at the DB):

1. `scripts/mlb_ingest_daily.py` computes `yesterday` (UTC) and calls
   `ingest_mlb_schedule(session, yesterday, yesterday)`.
2. `_fetch_json("/schedule", {...})` — disk cache miss → GET with backoff →
   JSON. Spring/exhibition games filtered; each kept game upserted into
   `mlb_games` keyed on `game_pk` (doubleheader legs are distinct `game_pk`s).
3. For each final game, `ingest_mlb_boxscore(session, game_pk)` fetches
   `/game/{gamePk}/boxscore`, upserts both `mlb_teams` rows and every
   participating `mlb_players` row, then builds batter rows (players with a
   non-empty `battingOrder`/batting stats) and pitcher rows (players with
   pitching stats — Ohtani produces one of each).
4. Rows upsert into `mlb_batter_game_logs` / `mlb_pitcher_game_logs` on
   `(game_pk, player_id)` — re-running converges to identical state.
5. `validate_mlb_row_counts(session, yesterday)` warns (`failed=True`, no
   raise) if games exist for the date but zero logs landed; the runner exits 1
   after completing all steps, mirroring `railway_ingest.py`.

## Key design decisions

| Decision | Chosen | Rejected alternative | Why |
|---|---|---|---|
| Upstream source | MLB StatsAPI via `httpx` | `pybaseball` (FanGraphs/BRef/Statcast scraping) | Official + keyless + JSON + async-native; pybaseball is sync, scraping-based, and adds a heavy dependency for data we don't need in this slice |
| Game identity | Upstream `gamePk` as PK | Date + home + away (NBA-style matchup key) | Doubleheaders make date+teams non-unique; `gamePk` is stable and distinct per leg |
| Two-way players | Separate batter/pitcher log tables | One `mlb_player_game_logs` table with nullable stat columns | A single table needs either two rows per player-game (breaking the `(game, player)` uniqueness convention) or ~30 nullable columns; separate tables keep per-stat columns NOT NULL and match the future one-model-per-stat split |
| Innings pitched storage | `outs_recorded: int` | `innings_pitched: float` (e.g. 6.2) | "6.2 innings" is base-3 notation, not a decimal; floats corrupt aggregation. Outs are exact integers; IP is derivable |
| Roster acquisition | Opportunistic upsert of players from each boxscore | Separate `/sports/1/players` roster crawl | Boxscores already carry id/name/position for everyone who played; a roster crawl adds calls and can still miss mid-season call-ups |
| Table placement | `chalk/mlb/models.py` on the shared `Base` | Add tables to `chalk/db/models.py` | Keeps sport code in the sport package (Option A target layout) while sharing metadata so Alembic sees one schema |
| Fetch seam | Single `_fetch_json` private function | Per-endpoint bespoke fetchers | One seam = one place for cache/backoff/proxy logic and one monkeypatch point for tests (mirrors `_fetch_with_backoff`) |

## Interfaces / contracts

No feature-generating functions exist in this slice, so no `as_of_date`
parameters are required yet; every stored row carries `game_date`, `season`,
and `created_at`/`updated_at` so future feature code can enforce the gate.

```python
# chalk/mlb/fetcher.py
async def ingest_mlb_teams(session: AsyncSession, season: int) -> int: ...
async def ingest_mlb_schedule(
    session: AsyncSession, start_date: date, end_date: date
) -> int: ...
async def ingest_mlb_boxscore(session: AsyncSession, game_pk: int) -> tuple[int, int]:
    """Returns (batter_rows, pitcher_rows) upserted."""
async def ingest_mlb_date(session: AsyncSession, game_date: date) -> dict[str, int]:
    """Schedule + boxscores for one date. Returns row-count summary."""

# chalk/mlb/validate.py
async def validate_mlb_row_counts(session: AsyncSession, game_date: date) -> bool:
    """True if healthy; logs a warning and returns False otherwise (never raises)."""

# scripts
python scripts/mlb_backfill.py [--start-season 2018] [--end-season 2026]
python scripts/mlb_ingest_daily.py   # exit 0 healthy / 1 any step failed
```

## Validation strategy

No model training in this slice. The stored data is structured for the
project-standard **walk-forward validation only** (never k-fold): `season` is a
first-class column on games and both log tables, so future MLB training can
split train/validate/test on season boundaries exactly as NBA does
(2015–2022 / 2022–23 / 2023–24 convention, adapted to MLB years 2018+).

## Open questions

- Exact `battingOrder` semantics for mid-game substitutes (StatsAPI encodes
  starter slots as `"100".."900"`, subs as `"101"` etc.) — resolve during
  implementation from a real fixture; stored as-is (string) either way.
- Whether `mlb_players.team_id` should be updated on every boxscore (players
  change teams mid-season). Decision: yes — last-seen team wins, matching how
  the NBA `players.team_id` behaves.
