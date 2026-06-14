# Accuracy Improvement Plan

**Last updated:** 2026-06-14
**Status:** Wave 1 implementation in progress; production deployment pending

---

## Context

This plan was derived from reading the full codebase and querying production Supabase directly. All file references, function names, and line numbers are exact. Each wave must be verified before starting the next — later waves depend on earlier ones.

Production state at time of writing:
- 13,314 games in DB (playoffs through 2026-05-30)
- 154,718 player game logs
- 45 betting lines at last read-only audit; Odds API code existed but Railway cron was still stubbed locally before this branch
- Duplicate game records: ESPN-style `401...` IDs (have stats) coexist with NBA API `004...` IDs (empty shells) for the same games
- Models trained on 2015-2024 regular season; currently predicting 2025-26 playoffs with no playoff-specific adjustment

Read-only production audit on 2026-06-14:
- `max(injuries.report_date)` is 2026-05-20 and there are 0 injury rows after that date.
- Game `401873342` is final on 2026-05-21 with 0 player logs, but its duplicate NBA-format game row `0042500302` has 26 player logs.
- There are 18 duplicate matchup groups, not just one; many duplicate `004...` rows already have player logs.
- Production Alembic version is `c3d4e5f6a7b8`; migrations in this branch are not yet applied.
- Railway logs and service variables could not be checked because Railway is not linked in this session.

---

## Pre-flight Fixes Before Wave 1

**Goal:** Fix confirmed correctness bugs and verify production-state claims before activating new data sources or retraining models.

### Task 0.1 - Fix roster injury feature lookup

`chalk/features/roster.py::get_absent_players()` must not require `Injury.report_date == game_date`. Injury reports can be published 1-7 days before tipoff, so roster features should use reports where `report_date <= as_of_date` and `report_date >= as_of_date - 7 days`.

The feature query must deduplicate by player and use only the latest report in the window. A stale `Out` report must not override a newer `Active`, `Questionable`, or other non-absent status.

Completion criteria:
- [x] Roster features include `Out` and `Doubtful` players reported in the 7-day window.
- [x] Future injury reports are excluded.
- [x] Latest report wins when multiple reports exist for a player.
- [x] Focused feature tests cover the above behavior.

### Task 0.2 - Fix betting line uniqueness before Odds API activation

`betting_lines` currently uses `(game_id, market, sportsbook)` as its unique key. That is correct for one game total per book, but wrong for player props because every player in a game can share the same market and sportsbook. The key must include `player_id`.

Game-level markets use `player_id = NULL`, so the PostgreSQL constraint must still make repeated game-total upserts deterministic. Use `NULLS NOT DISTINCT` or an equivalent unique-index strategy.

Completion criteria:
- [x] Alembic migration replaces `uq_betting_game_market_book` with a player-aware unique constraint.
- [x] SQLAlchemy model metadata matches the database constraint.
- [x] `upsert_betting_lines()` uses the same conflict target.
- [x] Focused ingestion tests assert the generated PostgreSQL upsert target.

### Task 0.3 - Verify production assumptions before data repair

The following items were checked against Supabase; Railway remains blocked until the project is linked:
- [x] Injury ingestion last successful DB report date is 2026-05-20.
- [x] Game `401873342` on 2026-05-21 has zero player logs.
- [x] Duplicate `0042500302` for the same physical game has 26 player logs, so data repair should merge canonical game IDs rather than simply backfill `401873342`.
- [ ] `ODDS_API_KEY` is present for the relevant Railway services.

Do not retrain models until these checks and any required migration/data repair are deployed.

---

## Wave 1 — Data Quality (prerequisite for everything else)

**Goal:** Clean the database and activate the Odds API pipeline. No model changes. No feature changes.

**Autonomous tools available:** Supabase MCP (execute SQL, apply migrations), Railway MCP (logs, env vars, redeploy)

---

### Task 1.1 — Fix Duplicate Game IDs

**Problem:**
`ingest_today_scoreboard` can create NBA API format IDs (`004...`) while ESPN fallback paths can create ESPN-style IDs (`401...`) for the same physical game. Both IDs can persist in the `games` table. A 2026-06-14 audit showed this is not limited to empty `004...` shells; several duplicate pairs have player logs on both IDs, and at least one reported missing-log ESPN row has logs on its duplicate NBA-format row.

**Evidence from production:**
```text
game_id=401873203  date=2026-05-30  status=final  player_logs=19   <- has stats
game_id=0042500317 date=2026-05-30  status=scheduled  player_logs=0  <- empty shell
game_id=401873342  date=2026-05-21  status=final  player_logs=0
game_id=0042500302 date=2026-05-21  status=final  player_logs=26
```

**Files to change:**
- `chalk/ingestion/seed.py` - `upsert_games()`
- `chalk/db/models.py` - `Game` matchup uniqueness
- `alembic/versions/` - migration to merge duplicate game IDs and add `uq_game_matchup`

**Implementation steps:**

1. **Migration to merge existing duplicate records:**
   Pick the canonical game row per `(date, home_team_id, away_team_id)` by highest player-log count, move non-conflicting child rows from duplicate IDs, delete duplicate child rows that already exist on the canonical game, delete duplicate games, and then create `uq_game_matchup`.

2. **Prevent future duplicates:**
   Add a unique constraint on `(date, home_team_id, away_team_id)` to `games` table so the same physical game cannot be inserted twice regardless of ID format:
   ```sql
   ALTER TABLE games
   ADD CONSTRAINT uq_game_matchup UNIQUE (date, home_team_id, away_team_id);
   ```
   Note: Apply this after the merge above, not before.

3. **Code change - prevent future duplicate matchups in `upsert_games`:**
   When any game ingest path creates a game, check if a record already exists for `(date, home_team_id, away_team_id)`. If yes and the incoming ID differs, skip insertion and keep the existing canonical game row.

**Verification using Supabase MCP:**
```sql
-- Should return 0 after fix
SELECT COUNT(*)
FROM (
  SELECT date, home_team_id, away_team_id
  FROM games
  GROUP BY date, home_team_id, away_team_id
  HAVING COUNT(*) > 1
) duplicate_matchups;
```

---

### Task 1.2 — Plug in the Odds API (Vegas Lines)

**Problem:**
`fetch_player_props()` existed in `chalk/ingestion/odds_fetcher.py` but step 5 of `scripts/railway_ingest.py` was stubbed before this branch — it only counted today's games and logs, never called the fetcher.

Additionally, `odds_fetcher.py` has a game ID mismatch: the Odds API returns its own internal event IDs, not NBA game IDs. Storing them raw means they can never JOIN to the `games` table.

**Files to change:**
- `scripts/railway_ingest.py` — replace stub with real `fetch_player_props()` call
- `chalk/ingestion/odds_fetcher.py` — fix game ID resolution (match Odds API event to NBA game by date + team names)
- `chalk/db/models.py` — `BettingLine.player_id` resolution (Odds API gives player name strings, not IDs — needs name→ID lookup)

**Implementation steps:**

1. **Fix `odds_fetcher.py` — game ID resolution:**
   After fetching events from the Odds API, resolve each event to an internal `game_id` by matching Eastern game date + home/away team name. Prefer the matching game row with the most player logs if duplicate game IDs exist before migration.

2. **Fix `odds_fetcher.py` — player ID resolution:**
   Player prop outcomes include player name strings in the `description` field. Reuse `resolve_player_id()` from `chalk/ingestion/injury_fetcher.py` to resolve to `player_id`.

3. **Activate in `railway_ingest.py`:**
   Replace the step 5 stub with:
   ```python
   from chalk.ingestion.odds_fetcher import fetch_player_props, fetch_game_totals

   async def do_fetch_odds(session):
       props = await fetch_player_props(session, today)
       totals = await fetch_game_totals(session, today)
       log.info("odds_fetched", props=props, totals=totals, date=str(today))
       return props + totals

   await run_step("fetch_odds_lines", with_session(do_fetch_odds))
   ```

4. **Add `vegas_line` as a feature:**
   Add `chalk/features/vegas.py` with:
   - `get_player_prop_line(player_id, stat, game_date)` → float (the market line for that stat)
   - `get_game_total_line(game_id, game_date)` → float (implied game total)

   Add both to `generate_features()` in `chalk/features/pipeline.py`.

**Markets to ingest from Odds API:**
| Market key | Maps to stat |
|---|---|
| `player_points` | `pts` |
| `player_rebounds` | `reb` |
| `player_assists` | `ast` |
| `player_threes` | `fg3m` |
| `player_blocks` | `blk` |
| `player_steals` | `stl` |
| `totals` | game total (both teams) |

**Verification using Supabase MCP:**
```sql
SELECT market, COUNT(*), AVG(line) FROM betting_lines
GROUP BY market ORDER BY COUNT(*) DESC;
```

**Railway MCP role:** After deploying the change, check Railway deploy logs for `odds_fetched` events to confirm the cron is calling the API. Set `ODDS_API_KEY` via Railway MCP `set_variables` if not already present.

---

### Wave 1 Completion Criteria
- [x] Migration added to merge duplicate physical game records and create `uq_game_matchup`
- [x] `upsert_games()` skips future duplicate matchup inserts
- [x] Odds fetcher resolves Odds API events to internal `games.game_id`
- [x] Odds fetcher resolves player prop outcome descriptions to `players.player_id`
- [x] Railway ingest script calls `fetch_player_props()` and `fetch_game_totals()`
- [x] Vegas-line features are added to `generate_features()`
- [ ] Migrations applied in production
- [ ] Railway `ODDS_API_KEY` verified on `web`/`ingest`
- [ ] `betting_lines` table verified after next deployed cron run

---

## Wave 2 — Feature Engineering

**Goal:** Add 3 new feature groups to `generate_features()`. No model retraining yet — verify features generate cleanly first.

**Depends on:** Wave 1 complete (clean game IDs, betting lines flowing)

---

### Task 2.1 — Rolling Standard Deviation Features

**Problem:**
`chalk/features/rolling.py` computes rolling averages and trend slopes for `pts`, `reb`, `ast` but never computes variance. A player averaging 20 pts with std dev 3 vs std dev 12 should produce very different confidence intervals. The quantile models currently have no signal about a player's consistency.

**File to change:** `chalk/features/rolling.py`

**What to add:**

New function `get_rolling_std()` — mirrors `get_rolling_avg()` exactly but computes standard deviation instead of mean. Apply to `TREND_STATS = ["pts", "reb", "ast"]` at windows `[5, 10]`.

New features added to `get_all_rolling_features()`:
```
pts_std_5g, pts_std_10g
reb_std_5g, reb_std_10g
ast_std_5g, ast_std_10g
```

That adds 6 features to the vector (currently ~80+ features).

**Leakage check:** Same `game_date < as_of_date` gate already used in `get_rolling_avg` must be applied identically.

---

### Task 2.2 — Head-to-Head History Features

**Problem:**
`chalk/features/opponent.py` measures how a *team* defends a *position* on average across all opponents. It has no signal for how *this specific player* has historically performed against *this specific opponent team*. SGA against the Spurs over 3 years is more predictive than SGA against average NBA defense.

**File to change:** `chalk/features/opponent.py`

**What to add:**

New function `get_h2h_avg()`:
```
get_h2h_avg(player_id, opponent_team_id, stat, min_games, as_of_date) -> float
```

Logic:
- Query `player_game_logs` joined to `games` where `player_id = player_id` AND the opponent is `opponent_team_id` AND `game_date < as_of_date`
- Require at least `min_games=3` matchups; return `0.0` if insufficient history (new player or new team)
- Return rolling average of `stat` across all historical matchups (no window cap — use all history)

New features added to `get_all_opponent_features()`:
```
h2h_pts_vs_opp    (career avg pts against this specific team)
h2h_reb_vs_opp
h2h_ast_vs_opp
h2h_fg3m_vs_opp
h2h_games_vs_opp  (sample size — let model learn to discount low-sample values)
```

**Leakage check:** The `as_of_date` gate is critical here — only games *before* the prediction date.

---

### Task 2.3 — Playoff Context Features

**Problem:**
`chalk/features/situational.py` already has `is_playoffs` (binary) and `playoff_round` (1-4). But the model has never been trained on enough playoff data to use these signals effectively — the training set (2015-2024 regular season) has very few playoff rows.

More importantly, the rolling features in Wave 2.1 use all prior games indiscriminately. During a playoff run, the last 3 playoff games are more predictive than the last 5 regular-season games.

**File to change:** `chalk/features/rolling.py`

**What to add:**

New function `get_rolling_avg_playoff()` — same as `get_rolling_avg` but adds a filter: only use `game_date` rows where the corresponding `games.is_playoffs = TRUE`.

New features in `get_all_rolling_features()`:
```
pts_avg_5g_playoff    (last 5 playoff games only; 0.0 if <3 playoff games in history)
reb_avg_5g_playoff
ast_avg_5g_playoff
fg3m_avg_5g_playoff
min_played_avg_5g_playoff
```

**Note:** These will be `0.0` for all regular season predictions — that's correct. The model will learn to ignore them when `is_playoffs=0`.

---

### Task 2.4 — Vegas Line as Feature

**Depends on:** Task 1.2 complete (betting lines flowing in DB)

**File to change:** Create `chalk/features/vegas.py`, add to `chalk/features/pipeline.py`

**What to add:**

```python
async def get_player_prop_line(
    session, player_id, stat, game_date, as_of_date
) -> float:
    """Market consensus prop line for player+stat on game_date.
    Returns 0.0 if no line exists (model learns to handle sparse coverage).
    """
```

Query `betting_lines` where `player_id = player_id` AND `market = <stat_market_key>` AND `DATE(timestamp) = game_date` AND `timestamp < as_of_date`. Average across sportsbooks for a consensus line.

```python
async def get_game_total_line(session, game_id, as_of_date) -> float:
    """Market game total (o/u line) for implied scoring environment."""
```

New features in `generate_features()`:
```
vegas_pts_line       (market prop line for pts; 0.0 if unavailable)
vegas_reb_line
vegas_ast_line
vegas_fg3m_line
vegas_game_total     (implied total points for the game)
vegas_has_line       (binary: 1.0 if any line exists for this player today)
```

**Leakage note:** Vegas lines for game day are set before tipoff, so using them as a feature for game-day predictions is valid. The `as_of_date` gate ensures we only use lines timestamped before the prediction window.

---

### Wave 2 Completion Criteria
- [ ] `generate_features()` returns ~95+ features (was ~80)
- [ ] No `None` values leak through (the existing `float(v) if v is not None else 0.0` guard in `pipeline.py:81` handles this)
- [ ] Run against 3-5 known player-game pairs and inspect output dict manually
- [ ] No data leakage: verify with a unit test that future game data is excluded

---

## Wave 3 — Model Retraining

**Goal:** Retrain all 7 stat models + playoff variants using the expanded feature set and updated training data (2015-2026 including 2024-25 season and 2025-26 playoffs).

**Depends on:** Wave 2 complete (all new features generating correctly)

---

### Task 3.1 — Retrain Base Models on 2024-26 Data

**Problem:**
`CLAUDE.md` says training cutoff is 2023-24. The DB now has 2024-25 and early 2025-26 data. New players (Wembanyama year 2, Dylan Harper, Stephon Castle) have only been seen in inference, never training.

**Files to change:**
- `scripts/train_all.py` — update season list passed to `build_training_matrix()`
- `chalk/models/player.py` — verify walk-forward CV still covers correct splits

**Training split update:**
```
Training:   2015-16 through 2023-24  (was: 2022-23)
Validation: 2024-25
Test:        2025-26 regular season + playoffs to date
```

**Process:**
1. Run `build_training_matrix()` for each of the 7 stats with new season list
2. Run Optuna hyperparameter tuning (already in `chalk/models/tuning.py`)
3. Retrain XGBoost + LightGBM models
4. Retrain quantile models for `pts`, `reb`, `ast`
5. Save new models via `registry.save_model()` / `registry.save_lgbm_model()`
6. Call `registry.invalidate_cache()` before serving

**Railway MCP role:** After committing new model `.joblib` files, redeploy the `web` service via Railway MCP to pick them up. Verify via Railway logs that the new model version is loading (`model_saved` log events).

**Target MAE improvements (from current baselines in CLAUDE.md):**

| Stat | Current Target | Expected post-retrain |
|---|---|---|
| pts | ≤ 5.0 | ≤ 4.5 (with Vegas line feature) |
| reb | ≤ 2.5 | ≤ 2.2 |
| ast | ≤ 2.0 | ≤ 1.8 |
| fg3m | ≤ 1.2 | ≤ 1.1 |

---

### Task 3.2 — Playoff-Specific Model Variants

**Problem:**
`chalk/predictions/player.py:62-70` logs a warning every time a playoff prediction is made because the models have never seen meaningful playoff data. Playoff pace is ~3-5% slower, defensive intensity increases, and rotation tightens (fewer players get minutes per game — confirmed in production: playoff games show 19-28 player rows vs regular season ~26-30).

**Approach: Separate model files, not model architecture changes**

Rather than changing the training code fundamentally, train a second set of models using only playoff game logs as training data + use the general model's prediction as an additional feature (stacking).

**Files to change:**
- `chalk/models/player.py` — add `train_playoff_model()` method
- `chalk/models/registry.py` — add `_playoff_path()`, `save_playoff_model()`, `load_playoff_model()`
- `chalk/predictions/player.py` — in `predict_player()`, branch on `game.is_playoffs` to use playoff model when available, fall back to base model

**Implementation:**

```python
# In registry.py
def _playoff_path(stat: str) -> Path:
    return MODEL_DIR / f"{stat}_playoff_model.joblib"
```

```python
# In player.py predict_player()
if game.is_playoffs:
    try:
        model = load_playoff_model(stat)
    except Exception:
        model = load_lgbm_model(stat)  # fallback to base
```

**Training data for playoff models:**
- Use all playoff game logs from 2015-2026 (~15,000 player-game rows across 11 playoff seasons)
- Include all Wave 2 features
- Add `playoff_round` as a high-weight feature (round 1 vs Finals play very differently)
- Use LightGBM only (better on smaller datasets than XGBoost)
- Walk-forward CV: train on 2015-22 playoffs, validate on 2022-23, test on 2023-24

**Verification using Supabase MCP:**
```sql
-- Check predictions table after redeployment for updated model_version
SELECT model_version, COUNT(*), MIN(created_at), MAX(created_at)
FROM predictions
GROUP BY model_version
ORDER BY MAX(created_at) DESC
LIMIT 5;
```

---

### Wave 3 Completion Criteria
- [ ] All 7 base stat models retrained and saved with new version timestamp
- [ ] Playoff model files exist for `pts`, `reb`, `ast`, `fg3m`
- [ ] `predict_player()` branches correctly for `game.is_playoffs`
- [ ] Validation MAE on 2024-25 holdout meets or beats targets above
- [ ] Railway `web` service redeployed and loading new model version (confirm via `model_version` in prediction responses)

---

## Execution Notes

### How I operate autonomously per wave:

**Supabase MCP** — I can:
- Run diagnostic SQL queries before making changes
- Apply schema migrations via `apply_migration`
- Verify row counts and data quality after each step
- Check for leakage in feature queries directly against production data

**Railway MCP** — I can:
- Read deployment logs to confirm cron steps executed correctly
- Set/update environment variables (e.g., `ODDS_API_KEY`)
- Trigger redeployment of `web` service after model files are committed
- Monitor HTTP error rates after changes go live

**What requires your action:**
- Approving each wave before I start it
- Running `scripts/train_all.py` locally (or on a machine with GPU/CPU time) — model training is compute-intensive and Railway is not the right place for it
- Reviewing and merging PRs for schema migrations before I apply them
- Providing `ODDS_API_KEY` if not already in Railway environment

### Branching strategy:
Each wave gets its own branch:
- `wave-1/data-quality`
- `wave-2/feature-engineering`
- `wave-3/model-retraining`

Per CLAUDE.md: all production deployments go to the `railway` branch, not `main`.

---

## What This Does NOT Include

- Frontend changes (out of scope)
- Changing the API response schema (breaking change)
- Real-time line movement tracking (would require websocket/streaming Odds API tier)
- Player tracking data (requires NBA Stats premium access)
- Coaching/lineup prediction (no structured data source available)
