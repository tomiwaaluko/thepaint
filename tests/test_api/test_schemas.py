"""Tests for API Pydantic schemas."""
from datetime import datetime, timezone

import pytest

from chalk.api.schemas import (
    FantasyScores,
    GamePredictionResponse,
    HealthResponse,
    InjuryContext,
    OverUnderResponse,
    PlayerPredictionResponse,
    StatPrediction,
    TeamPredictionResponse,
)


class TestStatPrediction:
    def test_create_with_field_names(self):
        sp = StatPrediction(
            stat="pts", p10=10.0, p25=15.0, p50=20.0, p75=25.0, p90=30.0,
            confidence="high",
        )
        assert sp.stat == "pts"
        assert sp.p50 == 20.0
        assert sp.confidence == "high"

    def test_create_with_aliases(self):
        sp = StatPrediction(
            stat="pts", p10=10.0, p25=15.0, median=20.0, p75=25.0, ceiling=30.0,
            confidence="medium",
        )
        assert sp.p50 == 20.0
        assert sp.p90 == 30.0

    def test_json_output_uses_aliases(self):
        sp = StatPrediction(
            stat="reb", p10=2.0, p25=4.0, p50=6.0, p75=8.0, p90=10.0,
            confidence="low",
        )
        data = sp.model_dump(by_alias=True)
        assert "median" in data
        assert "ceiling" in data

    def test_json_output_uses_field_names(self):
        sp = StatPrediction(
            stat="reb", p10=2.0, p25=4.0, p50=6.0, p75=8.0, p90=10.0,
            confidence="low",
        )
        data = sp.model_dump()
        assert "p50" in data
        assert "p90" in data


class TestFantasyScores:
    def test_defaults_to_zero(self):
        fs = FantasyScores()
        assert fs.draftkings == 0.0
        assert fs.fanduel == 0.0
        assert fs.yahoo == 0.0


class TestInjuryContext:
    def test_defaults(self):
        ic = InjuryContext()
        assert ic.player_status == "active"
        assert ic.absent_teammates == []
        assert ic.opportunity_adjustment == 1.0

    def test_with_absent_teammates(self):
        ic = InjuryContext(
            player_status="active",
            absent_teammates=["LeBron James", "Anthony Davis"],
            opportunity_adjustment=1.15,
        )
        assert len(ic.absent_teammates) == 2


class TestPlayerPredictionResponse:
    def _make_response(self) -> PlayerPredictionResponse:
        return PlayerPredictionResponse(
            player_id=2544,
            player_name="LeBron James",
            game_id="0022300001",
            opponent_team="GSW",
            as_of_ts=datetime(2024, 1, 15, 18, 0, 0, tzinfo=timezone.utc),
            model_version="20240115_120000",
            predictions=[
                StatPrediction(
                    stat="pts", p10=15.0, p25=20.0, p50=25.0, p75=30.0, p90=35.0,
                    confidence="high",
                ),
                StatPrediction(
                    stat="reb", p10=3.0, p25=5.0, p50=7.0, p75=9.0, p90=11.0,
                    confidence="medium",
                ),
            ],
            fantasy_scores=FantasyScores(draftkings=45.5, fanduel=42.0, yahoo=40.0),
            injury_context=InjuryContext(),
        )

    def test_create_full_response(self):
        resp = self._make_response()
        assert resp.player_id == 2544
        assert len(resp.predictions) == 2
        assert resp.fantasy_scores.draftkings == 45.5

    def test_serializes_to_json(self):
        resp = self._make_response()
        data = resp.model_dump_json()
        assert "LeBron James" in data
        assert "2544" in data

    def test_no_none_in_response(self):
        resp = self._make_response()
        data = resp.model_dump()
        assert _check_no_none(data)


class TestTeamPredictionResponse:
    def test_create(self):
        resp = TeamPredictionResponse(
            team_id=1610612747,
            team_name="Los Angeles Lakers",
            game_id="0022300001",
            opponent_team="Golden State Warriors",
            as_of_ts=datetime(2024, 1, 15, tzinfo=timezone.utc),
            model_version="20240115_120000",
            predicted_pts=112.5,
            predicted_pace=100.2,
            predicted_off_rtg=115.0,
            predicted_def_rtg=108.0,
        )
        assert resp.predicted_pts == 112.5


class TestHealthResponse:
    def test_ok_status(self):
        resp = HealthResponse(
            status="ok",
            checks={"database": "ok", "redis": "ok"},
            timestamp=datetime(2024, 1, 15, tzinfo=timezone.utc),
        )
        assert resp.status == "ok"

    def test_degraded_status(self):
        resp = HealthResponse(
            status="degraded",
            checks={"database": "ok", "redis": "error"},
            timestamp=datetime(2024, 1, 15, tzinfo=timezone.utc),
        )
        assert resp.status == "degraded"


class TestOverUnderResponse:
    def test_create(self):
        resp = OverUnderResponse(
            player_id=2544,
            player_name="LeBron James",
            stat="pts",
            line=24.5,
            sportsbook="DraftKings",
            over_probability=0.62,
            under_probability=0.38,
            implied_over_prob=0.52,
            edge=0.10,
            confidence="high",
        )
        assert resp.edge == 0.10


def _check_no_none(data) -> bool:
    """Recursively check that no values in a dict/list structure are None."""
    if isinstance(data, dict):
        return all(v is not None and _check_no_none(v) for v in data.values())
    if isinstance(data, list):
        return all(_check_no_none(item) for item in data)
    return True
