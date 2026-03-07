"""Tests for rolling window feature functions."""
from datetime import date

import pytest

from chalk.db.models import Game, Player, PlayerGameLog, Team
from chalk.features.rolling import (
    compute_trend_slope,
    get_all_rolling_features,
    get_rolling_avg,
    get_rolling_avg_split,
    get_stat_trend,
)

TEAM_ID = 1610612747  # Lakers
OPP_TEAM_ID = 1610612744  # Warriors
PLAYER_ID = 2544  # LeBron
SEASON = "2023-24"


@pytest.fixture
async def seeded_db(session):
    """Insert a team, player, and several game logs for testing."""
    session.add(Team(
        team_id=TEAM_ID, name="Los Angeles Lakers", abbreviation="LAL",
        conference="West", division="Pacific", city="Los Angeles",
    ))
    session.add(Team(
        team_id=OPP_TEAM_ID, name="Golden State Warriors", abbreviation="GSW",
        conference="West", division="Pacific", city="San Francisco",
    ))
    session.add(Player(
        player_id=PLAYER_ID, name="LeBron James",
        team_id=TEAM_ID, position="SF", is_active=True,
    ))

    # Create 10 games: 5 home, 5 away, spread across Jan 2024
    games = []
    logs = []
    for i in range(10):
        gid = f"002230{1000 + i}"
        game_date = date(2024, 1, 1 + i * 2)  # Jan 1, 3, 5, ..., 19
        is_home = i % 2 == 0  # even index = home
        games.append(Game(
            game_id=gid, date=game_date, season=SEASON,
            home_team_id=TEAM_ID if is_home else OPP_TEAM_ID,
            away_team_id=OPP_TEAM_ID if is_home else TEAM_ID,
        ))
        # pts: 20, 22, 24, 26, 28, 30, 32, 34, 36, 38
        logs.append(PlayerGameLog(
            game_id=gid, player_id=PLAYER_ID, team_id=TEAM_ID,
            game_date=game_date, season=SEASON,
            min_played=35.0, pts=20 + i * 2, reb=7 + i, ast=5 + i,
            stl=1, blk=1, to_committed=2, fg3m=2, fg3a=5,
            fgm=8, fga=16, ftm=4, fta=5, plus_minus=5, starter=True,
        ))

    session.add_all(games)
    session.add_all(logs)
    await session.commit()
    return session


class TestGetRollingAvg:
    @pytest.mark.asyncio
    async def test_rolling_avg_respects_as_of_date(self, seeded_db):
        """Game logs AFTER as_of_date must NOT be included."""
        session = seeded_db
        # as_of_date = Jan 10 → only games on Jan 1, 3, 5, 7, 9 are included
        # pts: 20, 22, 24, 26, 28 → avg = 24.0
        avg = await get_rolling_avg(session, PLAYER_ID, "pts", 10, date(2024, 1, 10))
        assert avg == pytest.approx(24.0)

        # Now include one more game (Jan 11 → pts=30)
        avg2 = await get_rolling_avg(session, PLAYER_ID, "pts", 10, date(2024, 1, 12))
        assert avg2 == pytest.approx(25.0)
        assert avg2 != avg

    @pytest.mark.asyncio
    async def test_rolling_avg_returns_zero_for_no_games(self, seeded_db):
        """Player with no game logs before as_of_date returns 0.0."""
        avg = await get_rolling_avg(seeded_db, PLAYER_ID, "pts", 5, date(2023, 1, 1))
        assert avg == 0.0

    @pytest.mark.asyncio
    async def test_rolling_avg_window_respected(self, seeded_db):
        """Only the last N games should be averaged."""
        session = seeded_db
        # as_of_date after all games, window=3 → last 3: pts 34, 36, 38
        avg = await get_rolling_avg(session, PLAYER_ID, "pts", 3, date(2024, 2, 1))
        assert avg == pytest.approx(36.0)

    @pytest.mark.asyncio
    async def test_rolling_avg_fewer_games_than_window(self, seeded_db):
        """If fewer games exist than window, average all available."""
        session = seeded_db
        # Only 2 games before Jan 4: pts 20, 22
        avg = await get_rolling_avg(session, PLAYER_ID, "pts", 10, date(2024, 1, 4))
        assert avg == pytest.approx(21.0)


class TestGetRollingAvgSplit:
    @pytest.mark.asyncio
    async def test_home_away_split_correct(self, seeded_db):
        """Home and away averages should differ based on our fixture data."""
        session = seeded_db
        as_of = date(2024, 2, 1)

        home_avg = await get_rolling_avg_split(
            session, PLAYER_ID, "pts", 10, as_of, "home"
        )
        away_avg = await get_rolling_avg_split(
            session, PLAYER_ID, "pts", 10, as_of, "away"
        )

        # Home games (even idx): pts 20, 24, 28, 32, 36 → avg 28.0
        # Away games (odd idx):  pts 22, 26, 30, 34, 38 → avg 30.0
        assert home_avg == pytest.approx(28.0)
        assert away_avg == pytest.approx(30.0)
        assert home_avg != away_avg

    @pytest.mark.asyncio
    async def test_split_respects_as_of_date(self, seeded_db):
        """Split query should also gate on as_of_date."""
        session = seeded_db
        # Before any games
        avg = await get_rolling_avg_split(
            session, PLAYER_ID, "pts", 10, date(2023, 1, 1), "home"
        )
        assert avg == 0.0


class TestComputeTrendSlope:
    def test_increasing_trend(self):
        slope = compute_trend_slope([10.0, 20.0, 30.0, 40.0])
        assert slope == pytest.approx(10.0)

    def test_decreasing_trend(self):
        slope = compute_trend_slope([40.0, 30.0, 20.0, 10.0])
        assert slope == pytest.approx(-10.0)

    def test_flat_trend(self):
        slope = compute_trend_slope([25.0, 25.0, 25.0, 25.0])
        assert slope == pytest.approx(0.0)

    def test_too_few_values(self):
        assert compute_trend_slope([10.0, 20.0]) == 0.0
        assert compute_trend_slope([]) == 0.0


class TestGetStatTrend:
    @pytest.mark.asyncio
    async def test_trend_positive_for_increasing_pts(self, seeded_db):
        """Our fixture data has linearly increasing pts → positive slope."""
        session = seeded_db
        slope = await get_stat_trend(session, PLAYER_ID, "pts", 10, date(2024, 2, 1))
        assert slope > 0

    @pytest.mark.asyncio
    async def test_trend_respects_as_of_date(self, seeded_db):
        """Trend with no data before as_of_date returns 0.0."""
        slope = await get_stat_trend(seeded_db, PLAYER_ID, "pts", 10, date(2023, 1, 1))
        assert slope == 0.0


class TestGetAllRollingFeatures:
    @pytest.mark.asyncio
    async def test_returns_all_expected_keys(self, seeded_db):
        """Feature dict should contain all rolling stat × window combos plus splits and trends."""
        features = await get_all_rolling_features(
            seeded_db, PLAYER_ID, date(2024, 2, 1)
        )

        # Basic rolling: 13 stats × 3 windows = 39
        for stat in [
            "pts", "reb", "ast", "stl", "blk", "to_committed",
            "fg3m", "fg3a", "fgm", "fga", "ftm", "fta", "min_played",
        ]:
            for w in [5, 10, 20]:
                assert f"{stat}_avg_{w}g" in features

        # Home/away splits: 3 stats × 2 locations = 6
        for stat in ["pts", "reb", "ast"]:
            assert f"{stat}_avg_10g_home" in features
            assert f"{stat}_avg_10g_away" in features

        # Trends: 3 stats = 3
        for stat in ["pts", "reb", "ast"]:
            assert f"{stat}_trend_10g" in features

        # Total: 39 + 6 + 3 = 48 keys
        assert len(features) == 48

    @pytest.mark.asyncio
    async def test_all_values_are_float(self, seeded_db):
        """Every value in the feature dict must be a float."""
        features = await get_all_rolling_features(
            seeded_db, PLAYER_ID, date(2024, 2, 1)
        )
        for key, val in features.items():
            assert isinstance(val, float), f"{key} is {type(val)}, expected float"

    @pytest.mark.asyncio
    async def test_no_none_values(self, seeded_db):
        """No None values should appear in the feature dict."""
        features = await get_all_rolling_features(
            seeded_db, PLAYER_ID, date(2024, 2, 1)
        )
        for key, val in features.items():
            assert val is not None, f"{key} is None"
