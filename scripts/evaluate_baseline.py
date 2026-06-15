"""Evaluate saved models against historical player game logs.

Usage:
    python scripts/evaluate_baseline.py --season 2024-25
    python scripts/evaluate_baseline.py --season 2024-25 --stats pts reb ast fg3m --max-rows 500
    python scripts/evaluate_baseline.py --season 2024-25 --method pipeline  # exact but slow
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

from chalk.db.models import Game, Player, PlayerGameLog, TeamGameLog
from chalk.db.session import async_session_factory
from chalk.exceptions import ModelNotFoundError
from chalk.features.pipeline import generate_features
from chalk.models.registry import load_lgbm_model, load_model

log = structlog.get_logger()

DEFAULT_STATS = ["pts", "reb", "ast", "fg3m", "stl", "blk", "to_committed"]
LGBM_STATS = {"pts", "reb", "ast", "fg3m"}
METADATA_COLS = {"player_id", "game_id", "game_date", "season"}
TARGET_PREFIX = "target_"

RAW_STATS = {
    "pts", "reb", "ast", "stl", "blk", "to_committed", "fg3m", "fg3a",
    "fgm", "fga", "ftm", "fta", "min_played", "plus_minus",
}


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


def _align_feature_frame(df: pd.DataFrame, expected_cols: list[str]) -> pd.DataFrame:
    aligned = pd.DataFrame(index=df.index)
    for col in expected_cols:
        aligned[col] = df[col] if col in df.columns else 0.0
    return aligned.fillna(0.0)


def _score_stat(
    season: str,
    stat: str,
    X: pd.DataFrame,
    y: pd.Series | np.ndarray,
) -> dict:
    model = _load_best_available_model(stat)
    expected_cols = model.feature_names or list(X.columns)
    aligned = _align_feature_frame(X, expected_cols)
    y_arr = np.array(y, dtype=float)
    preds = model.predict(aligned)
    errors = preds - y_arr
    return {
        "season": season,
        "stat": stat,
        "rows": int(len(y_arr)),
        "mae": float(np.mean(np.abs(errors))),
        "rmse": float(np.sqrt(np.mean(errors**2))),
        "bias": float(np.mean(errors)),
        "model_type": type(model).__name__,
    }


async def _bulk_eval_matrix(
    session,
    season: str,
    min_games: int,
    max_rows: int | None,
) -> pd.DataFrame:
    """Build a fast, leakage-safe evaluation matrix for one season.

    This mirrors the bulk feature construction used by scripts/train_all.py.
    Rolling features are shifted by one game, so a row never sees its own
    target box score.
    """
    date_range = await session.execute(
        select(func.min(PlayerGameLog.game_date), func.max(PlayerGameLog.game_date))
        .where(PlayerGameLog.season == season)
    )
    min_date, max_date = date_range.one()
    if min_date is None or max_date is None:
        return pd.DataFrame()

    logs_result = await session.execute(
        select(PlayerGameLog)
        .where(PlayerGameLog.game_date <= max_date)
        .order_by(PlayerGameLog.game_date.asc())
    )
    logs = logs_result.scalars().all()

    games_result = await session.execute(select(Game).where(Game.date <= max_date))
    games = {g.game_id: g for g in games_result.scalars().all()}

    players_result = await session.execute(select(Player))
    players = {p.player_id: p for p in players_result.scalars().all()}

    team_logs_result = await session.execute(
        select(TeamGameLog)
        .where(TeamGameLog.game_date <= max_date)
        .order_by(TeamGameLog.game_date.asc())
    )
    team_logs = team_logs_result.scalars().all()

    rows = []
    for log_row in logs:
        game = games.get(log_row.game_id)
        player = players.get(log_row.player_id)
        if not game or not player:
            continue
        is_home = game.home_team_id == log_row.team_id
        opp_team_id = game.away_team_id if is_home else game.home_team_id
        rows.append({
            "player_id": log_row.player_id,
            "game_id": log_row.game_id,
            "game_date": pd.Timestamp(log_row.game_date),
            "season": log_row.season,
            "team_id": log_row.team_id,
            "opp_team_id": opp_team_id,
            "is_home": int(is_home),
            "min_played": log_row.min_played,
            "pts": log_row.pts,
            "reb": log_row.reb,
            "ast": log_row.ast,
            "stl": log_row.stl,
            "blk": log_row.blk,
            "to_committed": log_row.to_committed,
            "fg3m": log_row.fg3m,
            "fg3a": log_row.fg3a,
            "fgm": log_row.fgm,
            "fga": log_row.fga,
            "ftm": log_row.ftm,
            "fta": log_row.fta,
            "plus_minus": log_row.plus_minus,
        })

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df = df.sort_values(["player_id", "game_date"]).reset_index(drop=True)

    eligible_counts = df[df["season"] == season].groupby("player_id").size()
    eligible_players = eligible_counts[eligible_counts >= min_games].index

    tgl_rows = [{
        "team_id": row.team_id,
        "game_date": pd.Timestamp(row.game_date),
        "opp_pts": row.pts,
        "opp_ast": row.ast,
        "opp_to": row.to_committed,
        "opp_oreb": row.oreb,
        "opp_dreb": row.dreb,
    } for row in team_logs]
    tgl = pd.DataFrame(tgl_rows)
    if not tgl.empty:
        tgl = tgl.sort_values(["team_id", "game_date"]).reset_index(drop=True)
        for window in [10, 15]:
            for col in ["opp_pts", "opp_ast", "opp_to"]:
                shifted = tgl.groupby("team_id")[col].shift(1)
                rolled = shifted.groupby(tgl["team_id"]).rolling(window, min_periods=3).mean()
                tgl[f"{col}_avg_{window}g"] = rolled.reset_index(level=0, drop=True)

    stat_cols = [
        "min_played", "pts", "reb", "ast", "stl", "blk", "to_committed",
        "fg3m", "fg3a", "fgm", "fga", "ftm", "fta", "plus_minus",
    ]
    for window in [5, 10, 20]:
        shifted = df.groupby("player_id")[stat_cols].shift(1)
        rolled = shifted.groupby(df["player_id"]).rolling(window, min_periods=1).mean()
        rolled = rolled.reset_index(level=0, drop=True)
        for col in stat_cols:
            df[f"{col}_avg_{window}g"] = rolled[col]

    for split_val, split_name in [(1, "home"), (0, "away")]:
        mask = df["is_home"] == split_val
        for col in ["pts", "reb", "ast"]:
            vals = df[col].where(mask)
            shifted = vals.groupby(df["player_id"]).shift(1)
            rolled = shifted.groupby(df["player_id"]).rolling(10, min_periods=1).mean()
            df[f"{col}_avg_10g_{split_name}"] = rolled.reset_index(level=0, drop=True)

    df["prev_game_date"] = df.groupby("player_id")["game_date"].shift(1)
    df["days_rest"] = (df["game_date"] - df["prev_game_date"]).dt.days.fillna(3).clip(0, 10)
    df["is_back_to_back"] = (df["days_rest"] <= 1).astype(float)
    df["is_well_rested"] = (df["days_rest"] >= 3).astype(float)

    df["game_number_in_season"] = df.groupby(["player_id", "season"]).cumcount() + 1
    df["is_second_half_season"] = (df["game_number_in_season"] > 41).astype(float)

    df["pts_momentum"] = df["pts_avg_5g"] - df["pts_avg_20g"]
    df["min_trend"] = df["min_played_avg_5g"] - df["min_played_avg_20g"]
    df["fg_pct_10g"] = df["fgm_avg_10g"] / df["fga_avg_10g"].replace(0, 1)
    df["fg3_pct_10g"] = df["fg3m_avg_10g"] / df["fg3a_avg_10g"].replace(0, 1)
    df["ft_pct_10g"] = df["ftm_avg_10g"] / df["fta_avg_10g"].replace(0, 1)
    df["ts_pct_10g"] = (
        df["pts_avg_10g"] / (2 * (df["fga_avg_10g"] + 0.44 * df["fta_avg_10g"])).replace(0, 1)
    )
    df["pts_trend_10g"] = df["pts_avg_5g"] - df["pts_avg_10g"]
    df["reb_trend_10g"] = df["reb_avg_5g"] - df["reb_avg_10g"]
    df["ast_trend_10g"] = df["ast_avg_5g"] - df["ast_avg_10g"]
    df["ast_to_ratio_10g"] = df["ast_avg_10g"] / df["to_committed_avg_10g"].replace(0, 1)
    df["fg3a_rate_10g"] = df["fg3a_avg_10g"] / df["fga_avg_10g"].replace(0, 1)
    df["ft_rate_10g"] = df["fta_avg_10g"] / df["fga_avg_10g"].replace(0, 1)

    team_fga = df.groupby(["team_id", "game_date"])["fga"].transform("sum").replace(0, 1)
    df["usage_rate_approx"] = df["fga"] / team_fga
    shifted_usage = df.groupby("player_id")["usage_rate_approx"].shift(1)
    df["usage_rate_10g"] = (
        shifted_usage.groupby(df["player_id"]).rolling(10, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
    )
    df["opportunity_score"] = df["min_played_avg_10g"] * df["usage_rate_10g"]

    team_min = df.groupby(["team_id", "game_date"])["min_played"].transform("sum").replace(0, 1)
    df["min_share_raw"] = df["min_played"] / team_min
    shifted_min_share = df.groupby("player_id")["min_share_raw"].shift(1)
    df["min_share_10g"] = (
        shifted_min_share.groupby(df["player_id"]).rolling(10, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
    )

    df["was_starter"] = (df["min_played"] >= 20).astype(float)
    shifted_start = df.groupby("player_id")["was_starter"].shift(1)
    df["starter_rate_10g"] = (
        shifted_start.groupby(df["player_id"]).rolling(10, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
    )

    if not tgl.empty:
        opp_feat_cols = [c for c in tgl.columns if c.endswith(("_avg_10g", "_avg_15g"))]
        tgl_merge = tgl[["team_id", "game_date"] + opp_feat_cols].rename(
            columns={"team_id": "opp_team_id"}
        )
        df = df.merge(tgl_merge, on=["opp_team_id", "game_date"], how="left", suffixes=("", "_dup"))

    for stat in DEFAULT_STATS:
        df[f"{TARGET_PREFIX}{stat}"] = df[stat].astype(float)

    target_mask = (df["season"] == season) & df["player_id"].isin(eligible_players)
    df = df.loc[target_mask].sort_values(["game_date", "player_id"]).reset_index(drop=True)
    if max_rows is not None:
        df = df.head(max_rows)

    meta = {
        "player_id", "game_id", "game_date", "season", "team_id", "opp_team_id",
        "prev_game_date", "is_home", "usage_rate_approx", "min_share_raw", "was_starter",
    } | RAW_STATS
    targets = {col for col in df.columns if col.startswith(TARGET_PREFIX)}
    dups = {col for col in df.columns if col.endswith("_dup")}
    feature_cols = sorted([col for col in df.columns if col not in meta and col not in targets and col not in dups])
    keep_cols = feature_cols + sorted(targets) + ["player_id", "game_id", "game_date", "season"]
    return df[keep_cols]


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
    method: str,
) -> list[dict]:
    async with async_session_factory() as session:
        if method == "bulk":
            matrix = await _bulk_eval_matrix(session, season, min_games, max_rows)
            if matrix.empty:
                raise SystemExit(f"No player logs found for season={season} min_games={min_games}")

            results = []
            feature_cols = [
                col for col in matrix.columns
                if col not in METADATA_COLS and not col.startswith(TARGET_PREFIX)
            ]
            X = matrix[feature_cols]
            for stat in stats:
                target_col = f"{TARGET_PREFIX}{stat}"
                if target_col not in matrix.columns:
                    raise SystemExit(f"Target column {target_col} not available")
                results.append(_score_stat(season, stat, X, matrix[target_col]))
            if output:
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(json.dumps(results, indent=2), encoding="utf-8")
            return results

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
            results.append(_score_stat(season, stat, X, y))

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
    parser.add_argument(
        "--method",
        choices=["bulk", "pipeline"],
        default="bulk",
        help="bulk mirrors training matrix features; pipeline uses exact API feature generation but is slow",
    )
    args = parser.parse_args()

    results = asyncio.run(
        evaluate_baseline(
            season=args.season,
            stats=args.stats,
            min_games=args.min_games,
            max_rows=args.max_rows,
            output=args.output,
            method=args.method,
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
