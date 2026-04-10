"""Stacking meta-learner: blends XGBoost + LightGBM + historical median."""
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import joblib
import numpy as np
import pandas as pd
import structlog
import xgboost as xgb
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error

from chalk.models.validation import TRAIN_SEASONS, get_feature_cols

if TYPE_CHECKING:
    import lightgbm as lgb
else:
    try:
        import lightgbm as lgb
    except (OSError, ImportError) as e:
        lgb = None  # type: ignore
        _LGBM_IMPORT_ERROR = e
    else:
        _LGBM_IMPORT_ERROR = None

log = structlog.get_logger()


@dataclass
class StackedEnsemble:
    """Stacking meta-learner that blends XGBoost, LightGBM, and historical median."""

    stat: str
    xgb_model: xgb.XGBRegressor | None = None
    lgbm_model: "lgb.LGBMRegressor | None" = None
    meta_model: Ridge | None = None
    xgb_params: dict = field(default_factory=dict)
    lgbm_params: dict = field(default_factory=dict)
    meta_alpha: float = 1.0
    feature_names: list[str] | None = None

    def train(
        self,
        df: pd.DataFrame,
        xgb_params: dict,
        lgbm_params: dict,
        meta_alpha: float = 1.0,
    ) -> dict:
        """Train ensemble using walk-forward OOF predictions.

        Returns dict with per-model and ensemble metrics.
        """
        if lgb is None:
            raise ImportError(
                f"LightGBM is not available: {_LGBM_IMPORT_ERROR}. "
                "This may be due to a missing system library (libgomp.so.1)."
            )
        self.xgb_params = xgb_params
        self.lgbm_params = lgbm_params
        self.meta_alpha = meta_alpha
        feature_cols = get_feature_cols(df)
        self.feature_names = feature_cols

        available_seasons = sorted(df["season"].unique())
        train_seasons = [s for s in TRAIN_SEASONS if s in available_seasons]

        if len(train_seasons) < 2:
            raise ValueError("Need at least 2 training seasons for stacking.")

        # Collect OOF predictions from base models
        oof_xgb = np.full(len(df), np.nan)
        oof_lgbm = np.full(len(df), np.nan)
        y_all = df["target"].values

        for i in range(1, len(train_seasons)):
            train_szns = train_seasons[:i]
            val_szn = train_seasons[i]

            train_mask = df["season"].isin(train_szns)
            val_mask = df["season"] == val_szn
            val_idx = df.index[val_mask]

            X_tr = df.loc[train_mask, feature_cols]
            y_tr = df.loc[train_mask, "target"]
            X_val = df.loc[val_mask, feature_cols]

            if len(X_tr) == 0 or len(X_val) == 0:
                continue

            # XGBoost fold
            xgb_fold = xgb.XGBRegressor(**xgb_params, early_stopping_rounds=50)
            xgb_fold.fit(X_tr, y_tr, eval_set=[(X_val, df.loc[val_mask, "target"])], verbose=False)
            oof_xgb[val_idx] = xgb_fold.predict(X_val)

            # LightGBM fold
            lgbm_fold = lgb.LGBMRegressor(**lgbm_params)
            lgbm_fold.fit(
                X_tr, y_tr,
                eval_set=[(X_val, df.loc[val_mask, "target"])],
                callbacks=[lgb.early_stopping(50), lgb.log_evaluation(0)],
            )
            oof_lgbm[val_idx] = lgbm_fold.predict(X_val)

        # Historical median (rolling 20-game median of target, shifted)
        hist_median = (
            df.groupby(df.get("player_id", df.index))["target"]
            .transform(lambda x: x.shift(1).rolling(20, min_periods=5).median())
        ).fillna(df["target"].mean()).values

        # Filter to rows with valid OOF predictions
        valid = ~np.isnan(oof_xgb) & ~np.isnan(oof_lgbm)
        meta_X = np.column_stack([oof_xgb[valid], oof_lgbm[valid], hist_median[valid]])
        meta_y = y_all[valid]

        # Train Ridge meta-learner
        self.meta_model = Ridge(alpha=meta_alpha)
        self.meta_model.fit(meta_X, meta_y)

        # Train final base models on all training data
        all_train_mask = df["season"].isin(train_seasons)
        X_full = df.loc[all_train_mask, feature_cols]
        y_full = df.loc[all_train_mask, "target"]

        self.xgb_model = xgb.XGBRegressor(**xgb_params)
        self.xgb_model.fit(X_full, y_full, verbose=False)

        self.lgbm_model = lgb.LGBMRegressor(**lgbm_params)
        self.lgbm_model.fit(X_full, y_full)

        # Compute OOF metrics
        xgb_mae = mean_absolute_error(meta_y, oof_xgb[valid])
        lgbm_mae = mean_absolute_error(meta_y, oof_lgbm[valid])
        ensemble_preds = self.meta_model.predict(meta_X)
        ensemble_mae = mean_absolute_error(meta_y, ensemble_preds)

        log.info(
            "ensemble_trained",
            stat=self.stat,
            xgb_oof_mae=round(xgb_mae, 4),
            lgbm_oof_mae=round(lgbm_mae, 4),
            ensemble_oof_mae=round(ensemble_mae, 4),
            meta_weights=list(np.round(self.meta_model.coef_, 4)),
        )

        return {
            "xgb_oof_mae": xgb_mae,
            "lgbm_oof_mae": lgbm_mae,
            "ensemble_oof_mae": ensemble_mae,
            "meta_weights": list(self.meta_model.coef_),
            "meta_intercept": float(self.meta_model.intercept_),
            "n_oof_rows": int(valid.sum()),
        }

    def predict(self, X: pd.DataFrame, hist_median: np.ndarray | None = None) -> np.ndarray:
        """Generate stacked predictions.

        Args:
            X: Feature matrix.
            hist_median: Historical median values per row. If None, uses mean of
                         XGBoost and LightGBM predictions as fallback.
        """
        xgb_preds = self.xgb_model.predict(X)
        lgbm_preds = self.lgbm_model.predict(X)

        if hist_median is None:
            hist_median = (xgb_preds + lgbm_preds) / 2

        meta_X = np.column_stack([xgb_preds, lgbm_preds, hist_median])
        return self.meta_model.predict(meta_X)

    def evaluate(self, X: pd.DataFrame, y: pd.Series, hist_median: np.ndarray | None = None) -> dict:
        """Evaluate ensemble on held-out data."""
        preds = self.predict(X, hist_median)
        xgb_preds = self.xgb_model.predict(X)
        lgbm_preds = self.lgbm_model.predict(X)

        return {
            "ensemble_mae": float(mean_absolute_error(y, preds)),
            "xgb_mae": float(mean_absolute_error(y, xgb_preds)),
            "lgbm_mae": float(mean_absolute_error(y, lgbm_preds)),
            "ensemble_rmse": float(np.sqrt(np.mean((y - preds) ** 2))),
            "ensemble_bias": float(np.mean(preds - y)),
        }

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump({
            "stat": self.stat,
            "xgb_model": self.xgb_model,
            "lgbm_model": self.lgbm_model,
            "meta_model": self.meta_model,
            "xgb_params": self.xgb_params,
            "lgbm_params": self.lgbm_params,
            "meta_alpha": self.meta_alpha,
            "feature_names": self.feature_names,
            "model_type": "ensemble",
        }, path)

    @classmethod
    def load(cls, path: Path) -> "StackedEnsemble":
        data = joblib.load(path)
        obj = cls(
            stat=data["stat"],
            xgb_params=data["xgb_params"],
            lgbm_params=data["lgbm_params"],
            meta_alpha=data["meta_alpha"],
        )
        obj.xgb_model = data["xgb_model"]
        obj.lgbm_model = data["lgbm_model"]
        obj.meta_model = data["meta_model"]
        obj.feature_names = data["feature_names"]
        return obj