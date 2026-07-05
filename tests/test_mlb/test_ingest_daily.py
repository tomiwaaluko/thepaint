"""Exit-code matrix for the daily MLB ingest cron (all steps mocked)."""
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

import chalk.db.session as db_session
import chalk.mlb.fetcher as fetcher
import chalk.mlb.validate as validate_mod
from scripts.mlb_ingest_daily import main_async


@pytest.fixture
def mocked_steps(engine, monkeypatch):
    """Wire main_async to the sqlite test engine and stub every ingest step."""
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(db_session, "async_session_factory", factory)

    state = {"validate_ok": True, "raise_in": None, "failed_games": 0, "calls": []}

    async def _teams(session, season):
        state["calls"].append("teams")
        if state["raise_in"] == "teams":
            raise RuntimeError("teams boom")
        return 30

    async def _date(session, game_date):
        state["calls"].append("yesterday")
        if state["raise_in"] == "yesterday":
            raise RuntimeError("date boom")
        return {
            "games": 2, "batter_rows": 10, "pitcher_rows": 5,
            "failed_games": state["failed_games"],
        }

    async def _schedule(session, start, end, use_cache=True):
        state["calls"].append("today")
        if state["raise_in"] == "today":
            raise RuntimeError("schedule boom")
        return 2

    async def _validate(session, game_date):
        state["calls"].append("validate")
        return state["validate_ok"]

    monkeypatch.setattr(fetcher, "ingest_mlb_teams", _teams)
    monkeypatch.setattr(fetcher, "ingest_mlb_date", _date)
    monkeypatch.setattr(fetcher, "ingest_mlb_schedule", _schedule)
    monkeypatch.setattr(validate_mod, "validate_mlb_row_counts", _validate)
    return state


class TestExitCodeMatrix:
    async def test_all_healthy_returns_not_failed(self, mocked_steps):
        assert await main_async() is False
        assert mocked_steps["calls"] == ["teams", "yesterday", "today", "validate"]

    async def test_validation_failure_marks_failed(self, mocked_steps):
        mocked_steps["validate_ok"] = False
        assert await main_async() is True

    @pytest.mark.parametrize("failing_step", ["teams", "yesterday", "today"])
    async def test_step_exception_marks_failed_but_continues(
        self, mocked_steps, failing_step
    ):
        mocked_steps["raise_in"] = failing_step
        assert await main_async() is True
        # Later steps still ran despite the earlier failure.
        assert "validate" in mocked_steps["calls"]

    async def test_partial_day_failed_games_marks_failed(self, mocked_steps):
        """Per-game failures isolated inside ingest_mlb_date still exit 1."""
        mocked_steps["failed_games"] = 1
        assert await main_async() is True
        assert "validate" in mocked_steps["calls"]
