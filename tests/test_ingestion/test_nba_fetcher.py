"""Tests for NBAFetcher ingestion functions."""
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from chalk.exceptions import IngestError
from chalk.ingestion.nba_fetcher import (
    _build_rows_from_espn_boxscore,
    _build_rows_from_live_boxscore,
    _cache_path,
    _espn_event_is_playoffs,
    _is_nba_game_id,
    _parse_espn_scoreboard_events,
    _parse_live_minutes,
    _parse_minutes,
    _parse_matchup,
    _fetch_with_backoff,
    _reconcile_espn_scoreboard_games,
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


class TestNbaGameId:
    def test_nba_game_id(self):
        assert _is_nba_game_id("0022500916") is True
        assert _is_nba_game_id("0042300401") is True

    def test_espn_event_id(self):
        assert _is_nba_game_id("401585601") is False


class TestEspnPlayoffsDetection:
    def test_regular_season(self):
        event = {"season": {"type": 2}, "competitions": [{"season": {"type": 2}}]}
        assert _espn_event_is_playoffs(event) is False

    def test_postseason_type(self):
        event = {"season": {"type": 3}, "competitions": [{}]}
        assert _espn_event_is_playoffs(event) is True

    def test_postseason_slug(self):
        event = {"season": {"slug": "post-season"}, "competitions": [{}]}
        assert _espn_event_is_playoffs(event) is True


class TestEspnScoreboardParse:
    def test_parse_events(self):
        payload = {
            "events": [
                {
                    "id": "401585601",
                    "season": {"type": 2},
                    "competitions": [
                        {
                            "competitors": [
                                {
                                    "homeAway": "home",
                                    "team": {"abbreviation": "LAL"},
                                },
                                {
                                    "homeAway": "away",
                                    "team": {"abbreviation": "GS"},
                                },
                            ],
                            "status": {"type": {"description": "Final"}},
                        }
                    ],
                }
            ]
        }
        games = _parse_espn_scoreboard_events(payload)
        assert len(games) == 1
        assert games[0]["ESPN_EVENT_ID"] == "401585601"
        assert games[0]["IS_PLAYOFFS"] is False
        assert games[0]["HOME_TEAM_ID"] == 1610612747
        assert games[0]["VISITOR_TEAM_ID"] == 1610612744


class TestReconcileEspnGameIds:
    @pytest.mark.asyncio
    async def test_prefers_existing_nba_game_id(self):
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = [("0022500916",)]
        mock_session.execute = AsyncMock(return_value=mock_result)

        espn_games = [
            {
                "ESPN_EVENT_ID": "401585601",
                "GAME_ID": "401585601",
                "HOME_TEAM_ID": 1610612747,
                "VISITOR_TEAM_ID": 1610612744,
                "IS_PLAYOFFS": False,
                "STATUS": "Final",
            }
        ]
        reconciled = await _reconcile_espn_scoreboard_games(
            mock_session,
            date(2026, 4, 14),
            espn_games,
        )
        assert reconciled[0]["GAME_ID"] == "0022500916"


class TestEspnBoxscoreRows:
    def test_builds_player_row(self):
        lookup = {(1610612747, "lebronjames"): 2544}
        payload = {
            "boxscore": {
                "teams": [
                    {
                        "team": {"abbreviation": "LAL"},
                        "statistics": [
                            {"name": "points", "displayValue": "110"},
                            {"name": "assists", "displayValue": "25"},
                            {"name": "rebounds", "displayValue": "40"},
                            {"name": "turnovers", "displayValue": "10"},
                            {"name": "fieldGoalsMade", "displayValue": "40"},
                            {"name": "fieldGoalsAttempted", "displayValue": "85"},
                            {"name": "threePointFieldGoalsAttempted", "displayValue": "30"},
                        ],
                    }
                ],
                "players": [
                    {
                        "team": {"abbreviation": "LAL"},
                        "statistics": [
                            {
                                "keys": ["minutes", "points", "rebounds", "assists", "steals", "blocks", "turnovers",
                                         "fieldGoalsMade-fieldGoalsAttempted",
                                         "threePointFieldGoalsMade-threePointFieldGoalsAttempted",
                                         "freeThrowsMade-freeThrowsAttempted", "plusMinus"],
                                "athletes": [
                                    {
                                        "athlete": {"displayName": "LeBron James"},
                                        "stats": ["32:14", "28", "7", "8", "1", "2", "3", "10-20", "4-8", "4-5", "+12"],
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
        }
        team_rows, player_rows = _build_rows_from_espn_boxscore(
            payload,
            "0022500916",
            date(2026, 4, 14),
            "2025-26",
            lookup,
        )
        assert len(team_rows) == 1
        assert len(player_rows) == 1
        assert player_rows[0]["game_id"] == "0022500916"
        assert player_rows[0]["player_id"] == 2544
        assert player_rows[0]["pts"] == 28


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


class TestParseLiveMinutes:
    def test_iso_duration(self):
        assert _parse_live_minutes("PT32M14.00S") == pytest.approx(32.233, abs=0.01)

    def test_standard_format(self):
        assert _parse_live_minutes("12:30") == pytest.approx(12.5)


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


class TestLiveBoxscoreRows:
    def test_builds_team_and_player_rows(self):
        payload = {
            "game": {
                "gameId": "0022500001",
                "homeTeam": {
                    "teamId": 1610612747,
                    "score": 110,
                    "statistics": {
                        "assists": 25,
                        "turnovers": 12,
                        "reboundsOffensive": 9,
                        "reboundsDefensive": 31,
                        "threePointersAttempted": 35,
                        "fieldGoalsAttempted": 90,
                    },
                    "players": [
                        {
                            "personId": 2544,
                            "starter": "1",
                            "statistics": {
                                "minutes": "PT32M14.00S",
                                "points": 28,
                                "reboundsTotal": 7,
                                "assists": 8,
                                "steals": 1,
                                "blocks": 2,
                                "turnovers": 3,
                                "threePointersMade": 4,
                                "threePointersAttempted": 8,
                                "fieldGoalsMade": 10,
                                "fieldGoalsAttempted": 20,
                                "freeThrowsMade": 4,
                                "freeThrowsAttempted": 5,
                                "plusMinusPoints": "+12",
                            },
                        },
                        {
                            "personId": 9999,
                            "statistics": {"minutes": "PT0M00.00S", "points": 0},
                        },
                    ],
                },
                "awayTeam": {
                    "teamId": 1610612744,
                    "score": 105,
                    "statistics": {},
                    "players": [],
                },
            }
        }

        team_rows, player_rows = _build_rows_from_live_boxscore(
            payload,
            date(2026, 4, 14),
            "2025-26",
        )

        assert len(team_rows) == 2
        assert team_rows[0]["fg3a_rate"] == pytest.approx(35 / 90)
        assert len(player_rows) == 1
        assert player_rows[0]["player_id"] == 2544
        assert player_rows[0]["min_played"] == pytest.approx(32.233, abs=0.01)
        assert player_rows[0]["plus_minus"] == 12


class TestFetchWithBackoff:
    @pytest.mark.asyncio
    async def test_raises_ingest_error_after_max_retries(self):
        class FailingEndpoint:
            def __init__(self, **kwargs):
                raise ConnectionError("nba_api is down")

        with pytest.raises(IngestError, match="Permanent failure"):
            await _fetch_with_backoff(
                FailingEndpoint,
                {"player_id": 2544},
                "TestEndpoint",
            )

    @pytest.mark.asyncio
    async def test_uses_cache(self, tmp_path, monkeypatch):
        """Verify cached response is returned without hitting the endpoint."""
        import chalk.ingestion.nba_fetcher as mod
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


class TestIngestPlayerSeason:
    @pytest.mark.asyncio
    async def test_parses_and_returns_count(self):
        """Mock _fetch_with_backoff, verify correct row count returned."""
        mock_session = AsyncMock()
        mock_result = AsyncMock()
        mock_result.rowcount = 1
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        with patch(
            "chalk.ingestion.nba_fetcher._fetch_with_backoff",
            return_value=SAMPLE_PLAYER_LOG,
        ):
            count = await ingest_player_season(mock_session, player_id=2544, season="2023-24")
            assert count == 1

    @pytest.mark.asyncio
    async def test_idempotent_call(self):
        """Running twice with same data should produce same result."""
        mock_session = AsyncMock()
        mock_result = AsyncMock()
        mock_result.rowcount = 1
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        with patch(
            "chalk.ingestion.nba_fetcher._fetch_with_backoff",
            return_value=SAMPLE_PLAYER_LOG,
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
