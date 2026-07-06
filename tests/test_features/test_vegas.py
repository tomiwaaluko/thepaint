"""Tests for Vegas line features."""
from datetime import date, datetime

import pytest

from chalk.db.models import BettingLine, Game, Player, Team
from chalk.features.vegas import get_game_total_line, get_player_prop_line, get_vegas_features

GAME_ID = "0022300001"
PLAYER_ID = 2544
TEAM_ID = 1610612747
OPP_TEAM_ID = 1610612744


@pytest.fixture
async def vegas_db(session):
    session.add_all(
        [
            Team(
                team_id=TEAM_ID,
                name="Los Angeles Lakers",
                abbreviation="LAL",
                conference="West",
                division="Pacific",
                city="Los Angeles",
            ),
            Team(
                team_id=OPP_TEAM_ID,
                name="Golden State Warriors",
                abbreviation="GSW",
                conference="West",
                division="Pacific",
                city="San Francisco",
            ),
        ]
    )
    session.add(
        Player(
            player_id=PLAYER_ID,
            name="LeBron James",
            team_id=TEAM_ID,
            position="SF",
            is_active=True,
        )
    )
    session.add(
        Game(
            game_id=GAME_ID,
            date=date(2024, 1, 15),
            season="2023-24",
            home_team_id=TEAM_ID,
            away_team_id=OPP_TEAM_ID,
        )
    )
    session.add_all(
        [
            BettingLine(
                game_id=GAME_ID,
                player_id=PLAYER_ID,
                sportsbook="draftkings",
                market="pts",
                line=25.5,
                over_odds=-110,
                under_odds=-110,
                timestamp=datetime(2024, 1, 15, 10, 0, 0),
            ),
            BettingLine(
                game_id=GAME_ID,
                player_id=PLAYER_ID,
                sportsbook="fanduel",
                market="player_points",
                line=26.5,
                over_odds=-105,
                under_odds=-115,
                timestamp=datetime(2024, 1, 15, 11, 0, 0),
            ),
            BettingLine(
                game_id=GAME_ID,
                player_id=None,
                sportsbook="draftkings",
                market="game_total",
                line=229.5,
                over_odds=-110,
                under_odds=-110,
                timestamp=datetime(2024, 1, 15, 10, 0, 0),
            ),
        ]
    )
    await session.commit()
    return session


@pytest.mark.asyncio
async def test_get_player_prop_line_averages_stat_and_market_key(vegas_db):
    line = await get_player_prop_line(vegas_db, PLAYER_ID, GAME_ID, "pts", date(2024, 1, 15))

    assert line == pytest.approx(26.0)


@pytest.mark.asyncio
async def test_get_player_prop_line_respects_as_of_cutoff(vegas_db):
    line = await get_player_prop_line(
        vegas_db,
        PLAYER_ID,
        GAME_ID,
        "pts",
        datetime(2024, 1, 15, 10, 30, 0),
    )

    assert line == pytest.approx(25.5)


@pytest.mark.asyncio
async def test_get_game_total_line(vegas_db):
    line = await get_game_total_line(vegas_db, GAME_ID, date(2024, 1, 15))

    assert line == pytest.approx(229.5)


@pytest.mark.asyncio
async def test_get_vegas_features_returns_sparse_defaults(vegas_db):
    features = await get_vegas_features(vegas_db, PLAYER_ID, GAME_ID, date(2024, 1, 15))

    assert features["vegas_pts_line"] == pytest.approx(26.0)
    assert features["vegas_reb_line"] == 0.0
    assert features["vegas_game_total"] == pytest.approx(229.5)
    assert features["vegas_has_line"] == 1.0
