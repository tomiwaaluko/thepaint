"""Ingest the current season's team + player game logs for recent games.

Fetches 2025-26 season data (or whatever current season is) from nba_api,
upserts into the database, and prints a summary of new game IDs to use
in the dashboard.

Usage:
    python scripts/ingest_recent.py
"""
import asyncio
import sys
from datetime import date, timedelta

import structlog
from nba_api.stats.static import players as nba_players
from sqlalchemy import text

from chalk.db.session import async_session_factory
from chalk.ingestion.nba_fetcher import ingest_player_season, ingest_team_season
from chalk.ingestion.seed import seed_teams

log = structlog.get_logger()

CURRENT_SEASON = "2025-26"
INTER_REQUEST_DELAY = 2.5


async def main():
    print(f"Ingesting {CURRENT_SEASON} season data...")

    async with async_session_factory() as session:
        await seed_teams(session)

        # 1. Team game logs (gets all games + scores for the full season)
        print("\n[1/2] Team game logs...")
        try:
            count = await ingest_team_season(session, CURRENT_SEASON)
            print(f"  Upserted {count} team game log rows")
        except Exception as e:
            print(f"  Team ingest error: {e}")

        await asyncio.sleep(INTER_REQUEST_DELAY)

        # 2. Player game logs — only active players
        all_active = nba_players.get_active_players()
        print(f"\n[2/2] Player game logs ({len(all_active)} active players)...")
        ingested = 0
        failed = 0
        for i, player in enumerate(all_active, 1):
            try:
                count = await ingest_player_season(
                    session, player["id"], CURRENT_SEASON,
                    team_id=0, player_name=player["full_name"],
                )
                if count > 0:
                    ingested += 1
            except Exception as exc:
                # Continue past individual player failures - one bad response
                # should not abort a 500-player backfill - but say so. Silently
                # swallowing this made a run that ingested nothing look
                # identical to a successful one.
                failed += 1
                print(f"  ! {player['full_name']} ({player['id']}): {exc}")
            if i % 50 == 0 or i == len(all_active):
                print(f"  {i}/{len(all_active)} players processed ({ingested} with data, {failed} failed)")
            await asyncio.sleep(INTER_REQUEST_DELAY)

        # 3. Show recent games now in DB
        cutoff = date.today() - timedelta(days=7)
        # Bound parameters, not an f-string. Both values are internal today
        # (a module constant and date.today()), so this was not exploitable -
        # but it was the only raw-SQL f-string in the repo, and that shape is
        # exactly what gets copied into a place where the inputs are not.
        r = await session.execute(
            text("""
                SELECT g.game_id, g.date, ht.abbreviation, at.abbreviation,
                       count(pl.player_id) as players
                FROM games g
                JOIN teams ht ON ht.team_id = g.home_team_id
                JOIN teams at ON at.team_id = g.away_team_id
                LEFT JOIN player_game_logs pl ON pl.game_id = g.game_id
                WHERE g.season = :season
                  AND g.date >= :cutoff
                GROUP BY g.game_id, g.date, ht.abbreviation, at.abbreviation
                ORDER BY g.date DESC
                LIMIT 15
            """),
            {"season": CURRENT_SEASON, "cutoff": cutoff},
        )
        rows = r.fetchall()
        print(f"\nRecent {CURRENT_SEASON} games now in DB (last 7 days):")
        for row in rows:
            print(f"  {row[1]}  {row[2]} vs {row[3]}  game_id={row[0]}  ({row[4]} player logs)")

        if rows:
            print("\nUpdate DEMO_GAME_IDS in dashboard/src/App.tsx to:")
            ids = [row[0] for row in rows[:3]]
            print(f'  const DEMO_GAME_IDS = {json.dumps(ids)};')


if __name__ == "__main__":
    import json
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
