"""Walk-forward cross-validation and data splitting utilities."""
import numpy as np
import pandas as pd
import structlog
import xgboost as xgb
from sklearn.metrics import mean_absolute_error

from chalk.models.base import DEFAULT_XGB_PARAMS

log = structlog.get_logger()

TRAIN_SEASONS = [
    "2015-16", "2016-17", "2017-18", "2018-19",
    "2019-20", "2020-21", "2021-22",
]
VALID_SEASON = "2022-23"
TEST_SEASON = "2023-24"

METADATA_COLS = {"target", "season", "game_id", "player_id", "game_date"}


def get_feature_cols(df: pd.DataFrame) -> list[str]:
    """Extract feature column names (everything except metadata)."""
    return [c for c in df.columns if c not in METADATA_COLS]


def check_for_leakage(df: pd.DataFrame, feature_cols: list[str]) -> list[str]:
    """Check if any metadata/identifier columns leaked into features."""
    suspects = {"game_id", "player_id", "game_date", "log_id", "season"}
    found = [c for c in feature_cols if c in suspects]
    if found:
        log.warning("leakage_detected", columns=found)
    return found


def get_train_val_test_split(
    df: pd.DataFrame,
    feature_cols: list[str],
    target_col: str = "target",
) -> tuple[pd.DataFrame, pd.Series, pd.DataFrame, pd.Series, pd.DataFrame, pd.Series]:
    """Split by season. Never shuffle."""
    train_mask = df["season"].isin(TRAIN_SEASONS)
    val_mask = df["season"] == VALID_SEASON
    test_mask = df["season"] == TEST_SEASON

    X_train = df.loc[train_mask, feature_cols]
    y_train = df.loc[train_mask, target_col]
    X_val = df.loc[val_mask, feature_cols]
    y_val = df.loc[val_mask, target_col]
    X_test = df.loc[test_mask, feature_cols]
    y_test = df.loc[test_mask, target_col]

    return X_train, y_train, X_val, y_val, X_test, y_test


def walk_forward_cv(
    df: pd.DataFrame,
    feature_cols: list[str],
    target_col: str,
    xgb_params: dict | None = None,
) -> dict:
    """Expanding-window walk-forward CV over training seasons.

    Each fold trains on all seasons up to the cutoff, validates on the next season.
    """
    params = xgb_params or DEFAULT_XGB_PARAMS
    fold_maes = []

    available_seasons = sorted(df["season"].unique())
    train_seasons_in_data = [s for s in TRAIN_SEASONS if s in available_seasons]

    if len(train_seasons_in_data) < 2:
        return {"cv_mae_mean": 0.0, "cv_mae_std": 0.0, "fold_maes": []}

    for i in range(1, len(train_seasons_in_data)):
        train_szns = train_seasons_in_data[:i]
        val_szn = train_seasons_in_data[i]

        train_mask = df["season"].isin(train_szns)
        val_mask = df["season"] == val_szn

        X_train = df.loc[train_mask, feature_cols]
        y_train = df.loc[train_mask, target_col]
        X_val = df.loc[val_mask, feature_cols]
        y_val = df.loc[val_mask, target_col]

        if len(X_train) == 0 or len(X_val) == 0:
            continue

        model = xgb.XGBRegressor(**params)
        model.fit(X_train, y_train, verbose=False)
        mae = mean_absolute_error(y_val, model.predict(X_val))
        fold_maes.append(mae)
        log.info("cv_fold", fold=i, val_season=val_szn, mae=round(mae, 3))

    return {
        "cv_mae_mean": float(np.mean(fold_maes)) if fold_maes else 0.0,
        "cv_mae_std": float(np.std(fold_maes)) if fold_maes else 0.0,
        "fold_maes": fold_maes,
    }
