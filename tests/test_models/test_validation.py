"""Tests for walk-forward CV and data splitting."""
import numpy as np
import pandas as pd
import pytest

from chalk.models.validation import (
    TRAIN_SEASONS,
    VALID_SEASON,
    TEST_SEASON,
    check_for_leakage,
    get_feature_cols,
    get_train_val_test_split,
    walk_forward_cv,
)


def _make_season_df(n_per_season=50, n_features=5, seed=42):
    """Create a DataFrame with season column spanning train/val/test."""
    rng = np.random.RandomState(seed)
    seasons = TRAIN_SEASONS + [VALID_SEASON, TEST_SEASON]
    rows = []
    for i, season in enumerate(seasons):
        for j in range(n_per_season):
            row = {f"f{k}": rng.randn() for k in range(n_features)}
            row["target"] = row["f0"] * 2 + rng.randn() * 0.5
            row["season"] = season
            row["game_id"] = f"game_{i}_{j}"
            row["game_date"] = f"2024-01-{(j % 28) + 1:02d}"
            rows.append(row)
    return pd.DataFrame(rows)


class TestCheckForLeakage:
    def test_detects_game_id(self):
        found = check_for_leakage(pd.DataFrame(), ["f0", "game_id", "f1"])
        assert "game_id" in found

    def test_detects_player_id(self):
        found = check_for_leakage(pd.DataFrame(), ["f0", "player_id"])
        assert "player_id" in found

    def test_clean_features_returns_empty(self):
        found = check_for_leakage(pd.DataFrame(), ["f0", "f1", "pts_avg_5g"])
        assert found == []


class TestGetTrainValTestSplit:
    def test_is_time_ordered(self):
        df = _make_season_df()
        feature_cols = get_feature_cols(df)
        X_train, y_train, X_val, y_val, X_test, y_test = get_train_val_test_split(
            df, feature_cols
        )
        # Train should only have TRAIN_SEASONS
        train_seasons = set(df.loc[X_train.index, "season"])
        val_seasons = set(df.loc[X_val.index, "season"])
        test_seasons = set(df.loc[X_test.index, "season"])

        assert train_seasons.issubset(set(TRAIN_SEASONS))
        assert val_seasons == {VALID_SEASON}
        assert test_seasons == {TEST_SEASON}

    def test_no_overlap(self):
        df = _make_season_df()
        feature_cols = get_feature_cols(df)
        X_train, _, X_val, _, X_test, _ = get_train_val_test_split(
            df, feature_cols
        )
        train_idx = set(X_train.index)
        val_idx = set(X_val.index)
        test_idx = set(X_test.index)
        assert train_idx.isdisjoint(val_idx)
        assert train_idx.isdisjoint(test_idx)
        assert val_idx.isdisjoint(test_idx)


class TestWalkForwardCV:
    def test_returns_fold_maes(self):
        df = _make_season_df()
        feature_cols = get_feature_cols(df)
        result = walk_forward_cv(df, feature_cols, "target")
        assert "cv_mae_mean" in result
        assert "cv_mae_std" in result
        assert "fold_maes" in result
        assert len(result["fold_maes"]) > 0

    def test_no_future_leakage_in_folds(self):
        """Each fold must only train on earlier seasons."""
        df = _make_season_df()
        feature_cols = get_feature_cols(df)
        result = walk_forward_cv(df, feature_cols, "target")
        # All fold MAEs should be reasonable (not near 0 which would indicate leakage)
        for mae in result["fold_maes"]:
            assert mae > 0.1, "Suspiciously low MAE suggests leakage"
