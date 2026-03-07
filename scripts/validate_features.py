"""Feature validation script.

Usage: python scripts/validate_features.py --player_id 2544 --game_id 0022301234
"""
import argparse
import asyncio
from datetime import date, timedelta

import structlog

from chalk.db.session import async_session_factory
from chalk.features.pipeline import generate_features

log = structlog.get_logger()


async def validate(player_id: int, game_id: str, as_of_date: date) -> None:
    async with async_session_factory() as session:
        print(f"\n=== Feature Validation ===")
        print(f"Player: {player_id}  Game: {game_id}  as_of_date: {as_of_date}")

        features = await generate_features(session, player_id, game_id, as_of_date)

        # Stats
        total = len(features)
        zeros = sum(1 for v in features.values() if v == 0.0)
        nulls = sum(1 for v in features.values() if v is None)

        print(f"\nFeature count: {total}")
        print(f"Zero values: {zeros}")
        print(f"Null values: {nulls}")

        # Print all features sorted
        print(f"\n--- All Features ---")
        for k in sorted(features.keys()):
            print(f"  {k:40s} = {features[k]:.4f}")

        # Leakage check: re-run with as_of_date one day earlier
        earlier_date = as_of_date - timedelta(days=1)
        print(f"\n--- Leakage Check (as_of_date - 1 day: {earlier_date}) ---")
        features_earlier = await generate_features(
            session, player_id, game_id, earlier_date,
        )
        diffs = 0
        for k in sorted(features.keys()):
            v1 = features[k]
            v2 = features_earlier.get(k, 0.0)
            if abs(v1 - v2) > 1e-6:
                diffs += 1
                print(f"  CHANGED {k}: {v2:.4f} -> {v1:.4f}")
        if diffs == 0:
            print("  WARNING: No features changed — may indicate insufficient data range")
        else:
            print(f"  {diffs} features changed (good — no leakage detected)")

        # Assertions
        assert nulls == 0, "Feature dict contains None values!"
        assert total >= 60, f"Expected 60+ features, got {total}"
        print(f"\nVALIDATION PASSED: {total} features, 0 nulls")


def main():
    parser = argparse.ArgumentParser(description="Validate feature pipeline")
    parser.add_argument("--player_id", type=int, required=True)
    parser.add_argument("--game_id", type=str, required=True)
    parser.add_argument("--as_of_date", type=str, default=None,
                        help="YYYY-MM-DD (defaults to 2024-01-15)")
    args = parser.parse_args()

    as_of = date.fromisoformat(args.as_of_date) if args.as_of_date else date(2024, 1, 15)
    asyncio.run(validate(args.player_id, args.game_id, as_of))


if __name__ == "__main__":
    main()
