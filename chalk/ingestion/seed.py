"""Seed reference data (teams, players) into the database."""
import structlog
from nba_api.stats.static import teams as nba_teams
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from chalk.db.models import Game, Player, Team

# Build abbreviation -> team_id lookup from nba_api static data
_TEAM_ABBR_TO_ID: dict[str, int] = {}
for _t in nba_teams.get_teams():
    _TEAM_ABBR_TO_ID[_t["abbreviation"]] = _t["id"]


def team_id_from_abbr(abbr: str) -> int:
    """Resolve team abbreviation to team_id. Returns 0 if unknown."""
    return _TEAM_ABBR_TO_ID.get(abbr, 0)

log = structlog.get_logger()

# nba_api static data doesn't include conference/division, so we map them
TEAM_CONF_DIV = {
    1610612737: ("East", "Southeast"),   # Hawks
    1610612738: ("East", "Atlantic"),     # Celtics
    1610612739: ("East", "Central"),      # Cavaliers
    1610612740: ("West", "Southwest"),    # Pelicans
    1610612741: ("East", "Central"),      # Bulls
    1610612742: ("West", "Southwest"),    # Mavericks
    1610612743: ("West", "Northwest"),    # Nuggets
    1610612744: ("West", "Pacific"),      # Warriors
    1610612745: ("West", "Southwest"),    # Rockets
    1610612746: ("West", "Pacific"),      # Clippers
    1610612747: ("West", "Pacific"),      # Lakers
    1610612748: ("East", "Southeast"),    # Heat
    1610612749: ("East", "Central"),      # Bucks
    1610612750: ("West", "Northwest"),    # Timberwolves
    1610612751: ("East", "Atlantic"),     # Nets
    1610612752: ("East", "Atlantic"),     # Knicks
    1610612753: ("East", "Southeast"),    # Magic
    1610612754: ("East", "Central"),      # Pacers
    1610612755: ("East", "Atlantic"),     # 76ers
    1610612756: ("West", "Pacific"),      # Suns
    1610612757: ("West", "Northwest"),    # Trail Blazers
    1610612758: ("West", "Pacific"),      # Kings
    1610612759: ("West", "Southwest"),    # Spurs
    1610612760: ("West", "Northwest"),    # Thunder
    1610612761: ("East", "Atlantic"),     # Raptors
    1610612762: ("West", "Northwest"),    # Jazz
    1610612763: ("West", "Southwest"),    # Grizzlies
    1610612764: ("East", "Southeast"),    # Wizards
    1610612765: ("East", "Central"),      # Pistons
    1610612766: ("East", "Southeast"),    # Hornets
}


async def seed_teams(session: AsyncSession) -> int:
    """Seed all 30 NBA teams. Returns count of rows upserted."""
    teams = nba_teams.get_teams()
    rows = []
    for t in teams:
        conf, div = TEAM_CONF_DIV.get(t["id"], ("Unknown", "Unknown"))
        rows.append({
            "team_id": t["id"],
            "name": t["full_name"],
            "abbreviation": t["abbreviation"],
            "conference": conf,
            "division": div,
            "city": t["city"],
        })

    stmt = pg_insert(Team).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["team_id"],
        set_={
            "name": stmt.excluded.name,
            "abbreviation": stmt.excluded.abbreviation,
            "conference": stmt.excluded.conference,
            "division": stmt.excluded.division,
            "city": stmt.excluded.city,
        },
    )
    result = await session.execute(stmt)
    await session.commit()
    log.info("seed_teams_done", count=result.rowcount)
    return result.rowcount


async def upsert_player(session: AsyncSession, player_id: int, name: str, team_id: int) -> None:
    """Upsert a single player record."""
    stmt = pg_insert(Player).values(
        player_id=player_id,
        name=name,
        team_id=team_id,
        position="N/A",
        is_active=True,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["player_id"],
        set_={"team_id": stmt.excluded.team_id, "name": stmt.excluded.name},
    )
    await session.execute(stmt)


async def upsert_games(session: AsyncSession, game_rows: list[dict]) -> None:
    """Upsert game records. Each dict needs: game_id, date, season, home_team_id, away_team_id."""
    if not game_rows:
        return
    stmt = pg_insert(Game).values(game_rows)
    stmt = stmt.on_conflict_do_nothing(index_elements=["game_id"])
    await session.execute(stmt)
