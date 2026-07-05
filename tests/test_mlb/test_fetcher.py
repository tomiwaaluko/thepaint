"""Tests for the MLB StatsAPI fetcher. Never hits the real API."""
import json
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import select

import chalk.mlb.fetcher as fetcher
from chalk.exceptions import IngestError
from chalk.mlb.fetcher import (
    _build_batter_rows,
    _build_pitcher_rows,
    _cache_path,
    _fetch_json,
    game_is_final,
    ingest_mlb_boxscore,
    ingest_mlb_date,
    ingest_mlb_schedule,
    ingest_mlb_teams,
    is_final_status,
)
from chalk.mlb.models import (
    MlbBatterGameLog,
    MlbGame,
    MlbPitcherGameLog,
    MlbPlayer,
    MlbTeam,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


@pytest.fixture
def cache_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(fetcher, "CACHE_DIR", tmp_path)
    return tmp_path


@pytest.fixture
def fake_api(monkeypatch):
    """Route _fetch_json to fixture payloads keyed by path prefix."""
    routes: dict[str, dict] = {}
    calls: list[str] = []

    async def _fake(path: str, params: dict | None = None, use_cache: bool = True) -> dict:
        calls.append(path)
        for prefix, payload in routes.items():
            if path.startswith(prefix):
                if isinstance(payload, Exception):
                    raise payload
                return payload
        raise AssertionError(f"unexpected StatsAPI path: {path}")

    monkeypatch.setattr(fetcher, "_fetch_json", _fake)
    _fake.routes = routes
    _fake.calls = calls
    return _fake


class TestCachePath:
    def test_sanitizes_path_traversal(self, cache_dir):
        p = _cache_path("../../etc/passwd", {})
        assert cache_dir in p.parents
        assert ".." not in p.parts

    def test_distinct_params_distinct_keys(self, cache_dir):
        a = _cache_path("schedule", {"startDate": "2024-06-01"})
        b = _cache_path("schedule", {"startDate": "2024-06-02"})
        assert a != b


class TestFetchJson:
    async def test_cache_hit_skips_http(self, cache_dir, monkeypatch):
        payload = {"hello": "world"}
        cache_file = _cache_path("teams", {"sportId": 1})
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(payload))

        async def _boom(url, params):
            raise AssertionError("HTTP called despite cache hit")

        monkeypatch.setattr(fetcher, "_http_get_json", _boom)
        assert await _fetch_json("teams", {"sportId": 1}) == payload

    async def test_use_cache_false_bypasses_read_and_write(self, cache_dir, monkeypatch):
        stale = {"stale": True}
        cache_file = _cache_path("schedule", {"d": "x"})
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(stale))

        async def _fresh(url, params):
            return {"fresh": True}

        monkeypatch.setattr(fetcher, "_http_get_json", _fresh)
        assert await _fetch_json("schedule", {"d": "x"}, use_cache=False) == {"fresh": True}
        assert json.loads(cache_file.read_text()) == stale

    async def test_retries_then_raises_ingest_error(self, cache_dir, monkeypatch):
        attempts = []

        async def _fail(url, params):
            attempts.append(url)
            raise ConnectionError("boom")

        monkeypatch.setattr(fetcher, "_http_get_json", _fail)
        monkeypatch.setattr(fetcher, "MAX_RETRIES", 3)
        monkeypatch.setattr(fetcher, "BASE_DELAY", 0)
        monkeypatch.setattr(fetcher.random, "uniform", lambda a, b: 0)

        with pytest.raises(IngestError):
            await _fetch_json("teams", {"sportId": 1})
        assert len(attempts) == 3

    async def test_success_writes_cache(self, cache_dir, monkeypatch):
        async def _ok(url, params):
            return {"ok": True}

        monkeypatch.setattr(fetcher, "_http_get_json", _ok)
        assert await _fetch_json("teams", {"sportId": 1}) == {"ok": True}
        assert json.loads(_cache_path("teams", {"sportId": 1}).read_text()) == {"ok": True}


class TestIngestTeams:
    async def test_upserts_and_is_idempotent(self, session, fake_api):
        fake_api.routes["teams"] = _load("teams.json")

        first = await ingest_mlb_teams(session, 2024)
        second = await ingest_mlb_teams(session, 2024)
        assert first == second == 3

        rows = (await session.execute(select(MlbTeam))).scalars().all()
        assert len(rows) == 3
        yankees = next(t for t in rows if t.team_id == 147)
        assert yankees.league == "American League"
        assert yankees.division == "American League East"
        assert yankees.city == "Bronx"


class TestIngestSchedule:
    async def test_doubleheader_yields_two_games_spring_excluded(self, session, fake_api):
        fake_api.routes["teams"] = _load("teams.json")
        fake_api.routes["schedule"] = _load("schedule_doubleheader.json")

        await ingest_mlb_teams(session, 2024)
        count = await ingest_mlb_schedule(session, date(2024, 7, 8), date(2024, 7, 8))
        assert count == 2  # spring-training game (gameType S) filtered out

        rows = (await session.execute(select(MlbGame))).scalars().all()
        assert {g.game_pk for g in rows} == {746001, 746002}
        assert {g.game_number for g in rows} == {1, 2}
        assert all(g.doubleheader == "Y" for g in rows)

    async def test_postseason_flag_derived_from_game_type(self, session, fake_api):
        payload = _load("schedule_single.json")
        payload["dates"][0]["games"][0]["gameType"] = "W"  # World Series
        fake_api.routes["teams"] = _load("teams.json")
        fake_api.routes["schedule"] = payload

        await ingest_mlb_teams(session, 2024)
        await ingest_mlb_schedule(session, date(2024, 6, 1), date(2024, 6, 1))
        game = (await session.execute(select(MlbGame))).scalar_one()
        assert game.is_postseason is True
        assert game.game_type == "W"

    async def test_idempotent_and_status_correctable(self, session, fake_api):
        payload = _load("schedule_single.json")
        fake_api.routes["teams"] = _load("teams.json")
        fake_api.routes["schedule"] = payload

        await ingest_mlb_teams(session, 2024)
        await ingest_mlb_schedule(session, date(2024, 6, 1), date(2024, 6, 1))
        payload["dates"][0]["games"][0]["status"]["detailedState"] = "Completed Early"
        await ingest_mlb_schedule(session, date(2024, 6, 1), date(2024, 6, 1))

        rows = (await session.execute(select(MlbGame))).scalars().all()
        assert len(rows) == 1
        assert rows[0].status == "Completed Early"


class TestFinality:
    def test_is_final_status_prefixes(self):
        assert is_final_status("Final")
        assert is_final_status("Final: Tied")
        assert is_final_status("Game Over")
        assert is_final_status("Completed Early: Rain")
        assert not is_final_status("In Progress")
        assert not is_final_status("Scheduled")

    def test_game_is_final_prefers_abstract_state(self):
        # Forfeit-style oddball: detailedState unknown to the prefix list, but
        # the upstream abstract state says the game is over.
        forfeit = MlbGame(
            game_pk=1, date=date(2024, 6, 1), season="2024", game_type="R",
            home_team_id=147, away_team_id=147,
            status="Forfeit", abstract_state="Final",
        )
        live = MlbGame(
            game_pk=2, date=date(2024, 6, 1), season="2024", game_type="R",
            home_team_id=147, away_team_id=147,
            status="In Progress", abstract_state="Live",
        )
        legacy = MlbGame(  # row predating the abstract_state column
            game_pk=3, date=date(2024, 6, 1), season="2024", game_type="R",
            home_team_id=147, away_team_id=147,
            status="Final", abstract_state=None,
        )
        assert game_is_final(forfeit) is True
        assert game_is_final(live) is False
        assert game_is_final(legacy) is True


class TestBoxscoreParsers:
    def test_batter_rows_skip_non_batters(self):
        rows = _build_batter_rows(
            _load("boxscore_regular.json"), game_date=date(2024, 6, 1), season="2024"
        )
        ids = {r["player_id"] for r in rows}
        # Devers, Ohtani, Judge batted; pitcher Bello and Bench Guy did not.
        assert ids == {646240, 660271, 543305}
        judge = next(r for r in rows if r["player_id"] == 543305)
        assert judge["hr"] == 1 and judge["sb"] == 1 and judge["plate_appearances"] == 5
        assert judge["team_id"] == 147

    def test_pitcher_rows_include_two_way_and_relief(self):
        rows = _build_pitcher_rows(
            _load("boxscore_regular.json"), game_date=date(2024, 6, 1), season="2024"
        )
        by_id = {r["player_id"]: r for r in rows}
        assert set(by_id) == {678394, 660271}
        assert by_id[660271]["is_starter"] is True
        assert by_id[660271]["outs_recorded"] == 18
        assert by_id[678394]["loss"] is True and by_id[678394]["win"] is False

    def test_relief_pitcher_not_starter(self):
        rows = _build_pitcher_rows(
            _load("boxscore_postseason.json"), game_date=date(2024, 10, 25), season="2024"
        )
        relief = next(r for r in rows if r["player_id"] == 621111)
        assert relief["is_starter"] is False
        assert relief["save"] is True


class TestIngestBoxscore:
    async def _seed_game(self, session, fake_api):
        fake_api.routes["teams"] = _load("teams.json")
        fake_api.routes["schedule"] = _load("schedule_single.json")
        await ingest_mlb_teams(session, 2024)
        await ingest_mlb_schedule(session, date(2024, 6, 1), date(2024, 6, 1))

    async def test_two_way_player_lands_in_both_tables(self, session, fake_api):
        await self._seed_game(session, fake_api)
        fake_api.routes["game/745123/boxscore"] = _load("boxscore_regular.json")

        batters, pitchers = await ingest_mlb_boxscore(session, 745123)
        assert (batters, pitchers) == (3, 2)

        b = (await session.execute(
            select(MlbBatterGameLog).where(MlbBatterGameLog.player_id == 660271)
        )).scalar_one()
        p = (await session.execute(
            select(MlbPitcherGameLog).where(MlbPitcherGameLog.player_id == 660271)
        )).scalar_one()
        assert b.total_bases == 6 and p.so == 8

    async def test_players_upserted_before_logs(self, session, fake_api):
        await self._seed_game(session, fake_api)
        fake_api.routes["game/745123/boxscore"] = _load("boxscore_regular.json")
        await ingest_mlb_boxscore(session, 745123)

        players = (await session.execute(select(MlbPlayer))).scalars().all()
        assert {p.player_id for p in players} >= {646240, 678394, 660271, 543305}
        ohtani = next(p for p in players if p.player_id == 660271)
        assert ohtani.team_id == 147  # home side in fixture

    async def test_idempotent(self, session, fake_api):
        await self._seed_game(session, fake_api)
        fake_api.routes["game/745123/boxscore"] = _load("boxscore_regular.json")

        await ingest_mlb_boxscore(session, 745123)
        await ingest_mlb_boxscore(session, 745123)

        batters = (await session.execute(select(MlbBatterGameLog))).scalars().all()
        pitchers = (await session.execute(select(MlbPitcherGameLog))).scalars().all()
        assert len(batters) == 3 and len(pitchers) == 2

    async def test_unknown_game_raises_ingest_error(self, session, fake_api):
        with pytest.raises(IngestError):
            await ingest_mlb_boxscore(session, 999999)


class TestIngestDate:
    async def test_composed_summary(self, session, fake_api):
        fake_api.routes["teams"] = _load("teams.json")
        fake_api.routes["schedule"] = _load("schedule_single.json")
        fake_api.routes["game/745123/boxscore"] = _load("boxscore_regular.json")

        await ingest_mlb_teams(session, 2024)
        summary = await ingest_mlb_date(session, date(2024, 6, 1))
        assert summary == {"games": 1, "batter_rows": 3, "pitcher_rows": 2, "failed_games": 0}

    async def test_no_games_day_is_healthy(self, session, fake_api):
        fake_api.routes["schedule"] = {"dates": []}
        summary = await ingest_mlb_date(session, date(2024, 12, 25))
        assert summary == {"games": 0, "batter_rows": 0, "pitcher_rows": 0, "failed_games": 0}

    async def test_one_failed_boxscore_does_not_sink_the_day(self, session, fake_api):
        """A permanent boxscore failure is counted, logged, and skipped."""
        payload = _load("schedule_single.json")
        second = json.loads(json.dumps(payload["dates"][0]["games"][0]))
        second["gamePk"] = 745124
        second["gameNumber"] = 2
        second["doubleHeader"] = "Y"
        payload["dates"][0]["games"][0]["doubleHeader"] = "Y"
        payload["dates"][0]["games"].append(second)

        fake_api.routes["teams"] = _load("teams.json")
        fake_api.routes["schedule"] = payload
        fake_api.routes["game/745123/boxscore"] = IngestError("boxscore 404")
        fake_api.routes["game/745124/boxscore"] = _load("boxscore_regular.json")

        await ingest_mlb_teams(session, 2024)
        summary = await ingest_mlb_date(session, date(2024, 6, 1))
        assert summary == {
            "games": 2, "batter_rows": 3, "pitcher_rows": 2, "failed_games": 1,
        }

    async def test_malformed_player_entry_skipped(self, session, fake_api):
        """A boxscore entry without a person id is dropped, not a crash."""
        payload = _load("boxscore_regular.json")
        payload["teams"]["home"]["players"]["IDBROKEN"] = {
            "position": {"abbreviation": "LF"},
            "battingOrder": "400",
            "stats": {"batting": {"atBats": 3, "plateAppearances": 3}, "pitching": {}},
        }
        fake_api.routes["teams"] = _load("teams.json")
        fake_api.routes["schedule"] = _load("schedule_single.json")
        fake_api.routes["game/745123/boxscore"] = payload

        await ingest_mlb_teams(session, 2024)
        summary = await ingest_mlb_date(session, date(2024, 6, 1))
        # The malformed entry is excluded; the three real batters land.
        assert summary["batter_rows"] == 3 and summary["failed_games"] == 0

    async def test_malformed_schedule_game_skipped(self, session, fake_api):
        """A schedule entry missing required keys is logged and skipped."""
        payload = _load("schedule_single.json")
        payload["dates"][0]["games"].append({"gameType": "R", "gamePk": 999})  # no teams
        fake_api.routes["teams"] = _load("teams.json")
        fake_api.routes["schedule"] = payload

        await ingest_mlb_teams(session, 2024)
        count = await ingest_mlb_schedule(session, date(2024, 6, 1), date(2024, 6, 1))
        assert count == 1  # only the well-formed game

    async def test_non_final_games_skipped(self, session, fake_api):
        payload = _load("schedule_single.json")
        payload["dates"][0]["games"][0]["status"]["detailedState"] = "In Progress"
        payload["dates"][0]["games"][0]["status"]["abstractGameState"] = "Live"
        fake_api.routes["teams"] = _load("teams.json")
        fake_api.routes["schedule"] = payload

        await ingest_mlb_teams(session, 2024)
        summary = await ingest_mlb_date(session, date(2024, 6, 1))
        assert summary == {"games": 1, "batter_rows": 0, "pitcher_rows": 0, "failed_games": 0}
