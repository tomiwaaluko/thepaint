# Phase 2 — Feature Engineering

## Goal
Build the complete feature generation pipeline. `generate_features(player_id, game_id, as_of_date)`
returns a validated dict of 80+ float features with zero None values. All feature functions
correctly gate on `as_of_date` — no future data ever leaks into a feature vector.

## Depends On
Phase 1 complete — `player_game_logs` and `team_game_logs` tables populated.

## Unlocks
Phase 3 (Baseline Models) — needs `generate_features()` to build training matrices.

## Skill Files to Read First
- `.claude/skills/feature-engineering/SKILL.md` — all patterns, function signatures, as_of_date rules
- `CLAUDE.md` — naming conventions, the leakage rule

---

## The as_of_date Rule (Read This First)

Every single function in this phase MUST filter database queries with `game_date < as_of_date`.
Use strict less-than, never less-than-or-equal (same-day leakage).
This is the most important correctness constraint in the project.
Write the as_of_date gate BEFORE any other logic in each function.
Add a comment `# as_of_date gate` next to every WHERE clause that enforces it.

---

## Step 1 — Rolling Window Averages

### `chalk/features/rolling.py`

**Constants:**
```python
ROLLING_WINDOWS = [5, 10, 20]
ROLLING_STATS = ["pts", "reb", "ast", "stl", "blk", "to_committed", "fg3m", "fg3a", "min_played", "fgm", "fga"]
```

**Functions to implement:**

`get_rolling_avg(session, player_id, stat, window, as_of_date) → float`
- Query last `window` game logs for player where `game_date < as_of_date` (as_of_date gate)
- Return avg of `stat` column, or 0.0 if no games found

`get_rolling_avg_split(session, player_id, stat, window, as_of_date, location) → float`
- Same as above but filter by `location` ("home" or "away")
- Output keys: `{stat}_avg_{window}g_home`, `{stat}_avg_{window}g_away`

`compute_trend_slope(values) → float`
- Linear regression slope over a list of floats
- Returns 0.0 if len(values) < 3

`get_stat_trend(session, player_id, stat, window, as_of_date) → float`
- Fetch last `window` values of `stat` in chronological order
- Return slope — positive = improving, negative = declining

`get_all_rolling_features(session, player_id, as_of_date) → dict[str, float]`
- Calls get_rolling_avg for every stat × window combination
- Calls get_rolling_avg_split for pts, reb, ast (home/away)
- Calls get_stat_trend for pts, reb, ast with window=10
- Returns flat dict, all keys snake_case: `pts_avg_5g`, `reb_avg_10g_home`, `pts_trend_10g`
- **Use asyncio.gather() to run all queries concurrently — do not run sequentially**

**Output keys (examples):**
```
pts_avg_5g, pts_avg_10g, pts_avg_20g
reb_avg_5g, reb_avg_10g, reb_avg_20g
ast_avg_5g, ast_avg_10g, ast_avg_20g
pts_avg_10g_home, pts_avg_10g_away
pts_trend_10g, reb_trend_10g, ast_trend_10g
min_played_avg_5g, min_played_avg_10g, min_played_avg_20g
fg3m_avg_5g, fg3m_avg_10g, fg3m_avg_20g
... (all ROLLING_STATS × ROLLING_WINDOWS)
```

---

## Step 2 — Opponent Defensive Features

### `chalk/features/opponent.py`

**Functions to implement:**

`get_opp_def_rtg(session, team_id, as_of_date, window=15) → float`
- Rolling average of team's def_rtg over last `window` games where `game_date < as_of_date`
- Output key: `opp_def_rtg_15g`

`get_opp_pace(session, team_id, as_of_date, window=15) → float`
- Rolling average of team's pace
- Output key: `opp_pace_15g`

`get_opp_pts_allowed_by_position(session, team_id, position, as_of_date, window=15) → float`
- How many pts does this team allow to players at `position` (PG/SG/SF/PF/C)?
- Join player_game_logs to players on player_id, filter by position and opponent team
- Output keys: `opp_pts_allowed_pg`, `opp_pts_allowed_sg`, etc.

`get_opp_fg3a_rate_allowed(session, team_id, as_of_date, window=15) → float`
- What fraction of opponent FGA are 3-pointers against this defense?
- Output key: `opp_fg3a_rate_allowed_15g`

`get_opp_stl_rate(session, team_id, as_of_date, window=15) → float`
`get_opp_blk_rate(session, team_id, as_of_date, window=15) → float`
- Output keys: `opp_stl_rate_15g`, `opp_blk_rate_15g`

`get_all_opponent_features(session, opponent_team_id, player_position, as_of_date) → dict[str, float]`
- Calls all above functions concurrently with asyncio.gather()
- Returns flat dict of all opponent features

---

## Step 3 — Situational Features

### `chalk/features/situational.py`

These features require no DB queries — compute from game and player objects.

**Function:**

`get_situational_features(game, player, previous_game_date) → dict[str, float]`

**Features to compute:**
```python
{
    # Rest
    "days_rest": min((game.date - previous_game_date).days, 7),  # cap at 7
    "is_back_to_back": 1.0 if days_rest == 0 else 0.0,
    "is_well_rested": 1.0 if days_rest >= 3 else 0.0,

    # Location
    "is_home": 1.0 if game.home_team_id == player.team_id else 0.0,
    "is_away": 1.0 if game.away_team_id == player.team_id else 0.0,
    "is_denver": 1.0 if is_denver_game(game) else 0.0,

    # Season context
    "game_number_in_season": game_number,           # 1–82
    "is_second_half_season": 1.0 if game_number > 41 else 0.0,
    "is_playoffs": 1.0 if game.is_playoffs else 0.0,
}
```

`get_previous_game_date(session, player_id, as_of_date) → date | None`
- Returns date of player's most recent game before as_of_date
- Returns None if no previous game found (treat days_rest as 7)

`get_game_number_in_season(session, team_id, season, as_of_date) → int`
- Count of games played by team in season before as_of_date

---

## Step 4 — Roster / Injury Context

### `chalk/features/roster.py`

**Functions:**

`get_absent_players(session, team_id, game_date) → list[Player]`
- Returns players with status "Out" or "Doubtful" on game_date
- Uses injury table

`get_roster_features(session, player_id, team_id, opponent_team_id, game_id, as_of_date) → dict[str, float]`

**Features:**
```python
{
    "absent_teammate_count": len(absent_teammates),
    "absent_teammate_usage_sum": sum of absent teammates' usage_rate_10g,
    "star_teammate_out": 1.0 if any absent teammate avg > 20 pts,
    "absent_opp_player_count": len(absent_opp_players),
    "key_opp_defender_out": 1.0 if top opp defender is out,
}
```

Note: `absent_teammate_usage_sum` is the single highest-signal feature for detecting
usage spikes when a teammate is injured. Always compute it.

---

## Step 5 — Usage & Role Features

### `chalk/features/usage.py`

**Functions:**

`get_usage_features(session, player_id, as_of_date) → dict[str, float]`

```python
{
    "usage_rate_10g": ...,        # % of team possessions used while on court
    "min_share_10g": ...,         # avg_min / 48
    "starter_rate_10g": ...,      # fraction of last 10 games started (0.0–1.0)
    "fg3a_rate_10g": ...,         # fg3a / fga — is this player a shooter?
    "ft_rate_10g": ...,           # fta / fga — free throw getter?
    "ast_to_ratio_10g": ...,      # ast / to_committed — ball security
}
```

`usage_rate` is not directly in player_game_logs — approximate as:
`(fga + 0.44 * fta + to_committed) / team_possessions_per_min * min_played`
Or use a simpler proxy: `(fga + 0.44 * fta + to_committed) / min_played * 36`

---

## Step 6 — Master Feature Pipeline

### `chalk/features/pipeline.py`

This is the single entry point. All model training and prediction code calls this function only.

```python
async def generate_features(
    session: AsyncSession,
    player_id: int,
    game_id: str,
    as_of_date: datetime,
) -> dict[str, float]:
    """
    Generate the complete feature vector for a player-game pair.

    Args:
        player_id: NBA player ID
        game_id: NBA game ID
        as_of_date: Only use data strictly before this datetime (leakage gate)

    Returns:
        Flat dict of ~80+ float features. No None values. All keys snake_case.

    Raises:
        FeatureError: If player or game not found, or critical features unavailable.
    """
```

**Implementation pattern:**
1. Fetch game and player from DB (raise FeatureError if not found)
2. Determine opponent_team_id
3. Run all feature groups concurrently with asyncio.gather()
4. Merge all dicts into single flat dict
5. Replace any None values with 0.0
6. Assert all values are float (raise FeatureError if not)
7. Return

```python
# Run all feature groups concurrently
rolling, opponent, roster, usage = await asyncio.gather(
    get_all_rolling_features(session, player_id, as_of_date),
    get_all_opponent_features(session, opponent_team_id, player.position, as_of_date),
    get_roster_features(session, player_id, player.team_id, opponent_team_id, game_id, as_of_date),
    get_usage_features(session, player_id, as_of_date),
)

# Situational is synchronous
prev_game_date = await get_previous_game_date(session, player_id, as_of_date)
situational = get_situational_features(game, player, prev_game_date)

features = {**rolling, **opponent, **roster, **usage, **situational}
```

`build_training_matrix(session, player_ids, stat, seasons) → pd.DataFrame`
- Calls generate_features for every player × game combination across seasons
- Adds target column = actual value of `stat` from player_game_logs
- Returns DataFrame with features + target + metadata (player_id, game_id, game_date, season)
- Used by Phase 3 model training

---

## Step 7 — Feature Validation Script

### `scripts/validate_features.py`

Run this after building features to sanity check the pipeline.

```
python scripts/validate_features.py --player_id 2544 --game_id 0022301234
```

Outputs:
- Full feature dict for the player/game
- Count of features, count of zeros, count of nulls
- Top 10 most informative features (highest variance in recent games)
- Confirms no leakage: re-run with as_of_date one day earlier and verify features change

---

## Step 8 — Tests

### `tests/test_features/test_rolling.py`

**Critical tests — all must pass:**

`test_rolling_avg_respects_as_of_date`
- Insert a game log dated AFTER as_of_date
- Verify that game is NOT included in the rolling average
- This is the most important test in the entire codebase

`test_rolling_avg_returns_zero_for_no_games`
- Player with no game logs returns 0.0, not None

`test_rolling_avg_window_respected`
- Insert 25 game logs, request window=5, verify only last 5 included

`test_home_away_split_correct`
- Insert 5 home games and 5 away games
- Verify home avg ≠ away avg and both correct

### `tests/test_features/test_opponent.py`

`test_opp_def_rtg_respects_as_of_date`
`test_opp_pts_allowed_by_position_correct`

### `tests/test_features/test_pipeline.py`

`test_generate_features_returns_no_none_values`
`test_generate_features_all_values_are_float`
`test_generate_features_as_of_date_gate`
- Call generate_features twice with different as_of_dates
- Verify features differ (earlier date has less data)

`test_build_training_matrix_shape`
- Verify matrix has expected number of rows and no NaN target values

---

## Phase 2 Completion Checklist

- [ ] `pytest tests/test_features/` — all tests pass, especially as_of_date gate tests
- [ ] `generate_features(2544, game_id, as_of_date)` returns 80+ features with zero Nones
- [ ] `build_training_matrix()` generates matrix for top 50 players in < 5 minutes
- [ ] Feature validation script confirms no leakage
- [ ] asyncio.gather() used in rolling and opponent feature functions (parallel queries)
- [ ] `TODO.md` updated — all Phase 2 checkboxes marked done
