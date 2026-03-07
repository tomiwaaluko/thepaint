"""Historical data backfill runner.

Usage: python scripts/backfill.py [--seasons 2015-16 2016-17 ...] [--players all|top150]
"""
import argparse
import asyncio
import json
from pathlib import Path

import structlog
from nba_api.stats.static import players as nba_players
from sqlalchemy import select, func

from chalk.config import settings
from chalk.db.models import PlayerGameLog
from chalk.db.session import async_session_factory
from chalk.exceptions import IngestError
from chalk.ingestion.nba_fetcher import ingest_player_season, ingest_team_season

log = structlog.get_logger()

SEASONS = [
    "2015-16", "2016-17", "2017-18", "2018-19", "2019-20",
    "2020-21", "2021-22", "2022-23", "2023-24", "2024-25",
]
INTER_REQUEST_DELAY = 2.5  # seconds between nba_api calls
PROGRESS_FILE = Path(".cache/backfill_progress.json")


def get_player_list(mode: str = "all") -> list[dict]:
    """Return list of players to backfill."""
    all_active = nba_players.get_active_players()
    if mode == "top150":
        return all_active[:150]
    return all_active


def load_progress() -> set[str]:
    """Load completed player-season pairs from progress file."""
    if PROGRESS_FILE.exists():
        data = json.loads(PROGRESS_FILE.read_text())
        return set(data.get("completed", []))
    return set()


def save_progress(completed: set[str]) -> None:
    """Persist completed player-season pairs."""
    PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
    PROGRESS_FILE.write_text(json.dumps({"completed": sorted(completed)}))


async def backfill(seasons: list[str], player_mode: str) -> None:
    players = get_player_list(player_mode)
    completed = load_progress()
    total = len(players) * len(seasons)
    done = 0
    skipped = []

    log.info("backfill_start", players=len(players), seasons=len(seasons), total=total)

    async with async_session_factory() as session:
        # Player game logs
        for player in players:
            pid = player["id"]
            pname = player["full_name"]
            for season in seasons:
                key = f"{pid}_{season}"
                if key in completed:
                    done += 1
                    continue

                try:
                    count = await ingest_player_season(session, pid, season, team_id=0)
                    completed.add(key)
                    done += 1
                    log.info(
                        "backfill_progress",
                        completed=done, total=total,
                        player=pname, season=season, rows=count,
                    )
                except IngestError as e:
                    skipped.append(f"{pname} {season}")
                    done += 1
                    log.error("backfill_skip", player=pname, season=season, error=str(e))

                save_progress(completed)
                await asyncio.sleep(INTER_REQUEST_DELAY)

        # Team game logs
        for season in seasons:
            try:
                count = await ingest_team_season(session, season)
                log.info("team_backfill", season=season, rows=count)
            except IngestError as e:
                log.error("team_backfill_skip", season=season, error=str(e))
            await asyncio.sleep(INTER_REQUEST_DELAY)

    log.info(
        "backfill_complete",
        total_done=done, skipped=len(skipped),
        skipped_list=skipped[:20],
    )


def main():
    parser = argparse.ArgumentParser(description="Backfill NBA data")
    parser.add_argument("--seasons", nargs="+", default=SEASONS)
    parser.add_argument("--players", choices=["all", "top150"], default="all")
    args = parser.parse_args()

    asyncio.run(backfill(args.seasons, args.players))


if __name__ == "__main__":
    main()
