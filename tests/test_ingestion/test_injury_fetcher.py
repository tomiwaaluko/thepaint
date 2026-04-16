"""Tests for the ESPN/Gemini injury fetcher."""
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from chalk.db.models import Player, Team
from chalk.ingestion import injury_fetcher
from chalk.ingestion.injury_fetcher import (
    MISSING_GEMINI_KEY_MESSAGE,
    _extract_espn_player_records,
    _extract_with_gemini,
    _filter_valid_player_ids,
    _match_player_id_by_name,
    _parse_gemini_json,
    fetch_and_store_injuries,
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


async def _seed_player(session, player_id: int = 2544, name: str = "LeBron James"):
    session.add(
        Team(
            team_id=1610612747,
            name="Lakers",
            abbreviation="LAL",
            conference="West",
            division="Pacific",
            city="Los Angeles",
        )
    )
    session.add(
        Player(
            player_id=player_id,
            name=name,
            team_id=1610612747,
            position="F",
            is_active=True,
        )
    )
    await session.commit()


class TestEspnParsing:
    def test_extracts_player_records(self):
        records = _extract_espn_player_records(SAMPLE_ESPN_RESPONSE)

        assert records == [
            {
                "full_name": "LeBron James",
                "team": "Los Angeles Lakers",
                "raw_status": "Day-To-Day",
                "raw_notes": "Left ankle soreness",
            }
        ]


class TestGeminiParsing:
    def test_valid_json(self):
        parsed = _parse_gemini_json(
            '{"player_name":"LeBron James","status":"Questionable",'
            '"injury_type":"ankle","return_date":"2026-04-20",'
            '"notes":"Left ankle soreness"}'
        )

        assert parsed == {
            "player_name": "LeBron James",
            "status": "Questionable",
            "injury_type": "ankle",
            "return_date": date(2026, 4, 20),
            "notes": "Left ankle soreness",
        }

    def test_malformed_json_skips_gracefully(self):
        assert _parse_gemini_json("```json nope```") is None

    def test_missing_fields_default_to_nulls(self):
        parsed = _parse_gemini_json('{"player_name":"LeBron James"}')

        assert parsed == {
            "player_name": "LeBron James",
            "status": "Active",
            "injury_type": None,
            "return_date": None,
            "notes": None,
        }

    @pytest.mark.asyncio
    async def test_extract_with_gemini_uses_raw_record_prompt(self):
        client = MagicMock()
        client.models.generate_content.return_value = MagicMock(
            text='{"player_name":"LeBron James","status":"Out"}'
        )
        record = {
            "full_name": "LeBron James",
            "team": "Los Angeles Lakers",
            "raw_status": "Out",
            "raw_notes": "Ankle",
        }

        with patch("chalk.ingestion.injury_fetcher.types") as mock_types:
            mock_types.GenerateContentConfig.return_value = MagicMock()
            parsed = await _extract_with_gemini(client, record)

        assert parsed["player_name"] == "LeBron James"
        assert parsed["status"] == "Out"
        assert client.models.generate_content.call_args.kwargs["model"] == "gemini-2.0-flash"
        prompt = client.models.generate_content.call_args.kwargs["contents"]
        assert "Player: LeBron James" in prompt
        assert "Notes: Ankle" in prompt


class TestPlayerMatching:
    @pytest.mark.asyncio
    async def test_exact_match(self, session):
        await _seed_player(session)
        assert await _match_player_id_by_name(session, "LeBron James") == 2544

    @pytest.mark.asyncio
    async def test_case_insensitive_match(self, session):
        await _seed_player(session)
        assert await _match_player_id_by_name(session, "lebron james") == 2544

    @pytest.mark.asyncio
    async def test_no_match_returns_none(self, session):
        await _seed_player(session)
        assert await _match_player_id_by_name(session, "Unknown Player") is None


class TestGetPlayerStatus:
    @pytest.mark.asyncio
    async def test_returns_active_when_no_record(self):
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        status = await get_player_status(mock_session, player_id=2544, game_date=date(2024, 1, 15))
        assert status == "Active"

    @pytest.mark.asyncio
    async def test_returns_injury_status(self):
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = "Out"
        mock_session.execute = AsyncMock(return_value=mock_result)

        status = await get_player_status(mock_session, player_id=2544, game_date=date(2024, 1, 15))
        assert status == "Out"


class TestResolvePlayerId:
    @pytest.mark.asyncio
    async def test_returns_db_match_without_static_fallback(self):
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
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        injury_fetcher._get_static_player_lookup.cache_clear()
        static_players = [
            {"id": 202710, "full_name": "Jimmy Butler", "is_active": True},
            {"id": 204456, "full_name": "T.J. McConnell", "is_active": True},
            {"id": 1630549, "full_name": "Day'Ron Sharpe", "is_active": True},
            {"id": 1629029, "full_name": "Luka Doncic", "is_active": True},
        ]
        with patch("chalk.ingestion.injury_fetcher.nba_static_players.get_players", return_value=static_players):
            assert await resolve_player_id(mock_session, "Jimmy Butler III") == 202710
            assert await resolve_player_id(mock_session, "T.J. McConnell") == 204456
            assert await resolve_player_id(mock_session, "Day'Ron Sharpe") == 1630549
            assert await resolve_player_id(mock_session, "Luka Doncic") == 1629029
        injury_fetcher._get_static_player_lookup.cache_clear()

    @pytest.mark.asyncio
    async def test_returns_none_when_no_db_or_static_match(self):
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch("chalk.ingestion.injury_fetcher._get_static_player_lookup", return_value={}):
            player_id = await resolve_player_id(mock_session, "Unknown Player")
            assert player_id is None

    @pytest.mark.asyncio
    async def test_falls_back_to_hardcoded_rookie_mapping(self):
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch("chalk.ingestion.injury_fetcher._get_static_player_lookup", return_value={}):
            player_id = await resolve_player_id(mock_session, "LJ Cryer")
            assert player_id == 1641940


class TestFilterValidPlayerIds:
    @pytest.mark.asyncio
    async def test_filters_out_missing_player_ids(self):
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [(100,)]
        mock_session.execute = AsyncMock(return_value=mock_result)

        rows = [
            {"player_id": 100, "report_date": date(2026, 4, 14), "status": "Out", "description": "Knee", "source": "espn"},
            {"player_id": 999, "report_date": date(2026, 4, 14), "status": "Out", "description": "Ankle", "source": "espn"},
        ]
        filtered = await _filter_valid_player_ids(mock_session, rows)
        assert len(filtered) == 1
        assert filtered[0]["player_id"] == 100

    @pytest.mark.asyncio
    async def test_returns_empty_for_empty_input(self):
        mock_session = AsyncMock()
        filtered = await _filter_valid_player_ids(mock_session, [])
        assert filtered == []
        mock_session.execute.assert_not_called()


class TestFetchAndStoreInjuries:
    @pytest.mark.asyncio
    async def test_missing_api_key_returns_early(self, monkeypatch):
        mock_session = AsyncMock()
        monkeypatch.setattr(injury_fetcher.settings, "gemini_api_key", None)

        with patch("chalk.ingestion.injury_fetcher.log.info") as mock_log:
            summary = await fetch_and_store_injuries(mock_session)

        assert summary == {"processed": 0, "inserted": 0, "skipped": 0, "errors": 0}
        mock_log.assert_called_once_with(MISSING_GEMINI_KEY_MESSAGE)
        mock_session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_valid_record_is_inserted(self, monkeypatch):
        mock_session = AsyncMock()
        monkeypatch.setattr(injury_fetcher.settings, "gemini_api_key", "test-key")

        with (
            patch("chalk.ingestion.injury_fetcher.genai") as mock_genai,
            patch("chalk.ingestion.injury_fetcher.types") as mock_types,
            patch("chalk.ingestion.injury_fetcher._fetch_espn_injuries", new_callable=AsyncMock, return_value=SAMPLE_ESPN_RESPONSE),
            patch("chalk.ingestion.injury_fetcher._extract_with_gemini", new_callable=AsyncMock) as mock_extract,
            patch("chalk.ingestion.injury_fetcher._match_player_id_by_name", new_callable=AsyncMock, return_value=2544),
            patch("chalk.ingestion.injury_fetcher.upsert_injuries", new_callable=AsyncMock, return_value=1) as mock_upsert,
            patch("chalk.ingestion.injury_fetcher.asyncio.sleep", new_callable=AsyncMock),
        ):
            mock_client = MagicMock()
            mock_genai.Client.return_value = mock_client
            mock_types.GenerateContentConfig.return_value = MagicMock()
            mock_extract.return_value = {
                "player_name": "LeBron James",
                "status": "Questionable",
                "injury_type": "ankle",
                "return_date": None,
                "notes": "Left ankle soreness",
            }

            summary = await fetch_and_store_injuries(mock_session)

        assert summary == {"processed": 1, "inserted": 1, "skipped": 0, "errors": 0}
        mock_genai.Client.assert_called_once_with(api_key="test-key")
        row = mock_upsert.call_args.args[1][0]
        assert row["player_id"] == 2544
        assert row["status"] == "Questionable"
        assert row["source"] == "ESPN/Gemini"

    @pytest.mark.asyncio
    async def test_malformed_gemini_json_skips_player(self, monkeypatch):
        mock_session = AsyncMock()
        monkeypatch.setattr(injury_fetcher.settings, "gemini_api_key", "test-key")

        with (
            patch("chalk.ingestion.injury_fetcher.genai") as mock_genai,
            patch("chalk.ingestion.injury_fetcher.types") as mock_types,
            patch("chalk.ingestion.injury_fetcher._fetch_espn_injuries", new_callable=AsyncMock, return_value=SAMPLE_ESPN_RESPONSE),
            patch("chalk.ingestion.injury_fetcher._extract_with_gemini", new_callable=AsyncMock, return_value=None),
            patch("chalk.ingestion.injury_fetcher.upsert_injuries", new_callable=AsyncMock, return_value=0),
            patch("chalk.ingestion.injury_fetcher.asyncio.sleep", new_callable=AsyncMock),
        ):
            mock_genai.Client.return_value = MagicMock()
            mock_types.GenerateContentConfig.return_value = MagicMock()
            summary = await fetch_and_store_injuries(mock_session)

        assert summary == {"processed": 1, "inserted": 0, "skipped": 1, "errors": 0}

    @pytest.mark.asyncio
    async def test_ingest_wrapper_returns_inserted_count(self, monkeypatch):
        mock_session = AsyncMock()
        with patch(
            "chalk.ingestion.injury_fetcher.fetch_and_store_injuries",
            new_callable=AsyncMock,
            return_value={"processed": 2, "inserted": 1, "skipped": 1, "errors": 0},
        ):
            assert await ingest_injuries(mock_session) == 1
