"""Tests for LGBMStatModel."""
import numpy as np
import pandas as pd
import pytest

from chalk.exceptions import ModelNotFoundError
from chalk.models.lgbm import LGBMStatModel, DEFAULT_LGBM_PARAMS


def _make_data(n=200, n_features=10, seed=42):
    """Generate synthetic regression data."""
    rng = np.random.RandomState(seed)
    X = pd.DataFrame(
        rng.randn(n, n_features),
        columns=[f"f{i}" for i in range(n_features)],
    )
    y = pd.Series(X["f0"] * 3 + X["f1"] * 2 + rng.randn(n) * 0.5, name="target")
    return X, y


class TestLGBMStatModel:
    def test_train_and_predict_shape(self):
        X, y = _make_data()
        model = LGBMStatModel(stat="pts", model_name="test_lgbm_pts")
        model.train(X, y)
        preds = model.predict(X)
        assert preds.shape == (len(X),)

    def test_predict_before_train_raises(self):
        X, _ = _make_data()
        model = LGBMStatModel(stat="pts", model_name="test_lgbm_pts")
        with pytest.raises(ModelNotFoundError):
            model.predict(X)

    def test_evaluate_returns_metrics(self):
        X, y = _make_data()
        model = LGBMStatModel(stat="pts", model_name="test_lgbm_pts")
        model.train(X, y)
        metrics = model.evaluate(X, y)
        assert "mae" in metrics
        assert "rmse" in metrics
        assert "bias" in metrics
        assert metrics["mae"] >= 0

    def test_feature_importance(self):
        X, y = _make_data()
        model = LGBMStatModel(stat="pts", model_name="test_lgbm_pts")
        model.train(X, y)
        fi = model.feature_importance()
        assert len(fi) == 10

    def test_save_and_load(self, tmp_path):
        X, y = _make_data()
        model = LGBMStatModel(stat="pts", model_name="test_lgbm_pts")
        model.train(X, y)
        preds_before = model.predict(X)

        path = tmp_path / "lgbm_model.joblib"
        model.save(path)

        loaded = LGBMStatModel.load(path)
        preds_after = loaded.predict(X)
        np.testing.assert_array_almost_equal(preds_before, preds_after)
        assert loaded.stat == "pts"
        assert loaded.feature_names == list(X.columns)

    def test_early_stopping_with_eval_set(self):
        X, y = _make_data(n=300)
        X_train, X_val = X[:200], X[200:]
        y_train, y_val = y[:200], y[200:]

        model = LGBMStatModel(stat="pts", model_name="test_lgbm_pts")
        model.train(X_train, y_train, X_val, y_val, early_stopping_rounds=10)
        preds = model.predict(X_val)
        assert preds.shape == (100,)
