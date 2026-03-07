"""Tests for opponent defensive feature functions."""
from datetime import date

import pytest

from chalk.db.models import Game, Player, PlayerGameLog, Team, TeamGameLog
from chalk.features.opponent import (
    get_all_opponent_features,
    get_opp_blk_rate,
    get_opp_def_rtg,
    get_opp_fg3a_rate_allowed,
    get_opp_pace,
    get_opp_pts_allowed_by_position,
    get_opp_stl_rate,
)

LAKERS_ID = 1610612747
WARRIORS_ID = 1610612744
PLAYER_ID = 2544
SEASON = "2023-24"


@pytest.fixture
async def opp_db(session):
    """Seed teams, players, games, and team/player game logs."""
    session.add_all([
        Team(team_id=LAKERS_ID, name="Lakers", abbreviation="LAL",
             conference="West", division="Pacific", city="LA"),
        Team(team_id=WARRIORS_ID, name="Warriors", abbreviation="GSW",
             conference="West", division="Pacific", city="SF"),
    ])
    session.add_all([
        Player(player_id=PLAYER_ID, name="LeBron James",
               team_id=LAKERS_ID, position="SF", is_active=True),
        Player(player_id=201939, name="Stephen Curry",
               team_id=WARRIORS_ID, position="PG", is_active=True),
    ])

    # 5 games: LAL vs GSW
    for i in range(5):
        gid = f"002230{2000 + i}"
        gdate = date(2024, 1, 1 + i * 3)
        session.add(Game(
            game_id=gid, date=gdate, season=SEASON,
            home_team_id=LAKERS_ID, away_team_id=WARRIORS_ID,
        ))
        # Team game logs for GSW (the opponent we'll query)
        session.add(TeamGameLog(
            game_id=gid, team_id=WARRIORS_ID, game_date=gdate, season=SEASON,
            pts=110 + i, pace=100.0 + i, off_rtg=112.0, def_rtg=108.0 + i,
            ts_pct=0.56, ast=25, to_committed=13, oreb=10, dreb=35,
            fg3a_rate=0.35 + i * 0.01,
        ))
        # Player game logs for LeBron (plays vs GSW)
        session.add(PlayerGameLog(
            game_id=gid, player_id=PLAYER_ID, team_id=LAKERS_ID,
            game_date=gdate, season=SEASON,
            min_played=36.0, pts=25 + i, reb=8, ast=7,
            stl=1 + (i % 2), blk=1, to_committed=3,
            fg3m=3, fg3a=7, fgm=9, fga=18, ftm=4, fta=5,
            plus_minus=5, starter=True,
        ))
        # Curry game logs (plays for GSW)
        session.add(PlayerGameLog(
            game_id=gid, player_id=201939, team_id=WARRIORS_ID,
            game_date=gdate, season=SEASON,
            min_played=34.0, pts=30 + i, reb=5, ast=6,
            stl=2, blk=0, to_committed=4,
            fg3m=5, fg3a=11, fgm=10, fga=20, ftm=5, fta=6,
            plus_minus=-3, starter=True,
        ))

    await session.commit()
    return session


class TestGetOppDefRtg:
    @pytest.mark.asyncio
    async def test_returns_avg_def_rtg(self, opp_db):
        # def_rtg: 108, 109, 110, 111, 112 → avg 110
        val = await get_opp_def_rtg(opp_db, WARRIORS_ID, date(2024, 2, 1))
        assert val == pytest.approx(110.0)

    @pytest.mark.asyncio
    async def test_respects_as_of_date(self, opp_db):
        # Only first 2 games before Jan 5: def_rtg 108, 109 → avg 108.5
        val = await get_opp_def_rtg(opp_db, WARRIORS_ID, date(2024, 1, 5))
        assert val == pytest.approx(108.5)

    @pytest.mark.asyncio
    async def test_no_data_returns_zero(self, opp_db):
        val = await get_opp_def_rtg(opp_db, WARRIORS_ID, date(2023, 1, 1))
        assert val == 0.0


class TestGetOppPace:
    @pytest.mark.asyncio
    async def test_returns_avg_pace(self, opp_db):
        # pace: 100, 101, 102, 103, 104 → avg 102
        val = await get_opp_pace(opp_db, WARRIORS_ID, date(2024, 2, 1))
        assert val == pytest.approx(102.0)


class TestGetOppPtsAllowedByPosition:
    @pytest.mark.asyncio
    async def test_returns_avg_pts_by_position(self, opp_db):
        # LeBron (SF) scored 25, 26, 27, 28, 29 against GSW → avg 27
        val = await get_opp_pts_allowed_by_position(
            opp_db, WARRIORS_ID, "SF", date(2024, 2, 1)
        )
        assert val == pytest.approx(27.0)

    @pytest.mark.asyncio
    async def test_no_data_returns_zero(self, opp_db):
        # No centers scored against GSW in our data
        val = await get_opp_pts_allowed_by_position(
            opp_db, WARRIORS_ID, "C", date(2024, 2, 1)
        )
        assert val == 0.0


class TestGetOppFg3aRate:
    @pytest.mark.asyncio
    async def test_returns_avg_rate(self, opp_db):
        # fg3a_rate: 0.35, 0.36, 0.37, 0.38, 0.39 → avg 0.37
        val = await get_opp_fg3a_rate_allowed(opp_db, WARRIORS_ID, date(2024, 2, 1))
        assert val == pytest.approx(0.37)


class TestGetOppStlRate:
    @pytest.mark.asyncio
    async def test_returns_avg_stl(self, opp_db):
        # GSW total stl per game: Curry has stl=2 each game → 2.0
        val = await get_opp_stl_rate(opp_db, WARRIORS_ID, date(2024, 2, 1))
        assert val == pytest.approx(2.0)


class TestGetOppBlkRate:
    @pytest.mark.asyncio
    async def test_returns_avg_blk(self, opp_db):
        # GSW total blk per game: Curry has blk=0 → 0.0
        val = await get_opp_blk_rate(opp_db, WARRIORS_ID, date(2024, 2, 1))
        assert val == pytest.approx(0.0)


class TestGetAllOpponentFeatures:
    @pytest.mark.asyncio
    async def test_returns_all_keys(self, opp_db):
        features = await get_all_opponent_features(
            opp_db, WARRIORS_ID, "SF", date(2024, 2, 1)
        )
        assert "opp_def_rtg_15g" in features
        assert "opp_pace_15g" in features
        assert "opp_pts_allowed_sf" in features
        assert "opp_fg3a_rate_allowed_15g" in features
        assert "opp_stl_rate_15g" in features
        assert "opp_blk_rate_15g" in features
        assert len(features) == 6

    @pytest.mark.asyncio
    async def test_all_values_are_float(self, opp_db):
        features = await get_all_opponent_features(
            opp_db, WARRIORS_ID, "SF", date(2024, 2, 1)
        )
        for k, v in features.items():
            assert isinstance(v, float), f"{k} is {type(v)}"
