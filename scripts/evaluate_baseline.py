"""Evaluate saved models against historical player game logs.

Usage:
    python scripts/evaluate_baseline.py --season 2024-25
    python scripts/evaluate_baseline.py --season 2024-25 --stats pts reb ast fg3m --max-rows 500
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import structlog
from sqlalchemy import func, select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from chalk.db.models import PlayerGameLog
from chalk.db.session import async_session_factory
from chalk.exceptions import ModelNotFoundError
from chalk.features.pipeline import generate_features
from chalk.models.registry import load_lgbm_model, load_model

log = structlog.get_logger()

DEFAULT_STATS = ["pts", "reb", "ast", "fg3m", "stl", "blk", "to_committed"]
LGBM_STATS = {"pts", "reb", "ast", "fg3m"}
METADATA_COLS = {"player_id", "game_id", "game_date", "season"}


def _load_best_available_model(stat: str):
    if stat in LGBM_STATS:
        try:
            return load_lgbm_model(stat)
        except (FileNotFoundError, ModelNotFoundError, OSError, ImportError):
            return load_model(stat)
    return load_model(stat)


def _align_features(features: list[dict], expected_cols: list[str]) -> pd.DataFrame:
    df = pd.DataFrame(features)
    aligned = pd.DataFrame(index=df.index)
    for col in expected_cols:
        aligned[col] = df[col] if col in df.columns else 0.0
    return aligned.fillna(0.0)


async def _qualified_logs(session, season: str, min_games: int, max_rows: int | None):
    qualified_subq = (
        select(PlayerGameLog.player_id)
        .where(PlayerGameLog.season == season)
        .group_by(PlayerGameLog.player_id)
        .having(func.count() >= min_games)
        .subquery()
    )
    stmt = (
        select(PlayerGameLog)
        .where(PlayerGameLog.season == season)
        .where(PlayerGameLog.player_id.in_(select(qualified_subq.c.player_id)))
        .order_by(PlayerGameLog.game_date.asc(), PlayerGameLog.player_id.asc())
    )
    if max_rows is not None:
        stmt = stmt.limit(max_rows)
    result = await session.execute(stmt)
    return result.scalars().all()


async def evaluate_baseline(
    season: str,
    stats: list[str],
    min_games: int,
    max_rows: int | None,
    output: Path | None,
) -> list[dict]:
    async with async_session_factory() as session:
        logs = await _qualified_logs(session, season, min_games, max_rows)
        if not logs:
            raise SystemExit(f"No player logs found for season={season} min_games={min_games}")

        feature_rows = []
        target_rows = []
        for index, game_log in enumerate(logs, start=1):
            try:
                features = await generate_features(
                    session,
                    game_log.player_id,
                    game_log.game_id,
                    game_log.game_date,
                )
            except Exception as exc:
                log.warning(
                    "baseline_feature_failed",
                    player_id=game_log.player_id,
                    game_id=game_log.game_id,
                    error=str(exc),
                )
                continue

            feature_rows.append(features)
            target_rows.append(game_log)
            if index % 250 == 0:
                log.info("baseline_progress", processed=index, total=len(logs))

        if not feature_rows:
            raise SystemExit(
                f"No features generated for season={season}; check feature errors above"
            )

        results = []
        for stat in stats:
            model = _load_best_available_model(stat)
            expected_cols = model.feature_names or [
                col for col in feature_rows[0] if col not in METADATA_COLS
            ]
            X = _align_features(feature_rows, expected_cols)
            y = np.array([float(getattr(row, stat)) for row in target_rows])
            preds = model.predict(X)
            errors = preds - y
            results.append(
                {
                    "season": season,
                    "stat": stat,
                    "rows": int(len(y)),
                    "mae": float(np.mean(np.abs(errors))),
                    "rmse": float(np.sqrt(np.mean(errors**2))),
                    "bias": float(np.mean(errors)),
                    "model_type": type(model).__name__,
                }
            )

    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(results, indent=2), encoding="utf-8")

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate saved model baseline MAE")
    parser.add_argument("--season", default="2024-25")
    parser.add_argument("--stats", nargs="+", default=DEFAULT_STATS)
    parser.add_argument("--min-games", type=int, default=20)
    parser.add_argument("--max-rows", type=int, default=None)
    parser.add_argument("--output", type=Path, default=Path(".cache/baseline_mae.json"))
    args = parser.parse_args()

    results = asyncio.run(
        evaluate_baseline(
            season=args.season,
            stats=args.stats,
            min_games=args.min_games,
            max_rows=args.max_rows,
            output=args.output,
        )
    )

    print(f"{'Stat':<14} {'Rows':>8} {'MAE':>8} {'RMSE':>8} {'Bias':>8} {'Model':>18}")
    print("-" * 72)
    for row in results:
        print(
            f"{row['stat']:<14} {row['rows']:>8} {row['mae']:>8.3f} "
            f"{row['rmse']:>8.3f} {row['bias']:>8.3f} {row['model_type']:>18}"
        )


if __name__ == "__main__":
    main()
