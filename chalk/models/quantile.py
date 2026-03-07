"""Quantile regression models for prediction intervals."""
import numpy as np
import pandas as pd
import structlog
import xgboost as xgb

from chalk.models.validation import get_feature_cols, get_train_val_test_split

log = structlog.get_logger()

QUANTILES = [0.10, 0.25, 0.50, 0.75, 0.90]
QUANTILE_STATS = ["pts", "reb", "ast"]


def train_quantile_models(
    df: pd.DataFrame,
    stat: str,
) -> tuple[dict[float, xgb.XGBRegressor], dict]:
    """Train quantile models for a stat. Returns (models_dict, coverage_metrics)."""
    feature_cols = get_feature_cols(df)
    X_train, y_train, X_val, y_val, X_test, y_test = get_train_val_test_split(
        df, feature_cols
    )

    models = {}
    coverage = {}

    for q in QUANTILES:
        model = xgb.XGBRegressor(
            objective="reg:quantileerror",
            quantile_alpha=q,
            n_estimators=500,
            learning_rate=0.05,
            max_depth=5,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42,
            n_jobs=-1,
        )
        model.fit(X_train, y_train, verbose=False)
        models[q] = model

        # Coverage check on test set
        preds = model.predict(X_test)
        actual_below = float(np.mean(y_test.values < preds))
        coverage[f"p{int(q * 100)}_coverage"] = actual_below

        log.info(
            "quantile_trained", stat=stat, quantile=q,
            coverage=round(actual_below, 3), target=q,
        )

    return models, coverage
