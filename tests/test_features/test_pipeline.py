"""Tests for the master feature pipeline."""
from datetime import date

import pytest

from chalk.db.models import Game, Player, PlayerGameLog, Team, TeamGameLog
from chalk.exceptions import FeatureError
from chalk.features.pipeline import build_training_matrix, generate_features

LAKERS_ID = 1610612747
WARRIORS_ID = 1610612744
NUGGETS_ID = 1610612743
PLAYER_ID = 2544
SEASON = "2023-24"


@pytest.fixture
async def pipeline_db(session):
    """Seed full data needed for pipeline testing."""
    session.add_all([
        Team(team_id=LAKERS_ID, name="Lakers", abbreviation="LAL",
             conference="West", division="Pacific", city="LA"),
        Team(team_id=WARRIORS_ID, name="Warriors", abbreviation="GSW",
             conference="West", division="Pacific", city="SF"),
        Team(team_id=NUGGETS_ID, name="Nuggets", abbreviation="DEN",
             conference="West", division="Northwest", city="Denver"),
    ])
    session.add(Player(
        player_id=PLAYER_ID, name="LeBron James",
        team_id=LAKERS_ID, position="SF", is_active=True,
    ))

    # Create 12 games with game logs
    for i in range(12):
        gid = f"002230{3000 + i}"
        gdate = date(2024, 1, 1 + i * 2)
        is_home = i % 2 == 0
        session.add(Game(
            game_id=gid, date=gdate, season=SEASON,
            home_team_id=LAKERS_ID if is_home else WARRIORS_ID,
            away_team_id=WARRIORS_ID if is_home else LAKERS_ID,
        ))
        session.add(PlayerGameLog(
            game_id=gid, player_id=PLAYER_ID, team_id=LAKERS_ID,
            game_date=gdate, season=SEASON,
            min_played=35.0, pts=25 + i, reb=7 + (i % 3), ast=6 + (i % 4),
            stl=1, blk=1, to_committed=3, fg3m=3, fg3a=7,
            fgm=9, fga=18, ftm=4, fta=5, plus_minus=5, starter=True,
        ))
        # Team game log for opponents
        session.add(TeamGameLog(
            game_id=gid, team_id=WARRIORS_ID, game_date=gdate, season=SEASON,
            pts=110, pace=100.0, off_rtg=112.0, def_rtg=108.0,
            ts_pct=0.56, ast=25, to_committed=13, oreb=10, dreb=35,
            fg3a_rate=0.37,
        ))

    await session.commit()
    return session


class TestGenerateFeatures:
    @pytest.mark.asyncio
    async def test_returns_no_none_values(self, pipeline_db):
        features = await generate_features(
            pipeline_db, PLAYER_ID, "0022303005", date(2024, 1, 12),
        )
        for k, v in features.items():
            assert v is not None, f"{k} is None"

    @pytest.mark.asyncio
    async def test_all_values_are_float(self, pipeline_db):
        features = await generate_features(
            pipeline_db, PLAYER_ID, "0022303005", date(2024, 1, 12),
        )
        for k, v in features.items():
            assert isinstance(v, float), f"{k} is {type(v)}, expected float"

    @pytest.mark.asyncio
    async def test_as_of_date_gate(self, pipeline_db):
        """Different as_of_dates should produce different feature values."""
        f_early = await generate_features(
            pipeline_db, PLAYER_ID, "0022303005", date(2024, 1, 6),
        )
        f_late = await generate_features(
            pipeline_db, PLAYER_ID, "0022303005", date(2024, 1, 20),
        )
        # With more history, averages should differ
        assert f_early["pts_avg_5g"] != f_late["pts_avg_5g"]

    @pytest.mark.asyncio
    async def test_raises_on_missing_player(self, pipeline_db):
        with pytest.raises(FeatureError, match="Player 99999"):
            await generate_features(
                pipeline_db, 99999, "0022303005", date(2024, 1, 12),
            )

    @pytest.mark.asyncio
    async def test_raises_on_missing_game(self, pipeline_db):
        with pytest.raises(FeatureError, match="Game FAKE"):
            await generate_features(
                pipeline_db, PLAYER_ID, "FAKE", date(2024, 1, 12),
            )

    @pytest.mark.asyncio
    async def test_feature_count(self, pipeline_db):
        """Should return 60+ features."""
        features = await generate_features(
            pipeline_db, PLAYER_ID, "0022303005", date(2024, 1, 20),
        )
        # Rolling: 13*3 + 3*2 + 3 = 48
        # Opponent: 6
        # Roster: 5
        # Usage: 6
        # Situational: 9
        # Total: ~74
        assert len(features) >= 60


class TestBuildTrainingMatrix:
    @pytest.mark.asyncio
    async def test_matrix_shape(self, pipeline_db):
        """Matrix should have rows for each game log and feature columns."""
        df = await build_training_matrix(
            pipeline_db, [PLAYER_ID], "pts", [SEASON],
        )
        # 12 game logs, but each one uses as_of_date = game_date (strict <),
        # so the first game has 0 prior games. All should still produce features.
        assert len(df) == 12
        assert "target" in df.columns
        assert "player_id" in df.columns
        assert df["target"].notna().all()

    @pytest.mark.asyncio
    async def test_empty_for_unknown_player(self, pipeline_db):
        df = await build_training_matrix(
            pipeline_db, [99999], "pts", [SEASON],
        )
        assert len(df) == 0
