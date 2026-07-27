"""Tests for NBAFetcher ingestion functions."""
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from chalk.exceptions import IngestError
from chalk.ingestion.nba_fetcher import (
    _build_rows_from_espn_boxscore,
    _build_rows_from_live_boxscore,
    _cache_path,
    _canonicalize_game_rows,
    _espn_event_is_playoffs,
    _fetch_with_backoff,
    _is_nba_game_id,
    _parse_espn_scoreboard_events,
    _parse_live_minutes,
    _parse_minutes,
    _parse_matchup,
    _reconcile_espn_scoreboard_games,
    ingest_game_boxscores_espn,
    ingest_player_season,
    ingest_team_season,
    ingest_today_scoreboard,
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


class TestCanonicalGameIds:
    @pytest.mark.asyncio
    async def test_maps_duplicate_matchup_to_existing_game_id(self):
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = "401859967"
        mock_session.execute = AsyncMock(return_value=mock_result)

        rows, game_id_map = await _canonicalize_game_rows(
            mock_session,
            [
                {
                    "game_id": "0042500405",
                    "date": date(2026, 6, 13),
                    "season": "2025-26",
                    "home_team_id": 1610612759,
                    "away_team_id": 1610612752,
                    "is_playoffs": True,
                }
            ],
        )

        assert rows[0]["game_id"] == "401859967"
        assert game_id_map == {"0042500405": "401859967"}

    @pytest.mark.asyncio
    async def test_collapses_duplicate_matchups_in_same_batch(self):
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        rows, game_id_map = await _canonicalize_game_rows(
            mock_session,
            [
                {
                    "game_id": "0042500405",
                    "date": date(2026, 6, 13),
                    "season": "2025-26",
                    "home_team_id": 1610612759,
                    "away_team_id": 1610612752,
                    "is_playoffs": True,
                },
                {
                    "game_id": "401859967",
                    "date": date(2026, 6, 13),
                    "season": "2025-26",
                    "home_team_id": 1610612759,
                    "away_team_id": 1610612752,
                    "is_playoffs": True,
                },
            ],
        )

        assert len(rows) == 1
        assert rows[0]["game_id"] == "0042500405"
        assert game_id_map == {
            "0042500405": "0042500405",
            "401859967": "0042500405",
        }


class TestIngestTodayScoreboard:
    @pytest.mark.asyncio
    async def test_invalid_scoreboard_headers_use_fallback(self):
        mock_board = MagicMock()
        mock_board.get_normalized_dict.return_value = {
            "GameHeader": [
                {
                    "GAME_ID": "0042500405",
                    "HOME_TEAM_ID": None,
                    "VISITOR_TEAM_ID": 1610612752,
                }
            ]
        }

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        with (
            patch("chalk.ingestion.nba_fetcher.scoreboardv2.ScoreboardV2", return_value=mock_board),
            patch("chalk.ingestion.nba_fetcher._fetch_scoreboard_cdn", AsyncMock(return_value=[])),
            patch(
                "chalk.ingestion.nba_fetcher._fetch_scoreboard_espn",
                AsyncMock(
                    return_value=[
                        {
                            "ESPN_EVENT_ID": "401859967",
                            "GAME_ID": "401859967",
                            "HOME_TEAM_ID": 1610612759,
                            "VISITOR_TEAM_ID": 1610612752,
                            "IS_PLAYOFFS": True,
                            "STATUS": "Final",
                        }
                    ]
                ),
            ),
            patch("chalk.ingestion.nba_fetcher.upsert_games", AsyncMock()) as upsert_games,
        ):
            count = await ingest_today_scoreboard(mock_session, date(2026, 6, 13))

        assert count == 1
        upsert_games.assert_awaited_once()
        inserted_rows = upsert_games.await_args.args[1]
        assert inserted_rows[0]["game_id"] == "401859967"
        assert inserted_rows[0]["home_team_id"] == 1610612759


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


class TestIngestGameBoxscoresEspn:
    """Tests for the public ingest_game_boxscores_espn entrypoint."""

    @pytest.mark.asyncio
    async def test_ingests_rows_for_reconciled_nba_game(self):
        """ESPN boxscore is fetched and rows are upserted for an NBA-format game ID."""
        mock_game = MagicMock()
        mock_game.game_id = "0022500916"
        mock_game.date = date(2026, 4, 14)
        mock_game.season = "2025-26"
        mock_game.home_team_id = 1610612747
        mock_game.away_team_id = 1610612744

        espn_scoreboard = [
            {
                "ESPN_EVENT_ID": "401585601",
                "GAME_ID": "401585601",
                "HOME_TEAM_ID": 1610612747,
                "VISITOR_TEAM_ID": 1610612744,
                "IS_PLAYOFFS": False,
                "STATUS": "Final",
            }
        ]
        espn_boxscore = {
            "boxscore": {
                "teams": [],
                "players": [],
            }
        }

        mock_session = AsyncMock()
        # _player_lookup_by_name query
        mock_player_result = MagicMock()
        mock_player_result.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_player_result)

        mock_fetch_boxscore = AsyncMock(return_value=espn_boxscore)

        with (
            patch(
                "chalk.ingestion.nba_fetcher._fetch_scoreboard_espn",
                AsyncMock(return_value=espn_scoreboard),
            ),
            patch(
                "chalk.ingestion.nba_fetcher._fetch_boxscore_espn",
                mock_fetch_boxscore,
            ),
            patch(
                "chalk.ingestion.nba_fetcher.upsert_team_game_logs",
                AsyncMock(return_value=0),
            ),
            patch(
                "chalk.ingestion.nba_fetcher.upsert_player_game_logs",
                AsyncMock(return_value=0),
            ),
        ):
            team_count, player_count = await ingest_game_boxscores_espn(
                mock_session, [mock_game]
            )
        assert team_count == 0
        assert player_count == 0
        # Verify that the ESPN event ID (not the NBA ID) was used for the boxscore fetch
        mock_fetch_boxscore.assert_awaited_once_with("401585601")

    @pytest.mark.asyncio
    async def test_skips_nba_game_with_no_espn_event_mapping(self):
        """Logs warning and skips game when ESPN event map has no match."""
        mock_game = MagicMock()
        mock_game.game_id = "0022500916"
        mock_game.date = date(2026, 4, 14)
        mock_game.season = "2025-26"
        mock_game.home_team_id = 1610612747
        mock_game.away_team_id = 1610612744

        mock_session = AsyncMock()
        mock_player_result = MagicMock()
        mock_player_result.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_player_result)

        upsert_team = AsyncMock(return_value=0)
        upsert_player_logs = AsyncMock(return_value=0)

        with (
            patch(
                "chalk.ingestion.nba_fetcher._fetch_scoreboard_espn",
                AsyncMock(return_value=[]),  # empty → event_map is empty
            ),
            patch("chalk.ingestion.nba_fetcher.upsert_team_game_logs", upsert_team),
            patch("chalk.ingestion.nba_fetcher.upsert_player_game_logs", upsert_player_logs),
        ):
            team_count, player_count = await ingest_game_boxscores_espn(
                mock_session, [mock_game]
            )

        # Nothing to upsert — the game was skipped
        upsert_team.assert_called_once_with(mock_session, [])
        upsert_player_logs.assert_called_once_with(mock_session, [])
        assert team_count == 0
        assert player_count == 0

    @pytest.mark.asyncio
    async def test_uses_espn_event_id_directly_for_espn_format_game(self):
        """When game_id is already an ESPN event ID, use it directly for the fetch."""
        mock_game = MagicMock()
        mock_game.game_id = "401585601"  # ESPN event ID — not a canonical NBA ID
        mock_game.date = date(2026, 4, 14)
        mock_game.season = "2025-26"
        mock_game.home_team_id = 1610612747
        mock_game.away_team_id = 1610612744

        espn_boxscore = {"boxscore": {"teams": [], "players": []}}

        mock_session = AsyncMock()
        mock_player_result = MagicMock()
        mock_player_result.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_player_result)

        mock_fetch_boxscore = AsyncMock(return_value=espn_boxscore)

        with (
            patch("chalk.ingestion.nba_fetcher._fetch_boxscore_espn", mock_fetch_boxscore),
            patch("chalk.ingestion.nba_fetcher.upsert_team_game_logs", AsyncMock(return_value=0)),
            patch("chalk.ingestion.nba_fetcher.upsert_player_game_logs", AsyncMock(return_value=0)),
        ):
            await ingest_game_boxscores_espn(mock_session, [mock_game])

        # ESPN event ID used directly — no reconciliation step needed
        mock_fetch_boxscore.assert_awaited_once_with("401585601")

    @pytest.mark.asyncio
    async def test_continues_on_boxscore_fetch_error(self):
        """Logs warning and returns zero counts when boxscore fetch raises."""
        mock_game = MagicMock()
        mock_game.game_id = "401585601"
        mock_game.date = date(2026, 4, 14)
        mock_game.season = "2025-26"
        mock_game.home_team_id = 1610612747
        mock_game.away_team_id = 1610612744

        mock_session = AsyncMock()
        mock_player_result = MagicMock()
        mock_player_result.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_player_result)

        with (
            patch(
                "chalk.ingestion.nba_fetcher._fetch_boxscore_espn",
                AsyncMock(side_effect=ConnectionError("API timeout")),
            ),
            patch("chalk.ingestion.nba_fetcher.upsert_team_game_logs", AsyncMock(return_value=0)),
            patch("chalk.ingestion.nba_fetcher.upsert_player_game_logs", AsyncMock(return_value=0)),
        ):
            team_count, player_count = await ingest_game_boxscores_espn(mock_session, [mock_game])

        # Exception is caught and logged — function should not propagate it
        assert team_count == 0
        assert player_count == 0


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
        import hashlib
        import json
        key = hashlib.md5(f"TestEndpoint{sorted({'key': 'val'}.items())}".encode(), usedforsecurity=False).hexdigest()
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
