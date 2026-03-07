# Phase 3 — Baseline ML Models

## Goal
Train XGBoost regressors for pts, reb, ast, fg3m, and team total. All models hit MAE targets
on the 2023-24 test holdout. Models registered in MLflow. Feature importance reviewed and
makes basketball sense.

## Depends On
Phase 2 complete — `generate_features()` working, `build_training_matrix()` produces clean data.

## Unlocks
Phase 4 (Prediction API) — needs trained models loadable from MLflow registry.

## Skill Files to Read First
- `.claude/skills/model-training/SKILL.md` — XGBoost setup, walk-forward CV, MAE targets
- `.claude/skills/mlflow-tracking/SKILL.md` — experiment naming, what to log, model registration

---

## MAE Targets (Production Readiness Gates)

| Stat | Target MAE | Notes |
|---|---|---|
| pts | ≤ 5.0 | Vegas baseline ~4.5 |
| reb | ≤ 2.5 | |
| ast | ≤ 2.0 | |
| fg3m | ≤ 1.2 | |
| stl | ≤ 0.5 | Use Poisson objective |
| blk | ≤ 0.5 | Use Poisson objective |
| to_committed | ≤ 1.0 | Use Poisson objective |
| team_total_pts | ≤ 8.0 | |

A model that does not meet its MAE target is still logged to MLflow but NOT registered.

---

## Step 1 — Base Trainer Class

### `chalk/models/base.py`

Build following the pattern in `.claude/skills/model-training/SKILL.md`.

**Class: `BaseStatModel`**

```python
@dataclass
class BaseStatModel:
    stat: str
    model_name: str
    xgb_params: dict = field(default_factory=lambda: DEFAULT_XGB_PARAMS)
    model: xgb.XGBRegressor | None = None
    feature_names: list[str] | None = None
```

**Methods:**
- `train(X_train, y_train)` — fits XGBRegressor, stores feature_names
- `predict(X) → np.ndarray` — raises ModelNotFoundError if not trained
- `evaluate(X, y) → dict` — returns mae, rmse, bias
- `feature_importance() → pd.Series` — sorted descending
- `save(path)` / `load(path)` — joblib serialize/deserialize

**Default XGB params:**
```python
DEFAULT_XGB_PARAMS = {
    "n_estimators": 500,
    "learning_rate": 0.05,
    "max_depth": 5,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "min_child_weight": 3,
    "reg_alpha": 0.1,
    "reg_lambda": 1.0,
    "random_state": 42,
    "n_jobs": -1,
    "eval_metric": "mae",
}

POISSON_PARAMS = {
    **DEFAULT_XGB_PARAMS,
    "objective": "count:poisson",
    "max_delta_step": 0.7,
    "n_estimators": 300,
    "max_depth": 4,
}
```

---

## Step 2 — Walk-Forward Cross-Validation

### `chalk/models/validation.py`

```python
TRAIN_SEASONS = ["2015-16", "2016-17", "2017-18", "2018-19", "2019-20", "2020-21", "2021-22"]
VALID_SEASON = "2022-23"
TEST_SEASON = "2023-24"
```

**Functions:**

`walk_forward_cv(df, feature_cols, target_col, train_seasons, val_seasons) → dict`
- Expanding window: fold 1 trains on season 0, fold 2 on seasons 0-1, etc.
- Returns: `{cv_mae_mean, cv_mae_std, fold_maes: list}`

`get_train_val_test_split(df, feature_cols, target_col)`
- Returns: `(X_train, y_train, X_val, y_val, X_test, y_test)`
- Train: TRAIN_SEASONS, Val: VALID_SEASON, Test: TEST_SEASON
- Never shuffle — preserve time order

`check_for_leakage(df, feature_cols) → list[str]`
- Warns if any of `game_id`, `player_id`, `game_date` appear in feature_cols
- Returns list of suspicious column names found

---

## Step 3 — Player Stat Models

### `chalk/models/player.py`

**Function: `train_player_stat_model(session, stat, player_ids, run_name) → BaseStatModel`**

Full implementation following `.claude/skills/model-training/SKILL.md` pattern:

1. Build training matrix via `build_training_matrix(session, player_ids, stat, ALL_SEASONS)`
2. Run `check_for_leakage()` — raise if game_id/player_id in features
3. Split into train/val/test using `get_train_val_test_split()`
4. Log row counts, feature count to MLflow
5. Run `walk_forward_cv()` and log cv_mae_mean
6. Train final model on full TRAIN_SEASONS data
7. Evaluate on val and test sets
8. Log all metrics, feature importance, feature list
9. Register if test MAE meets target (via `register_if_ready()`)
10. Return trained model

**Use Poisson objective for:** stl, blk, to_committed
**Use standard regression for:** pts, reb, ast, fg3m

---

## Step 4 — Quantile Models

### `chalk/models/quantile.py`

Train quantile variants for pts, reb, ast. These power the betting O/U probability distributions.

```python
QUANTILES = [0.10, 0.25, 0.50, 0.75, 0.90]
QUANTILE_STATS = ["pts", "reb", "ast"]
```

**Function: `train_quantile_models(session, stat, player_ids) → dict[float, xgb.XGBRegressor]`**

For each quantile:
```python
model = xgb.XGBRegressor(
    objective="reg:quantileerror",
    quantile_alpha=quantile,
    n_estimators=500,
    learning_rate=0.05,
    max_depth=5,
    random_state=42,
)
```

Log each quantile model to MLflow as separate run under `chalk/{stat}/quantile_p{int(q*100)}`.
Register under name `chalk-player-{stat}-q{int(q*100)}`.

**Evaluate quantile coverage:**
- On test set, verify that P(actual < p10_pred) ≈ 10% (calibration check)
- Log coverage metrics: `p10_coverage`, `p25_coverage`, `p50_coverage`, etc.

---

## Step 5 — Team Models

### `chalk/models/team.py`

**Models to train:**
- `TeamTotalModel` — predicts combined game total (home_pts + away_pts)
- `TeamPaceModel` — predicts possessions per game

**Features for team models** (different from player features):
- Both teams' rolling off_rtg and def_rtg (last 10, 20 games)
- Both teams' pace (last 10, 20 games)
- Home/away indicator
- Rest days for both teams
- Both teams' injury absences (star player out)
- Season game number

`build_team_training_matrix(session, seasons) → pd.DataFrame`
- One row per game (not per player)
- Target for total: home_pts + away_pts from team_game_logs

---

## Step 6 — MLflow Model Registry

### `chalk/models/registry.py`

```python
@lru_cache(maxsize=None)
def load_model(stat: str) -> xgb.XGBRegressor:
    """Load latest registered model for a stat. Cached in memory."""
    ...

def load_quantile_models(stat: str) -> dict[float, xgb.XGBRegressor]:
    """Load all 5 quantile models for a stat."""
    ...

def get_model_version(stat: str) -> str:
    """Return version string of currently loaded model."""
    ...

def invalidate_cache():
    """Clear the lru_cache — call after retraining."""
    load_model.cache_clear()
```

---

## Step 7 — Training Script

### `scripts/train_all.py`

```
Usage: python scripts/train_all.py [--stats pts reb ast fg3m] [--skip-quantile]
```

**Order of execution:**
1. Build training matrices for all stats (can parallelize with ProcessPoolExecutor)
2. Train player models for each stat
3. Train quantile models for pts, reb, ast
4. Train team total and pace models
5. Print final summary table:

```
Stat         | Val MAE | Test MAE | Target | Registered
-------------|---------|----------|--------|----------
pts          |  4.82   |  4.91    |  5.0   | ✓
reb          |  2.31   |  2.44    |  2.5   | ✓
ast          |  1.87   |  1.93    |  2.0   | ✓
fg3m         |  1.09   |  1.14    |  1.2   | ✓
team_total   |  7.62   |  7.89    |  8.0   | ✓
```

---

## Step 8 — Tests

### `tests/test_models/test_base.py`

`test_train_and_predict_returns_correct_shape`
`test_predict_before_train_raises_error`
`test_evaluate_returns_mae_rmse_bias`
`test_feature_importance_sums_to_one`

### `tests/test_models/test_validation.py`

`test_walk_forward_cv_no_future_leakage`
- Verify that fold N never trains on data from fold N+1 or later

`test_train_val_test_split_is_time_ordered`
- Verify max(train_dates) < min(val_dates) < min(test_dates)

`test_check_for_leakage_detects_game_id`
- Pass feature_cols containing "game_id", verify it's flagged

### `tests/test_models/test_player.py`

`test_training_produces_valid_model`
- Train on small synthetic dataset (3 seasons × 10 players)
- Verify model trains without error and predict() works

---

## Post-Training Review Checklist

Before marking Phase 3 done, manually review in MLflow UI:

- [ ] pts model feature importance top 5: should include `pts_avg_5g`, `min_played_avg_10g`, `opp_def_rtg_15g`
- [ ] If `game_id` or `player_id` appear in top 20 features → STOP, you have leakage
- [ ] Val MAE and test MAE within 0.5 of each other (if test << val, suspect leakage)
- [ ] Bias (mean prediction error) within ±0.5 for all stats
- [ ] Quantile coverage: p10 coverage between 8-12%, p90 coverage between 88-92%

---

## Phase 3 Completion Checklist

- [ ] `pytest tests/test_models/` — all tests pass
- [ ] `python scripts/train_all.py` runs without error
- [ ] pts MAE ≤ 5.0 on 2023-24 test set
- [ ] reb MAE ≤ 2.5 on 2023-24 test set
- [ ] ast MAE ≤ 2.0 on 2023-24 test set
- [ ] fg3m MAE ≤ 1.2 on 2023-24 test set
- [ ] team_total MAE ≤ 8.0 on 2023-24 test set
- [ ] All models registered in MLflow
- [ ] Feature importance reviewed — no leakage signals
- [ ] Quantile coverage within ±2% of target percentiles
- [ ] `TODO.md` updated — all Phase 3 checkboxes marked done
