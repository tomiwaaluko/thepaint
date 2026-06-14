"""Tests for Odds API ingestion helpers."""
from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import UniqueConstraint
from sqlalchemy.dialects import postgresql

from chalk.db.models import BettingLine, Game, Player, Team
from chalk.ingestion.odds_fetcher import (
    BETTING_LINE_CONFLICT_COLUMNS,
    _date_window_utc,
    _resolve_event_game_id,
    fetch_game_totals,
    fetch_player_props,
    upsert_betting_lines,
)

LAKERS_ID = 1610612747
WARRIORS_ID = 1610612744
GAME_ID = "0022300001"


class TestBettingLineUniqueness:
    def test_model_unique_constraint_includes_player_id(self):
        constraint = next(
            c
            for c in BettingLine.__table__.constraints
            if isinstance(c, UniqueConstraint)
            and c.name == "uq_betting_game_player_market_book"
        )

        assert [column.name for column in constraint.columns] == [
            "game_id",
            "player_id",
            "market",
            "sportsbook",
        ]
        assert constraint.dialect_options["postgresql"]["nulls_not_distinct"] is True

    @pytest.mark.asyncio
    async def test_upsert_conflict_target_includes_player_id(self):
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.rowcount = 2
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        rows = [
            {
                "game_id": "0022300001",
                "player_id": 1,
                "sportsbook": "draftkings",
                "market": "player_points",
                "line": 24.5,
                "over_odds": -110,
                "under_odds": -110,
                "timestamp": datetime(2024, 1, 15, 12, 0, 0),
            },
            {
                "game_id": "0022300001",
                "player_id": 2,
                "sportsbook": "draftkings",
                "market": "player_points",
                "line": 18.5,
                "over_odds": -105,
                "under_odds": -115,
                "timestamp": datetime(2024, 1, 15, 12, 0, 0),
            },
        ]

        count = await upsert_betting_lines(mock_session, rows)

        stmt = mock_session.execute.call_args.args[0]
        compiled = str(stmt.compile(dialect=postgresql.dialect()))
        assert count == 2
        assert BETTING_LINE_CONFLICT_COLUMNS == [
            "game_id",
            "player_id",
            "market",
            "sportsbook",
        ]
        assert "ON CONFLICT (game_id, player_id, market, sportsbook)" in compiled


@pytest.fixture
async def odds_db(session):
    session.add_all(
        [
            Team(
                team_id=LAKERS_ID,
                name="Los Angeles Lakers",
                abbreviation="LAL",
                conference="West",
                division="Pacific",
                city="Los Angeles",
            ),
            Team(
                team_id=WARRIORS_ID,
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
            player_id=2544,
            name="LeBron James",
            team_id=LAKERS_ID,
            position="SF",
            is_active=True,
        )
    )
    session.add(
        Game(
            game_id=GAME_ID,
            date=date(2024, 1, 15),
            season="2023-24",
            home_team_id=LAKERS_ID,
            away_team_id=WARRIORS_ID,
        )
    )
    await session.commit()
    return session


class TestOddsResolution:
    def test_date_window_uses_eastern_day_boundaries(self):
        start_utc, end_utc = _date_window_utc(date(2024, 1, 15))

        assert start_utc == "2024-01-15T05:00:00Z"
        assert end_utc == "2024-01-16T05:00:00Z"

    @pytest.mark.asyncio
    async def test_resolve_event_game_id_uses_eastern_game_date(self, odds_db):
        event = {
            "id": "odds-event-1",
            "commence_time": "2024-01-16T01:00:00Z",
            "home_team": "Los Angeles Lakers",
            "away_team": "Golden State Warriors",
        }
        team_lookup = {
            "losangeleslakers": LAKERS_ID,
            "goldenstatewarriors": WARRIORS_ID,
        }

        assert await _resolve_event_game_id(odds_db, event, team_lookup) == GAME_ID


class TestFetchPlayerProps:
    @pytest.mark.asyncio
    async def test_fetch_player_props_resolves_game_and_player_rows(self, odds_db):
        events = [
            {
                "id": "odds-event-1",
                "commence_time": "2024-01-16T01:00:00Z",
                "home_team": "Los Angeles Lakers",
                "away_team": "Golden State Warriors",
            }
        ]
        event_odds = {
            "bookmakers": [
                {
                    "key": "draftkings",
                    "markets": [
                        {
                            "key": "player_points",
                            "outcomes": [
                                {
                                    "name": "Over",
                                    "description": "LeBron James",
                                    "price": -110,
                                    "point": 25.5,
                                },
                                {
                                    "name": "Under",
                                    "description": "LeBron James",
                                    "price": -110,
                                    "point": 25.5,
                                },
                            ],
                        }
                    ],
                }
            ]
        }

        with (
            patch(
                "chalk.ingestion.odds_fetcher._fetch_odds",
                new_callable=AsyncMock,
                side_effect=[events, event_odds],
            ),
            patch(
                "chalk.ingestion.odds_fetcher.upsert_betting_lines",
                new_callable=AsyncMock,
                return_value=1,
            ) as mock_upsert,
        ):
            assert await fetch_player_props(odds_db, date(2024, 1, 15)) == 1

        rows = mock_upsert.call_args.args[1]
        assert rows == [
            {
                "game_id": GAME_ID,
                "player_id": 2544,
                "sportsbook": "draftkings",
                "market": "pts",
                "line": 25.5,
                "over_odds": -110,
                "under_odds": -110,
                "timestamp": rows[0]["timestamp"],
            }
        ]


class TestFetchGameTotals:
    @pytest.mark.asyncio
    async def test_fetch_game_totals_resolves_internal_game_id(self, odds_db):
        odds = [
            {
                "id": "odds-event-1",
                "commence_time": "2024-01-16T01:00:00Z",
                "home_team": "Los Angeles Lakers",
                "away_team": "Golden State Warriors",
                "bookmakers": [
                    {
                        "key": "fanduel",
                        "markets": [
                            {
                                "key": "totals",
                                "outcomes": [
                                    {"name": "Over", "price": -105, "point": 229.5},
                                    {"name": "Under", "price": -115, "point": 229.5},
                                ],
                            }
                        ],
                    }
                ],
            }
        ]

        with (
            patch(
                "chalk.ingestion.odds_fetcher._fetch_odds",
                new_callable=AsyncMock,
                return_value=odds,
            ),
            patch(
                "chalk.ingestion.odds_fetcher.upsert_betting_lines",
                new_callable=AsyncMock,
                return_value=1,
            ) as mock_upsert,
        ):
            assert await fetch_game_totals(odds_db, date(2024, 1, 15)) == 1

        rows = mock_upsert.call_args.args[1]
        assert rows[0]["game_id"] == GAME_ID
        assert rows[0]["player_id"] is None
        assert rows[0]["sportsbook"] == "fanduel"
        assert rows[0]["market"] == "game_total"
        assert rows[0]["line"] == 229.5

    @pytest.mark.asyncio
    async def test_fetch_game_totals_skips_incomplete_total(self, odds_db):
        odds = [
            {
                "id": "odds-event-1",
                "commence_time": "2024-01-16T01:00:00Z",
                "home_team": "Los Angeles Lakers",
                "away_team": "Golden State Warriors",
                "bookmakers": [
                    {
                        "key": "fanduel",
                        "markets": [
                            {
                                "key": "totals",
                                "outcomes": [
                                    {"name": "Over", "price": -105, "point": 229.5},
                                ],
                            }
                        ],
                    }
                ],
            }
        ]

        with (
            patch(
                "chalk.ingestion.odds_fetcher._fetch_odds",
                new_callable=AsyncMock,
                return_value=odds,
            ),
            patch(
                "chalk.ingestion.odds_fetcher.upsert_betting_lines",
                new_callable=AsyncMock,
                return_value=0,
            ) as mock_upsert,
        ):
            assert await fetch_game_totals(odds_db, date(2024, 1, 15)) == 0

        assert mock_upsert.call_args.args[1] == []
