"""Optuna hyperparameter search for XGBoost and LightGBM per stat."""
import numpy as np
import optuna
import pandas as pd
import structlog
import xgboost as xgb
from sklearn.metrics import mean_absolute_error

from chalk.models.validation import TRAIN_SEASONS

log = structlog.get_logger()

# Suppress Optuna's verbose trial logging
optuna.logging.set_verbosity(optuna.logging.WARNING)


def _walk_forward_objective(
    trial: optuna.Trial,
    df: pd.DataFrame,
    feature_cols: list[str],
    target_col: str,
    model_type: str = "xgb",
) -> float:
    """Optuna objective using walk-forward CV. Returns mean MAE across folds."""
    if model_type == "xgb":
        params = {
            "n_estimators": trial.suggest_int("n_estimators", 500, 3000),
            "learning_rate": trial.suggest_float("learning_rate", 0.005, 0.05, log=True),
            "max_depth": trial.suggest_int("max_depth", 3, 8),
            "subsample": trial.suggest_float("subsample", 0.6, 1.0),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.5, 1.0),
            "min_child_weight": trial.suggest_int("min_child_weight", 1, 10),
            "reg_alpha": trial.suggest_float("reg_alpha", 1e-8, 10.0, log=True),
            "reg_lambda": trial.suggest_float("reg_lambda", 1e-8, 10.0, log=True),
            "random_state": 42,
            "n_jobs": -1,
            "eval_metric": "mae",
        }
    else:
        params = {
            "n_estimators": trial.suggest_int("n_estimators", 500, 3000),
            "learning_rate": trial.suggest_float("learning_rate", 0.005, 0.05, log=True),
            "num_leaves": trial.suggest_int("num_leaves", 31, 127),
            "max_depth": trial.suggest_int("max_depth", -1, 8),
            "subsample": trial.suggest_float("subsample", 0.6, 1.0),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.5, 1.0),
            "min_child_samples": trial.suggest_int("min_child_samples", 5, 50),
            "reg_alpha": trial.suggest_float("reg_alpha", 1e-8, 10.0, log=True),
            "reg_lambda": trial.suggest_float("reg_lambda", 1e-8, 10.0, log=True),
            "objective": "regression_l1",
            "metric": "mae",
            "random_state": 42,
            "n_jobs": -1,
            "verbose": -1,
        }

    available_seasons = sorted(df["season"].unique())
    train_seasons = [s for s in TRAIN_SEASONS if s in available_seasons]

    if len(train_seasons) < 2:
        return float("inf")

    fold_maes = []
    for i in range(1, len(train_seasons)):
        train_szns = train_seasons[:i]
        val_szn = train_seasons[i]

        train_mask = df["season"].isin(train_szns)
        val_mask = df["season"] == val_szn

        X_train = df.loc[train_mask, feature_cols]
        y_train = df.loc[train_mask, target_col]
        X_val = df.loc[val_mask, feature_cols]
        y_val = df.loc[val_mask, target_col]

        if len(X_train) == 0 or len(X_val) == 0:
            continue

        if model_type == "xgb":
            model = xgb.XGBRegressor(**params, early_stopping_rounds=50)
            model.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)
        else:
            import lightgbm as lgb
            model = lgb.LGBMRegressor(**params)
            model.fit(
                X_train, y_train,
                eval_set=[(X_val, y_val)],
                callbacks=[lgb.early_stopping(50), lgb.log_evaluation(0)],
            )

        preds = model.predict(X_val)
        fold_maes.append(mean_absolute_error(y_val, preds))

        # Prune unpromising trials early
        trial.report(np.mean(fold_maes), i)
        if trial.should_prune():
            raise optuna.TrialPruned()

    return float(np.mean(fold_maes)) if fold_maes else float("inf")


def tune_stat(
    df: pd.DataFrame,
    stat: str,
    model_type: str = "xgb",
    n_trials: int = 50,
    storage: str | None = None,
) -> dict:
    """Run Optuna search for a stat model. Returns best params dict.

    Args:
        df: Feature matrix with 'target' and 'season' columns.
        stat: Stat name (for study naming).
        model_type: "xgb" or "lgbm".
        n_trials: Number of Optuna trials.
        storage: Optional SQLite URL for persistence (e.g. "sqlite:///optuna.db").
    """
    from chalk.models.validation import get_feature_cols
    feature_cols = get_feature_cols(df)

    study_name = f"chalk_{stat}_{model_type}"
    study = optuna.create_study(
        direction="minimize",
        study_name=study_name,
        storage=storage,
        load_if_exists=True,
        pruner=optuna.pruners.MedianPruner(n_startup_trials=5, n_warmup_steps=2),
    )

    log.info("optuna_start", stat=stat, model_type=model_type, n_trials=n_trials)

    study.optimize(
        lambda trial: _walk_forward_objective(
            trial, df, feature_cols, "target", model_type
        ),
        n_trials=n_trials,
    )

    log.info(
        "optuna_complete",
        stat=stat,
        model_type=model_type,
        best_mae=round(study.best_value, 4),
        best_trial=study.best_trial.number,
    )

    return {
        "best_params": study.best_params,
        "best_mae": study.best_value,
        "n_trials": len(study.trials),
        "study_name": study_name,
    }
