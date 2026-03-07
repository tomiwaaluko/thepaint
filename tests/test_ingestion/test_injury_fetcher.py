"""Tests for injury fetcher."""
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from chalk.ingestion.injury_fetcher import get_player_status, ingest_injuries


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
