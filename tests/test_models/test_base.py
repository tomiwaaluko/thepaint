"""Tests for BaseStatModel."""
import numpy as np
import pandas as pd
import pytest

from chalk.exceptions import ModelNotFoundError
from chalk.models.base import BaseStatModel, DEFAULT_XGB_PARAMS


def _make_data(n=200, n_features=10, seed=42):
    """Generate synthetic regression data."""
    rng = np.random.RandomState(seed)
    X = pd.DataFrame(
        rng.randn(n, n_features),
        columns=[f"f{i}" for i in range(n_features)],
    )
    y = pd.Series(X["f0"] * 3 + X["f1"] * 2 + rng.randn(n) * 0.5, name="target")
    return X, y


class TestBaseStatModel:
    def test_train_and_predict_returns_correct_shape(self):
        X, y = _make_data()
        model = BaseStatModel(stat="pts", model_name="test_pts")
        model.train(X, y)
        preds = model.predict(X)
        assert preds.shape == (len(X),)

    def test_predict_before_train_raises_error(self):
        X, _ = _make_data()
        model = BaseStatModel(stat="pts", model_name="test_pts")
        with pytest.raises(ModelNotFoundError):
            model.predict(X)

    def test_evaluate_returns_mae_rmse_bias(self):
        X, y = _make_data()
        model = BaseStatModel(stat="pts", model_name="test_pts")
        model.train(X, y)
        metrics = model.evaluate(X, y)
        assert "mae" in metrics
        assert "rmse" in metrics
        assert "bias" in metrics
        assert metrics["mae"] >= 0
        assert metrics["rmse"] >= 0

    def test_feature_importance_sums_to_approximately_one(self):
        X, y = _make_data()
        model = BaseStatModel(stat="pts", model_name="test_pts")
        model.train(X, y)
        fi = model.feature_importance()
        assert len(fi) == 10
        assert fi.sum() == pytest.approx(1.0, abs=0.01)

    def test_save_and_load(self, tmp_path):
        X, y = _make_data()
        model = BaseStatModel(stat="pts", model_name="test_pts")
        model.train(X, y)
        preds_before = model.predict(X)

        path = tmp_path / "model.joblib"
        model.save(path)

        loaded = BaseStatModel.load(path)
        preds_after = loaded.predict(X)
        np.testing.assert_array_almost_equal(preds_before, preds_after)
        assert loaded.stat == "pts"
        assert loaded.feature_names == list(X.columns)

    def test_feature_importance_before_train_raises(self):
        model = BaseStatModel(stat="pts", model_name="test_pts")
        with pytest.raises(ModelNotFoundError):
            model.feature_importance()
