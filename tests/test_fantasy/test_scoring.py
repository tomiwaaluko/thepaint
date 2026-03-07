"""Tests for fantasy scoring engine."""
import pytest

from chalk.api.schemas import StatPrediction
from chalk.fantasy.scoring import compute_all_fantasy_scores, compute_fantasy_score
from chalk.fantasy.simulation import SimulationResult, simulate_fantasy_scores


class TestComputeFantasyScore:
    def _typical_stats(self) -> dict[str, float]:
        return {
            "pts": 25.0,
            "reb": 7.0,
            "ast": 7.0,
            "stl": 1.2,
            "blk": 0.8,
            "to_committed": 2.5,
            "fg3m": 2.0,
        }

    def test_draftkings_basic(self):
        stats = self._typical_stats()
        score = compute_fantasy_score(stats, "draftkings")
        # 25*1 + 2*0.5 + 7*1.25 + 7*1.5 + 1.2*2 + 0.8*2 + 2.5*-0.5 = 42.50
        expected = 25 + 1 + 8.75 + 10.5 + 2.4 + 1.6 - 1.25
        assert abs(score - expected) < 0.01

    def test_draftkings_double_double_bonus(self):
        stats = {"pts": 20.0, "reb": 12.0, "ast": 5.0, "stl": 1.0, "blk": 0.5,
                 "to_committed": 2.0, "fg3m": 1.0}
        score = compute_fantasy_score(stats, "draftkings")
        # Base + 1.5 DD bonus
        score_no_bonus = compute_fantasy_score(
            {"pts": 9.0, "reb": 12.0, "ast": 5.0, "stl": 1.0, "blk": 0.5,
             "to_committed": 2.0, "fg3m": 1.0}, "draftkings"
        )
        # pts=20 gives DD (pts+reb >= 10), pts=9 does not
        stats_no_dd = dict(stats)
        stats_no_dd["pts"] = 9.0  # only reb >= 10 now
        score_one_dd = compute_fantasy_score(stats_no_dd, "draftkings")
        # With double-double, score should be higher by 1.5 + pts diff
        assert score > score_one_dd

    def test_draftkings_triple_double_bonus(self):
        stats = {"pts": 15.0, "reb": 12.0, "ast": 10.0, "stl": 1.0, "blk": 0.5,
                 "to_committed": 2.0, "fg3m": 1.0}
        score = compute_fantasy_score(stats, "draftkings")
        # Should include DD bonus (1.5) AND TD bonus (3.0)
        stats_dd = dict(stats)
        stats_dd["ast"] = 9.0  # drop to only DD
        score_dd = compute_fantasy_score(stats_dd, "draftkings")
        # Difference should include TD bonus + ast contribution diff
        assert score > score_dd

    def test_fanduel_no_bonus(self):
        stats = {"pts": 20.0, "reb": 12.0, "ast": 11.0, "stl": 1.0, "blk": 0.5,
                 "to_committed": 2.0}
        score = compute_fantasy_score(stats, "fanduel")
        # FD: 20*1 + 12*1.2 + 11*1.5 + 1*2 + 0.5*2 + 2*-1 = 20+14.4+16.5+2+1-2 = 51.9
        expected = 20 + 14.4 + 16.5 + 2 + 1 - 2
        assert abs(score - expected) < 0.01

    def test_yahoo_scoring(self):
        stats = {"pts": 20.0, "reb": 10.0, "ast": 5.0, "stl": 2.0, "blk": 1.0,
                 "to_committed": 3.0, "fg3m": 3.0}
        score = compute_fantasy_score(stats, "yahoo")
        # 20*1 + 3*0.5 + 10*1.2 + 5*1.5 + 2*2 + 1*2 - 3*1 = 20+1.5+12+7.5+4+2-3 = 44.0
        expected = 20 + 1.5 + 12 + 7.5 + 4 + 2 - 3
        assert abs(score - expected) < 0.01

    def test_all_zeros(self):
        score = compute_fantasy_score({}, "draftkings")
        assert score == 0.0


class TestComputeAllFantasyScores:
    def test_returns_all_platforms(self):
        stats = {"pts": 20.0, "reb": 8.0, "ast": 5.0, "stl": 1.0, "blk": 0.5,
                 "to_committed": 2.0, "fg3m": 2.0}
        result = compute_all_fantasy_scores(stats)
        assert result.draftkings > 0
        assert result.fanduel > 0
        assert result.yahoo > 0


class TestMonteCarloSimulation:
    def _make_predictions(self) -> list[StatPrediction]:
        return [
            StatPrediction(stat="pts", p10=15.0, p25=20.0, p50=25.0, p75=30.0, p90=35.0, confidence="medium"),
            StatPrediction(stat="reb", p10=3.0, p25=5.0, p50=7.0, p75=9.0, p90=11.0, confidence="medium"),
            StatPrediction(stat="ast", p10=3.0, p25=5.0, p50=7.0, p75=9.0, p90=11.0, confidence="medium"),
            StatPrediction(stat="fg3m", p10=0.5, p25=1.0, p50=2.0, p75=3.0, p90=4.0, confidence="medium"),
            StatPrediction(stat="stl", p10=0.3, p25=0.6, p50=1.2, p75=1.5, p90=2.0, confidence="medium"),
            StatPrediction(stat="blk", p10=0.1, p25=0.3, p50=0.8, p75=1.0, p90=1.5, confidence="medium"),
            StatPrediction(stat="to_committed", p10=1.0, p25=1.5, p50=2.5, p75=3.0, p90=4.0, confidence="medium"),
        ]

    def test_floor_less_than_ceiling(self):
        preds = self._make_predictions()
        result = simulate_fantasy_scores(preds, "draftkings")
        assert result.floor < result.ceiling

    def test_mean_between_floor_and_ceiling(self):
        preds = self._make_predictions()
        result = simulate_fantasy_scores(preds, "draftkings")
        assert result.floor <= result.mean <= result.ceiling

    def test_boom_rate_between_0_and_1(self):
        preds = self._make_predictions()
        result = simulate_fantasy_scores(preds, "draftkings")
        assert 0.0 <= result.boom_rate <= 1.0
        assert 0.0 <= result.bust_rate <= 1.0

    def test_std_positive(self):
        preds = self._make_predictions()
        result = simulate_fantasy_scores(preds, "draftkings")
        assert result.std > 0

    def test_different_platforms(self):
        preds = self._make_predictions()
        dk = simulate_fantasy_scores(preds, "draftkings")
        fd = simulate_fantasy_scores(preds, "fanduel")
        assert dk.platform == "draftkings"
        assert fd.platform == "fanduel"
        # Scores should differ between platforms
        assert dk.mean != fd.mean

    def test_deterministic_with_seed(self):
        preds = self._make_predictions()
        r1 = simulate_fantasy_scores(preds, "draftkings", seed=42)
        r2 = simulate_fantasy_scores(preds, "draftkings", seed=42)
        assert r1.mean == r2.mean
        assert r1.floor == r2.floor
