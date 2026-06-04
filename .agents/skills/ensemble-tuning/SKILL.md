---
name: ensemble-tuning
description: Use this skill when working on Phase 8 — ensemble models, Optuna hyperparameter tuning, LightGBM alternatives, stacking meta-learners, or edge/CLV tracking. Always use this skill when touching chalk/models/ for tuning work or adding new model types.
---

# Ensemble & Tuning Skill (Phase 8)

## Goal

Improve MAE by ≥ 2% over the best single Phase 3 model using:
1. Optuna hyperparameter search (per-stat XGBoost tuning)
2. LightGBM as an XGBoost alternative
3. Stacking meta-learner (blends XGBoost + LightGBM + historical median)

Phase 3 baselines to beat:
- PTS: 4.94 MAE → target ≤ 4.84
- REB: 2.02 MAE → target ≤ 1.98
- AST: 1.47 MAE → target ≤ 1.44
- 3PM: 0.94 MAE → target ≤ 0.92

---

## Optuna Hyperparameter Search

```python
import optuna
import xgboost as xgb
from chalk.models.validation import walk_forward_splits

def objective(trial, X, y, stat: str):
    params = {
        "n_estimators": trial.suggest_int("n_estimators", 500, 3000),
        "learning_rate": trial.suggest_float("learning_rate", 0.005, 0.05, log=True),
        "max_depth": trial.suggest_int("max_depth", 3, 8),
        "subsample": trial.suggest_float("subsample", 0.6, 1.0),
        "colsample_bytree": trial.suggest_float("colsample_bytree", 0.6, 1.0),
        "min_child_weight": trial.suggest_int("min_child_weight", 1, 10),
        "reg_alpha": trial.suggest_float("reg_alpha", 1e-8, 10.0, log=True),
        "reg_lambda": trial.suggest_float("reg_lambda", 1e-8, 10.0, log=True),
        "objective": "reg:squarederror",
        "tree_method": "hist",
        "random_state": 42,
    }

    # Walk-forward CV — NEVER random split
    maes = []
    for X_train, y_train, X_val, y_val in walk_forward_splits(X, y):
        model = xgb.XGBRegressor(**params, early_stopping_rounds=50)
        model.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)
        preds = model.predict(X_val)
        maes.append(np.mean(np.abs(preds - y_val)))

    return np.mean(maes)


def tune_stat(stat: str, X, y, n_trials: int = 100):
    study = optuna.create_study(
        direction="minimize",
        study_name=f"chalk_{stat}_xgb",
        storage="sqlite:///optuna.db",   # persist across runs
        load_if_exists=True,
    )
    study.optimize(lambda trial: objective(trial, X, y, stat), n_trials=n_trials)
    return study.best_params
```

---

## LightGBM Setup

LightGBM often outperforms XGBoost on sparse features. Train as an alternative and blend.

```python
import lightgbm as lgb

LGBM_PARAMS = {
    "n_estimators": 2000,
    "learning_rate": 0.01,
    "max_depth": -1,          # no limit, use num_leaves instead
    "num_leaves": 63,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "min_child_samples": 20,
    "reg_alpha": 0.1,
    "reg_lambda": 0.1,
    "objective": "regression_l1",   # MAE objective
    "metric": "mae",
    "random_state": 42,
    "n_jobs": -1,
    "verbose": -1,
}

model = lgb.LGBMRegressor(**LGBM_PARAMS)
model.fit(
    X_train, y_train,
    eval_set=[(X_val, y_val)],
    callbacks=[lgb.early_stopping(50), lgb.log_evaluation(100)],
)
```

---

## Stacking Meta-Learner

Train base models (XGBoost + LightGBM) with walk-forward CV, collect out-of-fold predictions,
then train a Ridge meta-learner on the OOF predictions.

```python
from sklearn.linear_model import Ridge
import numpy as np

def train_stacked_model(X, y, xgb_model, lgb_model):
    """
    1. Collect out-of-fold predictions from base models
    2. Train Ridge on OOF predictions
    3. Final prediction = Ridge(xgb_pred, lgb_pred, hist_median)
    """
    oof_xgb = np.zeros(len(y))
    oof_lgb = np.zeros(len(y))

    for train_idx, val_idx in walk_forward_split_indices(X, y):
        X_tr, X_val = X.iloc[train_idx], X.iloc[val_idx]
        y_tr = y.iloc[train_idx]

        xgb_model.fit(X_tr, y_tr)
        lgb_model.fit(X_tr, y_tr)

        oof_xgb[val_idx] = xgb_model.predict(X_val)
        oof_lgb[val_idx] = lgb_model.predict(X_val)

    # Historical median as third feature
    hist_median = y.rolling(20, min_periods=5).median().fillna(y.mean()).values

    meta_features = np.column_stack([oof_xgb, oof_lgb, hist_median])
    meta_model = Ridge(alpha=1.0)
    meta_model.fit(meta_features, y)

    return meta_model


def predict_stacked(xgb_pred, lgb_pred, hist_median, meta_model):
    meta_features = np.column_stack([xgb_pred, lgb_pred, hist_median])
    return meta_model.predict(meta_features)
```

---

## MLflow Logging for Ensemble Runs

```python
import mlflow

# Experiment naming convention: chalk/<stat>/ensemble
mlflow.set_experiment(f"chalk/{stat}/ensemble")

with mlflow.start_run(run_name=f"stack_{stat}_v1"):
    mlflow.log_params({
        "xgb_n_estimators": xgb_params["n_estimators"],
        "lgb_num_leaves": lgb_params["num_leaves"],
        "meta_learner": "ridge",
        "meta_alpha": 1.0,
    })
    mlflow.log_metrics({
        "val_mae_xgb": xgb_val_mae,
        "val_mae_lgb": lgb_val_mae,
        "val_mae_ensemble": ensemble_val_mae,
        "improvement_pct": (baseline_mae - ensemble_val_mae) / baseline_mae * 100,
    })
    mlflow.sklearn.log_model(meta_model, "meta_model")
    mlflow.xgboost.log_model(xgb_model, "xgb_base")
    mlflow.lightgbm.log_model(lgb_model, "lgb_base")
```

---

## Edge & CLV Tracking

After each game completes, compare model prediction vs. actual result vs. closing line.

```python
# chalk/betting/edge.py
def compute_clv(
    model_pred: float,
    opening_line: float,
    closing_line: float,
    actual: float,
) -> dict:
    """
    CLV = closing_line - model_pred (positive = model was sharper than market)
    Result edge = sign(actual - closing_line) * abs(actual - closing_line)
    """
    clv = closing_line - model_pred
    result_edge = actual - closing_line
    model_error = abs(actual - model_pred)
    line_error = abs(actual - closing_line)

    return {
        "clv": clv,
        "result_edge": result_edge,
        "model_mae": model_error,
        "line_mae": line_error,
        "beat_closing_line": model_error < line_error,
    }
```

---

## Phase 8 Acceptance Criteria

- [ ] Ensemble MAE ≥ 2% better than best single model on 2023-24 test set
- [ ] Optuna search runs ≥ 50 trials per stat, best params saved
- [ ] LightGBM trained and benchmarked against XGBoost for all stats
- [ ] Stacking meta-learner outperforms any single base model
- [ ] CLV tracking shows model beats closing line on > 50% of predictions
- [ ] All new models registered in MLflow under `chalk/<stat>/ensemble`
- [ ] Monthly retraining job added to `scripts/retrain_monthly.py`
