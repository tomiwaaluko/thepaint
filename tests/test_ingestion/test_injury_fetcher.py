"""Tests for injury fetcher."""
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from chalk.ingestion.injury_fetcher import (
    _canonical_player_name,
    get_player_status,
    ingest_injuries,
    resolve_player_id,
)


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


def _empty_lookup():
    return {
        "exact": {},
        "canonical": {},
        "canonical_names": tuple(),
        "player_ids": set(),
    }


class TestNameNormalization:
    def test_strips_suffixes_and_punctuation(self):
        assert _canonical_player_name("Jabari Smith Jr.") == "jabari smith"
        assert _canonical_player_name("P.J. Washington") == "p j washington"
        assert _canonical_player_name("Luka Dončić") == "luka doncic"


class TestResolvePlayerId:
    @pytest.mark.asyncio
    async def test_normalized_fallback_match(self):
        cache = {
            "exact": {},
            "canonical": {"c j mccollum": 101},
            "canonical_names": ("c j mccollum",),
            "player_ids": {101},
        }
        player_id = await resolve_player_id(
            AsyncMock(),
            "CJ McCollum",
            lookup_cache=cache,
            log_missing=False,
        )
        assert player_id == 101

    @pytest.mark.asyncio
    async def test_fuzzy_match(self):
        cache = {
            "exact": {},
            "canonical": {"nikola vucevic": 202},
            "canonical_names": ("nikola vucevic",),
            "player_ids": {202},
        }
        player_id = await resolve_player_id(
            AsyncMock(),
            "Nikola Vucevich",
            lookup_cache=cache,
            log_missing=False,
        )
        assert player_id == 202


class TestGetPlayerStatus:
    @pytest.mark.asyncio
    async def test_returns_active_when_no_record(self):
        """Should return 'Active' if no injury records exist."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        status = await get_player_status(
            mock_session,
            player_id=2544,
            game_date=date(2024, 1, 15),
        )
        assert status == "Active"

    @pytest.mark.asyncio
    async def test_returns_injury_status(self):
        """Should return the most recent injury status."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = "Out"
        mock_session.execute = AsyncMock(return_value=mock_result)

        status = await get_player_status(
            mock_session,
            player_id=2544,
            game_date=date(2024, 1, 15),
        )
        assert status == "Out"


class TestIngestInjuries:
    @pytest.mark.asyncio
    async def test_ingest_skips_unknown_players(self):
        """Players not resolvable via DB or static fallback should be skipped."""
        mock_session = AsyncMock()

        with (
            patch("chalk.ingestion.injury_fetcher.httpx.AsyncClient") as mock_client_cls,
            patch("chalk.ingestion.injury_fetcher._build_player_lookup", new=AsyncMock(return_value=_empty_lookup())),
            patch("chalk.ingestion.injury_fetcher.resolve_player_id", new=AsyncMock(return_value=None)),
            patch("chalk.ingestion.injury_fetcher._resolve_player_id_from_static", return_value=None),
            patch("chalk.ingestion.injury_fetcher.upsert_injuries", new=AsyncMock(return_value=0)),
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

    @pytest.mark.asyncio
    async def test_ingest_uses_static_fallback_when_db_lookup_fails(self):
        mock_session = AsyncMock()
        upsert_mock = AsyncMock(return_value=1)

        with (
            patch("chalk.ingestion.injury_fetcher.httpx.AsyncClient") as mock_client_cls,
            patch("chalk.ingestion.injury_fetcher._build_player_lookup", new=AsyncMock(return_value=_empty_lookup())),
            patch("chalk.ingestion.injury_fetcher.resolve_player_id", new=AsyncMock(return_value=None)),
            patch("chalk.ingestion.injury_fetcher._resolve_player_id_from_static", return_value=2544),
            patch("chalk.ingestion.injury_fetcher._ensure_player_exists", new=AsyncMock(return_value=True)),
            patch("chalk.ingestion.injury_fetcher.upsert_injuries", new=upsert_mock),
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

        assert count == 1
        rows = upsert_mock.await_args.args[1]
        assert len(rows) == 1
        assert rows[0]["player_id"] == 2544
