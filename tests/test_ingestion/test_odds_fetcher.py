"""Tests for Odds API ingestion helpers."""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import UniqueConstraint
from sqlalchemy.dialects import postgresql

from chalk.db.models import BettingLine
from chalk.ingestion.odds_fetcher import (
    BETTING_LINE_CONFLICT_COLUMNS,
    upsert_betting_lines,
)


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
