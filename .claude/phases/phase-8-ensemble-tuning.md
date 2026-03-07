# Phase 8 — Ensemble & Tuning

## Goal
Stacked ensemble blending XGBoost + LightGBM + historical median. Optuna hyperparameter
search. Edge tracking vs. closing line value. Monthly retraining job. Final MAE benchmarks
showing ≥ 2% improvement over Phase 3 baseline models.

## Depends On
Phase 7 complete — automated pipeline running, performance data accumulating.

## This Is Ongoing
Phase 8 has no hard completion date — it's the continuous improvement loop.
Work items here are prioritized by expected MAE improvement.

---

## Step 1 — LightGBM Parallel Models

### `chalk/models/lgbm_player.py`

Mirror the XGBoost model structure but use LightGBM. LightGBM is faster for inference
and often matches XGBoost accuracy with different error patterns — making it valuable
for ensembling.

```python
import lightgbm as lgb

DEFAULT_LGBM_PARAMS = {
    "n_estimators": 600,
    "learning_rate": 0.04,
    "num_leaves": 31,
    "max_depth": -1,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "reg_alpha": 0.1,
    "reg_lambda": 1.0,
    "random_state": 42,
    "n_jobs": -1,
    "verbose": -1,
}
```

Train LightGBM models for all stats using the same walk-forward CV as XGBoost.
Log to MLflow under `chalk/{stat}/lightgbm`.
Register as `chalk-player-{stat}-lgbm`.

---

## Step 2 — Historical Median Baseline

### `chalk/models/median_baseline.py`

The simplest possible baseline: predict the player's rolling median.

```python
class MedianBaseline:
    """Predict the rolling median of a player's stat over last 20 games."""

    def predict(self, features: dict) -> float:
        # Uses features[f"{stat}_avg_20g"] as the prediction
        # No training required
```

This baseline is surprisingly competitive (~15-20% worse than XGBoost).
Including it in the ensemble helps on edge cases (new players, very recent form changes).

---

## Step 3 — Stacking Meta-Learner

### `chalk/models/ensemble.py`

Level 1: XGBoost predictions, LightGBM predictions, MedianBaseline predictions
Level 2: Linear meta-learner that blends the three using out-of-fold predictions

```python
@dataclass
class StackedEnsemble:
    stat: str
    xgb_model: BaseStatModel
    lgbm_model: LGBMStatModel
    baseline: MedianBaseline
    meta_weights: dict[str, float] | None = None  # learned weights

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        xgb_preds = self.xgb_model.predict(X)
        lgbm_preds = self.lgbm_model.predict(X)
        baseline_preds = self.baseline.predict(X)

        if self.meta_weights:
            return (
                self.meta_weights["xgb"] * xgb_preds +
                self.meta_weights["lgbm"] * lgbm_preds +
                self.meta_weights["baseline"] * baseline_preds
            )
        # Default: equal weights
        return (xgb_preds + lgbm_preds + baseline_preds) / 3
```

**Meta-weight learning:**
Use out-of-fold predictions on validation set to learn optimal weights via
`scipy.optimize.minimize` with constraint that weights sum to 1 and all ≥ 0.

**Register ensemble under:** `chalk-player-{stat}-ensemble`

---

## Step 4 — Optuna Hyperparameter Search

### `scripts/tune_hyperparams.py`

```
Usage: python scripts/tune_hyperparams.py --stat pts --n-trials 200 --timeout 3600
```

Only run after confirming baseline MAE targets are met. Tune one stat at a time.

**Search space:**
```python
params = {
    "n_estimators": trial.suggest_int("n_estimators", 200, 1500),
    "learning_rate": trial.suggest_float("learning_rate", 0.005, 0.3, log=True),
    "max_depth": trial.suggest_int("max_depth", 3, 10),
    "subsample": trial.suggest_float("subsample", 0.5, 1.0),
    "colsample_bytree": trial.suggest_float("colsample_bytree", 0.4, 1.0),
    "min_child_weight": trial.suggest_int("min_child_weight", 1, 20),
    "reg_alpha": trial.suggest_float("reg_alpha", 1e-8, 100, log=True),
    "reg_lambda": trial.suggest_float("reg_lambda", 1e-8, 100, log=True),
    "gamma": trial.suggest_float("gamma", 0, 5),
}
```

**Objective:** minimize val MAE using walk-forward CV (not test set — don't overfit to test).

**After tuning:** compare tuned val MAE to baseline val MAE. Only adopt new params if
improvement is ≥ 1% on val set. Log both to MLflow for comparison.

---

## Step 5 — Edge Tracking Dashboard

### `chalk/monitoring/edge_tracker.py`

Track whether the model has real betting edge over time.

**Key metric: Closing Line Value (CLV)**
When model's implied line is sharper than Vegas closing line, that's evidence of real edge.

```python
def compute_rolling_clv(session, stat, days=60) -> CLVReport:
    """
    Compare model's pre-game line to the closing line.
    Positive CLV = model was sharper than where market settled.
    """

@dataclass
class CLVReport:
    stat: str
    mean_clv: float          # average CLV over period
    clv_win_rate: float      # % of predictions with positive CLV
    n_predictions: int
    period_days: int
    is_sharper_than_market: bool  # mean_clv > 0.02
```

**Add CLV tracking to Phase 6 dashboard:**
New tab: "Edge Report" — shows rolling CLV by stat, hit rate on high-confidence picks,
ROI simulation if betting $100 on each high-edge pick at -110.

---

## Step 6 — Monthly Retraining Job

### `airflow/dags/monthly_retrain.py`

**Schedule:** `0 10 1 * *` (10 AM on the 1st of each month)

**Tasks:**
```
check_data_freshness       (verify last 30 days of games are in DB)
        ↓
build_training_matrices    (rebuild from scratch with new data)
        ↓
train_all_xgboost          (using updated train window)
        ↓
train_all_lgbm
        ↓
train_ensembles
        ↓
compare_to_current_models  (new MAE vs. registered model MAE)
        ↓
promote_if_better          (register new model if MAE improves ≥ 1%)
        ↓
invalidate_model_cache     (clear lru_cache so API loads new models)
        ↓
notify_slack
```

**Training window for monthly retrain:** always uses all available seasons.
Each month adds ~30 new games per team to the training data.

**Promotion logic:**
```python
if new_test_mae < current_test_mae * 0.99:  # at least 1% improvement
    register_new_model_version()
    invalidate_cache()
    alert_model_promoted(stat, old_mae, new_mae)
else:
    alert_model_not_promoted(stat, old_mae, new_mae)
```

---

## Step 7 — Feature Importance Drift

### `chalk/monitoring/feature_drift.py`

Over time, the most predictive features may change (e.g., pace of play increases, 3-point
shooting becomes even more important). Monitor feature importance shifts.

```python
def compare_feature_importance(old_model, new_model, top_n=10) -> FeatureImportanceChange:
    """
    Compare top-N feature importances between two model versions.
    Alerts if any feature moves more than 5 positions in the top-10.
    """
```

Log feature importance comparison to MLflow on every retraining run.

---

## Phase 8 Milestones

Unlike earlier phases, Phase 8 is measured by improvement targets, not task completion.

**Milestone 1 — LightGBM trained for all stats:**
- LightGBM MAE within 5% of XGBoost MAE for each stat

**Milestone 2 — Ensemble beats single model:**
- Stacked ensemble MAE ≥ 2% better than best single model on test set

**Milestone 3 — Hyperparameter tuning complete for top 3 stats:**
- pts, reb, ast tuned MAE ≥ 1% better than default params

**Milestone 4 — Positive CLV on held-out data:**
- Rolling 60-day CLV > 0 for at least 3 stats
- This is the ultimate validation that the model has real predictive edge

**Milestone 5 — Monthly retraining running autonomously:**
- Retrain DAG has run at least 2 months without manual intervention
- At least one model version promoted automatically
