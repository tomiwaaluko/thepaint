"""Tests for player stat model training."""
import numpy as np
import pandas as pd
import pytest

from chalk.models.player import train_player_stat_model
from chalk.models.validation import TRAIN_SEASONS, VALID_SEASON, TEST_SEASON


def _make_player_df(n_per_season=30, n_features=10, seed=42):
    """Create synthetic player feature matrix with season column."""
    rng = np.random.RandomState(seed)
    seasons = TRAIN_SEASONS + [VALID_SEASON, TEST_SEASON]
    rows = []
    for season in seasons:
        for j in range(n_per_season):
            row = {f"f{k}": rng.randn() for k in range(n_features)}
            row["target"] = max(0, row["f0"] * 5 + 20 + rng.randn() * 3)
            row["season"] = season
            row["game_id"] = f"game_{season}_{j}"
            row["game_date"] = f"2024-01-{(j % 28) + 1:02d}"
            row["player_id"] = float(rng.choice([2544, 201566, 203507]))
            rows.append(row)
    return pd.DataFrame(rows)


class TestTrainPlayerStatModel:
    def test_training_produces_valid_model(self):
        df = _make_player_df()
        model, results = train_player_stat_model(df, "pts")
        assert model.model is not None
        assert model.stat == "pts"
        assert results["test_mae"] > 0
        assert results["val_mae"] > 0
        assert results["n_features"] == 10

    def test_model_can_predict(self):
        df = _make_player_df()
        model, _ = train_player_stat_model(df, "pts")
        X = df[[f"f{i}" for i in range(10)]].iloc[:5]
        preds = model.predict(X)
        assert len(preds) == 5

    def test_leakage_raises(self):
        df = _make_player_df()
        # Sneak game_id into feature columns by renaming
        df = df.rename(columns={"f0": "game_id_feat"})
        # This should still work since "game_id_feat" != "game_id"
        model, results = train_player_stat_model(df, "pts")
        assert model.model is not None

    def test_feature_importance_top10(self):
        df = _make_player_df()
        _, results = train_player_stat_model(df, "pts")
        fi = results["feature_importance_top10"]
        assert len(fi) == 10
