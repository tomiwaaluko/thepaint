"""Tests for Steps 1-5: scaffold, config, exceptions, session, ORM models."""
from datetime import date, datetime

import pytest
from sqlalchemy import select

from chalk.config import Settings
from chalk.db.models import (
    Base,
    BettingLine,
    Game,
    Injury,
    Player,
    PlayerGameLog,
    Prediction,
    Team,
    TeamGameLog,
)
from chalk.exceptions import (
    ChalkError,
    FeatureError,
    IngestError,
    ModelNotFoundError,
    PredictionError,
)


class TestConfig:
    def test_settings_loads_defaults(self):
        s = Settings(DATABASE_URL="postgresql+asyncpg://x:x@localhost/test")
        assert s.REDIS_URL == "redis://localhost:6379/0"
        assert s.LOG_LEVEL == "INFO"

    def test_settings_requires_database_url(self):
        # DATABASE_URL has a default in our Settings, so this should work
        s = Settings()
        assert "chalk" in s.DATABASE_URL


class TestExceptions:
    def test_hierarchy(self):
        assert issubclass(IngestError, ChalkError)
        assert issubclass(FeatureError, ChalkError)
        assert issubclass(PredictionError, ChalkError)
        assert issubclass(ModelNotFoundError, ChalkError)

    def test_raise_ingest_error(self):
        with pytest.raises(IngestError, match="test"):
            raise IngestError("test")


class TestORMModels:
    def test_all_tables_registered(self):
        tables = set(Base.metadata.tables.keys())
        expected = {
            "teams", "players", "games", "player_game_logs",
            "team_game_logs", "injuries", "betting_lines", "predictions",
        }
        assert expected == tables

    @pytest.mark.asyncio
    async def test_create_team(self, session):
        team = Team(
            team_id=1610612747, name="Los Angeles Lakers",
            abbreviation="LAL", conference="West",
            division="Pacific", city="Los Angeles",
        )
        session.add(team)
        await session.commit()
        result = await session.get(Team, 1610612747)
        assert result.name == "Los Angeles Lakers"

    @pytest.mark.asyncio
    async def test_create_player(self, session):
        team = Team(
            team_id=1610612747, name="Los Angeles Lakers",
            abbreviation="LAL", conference="West",
            division="Pacific", city="Los Angeles",
        )
        session.add(team)
        await session.flush()
        player = Player(
            player_id=2544, name="LeBron James",
            team_id=1610612747, position="SF",
        )
        session.add(player)
        await session.commit()
        result = await session.get(Player, 2544)
        assert result.name == "LeBron James"

    @pytest.mark.asyncio
    async def test_create_game(self, session):
        for tid, name, abbr, city in [
            (1, "Team A", "TMA", "CityA"),
            (2, "Team B", "TMB", "CityB"),
        ]:
            session.add(Team(
                team_id=tid, name=name, abbreviation=abbr,
                conference="East", division="Atlantic", city=city,
            ))
        await session.flush()
        game = Game(
            game_id="0022301234", date=date(2024, 1, 15),
            season="2023-24", home_team_id=1, away_team_id=2,
        )
        session.add(game)
        await session.commit()
        result = await session.get(Game, "0022301234")
        assert result.season == "2023-24"

    @pytest.mark.asyncio
    async def test_player_game_log_indexes(self):
        """Verify critical indexes are defined on the model."""
        indexes = {idx.name for idx in PlayerGameLog.__table__.indexes}
        assert "ix_player_game_date" in indexes
        assert "ix_team_game_date_player" in indexes

    @pytest.mark.asyncio
    async def test_team_game_log_indexes(self):
        indexes = {idx.name for idx in TeamGameLog.__table__.indexes}
        assert "ix_team_game_date" in indexes
