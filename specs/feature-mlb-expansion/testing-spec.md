# Testing Spec — MLB Expansion: Data Foundation

> Tests written *before* implementation (RED), per task, following the
> RED → GREEN → simplify rhythm of `/chalk-work`.

| | |
|---|---|
| **Branch** | `feature/mlb-expansion` |
| **Date** | 2026-07-04 |
| **Implementation spec** | ./implementation-spec.md |
| **Coverage target** | ≥ 80% (achieved: **93%** on new modules) |

## Planned tests
| ID | File | Test name | Asserts |
|---|---|---|---|
| U1 | `tests/test_mlb/test_models.py` | `test_mlb_tables_register_on_shared_base` | 5 MLB tables visible to Alembic via shared `Base.metadata` |
| U2 | `tests/test_mlb/test_models.py` | `test_create_team/player/game` | ORM rows persist on sqlite |
| U3 | `tests/test_mlb/test_models.py` | `test_doubleheader_legs_coexist` | same date+matchup storable twice with distinct `game_number` |
| U4 | `tests/test_mlb/test_models.py` | `test_duplicate_matchup_same_game_number_rejected` | matchup uniqueness enforced |
| U5 | `tests/test_mlb/test_models.py` | `test_two_way_player_has_batter_and_pitcher_rows` | Ohtani case: one row per log table, same game |
| U6 | `tests/test_mlb/test_models.py` | `test_duplicate_batter_log_rejected` | `(game_pk, player_id)` uniqueness |
| U7 | `tests/test_mlb/test_fetcher.py` | `TestCachePath` (2) | traversal-safe cache keys; params vary keys |
| U8 | `tests/test_mlb/test_fetcher.py` | `TestFetchJson` (4) | cache hit skips HTTP; `use_cache=False` bypasses read+write; retries → `IngestError`; success writes cache |
| U9 | `tests/test_mlb/test_fetcher.py` | `TestIngestTeams` | team upsert idempotent, full metadata mapped |
| U10 | `tests/test_mlb/test_fetcher.py` | `TestIngestSchedule` (3) | doubleheader = 2 games; spring-training filtered; postseason flag from gameType; re-ingest corrects status |
| U11 | `tests/test_mlb/test_fetcher.py` | `TestBoxscoreParsers` (3) | non-batters excluded; two-way + relief pitcher rows; W/L/SV flags |
| U12 | `tests/test_mlb/test_fetcher.py` | `TestIngestBoxscore` (4) | two-way lands in both tables; players upserted before logs; idempotent; unknown gamePk → `IngestError` |
| U13 | `tests/test_mlb/test_fetcher.py` | `TestIngestDate` (3) | composed summary; zero-games day healthy; non-final games skipped |
| U14 | `tests/test_mlb/test_validate.py` | `TestValidateMlbRowCounts` (3) | no-games healthy; games-without-logs warns `False`; games-with-logs `True`; never raises |
| U15 | `tests/test_mlb/test_backfill.py` | `TestSeasonWindows` (2) | Feb 15 – Nov 15 coverage; contiguous non-overlapping windows |
| U16 | `tests/test_mlb/test_backfill.py` | `TestProgressFile` (2) | progress round-trip; missing file = empty |
| U17 | `tests/test_mlb/test_backfill.py` | `TestBackfillSeason` (3) | resume skips completed; `IngestError` skips game and continues; progress persisted per game |
| U18 | `tests/test_mlb/test_ingest_daily.py` | `TestExitCodeMatrix` (3) | healthy → not failed; validation failure → failed; step exception → failed but later steps still run |

## Mandatory categories

### as_of_date leakage (one per feature function)
**N/A this slice** — no feature functions exist yet. Enabler verified instead:
every log row stores `game_date`, `season`, `created_at`, `updated_at`
(asserted implicitly by U2/U5 round-trips), so future gates are enforceable.

### Idempotency (ingestion)
- [x] `ingest_mlb_teams` run twice → same rows/values (U9)
- [x] `ingest_mlb_schedule` run twice → 1 game, status correctable (U10)
- [x] `ingest_mlb_boxscore` run twice → same log counts (U12)

### API (`httpx.AsyncClient`)
**N/A this slice** — no API routes added.

### Validation
Walk-forward enabler only: `season` is first-class on games and both log
tables (U2/U10); no training in this slice.

### Edge cases
- [x] doubleheader (two games, same date/teams) — U3, U10
- [x] two-way player (batter + pitcher lines, one game) — U5, U11, U12
- [x] postseason game-type flag (MLB analog of NBA `004` prefix) — U10
- [x] zero-games day — U13, U14
- [x] spring-training/exhibition exclusion — U10
- [x] upstream timeout/permanent failure → backoff → `IngestError` — U8
- [x] non-final games skipped by boxscore ingest — U13

## Mocking policy
Never hit the real MLB StatsAPI: all HTTP goes through the `_fetch_json` /
`_http_get_json` seams, monkeypatched to trimmed real-shape JSON fixtures in
`tests/test_mlb/fixtures/`. No secrets in fixtures (the API is keyless).

## RED baseline
Each task's tests were run before its implementation and failed for the
intended reason (module/function not yet present), e.g.:

```
tests/test_mlb/test_models.py — ModuleNotFoundError: chalk.mlb (pre-T2)
tests/test_mlb/test_fetcher.py, test_validate.py — 2 collection errors (pre-T4–T10)
tests/test_mlb/test_backfill.py, test_ingest_daily.py — scripts absent (pre-T13/T14)
```

## GREEN target (filled in phase 4)
```
tests/test_mlb/: 41 passed
full suite: 296 passed, 4 warnings in 91.14s  (baseline was 255 passed)
coverage (new modules): chalk/mlb/fetcher.py 94%, models.py 100%,
validate.py 100%, scripts/mlb_backfill.py 81%, scripts/mlb_ingest_daily.py 90%
TOTAL new-code coverage: 93%
```

Note: one pre-existing test updated — `tests/test_scaffold.py::test_all_tables_registered`
asserted *exact* equality of registered tables (single-sport assumption); relaxed to a
subset assertion so additional sport packages can register tables on the shared Base.
