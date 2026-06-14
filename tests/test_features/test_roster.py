"""Tests for roster and injury context features."""
from datetime import date

import pytest

from chalk.db.models import Injury, Player, Team
from chalk.features.roster import get_absent_players

TEAM_ID = 1610612747
OTHER_TEAM_ID = 1610612744


async def _seed_team(session):
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
                team_id=OTHER_TEAM_ID,
                name="Golden State Warriors",
                abbreviation="GSW",
                conference="West",
                division="Pacific",
                city="San Francisco",
            ),
        ]
    )
    await session.flush()


def _player(player_id: int, name: str, team_id: int = TEAM_ID) -> Player:
    return Player(
        player_id=player_id,
        name=name,
        team_id=team_id,
        position="F",
        is_active=True,
    )


def _injury(player_id: int, report_date: date, status: str) -> Injury:
    return Injury(
        player_id=player_id,
        report_date=report_date,
        status=status,
        source="test",
    )


@pytest.mark.asyncio
async def test_get_absent_players_uses_seven_day_lookback(session):
    await _seed_team(session)
    session.add(_player(1, "Injured Teammate"))
    session.add(_injury(1, date(2024, 1, 13), "Out"))
    await session.commit()

    absent = await get_absent_players(session, TEAM_ID, date(2024, 1, 15))

    assert [player.player_id for player in absent] == [1]


@pytest.mark.asyncio
async def test_get_absent_players_ignores_future_reports(session):
    await _seed_team(session)
    session.add(_player(1, "Future Injury"))
    session.add(_injury(1, date(2024, 1, 16), "Out"))
    await session.commit()

    absent = await get_absent_players(session, TEAM_ID, date(2024, 1, 15))

    assert absent == []


@pytest.mark.asyncio
async def test_get_absent_players_uses_latest_report_in_window(session):
    await _seed_team(session)
    session.add(_player(1, "Recovered Player"))
    session.add(_injury(1, date(2024, 1, 10), "Out"))
    session.add(_injury(1, date(2024, 1, 14), "Active"))
    await session.commit()

    absent = await get_absent_players(session, TEAM_ID, date(2024, 1, 15))

    assert absent == []


@pytest.mark.asyncio
async def test_get_absent_players_is_case_insensitive_for_absent_status(session):
    await _seed_team(session)
    session.add(_player(1, "Doubtful Player"))
    session.add(_injury(1, date(2024, 1, 14), "doubtful"))
    await session.commit()

    absent = await get_absent_players(session, TEAM_ID, date(2024, 1, 15))

    assert [player.player_id for player in absent] == [1]


@pytest.mark.asyncio
async def test_get_absent_players_filters_team(session):
    await _seed_team(session)
    session.add(_player(1, "Opponent Injury", team_id=OTHER_TEAM_ID))
    session.add(_injury(1, date(2024, 1, 14), "Out"))
    await session.commit()

    absent = await get_absent_players(session, TEAM_ID, date(2024, 1, 15))

    assert absent == []
