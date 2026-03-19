"""LightGBM stat model — drop-in alternative to XGBoost BaseStatModel."""
from dataclasses import dataclass, field
from pathlib import Path

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error

from chalk.exceptions import ModelNotFoundError

DEFAULT_LGBM_PARAMS = {
    "n_estimators": 2000,
    "learning_rate": 0.01,
    "max_depth": -1,
    "num_leaves": 63,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "min_child_samples": 20,
    "reg_alpha": 0.1,
    "reg_lambda": 0.1,
    "objective": "regression_l1",
    "metric": "mae",
    "random_state": 42,
    "n_jobs": -1,
    "verbose": -1,
}


@dataclass
class LGBMStatModel:
    stat: str
    model_name: str
    lgbm_params: dict = field(default_factory=lambda: dict(DEFAULT_LGBM_PARAMS))
    model: lgb.LGBMRegressor | None = None
    feature_names: list[str] | None = None

    def train(
        self,
        X_train: pd.DataFrame,
        y_train: pd.Series,
        X_val: pd.DataFrame | None = None,
        y_val: pd.Series | None = None,
        early_stopping_rounds: int | None = 50,
    ) -> None:
        params = dict(self.lgbm_params)
        self.model = lgb.LGBMRegressor(**params)
        fit_kwargs: dict = {}
        if X_val is not None and y_val is not None:
            fit_kwargs["eval_set"] = [(X_val, y_val)]
            fit_kwargs["callbacks"] = [
                lgb.early_stopping(early_stopping_rounds or 50),
                lgb.log_evaluation(0),
            ]
        self.model.fit(X_train, y_train, **fit_kwargs)
        self.feature_names = list(X_train.columns)

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        if self.model is None:
            raise ModelNotFoundError(f"Model '{self.model_name}' not trained.")
        return self.model.predict(X)

    def evaluate(self, X: pd.DataFrame, y: pd.Series) -> dict[str, float]:
        preds = self.predict(X)
        return {
            "mae": float(mean_absolute_error(y, preds)),
            "rmse": float(np.sqrt(np.mean((y - preds) ** 2))),
            "bias": float(np.mean(preds - y)),
        }

    def feature_importance(self) -> pd.Series:
        if self.model is None:
            raise ModelNotFoundError("Model not trained.")
        return pd.Series(
            self.model.feature_importances_,
            index=self.model.feature_names_in_,
        ).sort_values(ascending=False)

    def save(self, path: Path) -> None:
        if self.model is None:
            raise ModelNotFoundError("Model not trained.")
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump({
            "model": self.model,
            "stat": self.stat,
            "model_name": self.model_name,
            "lgbm_params": self.lgbm_params,
            "feature_names": self.feature_names,
            "model_type": "lgbm",
        }, path)

    @classmethod
    def load(cls, path: Path) -> "LGBMStatModel":
        data = joblib.load(path)
        obj = cls(
            stat=data["stat"],
            model_name=data["model_name"],
            lgbm_params=data.get("lgbm_params", DEFAULT_LGBM_PARAMS),
        )
        obj.model = data["model"]
        obj.feature_names = data["feature_names"]
        return obj
