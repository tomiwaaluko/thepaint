---
name: feature-engineering
description: Use this skill whenever building, modifying, or debugging any feature generation code in Chalk. Covers rolling window averages, opponent defensive profiles, situational features, roster/injury context, and the master feature pipeline. Always use this skill when touching anything in chalk/features/, when writing generate_features(), or when a function requires an as_of_date parameter. Critical for preventing data leakage.
---

# Feature Engineering Skill

## The Prime Directive: as_of_date

Every single feature function must accept `as_of_date: datetime` and filter all database queries to `game_date < as_of_date`. This is non-negotiable. Validate it exists in every function signature before writing any logic.

```python
# ALL feature functions follow this signature pattern
async def get_rolling_avg(
    session: AsyncSession,
    player_id: int,
    stat: str,
    window: int,
    as_of_date: datetime,
) -> float | None:
    result = await session.execute(
        select(func.avg(getattr(PlayerGameLog, stat)))
        .where(PlayerGameLog.player_id == player_id)
        .where(PlayerGameLog.game_date < as_of_date)  # ← ALWAYS this filter
        .order_by(PlayerGameLog.game_date.desc())
        .limit(window)
    )
    return result.scalar()
```

---

## Feature Categories & Implementation

### 1. Rolling Window Averages (`features/rolling.py`)

Compute for windows `[5, 10, 20]` for every tracked stat.

**Stats to roll:** `pts, reb, ast, stl, blk, to_committed, fg3m, fg3a, fgm, fga, ftm, fta, min_played`

**Output keys follow pattern:** `{stat}_avg_{window}g` e.g. `pts_avg_5g`, `reb_avg_10g`

```python
ROLLING_WINDOWS = [5, 10, 20]
ROLLING_STATS = ["pts", "reb", "ast", "stl", "blk", "to_committed", "fg3m", "fg3a", "min_played"]

async def get_all_rolling_features(
    session: AsyncSession,
    player_id: int,
    as_of_date: datetime,
) -> dict[str, float]:
    features = {}
    for stat in ROLLING_STATS:
        for window in ROLLING_WINDOWS:
            val = await get_rolling_avg(session, player_id, stat, window, as_of_date)
            features[f"{stat}_avg_{window}g"] = val if val is not None else 0.0
    return features
```

**Also compute home/away splits:**
- `pts_avg_10g_home`, `pts_avg_10g_away` — filter by `game_location IN ('home', 'away')`

**Trend slope** — whether player is improving or declining:
```python
# pts_trend_10g = slope of linear regression over last 10 game pts values
# positive = improving, negative = declining
def compute_trend(values: list[float]) -> float:
    if len(values) < 3:
        return 0.0
    x = np.arange(len(values))
    slope, _ = np.polyfit(x, values, 1)
    return float(slope)
```

---

### 2. Opponent Defensive Features (`features/opponent.py`)

Key insight: a player facing a weak defense gets more opportunities and scores more.

**Opponent Defensive Rating** — points allowed per 100 possessions, rolling 15 games:
```python
# Output key: opp_def_rtg_15g
async def get_opp_def_rtg(session, opponent_team_id, as_of_date, window=15) -> float:
    ...
```

**Position-Specific Points Allowed** — how many points does this defense allow to players at this position:
```python
# Output keys: opp_pts_allowed_pg, opp_pts_allowed_sg, opp_pts_allowed_sf, opp_pts_allowed_pf, opp_pts_allowed_c
# Uses rolling 15 games, filtered by position of the scoring player
```

**Opponent Pace** — affects total counting stat opportunities:
```python
# Output key: opp_pace_15g
# Higher pace = more possessions = more opportunities for everyone
```

**Opponent 3PA Rate Allowed** — critical for shooter projections:
```python
# Output key: opp_fg3a_rate_allowed_15g
# What % of opponent FGA are 3s against this defense
```

**Opponent Steal/Block Rates** — affects turnovers and interior scoring:
```python
# Output keys: opp_stl_rate_15g, opp_blk_rate_15g
```

---

### 3. Situational Features (`features/situational.py`)

```python
def get_situational_features(
    game: Game,
    player: Player,
    as_of_date: datetime,
) -> dict[str, float]:
    return {
        # Rest
        "days_rest": (game.date - last_game_date).days,  # cap at 7
        "is_back_to_back": 1.0 if days_rest == 0 else 0.0,
        "is_well_rested": 1.0 if days_rest >= 3 else 0.0,

        # Location
        "is_home": 1.0 if game.home_team_id == player.team_id else 0.0,
        "is_denver": 1.0 if opponent_arena == "Ball Arena" else 0.0,  # altitude

        # Season context
        "games_into_season": game_number_this_season,
        "is_second_half_season": 1.0 if game_number > 41 else 0.0,

        # Game importance (wins needed for playoff seeding)
        "playoff_games_back": games_back_from_8th_seed,
    }
```

---

### 4. Roster / Injury Context Features (`features/roster.py`)

This is the highest-leverage situational signal. When a star teammate is out, secondary players see usage spikes.

```python
async def get_roster_features(
    session: AsyncSession,
    player_id: int,
    team_id: int,
    game_id: int,
    as_of_date: datetime,
) -> dict[str, float]:
    # Get list of teammates out for this game
    absent_teammates = await get_absent_players(session, team_id, game_id, as_of_date)

    # Sum usage rates of absent teammates = opportunity available
    absent_usage_sum = sum(
        await get_rolling_avg(session, p.player_id, "usage_rate", 10, as_of_date)
        for p in absent_teammates
    )

    # Get absent key opponent defenders
    absent_opp_defenders = await get_absent_players(session, opponent_team_id, game_id, as_of_date)

    return {
        "absent_teammate_count": len(absent_teammates),
        "absent_teammate_usage_sum": absent_usage_sum,  # key signal
        "star_teammate_out": 1.0 if any(p.is_star for p in absent_teammates) else 0.0,
        "key_opp_defender_out": 1.0 if any(p.is_key_defender for p in absent_opp_defenders) else 0.0,
    }
```

---

### 5. Usage & Role Features

```python
{
    "usage_rate_10g": ...,          # % of team possessions used
    "min_share_10g": ...,           # avg_min / 48
    "starter_rate_10g": ...,        # how often starting (0.0–1.0)
    "assist_opp_rate_10g": ...,     # assist opportunities per minute
}
```

---

### 6. Master Pipeline (`features/pipeline.py`)

The single entry point for all feature generation. All model training and prediction calls this.

```python
async def generate_features(
    session: AsyncSession,
    player_id: int,
    game_id: int,
    as_of_date: datetime,
) -> dict[str, float]:
    """
    Generate the full feature vector for a player-game prediction.
    Returns a flat dict of ~80 features. All values are floats.
    Missing values default to 0.0 — never return None in the dict.
    """
    game = await get_game(session, game_id)
    player = await get_player(session, player_id)
    opponent_team_id = get_opponent_id(game, player.team_id)

    features = {}
    features.update(await get_all_rolling_features(session, player_id, as_of_date))
    features.update(await get_opp_defensive_features(session, opponent_team_id, as_of_date))
    features.update(get_situational_features(game, player, as_of_date))
    features.update(await get_roster_features(session, player_id, player.team_id, game_id, as_of_date))

    # Validate: no None values, all float
    assert all(v is not None for v in features.values()), "Feature dict contains None"
    return {k: float(v) for k, v in features.items()}
```

---

## Testing Requirements

Every feature function needs a test that verifies the `as_of_date` gate:

```python
async def test_rolling_avg_respects_as_of_date(session):
    # Insert a game log dated AFTER as_of_date
    future_log = PlayerGameLog(game_date=date(2024, 3, 1), pts=50, ...)
    session.add(future_log)

    # Feature should NOT include the future game
    result = await get_rolling_avg(session, player_id, "pts", 5, as_of_date=date(2024, 2, 1))
    assert result != 50  # future data must not appear
```

---

## Common Mistakes to Avoid

- Using `game_date <= as_of_date` instead of `<` (same-day leakage)
- Forgetting to handle NULL / no games found (return 0.0, not None)
- Computing opponent features using the wrong team_id (always use opponent, not player's team)
- Mixing home/away splits with overall averages in the same window
- Using season-level stats instead of rolling stats (season stats include future games)
