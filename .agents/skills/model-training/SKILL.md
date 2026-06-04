---
name: model-training
description: Use this skill whenever building, running, or debugging ML model training code in Chalk. Covers XGBoost and LightGBM setup for NBA stat regression, walk-forward time-series cross-validation, hyperparameter search with Optuna, feature importance analysis, quantile regression for betting distributions, and saving/loading models. Always use this skill when touching chalk/models/, writing train_all.py, or adding new stat models.
---

# Model Training Skill

## Model Architecture Overview

One XGBoost regressor per stat. Train independently — do not use multi-output models.

| Model | Target Stat | Type | MAE Target |
|---|---|---|---|
| `PlayerPtsModel` | pts | XGBoost Regressor | ≤ 5.0 |
| `PlayerRebModel` | reb | XGBoost Regressor | ≤ 2.5 |
| `PlayerAstModel` | ast | XGBoost Regressor | ≤ 2.0 |
| `PlayerFg3mModel` | fg3m | XGBoost Regressor | ≤ 1.2 |
| `PlayerStlModel` | stl | Poisson (XGB) | ≤ 0.5 |
| `PlayerBlkModel` | blk | Poisson (XGB) | ≤ 0.5 |
| `PlayerToModel` | to_committed | Poisson (XGB) | ≤ 1.0 |
| `TeamTotalModel` | game_total_pts | XGBoost Regressor | ≤ 8.0 |
| `TeamPaceModel` | pace | XGBoost Regressor | ≤ 3.0 |

For betting use: also train **quantile variants** of pts, reb, ast at q=[0.1, 0.25, 0.5, 0.75, 0.9].

---

## Base Trainer Class (`models/base.py`)

```python
from dataclasses import dataclass, field
from pathlib import Path
import xgboost as xgb
import numpy as np
import pandas as pd
import mlflow
from sklearn.metrics import mean_absolute_error
from chalk.features.pipeline import generate_features_batch
import structlog

log = structlog.get_logger()

TRAIN_SEASONS = ["2015-16", "2016-17", "2017-18", "2018-19", "2019-20", "2020-21", "2021-22"]
VALID_SEASON = "2022-23"
TEST_SEASON = "2023-24"


@dataclass
class BaseStatModel:
    stat: str
    model_name: str
    xgb_params: dict = field(default_factory=lambda: {
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
    })
    model: xgb.XGBRegressor | None = None

    def train(self, X_train: pd.DataFrame, y_train: pd.Series):
        self.model = xgb.XGBRegressor(**self.xgb_params)
        self.model.fit(
            X_train, y_train,
            eval_set=[(X_train, y_train)],
            verbose=False,
        )

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        if self.model is None:
            raise RuntimeError("Model not trained. Call train() first.")
        return self.model.predict(X)

    def evaluate(self, X: pd.DataFrame, y: pd.Series) -> dict[str, float]:
        preds = self.predict(X)
        return {
            "mae": mean_absolute_error(y, preds),
            "rmse": np.sqrt(np.mean((y - preds) ** 2)),
            "bias": float(np.mean(preds - y)),  # positive = overestimates
        }

    def feature_importance(self) -> pd.Series:
        return pd.Series(
            self.model.feature_importances_,
            index=self.model.feature_names_in_,
        ).sort_values(ascending=False)
```

---

## Walk-Forward Cross-Validation (MANDATORY)

Never use random k-fold. Always use time-ordered splits.

```python
def walk_forward_cv(
    df: pd.DataFrame,          # must have 'season' column
    feature_cols: list[str],
    target_col: str,
    train_seasons: list[str],
    val_season: str,
) -> dict[str, float]:
    """
    Expanding window CV: train on all seasons up to each fold's cutoff.
    Returns mean MAE across folds.
    """
    fold_maes = []

    # Expanding window: fold 1 = 2015-16, fold 2 = 2015-16 + 2016-17, etc.
    for i, cutoff_season in enumerate(train_seasons[1:], start=1):
        train_mask = df["season"].isin(train_seasons[:i+1])
        val_mask = df["season"] == train_seasons[i]  # validate on held-out season

        X_train = df.loc[train_mask, feature_cols]
        y_train = df.loc[train_mask, target_col]
        X_val = df.loc[val_mask, feature_cols]
        y_val = df.loc[val_mask, target_col]

        model = xgb.XGBRegressor(**DEFAULT_PARAMS)
        model.fit(X_train, y_train, verbose=False)
        mae = mean_absolute_error(y_val, model.predict(X_val))
        fold_maes.append(mae)
        log.info("cv_fold", fold=i, val_season=cutoff_season, mae=round(mae, 3))

    return {"cv_mae_mean": np.mean(fold_maes), "cv_mae_std": np.std(fold_maes)}
```

---

## Full Training Pipeline (`models/player.py`)

```python
async def train_player_stat_model(
    session: AsyncSession,
    stat: str,
    player_ids: list[int],
    mlflow_experiment: str,
) -> BaseStatModel:
    """Train a model for one stat across all tracked players."""

    with mlflow.start_run(experiment_id=mlflow.get_experiment_by_name(mlflow_experiment).experiment_id):

        # 1. Build feature matrix
        log.info("building_feature_matrix", stat=stat, n_players=len(player_ids))
        records = await build_training_records(session, player_ids, stat)
        df = pd.DataFrame(records)

        feature_cols = [c for c in df.columns if c not in ["target", "season", "game_id", "player_id", "game_date"]]
        X = df[feature_cols]
        y = df["target"]

        # 2. Split by season (NEVER random split)
        train_mask = df["season"].isin(TRAIN_SEASONS)
        val_mask = df["season"] == VALID_SEASON
        test_mask = df["season"] == TEST_SEASON

        X_train, y_train = X[train_mask], y[train_mask]
        X_val, y_val = X[val_mask], y[val_mask]
        X_test, y_test = X[test_mask], y[test_mask]

        # 3. Log params
        model = BaseStatModel(stat=stat, model_name=f"chalk_{stat}_xgb")
        mlflow.log_params(model.xgb_params)
        mlflow.log_param("n_train_rows", len(X_train))
        mlflow.log_param("n_features", len(feature_cols))
        mlflow.log_param("train_seasons", TRAIN_SEASONS)

        # 4. Train
        model.train(X_train, y_train)

        # 5. Evaluate on val + test
        val_metrics = model.evaluate(X_val, y_val)
        test_metrics = model.evaluate(X_test, y_test)

        mlflow.log_metrics({f"val_{k}": v for k, v in val_metrics.items()})
        mlflow.log_metrics({f"test_{k}": v for k, v in test_metrics.items()})

        log.info("training_complete", stat=stat, val_mae=val_metrics["mae"], test_mae=test_metrics["mae"])

        # 6. Log feature importance
        fi = model.feature_importance()
        mlflow.log_dict(fi.head(20).to_dict(), "feature_importance_top20.json")

        # 7. Register model if test MAE meets target
        target_mae = {"pts": 5.0, "reb": 2.5, "ast": 2.0, "fg3m": 1.2}.get(stat, 999)
        if test_metrics["mae"] <= target_mae:
            mlflow.xgboost.log_model(model.model, f"chalk_{stat}_model",
                                     registered_model_name=f"chalk-player-{stat}")
            log.info("model_registered", stat=stat, mae=test_metrics["mae"])
        else:
            log.warning("model_below_target", stat=stat, mae=test_metrics["mae"], target=target_mae)

    return model
```

---

## Quantile Regression (for Betting O/U)

Train quantile models to produce prediction intervals.

```python
def train_quantile_model(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    quantile: float,  # e.g. 0.1, 0.25, 0.5, 0.75, 0.9
) -> xgb.XGBRegressor:
    model = xgb.XGBRegressor(
        objective="reg:quantileerror",
        quantile_alpha=quantile,
        n_estimators=500,
        learning_rate=0.05,
        max_depth=5,
        random_state=42,
    )
    model.fit(X_train, y_train, verbose=False)
    return model

# Train all 5 quantile models per stat
QUANTILES = [0.10, 0.25, 0.50, 0.75, 0.90]

quantile_models = {
    q: train_quantile_model(X_train, y_train, q)
    for q in QUANTILES
}
```

---

## Poisson Regression for Low-Count Stats

For stl, blk, to_committed — these are count data, not continuous.

```python
# Use XGBoost with count:poisson objective
poisson_params = {
    "objective": "count:poisson",
    "max_delta_step": 0.7,  # stabilizes Poisson training
    "n_estimators": 300,
    "learning_rate": 0.05,
    "max_depth": 4,
}
```

---

## Hyperparameter Search with Optuna

Use after initial model validates well. Don't tune until baseline MAE is ≤ target.

```python
import optuna

def optuna_objective(trial: optuna.Trial, X_train, y_train, X_val, y_val) -> float:
    params = {
        "n_estimators": trial.suggest_int("n_estimators", 200, 1000),
        "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.2, log=True),
        "max_depth": trial.suggest_int("max_depth", 3, 8),
        "subsample": trial.suggest_float("subsample", 0.6, 1.0),
        "colsample_bytree": trial.suggest_float("colsample_bytree", 0.6, 1.0),
        "min_child_weight": trial.suggest_int("min_child_weight", 1, 10),
        "reg_alpha": trial.suggest_float("reg_alpha", 1e-8, 10.0, log=True),
        "reg_lambda": trial.suggest_float("reg_lambda", 1e-8, 10.0, log=True),
    }
    model = xgb.XGBRegressor(**params, random_state=42)
    model.fit(X_train, y_train, verbose=False)
    return mean_absolute_error(y_val, model.predict(X_val))

study = optuna.create_study(direction="minimize")
study.optimize(lambda t: optuna_objective(t, X_train, y_train, X_val, y_val), n_trials=100)
```

---

## Feature Importance Analysis

Always inspect feature importance after training. Top 5 features should make basketball sense.

Expected top features for `pts` model:
1. `pts_avg_5g` — recent form
2. `min_played_avg_10g` — opportunity
3. `usage_rate_10g` — role
4. `opp_def_rtg_15g` — matchup quality
5. `absent_teammate_usage_sum` — injury context

If `game_id` or `player_id` appear in top 10, you have a leakage problem.

---

## Training Run Checklist

Before calling a model production-ready:
- [ ] MAE on 2023-24 test set meets target (see table above)
- [ ] MAE is not significantly better than val MAE (if test << val, suspect leakage)
- [ ] Feature importance top 10 makes basketball sense
- [ ] Bias (mean prediction error) is within ±0.3 (not systematically over/under-predicting)
- [ ] Model registered in MLflow with version tag
- [ ] Re-run with 3 different random seeds — MAE variance < 0.2 (stable training)
