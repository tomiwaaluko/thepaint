---
name: mlflow-tracking
description: Use this skill whenever writing code that interacts with MLflow in Chalk. Covers experiment naming conventions, what params and metrics to log, artifact logging, model registration, loading models for inference, and model versioning. Always use this skill when touching chalk/models/registry.py, writing any mlflow.log_* calls, or setting up new experiments.
---

# MLflow Tracking Skill

## Experiment Naming Convention

```
chalk/{stat}/{model_type}

Examples:
  chalk/pts/xgboost
  chalk/reb/xgboost
  chalk/pts/quantile_p10
  chalk/pts/quantile_p90
  chalk/team_total/xgboost
  chalk/pace/xgboost
```

Always create the experiment before logging if it doesn't exist:

```python
import mlflow

def get_or_create_experiment(name: str) -> str:
    experiment = mlflow.get_experiment_by_name(name)
    if experiment is None:
        return mlflow.create_experiment(name)
    return experiment.experiment_id
```

---

## Run Naming Convention

```
{context}_{season_range}

Examples:
  player_2015_2024          ← all players, full training window
  lebron_james_2023         ← single-player run (for debugging)
  team_2015_2024
  quantile_p50_2015_2024
```

---

## What to Log

### Parameters (log once per run)
```python
mlflow.log_params({
    # Model config
    "model_type": "xgboost",
    "stat": "pts",
    "n_estimators": 500,
    "learning_rate": 0.05,
    "max_depth": 5,
    "subsample": 0.8,
    "colsample_bytree": 0.8,

    # Data config
    "train_seasons": str(TRAIN_SEASONS),
    "val_season": VALID_SEASON,
    "test_season": TEST_SEASON,
    "n_train_rows": len(X_train),
    "n_val_rows": len(X_val),
    "n_test_rows": len(X_test),
    "n_features": len(feature_cols),
    "n_players": len(player_ids),

    # Feature config
    "rolling_windows": str([5, 10, 20]),
    "opponent_window": 15,
})
```

### Metrics (log per split)
```python
mlflow.log_metrics({
    # Validation set
    "val_mae": val_metrics["mae"],
    "val_rmse": val_metrics["rmse"],
    "val_bias": val_metrics["bias"],

    # Test set (2023-24 holdout)
    "test_mae": test_metrics["mae"],
    "test_rmse": test_metrics["rmse"],
    "test_bias": test_metrics["bias"],

    # MAE delta (positive = test worse than val, expected; negative = suspect leakage)
    "mae_delta_val_to_test": test_metrics["mae"] - val_metrics["mae"],
})
```

### Artifacts
```python
# Feature importance (always)
fi_dict = model.feature_importance().head(20).to_dict()
mlflow.log_dict(fi_dict, "feature_importance_top20.json")

# Full feature list (for reproducibility)
mlflow.log_dict({"features": feature_cols}, "feature_columns.json")

# Prediction vs actual plot (optional but useful)
fig = plot_predictions_vs_actual(y_test, test_preds)
mlflow.log_figure(fig, "predictions_vs_actual.png")
```

---

## Model Registration

Register to the model registry only when MAE meets production target.

```python
MAE_TARGETS = {
    "pts": 5.0,
    "reb": 2.5,
    "ast": 2.0,
    "fg3m": 1.2,
    "stl": 0.5,
    "blk": 0.5,
    "to_committed": 1.0,
    "team_total": 8.0,
    "pace": 3.0,
}

REGISTERED_MODEL_NAMES = {
    "pts": "chalk-player-pts",
    "reb": "chalk-player-reb",
    "ast": "chalk-player-ast",
    "fg3m": "chalk-player-fg3m",
    "stl": "chalk-player-stl",
    "blk": "chalk-player-blk",
    "to_committed": "chalk-player-to",
    "team_total": "chalk-team-total",
    "pace": "chalk-team-pace",
}

def register_if_ready(model, stat: str, test_mae: float, artifact_path: str):
    target = MAE_TARGETS.get(stat)
    registered_name = REGISTERED_MODEL_NAMES.get(stat)

    if test_mae <= target:
        model_uri = mlflow.xgboost.log_model(
            model.model,
            artifact_path=artifact_path,
            registered_model_name=registered_name,
        )
        # Tag it
        client = mlflow.MlflowClient()
        version = client.get_latest_versions(registered_name)[0].version
        client.set_model_version_tag(registered_name, version, "test_mae", str(round(test_mae, 4)))
        client.set_model_version_tag(registered_name, version, "train_seasons", str(TRAIN_SEASONS))
        log.info("model_registered", stat=stat, mae=test_mae, version=version)
        return model_uri
    else:
        # Still log the model artifact, just don't register
        mlflow.xgboost.log_model(model.model, artifact_path=artifact_path)
        log.warning("model_not_registered", stat=stat, mae=test_mae, target=target)
        return None
```

---

## Model Registry Helper (`models/registry.py`)

```python
import mlflow
import xgboost as xgb
from functools import lru_cache

REGISTERED_MODEL_NAMES = {
    "pts": "chalk-player-pts",
    "reb": "chalk-player-reb",
    "ast": "chalk-player-ast",
    "fg3m": "chalk-player-fg3m",
    "stl": "chalk-player-stl",
    "blk": "chalk-player-blk",
    "to_committed": "chalk-player-to",
}

@lru_cache(maxsize=None)
def load_model(stat: str) -> xgb.XGBRegressor:
    """Load latest production model for a stat. Cached after first load."""
    registered_name = REGISTERED_MODEL_NAMES[stat]
    model_uri = f"models:/{registered_name}/latest"
    return mlflow.xgboost.load_model(model_uri)


def load_quantile_models(stat: str) -> dict[float, xgb.XGBRegressor]:
    """Load all quantile models for a stat (for O/U distributions)."""
    quantiles = [0.10, 0.25, 0.50, 0.75, 0.90]
    return {
        q: mlflow.xgboost.load_model(f"models:/chalk-player-{stat}-q{int(q*100)}/latest")
        for q in quantiles
    }
```

---

## MLflow Server Setup (docker-compose.yml addition)

```yaml
mlflow:
  image: ghcr.io/mlflow/mlflow:v2.10.0
  ports:
    - "5000:5000"
  environment:
    - MLFLOW_BACKEND_STORE_URI=postgresql://chalk:chalk@db:5432/mlflow
    - MLFLOW_DEFAULT_ARTIFACT_ROOT=/mlflow/artifacts
  volumes:
    - mlflow_artifacts:/mlflow/artifacts
  depends_on:
    - db
```

Set `MLFLOW_TRACKING_URI=http://localhost:5000` in `.env`.

---

## Comparing Runs

Use the MLflow UI at `http://localhost:5000` to compare runs.
Key comparison columns to enable: `test_mae`, `val_mae`, `mae_delta_val_to_test`, `n_features`.

A healthy `mae_delta_val_to_test` is 0.1–0.5. If it's negative (test better than val), suspect leakage.
If it's > 1.0, the model is not generalizing — add regularization or reduce features.
