"""Tests for model drift monitoring."""
from datetime import date, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chalk.db.models import Game, Player, PlayerGameLog, Prediction, Team
from chalk.monitoring.drift import (
    BASELINE_MAES,
    DRIFT_THRESHOLD,
    DriftReport,
    check_for_drift,
    compute_daily_mae,
)


@pytest_asyncio.fixture
async def seeded_session(session: AsyncSession):
    """Seed DB with a team, player, game, game log, and prediction."""
    team = Team(
        team_id=1, name="Test Team", abbreviation="TST",
        conference="East", division="Atlantic", city="Test",
    )
    opp = Team(
        team_id=2, name="Opp Team", abbreviation="OPP",
        conference="West", division="Pacific", city="Opp",
    )
    session.add_all([team, opp])
    await session.flush()

    player = Player(
        player_id=100, name="Test Player", team_id=1,
        position="G", is_active=True,
    )
    session.add(player)
    await session.flush()

    game_date = date.today() - timedelta(days=1)
    game = Game(
        game_id="G001", date=game_date, season="2023-24",
        home_team_id=1, away_team_id=2,
    )
    session.add(game)
    await session.flush()

    # Actual stats
    log = PlayerGameLog(
        game_id="G001", player_id=100, team_id=1,
        game_date=game_date, season="2023-24", min_played=30.0,
        pts=25, reb=7, ast=5, stl=1, blk=0,
        to_committed=2, fg3m=3, fg3a=8, fgm=9, fga=18,
        ftm=4, fta=5, plus_minus=8, starter=True,
    )
    session.add(log)
    await session.flush()

    yield session, game_date


class TestComputeDailyMae:
    @pytest.mark.asyncio
    async def test_computes_mae_for_matching_predictions(self, seeded_session):
        session, game_date = seeded_session

        # Prediction: p50=20 vs actual=25 → error=5
        pred = Prediction(
            game_id="G001", player_id=100, model_version="v1",
            as_of_ts=game_date, stat="pts",
            p10=10, p25=15, p50=20.0, p75=25, p90=30,
        )
        session.add(pred)
        await session.flush()

        maes = await compute_daily_mae(session, game_date)
        assert "pts" in maes
        assert maes["pts"] == 5.0  # |20 - 25| = 5

    @pytest.mark.asyncio
    async def test_returns_empty_for_no_predictions(self, seeded_session):
        session, game_date = seeded_session
        maes = await compute_daily_mae(session, game_date)
        assert maes == {}

    @pytest.mark.asyncio
    async def test_multiple_predictions_averaged(self, seeded_session):
        session, game_date = seeded_session

        # Add a second player
        player2 = Player(
            player_id=101, name="Player Two", team_id=1,
            position="F", is_active=True,
        )
        session.add(player2)
        await session.flush()

        log2 = PlayerGameLog(
            game_id="G001", player_id=101, team_id=1,
            game_date=game_date, season="2023-24", min_played=25.0,
            pts=15, reb=5, ast=3, stl=0, blk=1,
            to_committed=1, fg3m=1, fg3a=4, fgm=6, fga=14,
            ftm=2, fta=2, plus_minus=-3, starter=False,
        )
        session.add(log2)

        # Predictions: p50=20 for player100 (error=5), p50=18 for player101 (error=3)
        pred1 = Prediction(
            game_id="G001", player_id=100, model_version="v1",
            as_of_ts=game_date, stat="pts",
            p10=10, p25=15, p50=20.0, p75=25, p90=30,
        )
        pred2 = Prediction(
            game_id="G001", player_id=101, model_version="v1",
            as_of_ts=game_date, stat="pts",
            p10=8, p25=12, p50=18.0, p75=22, p90=28,
        )
        session.add_all([pred1, pred2])
        await session.flush()

        maes = await compute_daily_mae(session, game_date)
        # (|20-25| + |18-15|) / 2 = (5 + 3) / 2 = 4.0
        assert maes["pts"] == 4.0


class TestCheckForDrift:
    @pytest.mark.asyncio
    async def test_no_drift_when_mae_matches_baseline(self, seeded_session):
        session, game_date = seeded_session

        # Predict p50=30 for pts=25 → error = 5.0, baseline is 4.94
        pred = Prediction(
            game_id="G001", player_id=100, model_version="v1",
            as_of_ts=game_date, stat="pts",
            p10=10, p25=20, p50=30.0, p75=35, p90=40,
        )
        session.add(pred)
        await session.flush()

        report = await check_for_drift(session, "pts")
        assert report.stat == "pts"
        assert report.n_predictions == 1
        # error = 5.0, baseline = 4.94, drift = (5.0-4.94)/4.94 = ~1.2%
        assert report.drift_pct < DRIFT_THRESHOLD
        assert not report.is_drifting

    @pytest.mark.asyncio
    async def test_detects_drift_when_mae_high(self, seeded_session):
        session, game_date = seeded_session

        # Predict p50=10 for pts=25 → error = 15, baseline is 4.94
        pred = Prediction(
            game_id="G001", player_id=100, model_version="v1",
            as_of_ts=game_date, stat="pts",
            p10=5, p25=8, p50=10.0, p75=15, p90=20,
        )
        session.add(pred)
        await session.flush()

        report = await check_for_drift(session, "pts")
        # error = 15, baseline = 4.94, drift = (15-4.94)/4.94 = ~203%
        assert report.is_drifting
        assert report.drift_pct > DRIFT_THRESHOLD

    @pytest.mark.asyncio
    async def test_no_predictions_returns_safe_report(self, seeded_session):
        session, _ = seeded_session
        report = await check_for_drift(session, "pts")
        assert report.n_predictions == 0
        assert not report.is_drifting


class TestDriftReport:
    def test_dataclass_fields(self):
        report = DriftReport(
            stat="pts",
            rolling_mae=5.5,
            baseline_mae=4.94,
            drift_pct=0.113,
            is_drifting=False,
            n_predictions=100,
        )
        assert report.stat == "pts"
        assert not report.is_drifting
