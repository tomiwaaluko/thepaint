# Phase 5 — Betting & Fantasy

## Goal
Over/under probability distributions vs. Vegas lines with edge calculation. Fantasy scoring
for DraftKings, FanDuel, and Yahoo including Monte Carlo floor/ceiling simulation.

## Depends On
Phase 4 complete — prediction API working with quantile distributions.

## Unlocks
Phase 6 (Dashboard) — betting and fantasy routes feed the UI.

## Skill Files to Read First
- `.claude/skills/api-patterns/SKILL.md` — OverUnderResponse schema, props route pattern

---

## Step 1 — Over/Under Probability Module

### `chalk/betting/over_under.py`

**Core concept:** Given a quantile distribution (p10, p25, p50, p75, p90) for a stat and
a Vegas line, estimate the probability that the actual value exceeds the line.

**Functions:**

`fit_distribution(p10, p25, p50, p75, p90) → scipy.stats distribution`
- Fit a continuous distribution to the 5 quantile points
- Use a normal distribution as baseline: mean=p50, std estimated from (p90-p10)/2.56
- For skewed stats (pts), try a lognormal fit and pick best by KS test

`over_probability(line: float, p10, p25, p50, p75, p90) → float`
- Returns P(stat > line) using the fitted distribution
- Clamp result to [0.01, 0.99] — never return 0% or 100%

`american_to_implied_probability(odds: int) → float`
- Convert American odds to implied probability
- -110 → 0.524, +120 → 0.455, etc.
- Apply vig removal: divide by (over_implied + under_implied) to get true probability

`calculate_edge(over_prob: float, implied_prob: float) → float`
- edge = over_prob - implied_prob
- Positive = model likes the over vs. the book
- Negative = model likes the under

`build_over_under_response(session, player_id, game_id, stat, as_of_date) → OverUnderResponse`
- Get prediction from `predict_player()`
- Get Vegas line from `betting_lines` table for this player/stat/game
- Compute over_probability, implied probability from odds, edge
- Return OverUnderResponse

**Edge thresholds for confidence:**
- `|edge| >= 0.08` → "high" confidence
- `|edge| >= 0.04` → "medium" confidence
- `|edge| < 0.04` → "low" confidence (too close to call)

---

## Step 2 — Edge Calculator

### `chalk/betting/edge.py`

**Functions for tracking model performance over time:**

`log_prediction_vs_result(session, pred_id, actual_value) → None`
- After a game is final, record actual vs. predicted
- Used for model drift monitoring in Phase 7

`calculate_clv(session, player_id, stat, game_id) → float | None`
- Closing Line Value: compare model's line to the Vegas closing line
- Positive CLV means model was sharper than the market
- Returns None if closing line not available

`get_edge_summary(session, days=30) → dict`
- Rolling 30-day summary: hit rate, mean edge, ROI if betting at -110 on all high-confidence picks
- Returns: `{hit_rate, mean_edge, roi, n_picks, n_high_confidence}`

---

## Step 3 — Fantasy Scoring Engine

### `chalk/fantasy/scoring.py`

**Fantasy scoring formulas (exact):**

```python
SCORING = {
    "draftkings": {
        "pts": 1.0,
        "fg3m": 0.5,
        "reb": 1.25,
        "ast": 1.5,
        "stl": 2.0,
        "blk": 2.0,
        "to_committed": -0.5,
        "double_double_bonus": 1.5,   # if 2+ stats >= 10
        "triple_double_bonus": 3.0,   # if 3+ stats >= 10
    },
    "fanduel": {
        "pts": 1.0,
        "reb": 1.2,
        "ast": 1.5,
        "stl": 2.0,
        "blk": 2.0,
        "to_committed": -1.0,
        # No bonus for DD/TD
    },
    "yahoo": {
        "pts": 1.0,
        "fg3m": 0.5,
        "reb": 1.2,
        "ast": 1.5,
        "stl": 2.0,
        "blk": 2.0,
        "to_committed": -1.0,
    }
}

def compute_fantasy_score(stats: dict[str, float], platform: str) -> float:
    """Compute fantasy score for a platform given a stat dict."""
    scoring = SCORING[platform]
    score = sum(stats.get(stat, 0) * mult for stat, mult in scoring.items()
                if stat not in ("double_double_bonus", "triple_double_bonus"))

    # DraftKings bonuses
    if platform == "draftkings":
        double_digit_count = sum(1 for s in ["pts", "reb", "ast", "stl", "blk"]
                                  if stats.get(s, 0) >= 10)
        if double_digit_count >= 2:
            score += scoring["double_double_bonus"]
        if double_digit_count >= 3:
            score += scoring["triple_double_bonus"]
    return round(score, 2)

def compute_all_fantasy_scores(stats: dict[str, float]) -> FantasyScores:
    return FantasyScores(
        draftkings=compute_fantasy_score(stats, "draftkings"),
        fanduel=compute_fantasy_score(stats, "fanduel"),
        yahoo=compute_fantasy_score(stats, "yahoo"),
    )
```

---

## Step 4 — Monte Carlo Simulation

### `chalk/fantasy/simulation.py`

For GPP (tournament) DFS, players need floor/ceiling projections, not just medians.
Monte Carlo samples from the prediction distribution to get a realistic range.

**Function: `simulate_fantasy_scores(stat_predictions, platform, n_simulations=1000) → SimulationResult`**

```python
@dataclass
class SimulationResult:
    platform: str
    mean: float
    floor: float       # 10th percentile of simulated scores
    ceiling: float     # 90th percentile of simulated scores
    std: float
    boom_rate: float   # P(score >= 1.5x mean) — useful for GPP
    bust_rate: float   # P(score <= 0.6x mean)
```

**Simulation logic:**
1. For each stat, fit a distribution to (p10, p25, p50, p75, p90)
2. Draw `n_simulations` correlated samples (pts and min are positively correlated)
3. Compute fantasy score for each simulation
4. Return percentile stats of the fantasy score distribution

**Correlation structure:**
- pts and min_played: ρ = 0.7
- reb and min_played: ρ = 0.6
- ast and min_played: ρ = 0.55
- pts and fg3m: ρ = 0.4
- Use multivariate normal with this correlation matrix

---

## Step 5 — API Routes

### `chalk/api/routes/props.py`

**`GET /v1/players/{player_id}/props`**

Query params:
- `game_id: str` (required)
- `stats: list[str]` (optional, default: pts, reb, ast, fg3m)

Returns list of OverUnderResponse — one per stat with Vegas line, O/U probability, and edge.

Cache key: `props:player:{player_id}:game:{game_id}`
TTL: 15 minutes (invalidate when betting lines update)

**`GET /v1/games/{game_id}/props`**

Returns all player props for a full game slate — for dashboard "value board" view.
Sorted by absolute edge descending (highest edge plays first).

### `chalk/api/routes/fantasy.py`

**`GET /v1/players/{player_id}/fantasy`**

Query params:
- `game_id: str` (required)
- `platform: str` (optional, default: "draftkings")

Returns FantasyScores + SimulationResult (floor/ceiling).

**`GET /v1/games/{game_id}/fantasy`**

Returns all players' fantasy projections for a slate.
Include `salary` field if available from DK/FD salary data.
Sort by `value_score = projected_dk_pts / (salary / 1000)` descending.

---

## Step 6 — Tests

### `tests/test_betting/test_over_under.py`

`test_over_probability_above_ceiling_is_near_zero`
- If line = p90 + 5, P(over) should be < 0.05

`test_over_probability_below_floor_is_near_one`
- If line = p10 - 5, P(over) should be > 0.95

`test_american_to_implied_probability_correct`
- -110 → ~0.524
- +110 → ~0.476
- Even (+100) → 0.5

`test_edge_calculation`
- model gives 60% over, implied 52% → edge = +0.08

### `tests/test_fantasy/test_scoring.py`

`test_draftkings_double_double_bonus`
- 10+ pts AND 10+ reb → score includes +1.5 bonus

`test_fanduel_no_triple_double_bonus`
- 10+ in 3 stats on FD → no bonus (FD doesn't have one)

`test_yahoo_scoring_formula`

`test_monte_carlo_floor_less_than_ceiling`

---

## Phase 5 Completion Checklist

- [ ] `pytest tests/test_betting/ tests/test_fantasy/` — all tests pass
- [ ] `/v1/players/{id}/props` returns O/U probability + edge for any Vegas line
- [ ] O/U probabilities calibrated: P(over when model says 70%) ≈ 70% on held-out games
- [ ] Fantasy scores match manual calculation for a known game
- [ ] Monte Carlo floor/ceiling makes sense: ceiling ≈ 90th percentile game
- [ ] `/v1/games/{id}/fantasy` returns sorted value board
- [ ] DraftKings double-double bonus computed correctly
- [ ] `TODO.md` updated — all Phase 5 checkboxes marked done
