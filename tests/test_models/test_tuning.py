"""Tests for Optuna hyperparameter tuning."""
import numpy as np
import pandas as pd
import pytest

from chalk.models.tuning import tune_stat


def _make_matrix(n=500, n_features=10, seed=42):
    """Generate synthetic feature matrix with season column."""
    rng = np.random.RandomState(seed)
    seasons = ["2015-16", "2016-17", "2017-18", "2018-19", "2019-20", "2020-21", "2021-22"]
    rows_per = n // len(seasons)

    dfs = []
    for szn in seasons:
        X = pd.DataFrame(
            rng.randn(rows_per, n_features),
            columns=[f"f{i}" for i in range(n_features)],
        )
        X["target"] = X["f0"] * 3 + X["f1"] * 2 + rng.randn(rows_per) * 0.5
        X["season"] = szn
        X["game_id"] = [f"g{i}" for i in range(rows_per)]
        X["player_id"] = rng.randint(1, 50, rows_per)
        X["game_date"] = pd.date_range("2015-10-01", periods=rows_per, freq="D").astype(str)
        dfs.append(X)
    return pd.concat(dfs, ignore_index=True)


class TestTuneStat:
    def test_tune_xgb_returns_best_params(self):
        df = _make_matrix()
        result = tune_stat(df, "pts", model_type="xgb", n_trials=3)
        assert "best_params" in result
        assert "best_mae" in result
        assert result["best_mae"] > 0
        assert result["n_trials"] == 3
        assert "n_estimators" in result["best_params"]

    def test_tune_lgbm_returns_best_params(self):
        df = _make_matrix()
        result = tune_stat(df, "pts", model_type="lgbm", n_trials=3)
        assert "best_params" in result
        assert "best_mae" in result
        assert "num_leaves" in result["best_params"]

    def test_tune_with_storage(self, tmp_path):
        df = _make_matrix()
        db_path = tmp_path / "test_optuna.db"
        result = tune_stat(
            df, "pts", model_type="xgb", n_trials=2,
            storage=f"sqlite:///{db_path}",
        )
        assert result["n_trials"] == 2
        assert db_path.exists()
