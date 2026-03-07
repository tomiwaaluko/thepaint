"""Team total points model."""
import structlog

from chalk.models.base import DEFAULT_XGB_PARAMS, MAE_TARGETS, BaseStatModel
from chalk.models.validation import (
    check_for_leakage,
    get_feature_cols,
    get_train_val_test_split,
)

log = structlog.get_logger()


TEAM_XGB_PARAMS = {
    "n_estimators": 200,
    "learning_rate": 0.03,
    "max_depth": 3,
    "subsample": 0.7,
    "colsample_bytree": 0.5,
    "min_child_weight": 10,
    "reg_alpha": 1.0,
    "reg_lambda": 5.0,
    "random_state": 42,
    "n_jobs": -1,
    "eval_metric": "mae",
}


def train_team_total_model(df, run_name: str = "") -> tuple[BaseStatModel, dict]:
    """Train team total points model from pre-built feature matrix."""
    feature_cols = get_feature_cols(df)

    leaked = check_for_leakage(df, feature_cols)
    if leaked:
        raise ValueError(f"Leakage detected: {leaked}")

    params = dict(TEAM_XGB_PARAMS)
    model = BaseStatModel(stat="team_total", model_name="chalk_team_total_xgb", xgb_params=params)

    X_train, y_train, X_val, y_val, X_test, y_test = get_train_val_test_split(
        df, feature_cols
    )

    log.info(
        "team_training_start",
        train_rows=len(X_train), val_rows=len(X_val), test_rows=len(X_test),
    )

    model.train(X_train, y_train)

    val_metrics = model.evaluate(X_val, y_val)
    test_metrics = model.evaluate(X_test, y_test)

    target_mae = MAE_TARGETS["team_total"]
    meets_target = test_metrics["mae"] <= target_mae

    log.info(
        "team_training_complete",
        val_mae=round(val_metrics["mae"], 3),
        test_mae=round(test_metrics["mae"], 3),
        meets_target=meets_target,
    )

    results = {
        "stat": "team_total",
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
