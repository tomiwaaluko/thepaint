"""Tests for MLB ORM table definitions."""
from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from chalk.mlb.models import (
    MlbBatterGameLog,
    MlbGame,
    MlbPitcherGameLog,
    MlbPlayer,
    MlbTeam,
)


def _team(team_id: int = 147) -> MlbTeam:
    return MlbTeam(
        team_id=team_id,
        name="New York Yankees",
        abbreviation="NYY",
        league="American League",
        division="American League East",
        venue="Yankee Stadium",
        city="Bronx",
    )


def _player(player_id: int = 660271, team_id: int = 147) -> MlbPlayer:
    return MlbPlayer(
        player_id=player_id,
        name="Shohei Ohtani",
        team_id=team_id,
        position="TWP",
        bats="L",
        throws="R",
    )


def _game(game_pk: int = 745123, game_number: int = 1) -> MlbGame:
    return MlbGame(
        game_pk=game_pk,
        date=date(2024, 6, 1),
        season="2024",
        game_type="R",
        is_postseason=False,
        doubleheader="N",
        game_number=game_number,
        home_team_id=147,
        away_team_id=147,
        status="Final",
    )


class TestMetadataRegistration:
    def test_mlb_tables_register_on_shared_base(self):
        """Alembic autogenerate sees MLB tables via the shared Base metadata."""
        from chalk.db.models import Base

        expected = {
            "mlb_teams", "mlb_players", "mlb_games",
            "mlb_batter_game_logs", "mlb_pitcher_game_logs",
        }
        assert expected <= set(Base.metadata.tables)


class TestORMModels:
    async def test_create_team(self, session):
        session.add(_team())
        await session.commit()
        row = (await session.execute(select(MlbTeam))).scalar_one()
        assert row.abbreviation == "NYY"
        assert row.league == "American League"

    async def test_create_player(self, session):
        session.add(_team())
        session.add(_player())
        await session.commit()
        row = (await session.execute(select(MlbPlayer))).scalar_one()
        assert row.name == "Shohei Ohtani"
        assert row.is_active is True

    async def test_create_game(self, session):
        session.add(_team())
        session.add(_game())
        await session.commit()
        row = (await session.execute(select(MlbGame))).scalar_one()
        assert row.game_pk == 745123
        assert row.is_postseason is False

    async def test_doubleheader_legs_coexist(self, session):
        """Same date + same teams must be storable twice with distinct game_number."""
        session.add(_team())
        session.add(_game(game_pk=745123, game_number=1))
        session.add(_game(game_pk=745124, game_number=2))
        await session.commit()
        rows = (await session.execute(select(MlbGame))).scalars().all()
        assert len(rows) == 2

    async def test_duplicate_matchup_same_game_number_rejected(self, session):
        session.add(_team())
        session.add(_game(game_pk=745123, game_number=1))
        session.add(_game(game_pk=745125, game_number=1))
        with pytest.raises(IntegrityError):
            await session.commit()

    async def test_two_way_player_has_batter_and_pitcher_rows(self, session):
        """A two-way player may produce one row in each log table for one game."""
        session.add(_team())
        session.add(_player())
        session.add(_game())
        await session.commit()

        session.add(
            MlbBatterGameLog(
                game_pk=745123, player_id=660271, team_id=147,
                game_date=date(2024, 6, 1), season="2024",
                ab=4, r=1, h=2, doubles=1, triples=0, hr=1, rbi=2,
                bb=0, so=1, sb=0, cs=0, hbp=0, total_bases=6,
                plate_appearances=4, batting_order="100", position="DH",
            )
        )
        session.add(
            MlbPitcherGameLog(
                game_pk=745123, player_id=660271, team_id=147,
                game_date=date(2024, 6, 1), season="2024",
                is_starter=True, outs_recorded=18, h=4, r=2, er=2,
                bb=1, so=8, hr=1, batters_faced=23, pitches_thrown=95,
                win=True, loss=False, save=False, hold=False,
            )
        )
        await session.commit()

        batter = (await session.execute(select(MlbBatterGameLog))).scalar_one()
        pitcher = (await session.execute(select(MlbPitcherGameLog))).scalar_one()
        assert batter.player_id == pitcher.player_id == 660271

    async def test_duplicate_batter_log_rejected(self, session):
        session.add(_team())
        session.add(_player())
        session.add(_game())
        await session.commit()
        for _ in range(2):
            session.add(
                MlbBatterGameLog(
                    game_pk=745123, player_id=660271, team_id=147,
                    game_date=date(2024, 6, 1), season="2024",
                    ab=4, r=0, h=0, doubles=0, triples=0, hr=0, rbi=0,
                    bb=0, so=0, sb=0, cs=0, hbp=0, total_bases=0,
                    plate_appearances=4, position="DH",
                )
            )
        with pytest.raises(IntegrityError):
            await session.commit()
