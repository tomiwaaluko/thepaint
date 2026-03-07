"""Player stat model training."""
import structlog

from chalk.models.base import (
    DEFAULT_XGB_PARAMS,
    MAE_TARGETS,
    POISSON_PARAMS,
    POISSON_STATS,
    BaseStatModel,
)
from chalk.models.validation import (
    check_for_leakage,
    get_feature_cols,
    get_train_val_test_split,
    walk_forward_cv,
)

log = structlog.get_logger()

PLAYER_STATS = ["pts", "reb", "ast", "fg3m", "stl", "blk", "to_committed"]


def train_player_stat_model(
    df,
    stat: str,
    run_name: str = "",
) -> tuple[BaseStatModel, dict]:
    """Train a single player stat model from a pre-built feature matrix.

    Returns (model, results_dict) where results_dict has val/test metrics.
    """
    feature_cols = get_feature_cols(df)

    # Leakage check
    leaked = check_for_leakage(df, feature_cols)
    if leaked:
        raise ValueError(f"Leakage detected in feature columns: {leaked}")

    # Pick params based on stat type
    params = dict(POISSON_PARAMS) if stat in POISSON_STATS else dict(DEFAULT_XGB_PARAMS)
    model_name = f"chalk_{stat}_xgb"
    model = BaseStatModel(stat=stat, model_name=model_name, xgb_params=params)

    # Split
    X_train, y_train, X_val, y_val, X_test, y_test = get_train_val_test_split(
        df, feature_cols
    )

    log.info(
        "training_start", stat=stat,
        train_rows=len(X_train), val_rows=len(X_val), test_rows=len(X_test),
        n_features=len(feature_cols),
    )

    # Walk-forward CV on training seasons
    cv_results = walk_forward_cv(df, feature_cols, "target", params)

    # Train final model on full training set with early stopping on val
    model.train(X_train, y_train, X_val, y_val)

    # Evaluate
    val_metrics = model.evaluate(X_val, y_val)
    test_metrics = model.evaluate(X_test, y_test)

    target_mae = MAE_TARGETS.get(stat, 999.0)
    meets_target = test_metrics["mae"] <= target_mae

    log.info(
        "training_complete", stat=stat,
        cv_mae=round(cv_results["cv_mae_mean"], 3),
        val_mae=round(val_metrics["mae"], 3),
        test_mae=round(test_metrics["mae"], 3),
        target_mae=target_mae,
        meets_target=meets_target,
    )

    results = {
        "stat": stat,
        "cv_mae_mean": cv_results["cv_mae_mean"],
        "cv_mae_std": cv_results["cv_mae_std"],
        "val_mae": val_metrics["mae"],
        "val_rmse": val_metrics["rmse"],
        "val_bias": val_metrics["bias"],
        "test_mae": test_metrics["mae"],
        "test_rmse": test_metrics["rmse"],
        "test_bias": test_metrics["bias"],
        "target_mae": target_mae,
        "meets_target": meets_target,
        "n_train_rows": len(X_train),
        "n_val_rows": len(X_val),
        "n_test_rows": len(X_test),
        "n_features": len(feature_cols),
        "feature_importance_top10": model.feature_importance().head(10).to_dict(),
    }

    return model, results
