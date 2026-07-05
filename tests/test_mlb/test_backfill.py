"""Tests for the MLB historical backfill runner (mocked ingest — no network)."""
import json
from datetime import date

import pytest

import scripts.mlb_backfill as backfill_mod
from chalk.exceptions import IngestError
from chalk.mlb.models import MlbGame, MlbTeam
from scripts.mlb_backfill import (
    backfill_season,
    load_progress,
    save_progress,
    season_windows,
)


class TestSeasonWindows:
    def test_covers_february_through_november(self):
        windows = season_windows(2024)
        assert windows[0][0] == date(2024, 2, 15)
        assert windows[-1][1] == date(2024, 11, 30)

    def test_windows_are_contiguous_and_non_overlapping(self):
        windows = season_windows(2024)
        for (_, prev_end), (next_start, _) in zip(windows, windows[1:]):
            assert (next_start - prev_end).days == 1


class TestProgressFile:
    def test_round_trip(self, tmp_path, monkeypatch):
        monkeypatch.setattr(backfill_mod, "PROGRESS_FILE", tmp_path / "progress.json")
        save_progress({745123, 745124})
        assert load_progress() == {745123, 745124}

    def test_missing_file_is_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr(backfill_mod, "PROGRESS_FILE", tmp_path / "nope.json")
        assert load_progress() == set()


@pytest.fixture
def seeded_games(session):
    async def _seed():
        session.add(MlbTeam(
            team_id=147, name="New York Yankees", abbreviation="NYY",
            league="American League", division="American League East", city="Bronx",
        ))
        for pk, day in [(745123, 1), (745124, 2), (745125, 3)]:
            session.add(MlbGame(
                game_pk=pk, date=date(2024, 6, day), season="2024", game_type="R",
                home_team_id=147, away_team_id=147, status="Final",
            ))
        await session.commit()
    return _seed


@pytest.fixture
def quiet_backfill(tmp_path, monkeypatch):
    """No sleeps, no real ingest of teams/schedule, progress in tmp."""
    monkeypatch.setattr(backfill_mod, "PROGRESS_FILE", tmp_path / "progress.json")
    monkeypatch.setattr(backfill_mod, "INTER_REQUEST_DELAY", 0)

    async def _noop_teams(session, season):
        return 0

    async def _noop_schedule(session, start, end, use_cache=True):
        return 0

    monkeypatch.setattr(backfill_mod, "ingest_mlb_teams", _noop_teams)
    monkeypatch.setattr(backfill_mod, "ingest_mlb_schedule", _noop_schedule)


class TestBackfillSeason:
    async def test_resume_skips_completed_games(
        self, session, seeded_games, quiet_backfill, monkeypatch
    ):
        await seeded_games()
        ingested = []

        async def _fake_boxscore(sess, game_pk):
            ingested.append(game_pk)
            return (2, 2)

        monkeypatch.setattr(backfill_mod, "ingest_mlb_boxscore", _fake_boxscore)
        completed = {745123}
        done, skipped = await backfill_season(session, 2024, completed)

        assert ingested == [745124, 745125]
        assert completed == {745123, 745124, 745125}
        assert done == 2 and skipped == 0

    async def test_ingest_error_skips_game_and_continues(
        self, session, seeded_games, quiet_backfill, monkeypatch
    ):
        await seeded_games()

        async def _flaky_boxscore(sess, game_pk):
            if game_pk == 745124:
                raise IngestError("boxscore fetch failed")
            return (2, 2)

        monkeypatch.setattr(backfill_mod, "ingest_mlb_boxscore", _flaky_boxscore)
        completed: set[int] = set()
        done, skipped = await backfill_season(session, 2024, completed)

        assert done == 2 and skipped == 1
        assert 745124 not in completed
        assert completed == {745123, 745125}

    async def test_db_error_skips_game_and_continues(
        self, session, seeded_games, quiet_backfill, monkeypatch
    ):
        """DB-level failures are per-game skips too, with a rollback."""
        from sqlalchemy.exc import OperationalError

        await seeded_games()

        async def _db_boom(sess, game_pk):
            if game_pk == 745124:
                raise OperationalError("stmt", {}, Exception("db down"))
            return (2, 2)

        monkeypatch.setattr(backfill_mod, "ingest_mlb_boxscore", _db_boom)
        completed: set[int] = set()
        done, skipped = await backfill_season(session, 2024, completed)
        assert done == 2 and skipped == 1
        assert completed == {745123, 745125}

    async def test_progress_flushed_incrementally(
        self, session, seeded_games, quiet_backfill, monkeypatch, tmp_path
    ):
        """With flush-every-1, progress hits disk mid-run, not just at the end."""
        await seeded_games()
        monkeypatch.setattr(backfill_mod, "PROGRESS_FLUSH_EVERY", 1)
        mid_run_snapshots = []

        async def _fake_boxscore(sess, game_pk):
            progress = tmp_path / "progress.json"
            if progress.exists():
                mid_run_snapshots.append(set(json.loads(progress.read_text())["completed"]))
            return (1, 1)

        monkeypatch.setattr(backfill_mod, "ingest_mlb_boxscore", _fake_boxscore)
        await backfill_season(session, 2024, set())

        # By the third game's ingest, the first two were already on disk.
        assert mid_run_snapshots[-1] == {745123, 745124}
        saved = json.loads((tmp_path / "progress.json").read_text())
        assert set(saved["completed"]) == {745123, 745124, 745125}

    async def test_backfill_iterates_seasons(self, quiet_backfill, monkeypatch):
        """backfill() walks the season range and shares the completed set."""
        from unittest.mock import MagicMock

        seen = []

        async def _fake_season(session, season, completed):
            seen.append(season)
            completed.add(700000 + season)
            return (1, 0)

        class _FakeSessionCtx:
            async def __aenter__(self):
                return MagicMock()

            async def __aexit__(self, *args):
                return False

        monkeypatch.setattr(backfill_mod, "backfill_season", _fake_season)
        monkeypatch.setattr(backfill_mod, "async_session_factory", lambda: _FakeSessionCtx())
        await backfill_mod.backfill(2023, 2025)
        assert seen == [2023, 2024, 2025]
