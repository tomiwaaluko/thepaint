"""Base trainer class for all stat models."""
from dataclasses import dataclass, field
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import mean_absolute_error

from chalk.exceptions import ModelNotFoundError

DEFAULT_XGB_PARAMS = {
    "n_estimators": 2000,
    "learning_rate": 0.01,
    "max_depth": 5,
    "subsample": 0.8,
    "colsample_bytree": 0.7,
    "min_child_weight": 5,
    "reg_alpha": 0.3,
    "reg_lambda": 1.5,
    "random_state": 42,
    "n_jobs": -1,
    "eval_metric": "mae",
}

POISSON_PARAMS = {
    **DEFAULT_XGB_PARAMS,
    "objective": "count:poisson",
    "max_delta_step": 0.7,
    "n_estimators": 300,
    "max_depth": 4,
}

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

POISSON_STATS = {"stl", "blk", "to_committed"}


@dataclass
class BaseStatModel:
    stat: str
    model_name: str
    xgb_params: dict = field(default_factory=lambda: dict(DEFAULT_XGB_PARAMS))
    model: xgb.XGBRegressor | None = None
    feature_names: list[str] | None = None

    def train(
        self, X_train: pd.DataFrame, y_train: pd.Series,
        X_val: pd.DataFrame | None = None, y_val: pd.Series | None = None,
        early_stopping_rounds: int | None = 50,
    ) -> None:
        params = dict(self.xgb_params)
        fit_kwargs: dict = {"verbose": False}
        if X_val is not None and y_val is not None:
            params["early_stopping_rounds"] = early_stopping_rounds
            fit_kwargs["eval_set"] = [(X_val, y_val)]
        self.model = xgb.XGBRegressor(**params)
        self.model.fit(X_train, y_train, **fit_kwargs)
        self.feature_names = list(X_train.columns)

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        if self.model is None:
            raise ModelNotFoundError(f"Model '{self.model_name}' not trained. Call train() first.")
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
            "xgb_params": self.xgb_params,
            "feature_names": self.feature_names,
        }, path)

    @classmethod
    def load(cls, path: Path) -> "BaseStatModel":
        data = joblib.load(path)
        obj = cls(
            stat=data["stat"],
            model_name=data["model_name"],
            xgb_params=data["xgb_params"],
        )
        obj.model = data["model"]
        obj.feature_names = data["feature_names"]
        return obj
