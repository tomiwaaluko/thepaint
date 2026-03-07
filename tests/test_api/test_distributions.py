"""Tests for the distribution builder."""
import pytest

from chalk.predictions.distributions import (
    build_stat_prediction,
    compute_confidence,
    estimate_interval_from_mae,
    fix_quantile_crossing,
)


class TestComputeConfidence:
    def test_high_confidence_tight_spread(self):
        assert compute_confidence("pts", 20.0, 28.0) == "high"

    def test_low_confidence_wide_spread(self):
        assert compute_confidence("pts", 5.0, 35.0) == "low"

    def test_medium_confidence(self):
        assert compute_confidence("pts", 15.0, 29.0) == "medium"

    def test_unknown_stat_uses_default_threshold(self):
        result = compute_confidence("unknown_stat", 5.0, 25.0)
        assert result == "low"


class TestFixQuantileCrossing:
    def test_already_ordered(self):
        preds = {0.10: 5.0, 0.25: 10.0, 0.50: 15.0, 0.75: 20.0, 0.90: 25.0}
        fixed = fix_quantile_crossing(preds)
        assert fixed == preds

    def test_fixes_crossing(self):
        preds = {0.10: 5.0, 0.25: 12.0, 0.50: 10.0, 0.75: 20.0, 0.90: 25.0}
        fixed = fix_quantile_crossing(preds)
        values = [fixed[q] for q in sorted(fixed.keys())]
        # Must be non-decreasing
        for i in range(1, len(values)):
            assert values[i] >= values[i - 1]

    def test_all_same_value(self):
        preds = {0.10: 10.0, 0.25: 10.0, 0.50: 10.0, 0.75: 10.0, 0.90: 10.0}
        fixed = fix_quantile_crossing(preds)
        assert all(v == 10.0 for v in fixed.values())


class TestEstimateIntervalFromMae:
    def test_returns_five_quantiles(self):
        result = estimate_interval_from_mae(20.0, "pts")
        assert set(result.keys()) == {0.10, 0.25, 0.50, 0.75, 0.90}

    def test_p50_equals_input(self):
        result = estimate_interval_from_mae(20.0, "pts")
        assert result[0.50] == 20.0

    def test_non_decreasing(self):
        result = estimate_interval_from_mae(20.0, "pts")
        values = [result[q] for q in sorted(result.keys())]
        for i in range(1, len(values)):
            assert values[i] >= values[i - 1]

    def test_floor_at_zero(self):
        result = estimate_interval_from_mae(1.0, "pts")
        assert result[0.10] >= 0.0


class TestBuildStatPrediction:
    def test_with_quantile_preds(self):
        q_preds = {0.10: 5.0, 0.25: 10.0, 0.50: 15.0, 0.75: 20.0, 0.90: 25.0}
        sp = build_stat_prediction("pts", q_preds, 15.0)
        assert sp.stat == "pts"
        assert sp.p50 == 15.0
        assert sp.p10 == 5.0

    def test_without_quantile_preds(self):
        sp = build_stat_prediction("stl", None, 1.5)
        assert sp.stat == "stl"
        assert sp.p50 == 1.5
        assert sp.p10 < sp.p50
        assert sp.p90 > sp.p50

    def test_confidence_populated(self):
        q_preds = {0.10: 5.0, 0.25: 10.0, 0.50: 15.0, 0.75: 20.0, 0.90: 25.0}
        sp = build_stat_prediction("pts", q_preds, 15.0)
        assert sp.confidence in ("high", "medium", "low")

    def test_values_non_negative(self):
        sp = build_stat_prediction("blk", None, 0.5)
        assert sp.p10 >= 0.0
        assert sp.p25 >= 0.0
