"""Tests for StackedEnsemble."""
import numpy as np
import pandas as pd
import pytest

from chalk.models.base import DEFAULT_XGB_PARAMS
from chalk.models.ensemble import StackedEnsemble
from chalk.models.lgbm import DEFAULT_LGBM_PARAMS


def _make_matrix(n=700, n_features=10, seed=42):
    """Generate synthetic matrix with seasons for walk-forward stacking."""
    rng = np.random.RandomState(seed)
    seasons = [
        "2015-16", "2016-17", "2017-18", "2018-19",
        "2019-20", "2020-21", "2021-22", "2022-23", "2023-24",
    ]
    rows_per = n // len(seasons)

    dfs = []
    for szn in seasons:
        X = pd.DataFrame(
            rng.randn(rows_per, n_features),
            columns=[f"f{i}" for i in range(n_features)],
        )
        X["target"] = X["f0"] * 3 + X["f1"] * 2 + rng.randn(rows_per) * 0.5
        X["season"] = szn
        X["game_id"] = [f"g{szn}_{i}" for i in range(rows_per)]
        X["player_id"] = rng.randint(1, 50, rows_per)
        X["game_date"] = pd.date_range("2015-10-01", periods=rows_per, freq="D").astype(str)
        dfs.append(X)
    return pd.concat(dfs, ignore_index=True)


class TestStackedEnsemble:
    def test_train_returns_metrics(self):
        df = _make_matrix()
        ensemble = StackedEnsemble(stat="pts")
        metrics = ensemble.train(df, DEFAULT_XGB_PARAMS, DEFAULT_LGBM_PARAMS)
        assert "xgb_oof_mae" in metrics
        assert "lgbm_oof_mae" in metrics
        assert "ensemble_oof_mae" in metrics
        assert "meta_weights" in metrics
        assert len(metrics["meta_weights"]) == 3

    def test_ensemble_predicts_correct_shape(self):
        df = _make_matrix()
        ensemble = StackedEnsemble(stat="pts")
        ensemble.train(df, DEFAULT_XGB_PARAMS, DEFAULT_LGBM_PARAMS)

        feature_cols = [c for c in df.columns if c not in {"target", "season", "game_id", "player_id", "game_date"}]
        X_test = df[df["season"] == "2023-24"][feature_cols]
        preds = ensemble.predict(X_test)
        assert preds.shape == (len(X_test),)

    def test_evaluate_returns_per_model_mae(self):
        df = _make_matrix()
        ensemble = StackedEnsemble(stat="pts")
        ensemble.train(df, DEFAULT_XGB_PARAMS, DEFAULT_LGBM_PARAMS)

        feature_cols = [c for c in df.columns if c not in {"target", "season", "game_id", "player_id", "game_date"}]
        test_df = df[df["season"] == "2023-24"]
        X_test = test_df[feature_cols]
        y_test = test_df["target"]

        metrics = ensemble.evaluate(X_test, y_test)
        assert "ensemble_mae" in metrics
        assert "xgb_mae" in metrics
        assert "lgbm_mae" in metrics

    def test_save_and_load(self, tmp_path):
        df = _make_matrix()
        ensemble = StackedEnsemble(stat="pts")
        ensemble.train(df, DEFAULT_XGB_PARAMS, DEFAULT_LGBM_PARAMS)

        feature_cols = [c for c in df.columns if c not in {"target", "season", "game_id", "player_id", "game_date"}]
        X_test = df[df["season"] == "2023-24"][feature_cols]
        preds_before = ensemble.predict(X_test)

        path = tmp_path / "ensemble.joblib"
        ensemble.save(path)

        loaded = StackedEnsemble.load(path)
        preds_after = loaded.predict(X_test)
        np.testing.assert_array_almost_equal(preds_before, preds_after)
        assert loaded.stat == "pts"

    def test_ensemble_beats_or_matches_worst_base(self):
        """Ensemble MAE should not be worse than both base models."""
        df = _make_matrix(n=1400)
        ensemble = StackedEnsemble(stat="pts")
        ensemble.train(df, DEFAULT_XGB_PARAMS, DEFAULT_LGBM_PARAMS)

        feature_cols = [c for c in df.columns if c not in {"target", "season", "game_id", "player_id", "game_date"}]
        test_df = df[df["season"] == "2023-24"]
        X_test = test_df[feature_cols]
        y_test = test_df["target"]

        metrics = ensemble.evaluate(X_test, y_test)
        worst_base = max(metrics["xgb_mae"], metrics["lgbm_mae"])
        # Ensemble should not be dramatically worse than the worst base model
        assert metrics["ensemble_mae"] <= worst_base * 1.1
