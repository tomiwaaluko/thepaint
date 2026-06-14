"""Backfill team/player box scores for one stored game.

Usage:
    python scripts/backfill_game_boxscore.py --game-id 401873342
"""
import argparse
import asyncio
import sys
from pathlib import Path

import structlog
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from chalk.db.models import Game
from chalk.db.session import async_session_factory
from chalk.ingestion.nba_fetcher import (
    ingest_game_boxscores_cdn,
    ingest_game_boxscores_espn,
)

log = structlog.get_logger()


async def backfill_game(game_id: str) -> tuple[int, int]:
    async with async_session_factory() as session:
        result = await session.execute(select(Game).where(Game.game_id == game_id))
        game = result.scalar_one_or_none()
        if game is None:
            raise SystemExit(f"Game {game_id} not found")

        team_rows, player_rows = await ingest_game_boxscores_cdn(session, [game])
        source = "cdn"
        if not player_rows:
            espn_team_rows, espn_player_rows = await ingest_game_boxscores_espn(session, [game])
            team_rows += espn_team_rows
            player_rows += espn_player_rows
            source = "cdn+espn" if team_rows != espn_team_rows else "espn"
        await session.commit()
        log.info(
            "game_boxscore_backfilled",
            game_id=game_id,
            source=source,
            team_rows=team_rows,
            player_rows=player_rows,
        )
        return team_rows, player_rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill one game boxscore")
    parser.add_argument("--game-id", required=True)
    args = parser.parse_args()

    team_rows, player_rows = asyncio.run(backfill_game(args.game_id))
    print(f"team_rows={team_rows} player_rows={player_rows}")


if __name__ == "__main__":
    main()
