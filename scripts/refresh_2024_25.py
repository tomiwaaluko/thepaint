"""Refresh 2024-25 season data and retrain models.

1. Clears cached nba_api responses for 2024-25 season
2. Re-ingests team and player game logs for 2024-25
3. Clears cached feature matrices
4. Retrains all models
"""
import asyncio
import hashlib
import json
import sys
from pathlib import Path

import structlog
from nba_api.stats.static import players as nba_players

from chalk.config import settings
from chalk.db.session import async_session_factory
from chalk.exceptions import IngestError
from chalk.ingestion.nba_fetcher import ingest_player_season, ingest_team_season
from chalk.ingestion.seed import seed_teams

log = structlog.get_logger()

CACHE_DIR = Path(settings.NBA_API_CACHE_DIR)
MATRIX_DIR = Path(".cache/matrices")
SEASON = "2024-25"
INTER_REQUEST_DELAY = 2.5


def _cache_path(endpoint: str, params: dict) -> Path:
    key = hashlib.md5(f"{endpoint}{sorted(params.items())}".encode()).hexdigest()
    return CACHE_DIR / endpoint / f"{key}.json"


def clear_2024_25_cache():
    """Delete cached nba_api responses for 2024-25 season."""
    deleted = 0

    # Team game log cache
    team_cache = _cache_path(
        "LeagueGameLog_Teams",
        {"season": SEASON, "player_or_team_abbreviation": "T"},
    )
    if team_cache.exists():
        team_cache.unlink()
        deleted += 1
        print(f"  Deleted team cache: {team_cache.name}")

    # Player game log caches — compute hash for each active player
    all_active = nba_players.get_active_players()
    for player in all_active:
        pid = player["id"]
        player_cache = _cache_path(
            "PlayerGameLog",
            {"player_id": pid, "season": SEASON, "season_type_all_star": "Regular Season"},
        )
        if player_cache.exists():
            player_cache.unlink()
            deleted += 1

    print(f"  Cleared {deleted} cached API responses for {SEASON}")
    return deleted


def clear_matrix_cache():
    """Delete cached feature matrices so they get rebuilt."""
    deleted = 0
    for f in MATRIX_DIR.glob("*.parquet"):
        f.unlink()
        deleted += 1
        print(f"  Deleted matrix cache: {f.name}")
    print(f"  Cleared {deleted} matrix files")


async def refresh_data():
    """Ingest fresh 2024-25 data for all active players."""
    all_active = nba_players.get_active_players()
    total = len(all_active)
    skipped = 0
    ingested = 0

    async with async_session_factory() as session:
        await seed_teams(session)

        # Team game logs first
        print(f"\n[2/4] Ingesting team game logs for {SEASON}...")
        try:
            count = await ingest_team_season(session, SEASON)
            print(f"  Team logs: {count} rows upserted")
        except IngestError as e:
            print(f"  Team log error: {e}")

        await asyncio.sleep(INTER_REQUEST_DELAY)

        # Player game logs
        print(f"\n[3/4] Ingesting player game logs for {SEASON} ({total} players)...")
        for i, player in enumerate(all_active, 1):
            pid = player["id"]
            pname = player["full_name"]
            try:
                count = await ingest_player_season(
                    session, pid, SEASON, team_id=0, player_name=pname,
                )
                if count > 0:
                    ingested += 1
                if i % 50 == 0 or i == total:
                    print(f"  Progress: {i}/{total} players ({ingested} with data)")
            except IngestError:
                skipped += 1
            except Exception as e:
                skipped += 1
                if i % 100 == 0:
                    print(f"  Warning at {pname}: {e}")

            await asyncio.sleep(INTER_REQUEST_DELAY)

    print(f"  Done: {ingested} players ingested, {skipped} skipped")


async def main():
    print("=" * 60)
    print(f"Refreshing {SEASON} data and retraining models")
    print("=" * 60)

    # Step 1: Clear caches
    print(f"\n[1/4] Clearing cached {SEASON} API responses...")
    clear_2024_25_cache()

    # Step 2-3: Refresh data
    await refresh_data()

    # Step 4: Clear matrix caches and retrain
    print("\n[4/4] Clearing matrix caches and retraining...")
    clear_matrix_cache()

    # Import and run training
    from scripts.train_all import run_training
    await run_training(
        stats=["pts", "reb", "ast", "fg3m"],
        skip_quantile=False,
        min_games=100,
    )

    print("\nDone! Compare MAE results above with previous:")
    print("  Previous: pts=4.94, reb=2.02, ast=1.47, fg3m=0.94")


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
