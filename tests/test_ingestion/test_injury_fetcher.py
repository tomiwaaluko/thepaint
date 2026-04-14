"""Tests for injury fetcher."""
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from chalk.ingestion import injury_fetcher
from chalk.ingestion.injury_fetcher import get_player_status, ingest_injuries, resolve_player_id


SAMPLE_ESPN_RESPONSE = {
    "injuries": [
        {
            "team": {"displayName": "Los Angeles Lakers"},
            "injuries": [
                {
                    "athlete": {"displayName": "LeBron James"},
                    "status": "Day-To-Day",
                    "details": {"detail": "Left ankle soreness"},
                }
            ],
        }
    ]
}


class TestGetPlayerStatus:
    @pytest.mark.asyncio
    async def test_returns_active_when_no_record(self):
        """Should return 'Active' if no injury records exist."""
        mock_session = AsyncMock()
        # scalar_one_or_none is a sync method on the Result object
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        status = await get_player_status(mock_session, player_id=2544, game_date=date(2024, 1, 15))
        assert status == "Active"

    @pytest.mark.asyncio
    async def test_returns_injury_status(self):
        """Should return the most recent injury status."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = "Out"
        mock_session.execute = AsyncMock(return_value=mock_result)

        status = await get_player_status(mock_session, player_id=2544, game_date=date(2024, 1, 15))
        assert status == "Out"


class TestResolvePlayerId:
    @pytest.mark.asyncio
    async def test_returns_db_match_without_static_fallback(self):
        """When DB match exists, return it directly."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = 2544
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch("chalk.ingestion.injury_fetcher._get_static_player_lookup") as mock_lookup:
            player_id = await resolve_player_id(mock_session, "LeBron James")
            assert player_id == 2544
            mock_lookup.assert_not_called()

    @pytest.mark.asyncio
    async def test_falls_back_to_static_lookup_with_normalized_name(self):
        """Should resolve names with punctuation/suffix/diacritic variants via static lookup."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        injury_fetcher._get_static_player_lookup.cache_clear()
        static_players = [
            {"id": 202710, "full_name": "Jimmy Butler", "is_active": True},
            {"id": 204456, "full_name": "T.J. McConnell", "is_active": True},
            {"id": 1630549, "full_name": "Day'Ron Sharpe", "is_active": True},
            {"id": 1629029, "full_name": "Luka Dončić", "is_active": True},
        ]
        with patch("chalk.ingestion.injury_fetcher.nba_static_players.get_players", return_value=static_players) as mock_get_players:
            assert await resolve_player_id(mock_session, "Jimmy Butler III") == 202710
            assert await resolve_player_id(mock_session, "T.J. McConnell") == 204456
            assert await resolve_player_id(mock_session, "Day'Ron Sharpe") == 1630549
            assert await resolve_player_id(mock_session, "Luka Doncic") == 1629029
            mock_get_players.assert_called_once()
        injury_fetcher._get_static_player_lookup.cache_clear()

    @pytest.mark.asyncio
    async def test_returns_none_when_no_db_or_static_match(self):
        """Should return None when both DB and static lookup fail."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch("chalk.ingestion.injury_fetcher._get_static_player_lookup", return_value={}):
            player_id = await resolve_player_id(mock_session, "Unknown Player")
            assert player_id is None

    @pytest.mark.asyncio
    async def test_falls_back_to_hardcoded_rookie_mapping(self):
        """Should resolve rookie names from hardcoded IDs when DB/static lookup miss."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch("chalk.ingestion.injury_fetcher._get_static_player_lookup", return_value={}):
            player_id = await resolve_player_id(mock_session, "LJ Cryer")
            assert player_id == 1641940


class TestIngestInjuries:
    @pytest.mark.asyncio
    async def test_ingest_skips_unknown_players(self):
        """Players not in DB should be skipped."""
        mock_session = AsyncMock()

        with (
            patch("chalk.ingestion.injury_fetcher.httpx.AsyncClient") as mock_client_cls,
            patch("chalk.ingestion.injury_fetcher.resolve_player_id", new_callable=AsyncMock, return_value=None),
        ):
            mock_client = AsyncMock()
            mock_resp = MagicMock()
            mock_resp.json.return_value = SAMPLE_ESPN_RESPONSE
            mock_resp.raise_for_status.return_value = None
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            count = await ingest_injuries(mock_session)
            assert count == 0
