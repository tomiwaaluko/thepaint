"""Tests for MLB row-count validation (warn-style, never raises)."""
from datetime import date

from chalk.mlb.models import MlbBatterGameLog, MlbGame, MlbPlayer, MlbTeam
from chalk.mlb.validate import validate_mlb_row_counts

GAME_DATE = date(2024, 6, 1)


async def _seed_final_game(session):
    session.add(MlbTeam(
        team_id=147, name="New York Yankees", abbreviation="NYY",
        league="American League", division="American League East", city="Bronx",
    ))
    session.add(MlbGame(
        game_pk=745123, date=GAME_DATE, season="2024", game_type="R",
        home_team_id=147, away_team_id=147, status="Final",
    ))
    await session.commit()


class TestValidateMlbRowCounts:
    async def test_no_games_day_is_healthy(self, session):
        assert await validate_mlb_row_counts(session, GAME_DATE) is True

    async def test_games_without_logs_fails_softly(self, session):
        await _seed_final_game(session)
        assert await validate_mlb_row_counts(session, GAME_DATE) is False

    async def test_games_with_logs_is_healthy(self, session):
        await _seed_final_game(session)
        session.add(MlbPlayer(player_id=543305, name="Aaron Judge", team_id=147, position="CF"))
        session.add(MlbBatterGameLog(
            game_pk=745123, player_id=543305, team_id=147,
            game_date=GAME_DATE, season="2024",
            ab=3, r=2, h=2, doubles=0, triples=0, hr=1, rbi=3, bb=2, so=0,
            sb=1, cs=0, hbp=0, total_bases=5, plate_appearances=5, position="CF",
        ))
        await session.commit()
        assert await validate_mlb_row_counts(session, GAME_DATE) is True
