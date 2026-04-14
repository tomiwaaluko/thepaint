"""Tests for NBAFetcher ingestion functions."""
import json
from datetime import date
from pathlib import Path
from uuid import uuid4
from unittest.mock import AsyncMock, patch

import pytest

from chalk.exceptions import IngestError
from chalk.ingestion.nba_fetcher import (
    _cache_path,
    _parse_minutes,
    _parse_matchup,
    _fetch_with_backoff,
    ingest_today_scoreboard,
    ingest_player_season,
    ingest_team_season,
)


SAMPLE_PLAYER_LOG = {
    "PlayerGameLog": [
        {
            "Game_ID": "0022301234",
            "GAME_DATE": "Jan 15, 2024",
            "MATCHUP": "LAL vs. GSW",
            "TEAM_ID": 1610612747,
            "MIN": "35:42",
            "PTS": 28,
            "REB": 7,
            "AST": 9,
            "STL": 2,
            "BLK": 1,
            "TOV": 3,
            "FG3M": 4,
            "FG3A": 8,
            "FGM": 10,
            "FGA": 20,
            "FTM": 4,
            "FTA": 5,
            "PLUS_MINUS": 12,
        }
    ]
}

SAMPLE_TEAM_LOG = {
    "LeagueGameLog": [
        {
            "GAME_ID": "0022301234",
            "TEAM_ID": 1610612747,
            "GAME_DATE": "Jan 15, 2024",
            "PTS": 120,
            "AST": 30,
            "TOV": 12,
            "OREB": 10,
            "DREB": 35,
        }
    ]
}


class TestParseMinutes:
    def test_standard_format(self):
        assert _parse_minutes("32:14") == pytest.approx(32.233, abs=0.01)

    def test_just_minutes(self):
        assert _parse_minutes("32") == 32.0

    def test_none(self):
        assert _parse_minutes(None) == 0.0

    def test_empty_string(self):
        assert _parse_minutes("") == 0.0

    def test_integer_input(self):
        assert _parse_minutes(38) == 38.0

    def test_float_input(self):
        assert _parse_minutes(32.5) == 32.5


class TestParseMatchup:
    def test_home_game(self):
        team, opp, is_home = _parse_matchup("LAL vs. GSW")
        assert is_home is True
        assert team == "LAL"
        assert opp == "GSW"

    def test_away_game(self):
        team, opp, is_home = _parse_matchup("LAL @ GSW")
        assert is_home is False
        assert team == "LAL"
        assert opp == "GSW"


class TestCachePath:
    def test_returns_path(self):
        path = _cache_path("PlayerGameLog", {"player_id": 2544, "season": "2023-24"})
        assert path.suffix == ".json"
        assert "PlayerGameLog" in str(path)


class TestFetchWithBackoff:
    @pytest.mark.asyncio
    async def test_raises_ingest_error_after_max_retries(self):
        class FailingEndpoint:
            def __init__(self, **kwargs):
                raise ConnectionError("nba_api is down")

        with (
            patch("chalk.ingestion.nba_fetcher.asyncio.sleep", new=AsyncMock()) as sleep_mock,
            patch("chalk.ingestion.nba_fetcher.random.uniform", return_value=0.0),
            pytest.raises(IngestError, match="Permanent failure"),
        ):
            await _fetch_with_backoff(FailingEndpoint, {"player_id": 2544}, "TestEndpoint")

        delays = [call.args[0] for call in sleep_mock.await_args_list if call.args]
        assert any(delay >= 60 for delay in delays)

    @pytest.mark.asyncio
    async def test_uses_cache(self, monkeypatch):
        """Verify cached response is returned without hitting the endpoint."""
        import chalk.ingestion.nba_fetcher as mod

        tmp_path = Path(".cache/test_nba_fetcher") / str(uuid4())
        tmp_path.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(mod, "CACHE_DIR", tmp_path)

        cache_dir = tmp_path / "TestEndpoint"
        cache_dir.mkdir()
        cache_file = _cache_path.__wrapped__(
            "TestEndpoint", {"key": "val"}
        ) if hasattr(_cache_path, "__wrapped__") else None

        # Manually compute the cache path with monkeypatched dir
        import hashlib, json
        key = hashlib.md5(f"TestEndpoint{sorted({'key': 'val'}.items())}".encode()).hexdigest()
        cache_file = tmp_path / "TestEndpoint" / f"{key}.json"
        cache_file.write_text(json.dumps({"data": "cached"}))

        call_count = 0

        class FakeEndpoint:
            def __init__(self, **kwargs):
                nonlocal call_count
                call_count += 1

            def get_normalized_dict(self):
                return {"data": "live"}

        result = await _fetch_with_backoff(FakeEndpoint, {"key": "val"}, "TestEndpoint")
        assert result == {"data": "cached"}
        assert call_count == 0

    @pytest.mark.asyncio
    async def test_logs_failed_player_ids_for_targeted_retry(self, monkeypatch):
        import chalk.ingestion.nba_fetcher as mod

        tmp_path = Path(".cache/test_nba_fetcher") / str(uuid4())
        tmp_path.mkdir(parents=True, exist_ok=True)
        failed_log = tmp_path / "failed_player_ingest.jsonl"
        monkeypatch.setattr(mod, "FAILED_PLAYER_LOG", failed_log)

        class FailingEndpoint:
            def __init__(self, **kwargs):
                raise TimeoutError("timed out")

        with (
            patch("chalk.ingestion.nba_fetcher.asyncio.sleep", new=AsyncMock()),
            patch("chalk.ingestion.nba_fetcher.random.uniform", return_value=0.0),
            pytest.raises(IngestError, match="Permanent failure"),
        ):
            await _fetch_with_backoff(
                FailingEndpoint,
                {"player_id": 2544, "season": "2023-24"},
                "PlayerGameLog",
            )

        assert failed_log.exists()
        payload = json.loads(failed_log.read_text(encoding="utf-8").strip())
        assert payload["player_id"] == 2544
        assert payload["season"] == "2023-24"
        assert "timed out" in payload["error"]


class TestFetchWithBackoffProxy:
    @pytest.mark.asyncio
    async def test_passes_proxy_when_nba_proxy_url_set(self, monkeypatch, tmp_path):
        """When NBA_PROXY_URL is configured, it should be forwarded to the endpoint."""
        import chalk.ingestion.nba_fetcher as mod

        monkeypatch.setattr(mod, "CACHE_DIR", tmp_path)
        monkeypatch.setattr(mod.settings, "NBA_PROXY_URL", "http://proxy.example.com:8080")

        captured = {}

        class CapturingEndpoint:
            def __init__(self, **kwargs):
                captured.update(kwargs)

            def get_normalized_dict(self):
                return {"data": "live"}

        with (
            patch("chalk.ingestion.nba_fetcher.asyncio.sleep", new=AsyncMock()),
            patch("chalk.ingestion.nba_fetcher.random.uniform", return_value=0.0),
        ):
            result = await _fetch_with_backoff(CapturingEndpoint, {"key": "proxy_val"}, "TestProxy")

        assert captured.get("proxy") == "http://proxy.example.com:8080"
        assert result == {"data": "live"}

    @pytest.mark.asyncio
    async def test_no_proxy_when_nba_proxy_url_empty(self, monkeypatch, tmp_path):
        """When NBA_PROXY_URL is empty, proxy should be None."""
        import chalk.ingestion.nba_fetcher as mod

        monkeypatch.setattr(mod, "CACHE_DIR", tmp_path)
        monkeypatch.setattr(mod.settings, "NBA_PROXY_URL", "")

        captured = {}

        class CapturingEndpoint:
            def __init__(self, **kwargs):
                captured.update(kwargs)

            def get_normalized_dict(self):
                return {"data": "live"}

        with (
            patch("chalk.ingestion.nba_fetcher.asyncio.sleep", new=AsyncMock()),
            patch("chalk.ingestion.nba_fetcher.random.uniform", return_value=0.0),
        ):
            await _fetch_with_backoff(CapturingEndpoint, {"key": "noproxy_val"}, "TestNoProxy")

        assert captured.get("proxy") is None


class TestIngestTodayScoreboard:
    @pytest.mark.asyncio
    async def test_uses_shared_fetch_path(self):
        import chalk.ingestion.nba_fetcher as mod

        mock_session = AsyncMock()
        sample = {
            "GameHeader": [
                {
                    "GAME_ID": "0022301234",
                    "HOME_TEAM_ID": 1610612747,
                    "VISITOR_TEAM_ID": 1610612744,
                }
            ]
        }

        with (
            patch("chalk.ingestion.nba_fetcher._fetch_with_backoff", new=AsyncMock(return_value=sample)) as fetch_mock,
            patch("chalk.ingestion.nba_fetcher.upsert_games", new=AsyncMock()) as upsert_mock,
            patch("chalk.ingestion.nba_fetcher.asyncio.sleep", new=AsyncMock()) as sleep_mock,
            patch("chalk.ingestion.nba_fetcher.random.uniform", return_value=3.0),
        ):
            count = await ingest_today_scoreboard(mock_session, date(2024, 1, 15))

        fetch_mock.assert_awaited_once_with(
            mod.scoreboardv2.ScoreboardV2,
            {"game_date": "01/15/2024", "day_offset": 0, "league_id": "00"},
            endpoint_name="ScoreboardV2",
        )
        upsert_mock.assert_awaited_once()
        sleep_mock.assert_awaited()
        assert count == 1

    @pytest.mark.asyncio
    async def test_returns_zero_if_scoreboard_fetch_fails(self):
        mock_session = AsyncMock()

        with (
            patch(
                "chalk.ingestion.nba_fetcher._fetch_with_backoff",
                new=AsyncMock(side_effect=IngestError("timeout")),
            ),
            patch("chalk.ingestion.nba_fetcher.asyncio.sleep", new=AsyncMock()),
        ):
            count = await ingest_today_scoreboard(mock_session, date(2024, 1, 15))

        assert count == 0


class TestIngestPlayerSeason:
    @pytest.mark.asyncio
    async def test_parses_and_returns_count(self):
        """Mock _fetch_with_backoff, verify correct row count returned."""
        mock_session = AsyncMock()
        mock_result = AsyncMock()
        mock_result.rowcount = 1
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        with (
            patch("chalk.ingestion.nba_fetcher._fetch_with_backoff", return_value=SAMPLE_PLAYER_LOG),
            patch("chalk.ingestion.nba_fetcher.asyncio.sleep", new=AsyncMock()) as sleep_mock,
            patch("chalk.ingestion.nba_fetcher.random.uniform", return_value=4.0),
        ):
            count = await ingest_player_season(mock_session, player_id=2544, season="2023-24")
            assert count == 1
        sleep_mock.assert_awaited()

    @pytest.mark.asyncio
    async def test_idempotent_call(self):
        """Running twice with same data should produce same result."""
        mock_session = AsyncMock()
        mock_result = AsyncMock()
        mock_result.rowcount = 1
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        with (
            patch("chalk.ingestion.nba_fetcher._fetch_with_backoff", return_value=SAMPLE_PLAYER_LOG),
            patch("chalk.ingestion.nba_fetcher.asyncio.sleep", new=AsyncMock()),
        ):
            count1 = await ingest_player_season(mock_session, player_id=2544, season="2023-24")
            count2 = await ingest_player_season(mock_session, player_id=2544, season="2023-24")
            assert count1 == count2


class TestIngestTeamSeason:
    @pytest.mark.asyncio
    async def test_parses_and_returns_count(self):
        mock_session = AsyncMock()
        mock_result = AsyncMock()
        mock_result.rowcount = 1
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        with patch(
            "chalk.ingestion.nba_fetcher._fetch_with_backoff",
            return_value=SAMPLE_TEAM_LOG,
        ):
            count = await ingest_team_season(mock_session, season="2023-24")
            assert count == 1
