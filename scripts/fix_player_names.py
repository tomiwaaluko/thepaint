"""
One-time repair script: fixes players whose name was stored as a numeric ID.

Run this once against production to repair bad data from railway_ingest.py
calls that didn't pass player_name (so name defaulted to str(player_id)).

Usage:
    python -m scripts.fix_player_names
"""
import asyncio

import structlog
from nba_api.stats.static import players as nba_players_static
from sqlalchemy import select, update

from chalk.db.models import Player
from chalk.db.session import async_session_factory

log = structlog.get_logger()

_PLAYER_ID_TO_NAME: dict[int, str] = {
    p["id"]: p["full_name"] for p in nba_players_static.get_players()
}


async def main():
    async with async_session_factory() as session:
        result = await session.execute(select(Player))
        players = result.scalars().all()

        fixed = 0
        for player in players:
            # A name that is purely numeric means it was stored as the player ID
            if player.name and player.name.isdigit():
                real_name = _PLAYER_ID_TO_NAME.get(player.player_id)
                if real_name:
                    await session.execute(
                        update(Player)
                        .where(Player.player_id == player.player_id)
                        .values(name=real_name)
                    )
                    log.info("fixed_player_name", player_id=player.player_id, name=real_name)
                    fixed += 1
                else:
                    log.warning("name_not_found", player_id=player.player_id)

        await session.commit()
        log.info("repair_complete", fixed=fixed, total=len(players))


if __name__ == "__main__":
    asyncio.run(main())
