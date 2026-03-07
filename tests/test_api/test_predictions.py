"""Tests for prediction engines — mocked models and features."""
from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from chalk.api.schemas import PlayerPredictionResponse
from chalk.predictions.player import (
    _compute_fantasy_scores,
    _get_stat_value,
    predict_player,
)
from chalk.api.schemas import StatPrediction


class TestComputeFantasyScores:
    def _make_predictions(self):
        return [
            StatPrediction(stat="pts", p10=15.0, p25=20.0, p50=25.0, p75=30.0, p90=35.0, confidence="high"),
            StatPrediction(stat="reb", p10=3.0, p25=5.0, p50=7.0, p75=9.0, p90=11.0, confidence="medium"),
            StatPrediction(stat="ast", p10=3.0, p25=5.0, p50=7.0, p75=9.0, p90=11.0, confidence="medium"),
            StatPrediction(stat="stl", p10=0.5, p25=0.8, p50=1.2, p75=1.5, p90=2.0, confidence="medium"),
            StatPrediction(stat="blk", p10=0.2, p25=0.4, p50=0.8, p75=1.0, p90=1.5, confidence="medium"),
            StatPrediction(stat="to_committed", p10=1.0, p25=1.5, p50=2.5, p75=3.0, p90=4.0, confidence="medium"),
            StatPrediction(stat="fg3m", p10=0.5, p25=1.0, p50=2.0, p75=3.0, p90=4.0, confidence="medium"),
        ]

    def test_draftkings_scoring(self):
        preds = self._make_predictions()
        fantasy = _compute_fantasy_scores(preds)
        # DK: pts*1 + fg3m*0.5 + reb*1.25 + ast*1.5 + stl*2 + blk*2 + to*-0.5
        expected_dk = 25*1 + 2*0.5 + 7*1.25 + 7*1.5 + 1.2*2 + 0.8*2 + 2.5*-0.5
        assert abs(fantasy.draftkings - expected_dk) < 0.01

    def test_all_scores_positive_for_typical_player(self):
        preds = self._make_predictions()
        fantasy = _compute_fantasy_scores(preds)
        assert fantasy.draftkings > 0
        assert fantasy.fanduel > 0
        assert fantasy.yahoo > 0


class TestGetStatValue:
    def test_finds_stat(self):
        preds = [
            StatPrediction(stat="pts", p10=10.0, p25=15.0, p50=20.0, p75=25.0, p90=30.0, confidence="high"),
        ]
        assert _get_stat_value(preds, "pts") == 20.0

    def test_returns_zero_for_missing(self):
        assert _get_stat_value([], "pts") == 0.0
