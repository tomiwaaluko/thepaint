"""Tests for over/under probability module."""
import pytest

from chalk.betting.over_under import (
    american_to_implied_probability,
    calculate_edge,
    edge_confidence,
    fit_distribution,
    over_probability,
    remove_vig,
)


class TestOverProbability:
    def test_above_ceiling_near_zero(self):
        prob = over_probability(40.0, p10=15.0, p25=20.0, p50=25.0, p75=30.0, p90=35.0)
        assert prob < 0.05

    def test_below_floor_near_one(self):
        prob = over_probability(5.0, p10=15.0, p25=20.0, p50=25.0, p75=30.0, p90=35.0)
        assert prob > 0.95

    def test_at_median_near_half(self):
        prob = over_probability(25.0, p10=15.0, p25=20.0, p50=25.0, p75=30.0, p90=35.0)
        assert 0.45 < prob < 0.55

    def test_clamped_to_min(self):
        prob = over_probability(100.0, p10=15.0, p25=20.0, p50=25.0, p75=30.0, p90=35.0)
        assert prob >= 0.01

    def test_clamped_to_max(self):
        prob = over_probability(-50.0, p10=15.0, p25=20.0, p50=25.0, p75=30.0, p90=35.0)
        assert prob <= 0.99

    def test_higher_line_lower_probability(self):
        prob_low = over_probability(20.0, p10=15.0, p25=20.0, p50=25.0, p75=30.0, p90=35.0)
        prob_high = over_probability(30.0, p10=15.0, p25=20.0, p50=25.0, p75=30.0, p90=35.0)
        assert prob_low > prob_high


class TestFitDistribution:
    def test_returns_distribution(self):
        dist = fit_distribution(15.0, 20.0, 25.0, 30.0, 35.0)
        assert hasattr(dist, "cdf")
        assert hasattr(dist, "ppf")

    def test_handles_zero_spread(self):
        dist = fit_distribution(25.0, 25.0, 25.0, 25.0, 25.0)
        # Should not raise, uses minimum std
        assert dist.cdf(25.0) > 0


class TestAmericanToImpliedProbability:
    def test_minus_110(self):
        prob = american_to_implied_probability(-110)
        assert abs(prob - 0.524) < 0.01

    def test_plus_110(self):
        prob = american_to_implied_probability(110)
        assert abs(prob - 0.476) < 0.01

    def test_even_money(self):
        prob = american_to_implied_probability(100)
        assert prob == 0.5

    def test_heavy_favorite(self):
        prob = american_to_implied_probability(-300)
        assert prob > 0.7

    def test_big_underdog(self):
        prob = american_to_implied_probability(300)
        assert prob < 0.3


class TestRemoveVig:
    def test_removes_vig(self):
        over_imp = american_to_implied_probability(-110)
        under_imp = american_to_implied_probability(-110)
        true_over, true_under = remove_vig(over_imp, under_imp)
        assert abs(true_over - 0.5) < 0.01
        assert abs(true_under - 0.5) < 0.01
        assert abs(true_over + true_under - 1.0) < 0.001


class TestCalculateEdge:
    def test_positive_edge(self):
        edge = calculate_edge(0.60, 0.52)
        assert edge == 0.08

    def test_negative_edge(self):
        edge = calculate_edge(0.45, 0.52)
        assert edge == -0.07

    def test_zero_edge(self):
        edge = calculate_edge(0.50, 0.50)
        assert edge == 0.0


class TestEdgeConfidence:
    def test_high(self):
        assert edge_confidence(0.10) == "high"

    def test_medium(self):
        assert edge_confidence(0.05) == "medium"

    def test_low(self):
        assert edge_confidence(0.02) == "low"

    def test_negative_high(self):
        assert edge_confidence(-0.09) == "high"
