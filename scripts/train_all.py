"""Full model training pipeline.

Usage:
    python scripts/train_all.py [--stats pts reb ast fg3m] [--skip-quantile] [--min-games 100]
    python scripts/train_all.py --build-matrix  # Only build and cache feature matrices
"""
import argparse
import asyncio
from pathlib import Path

import numpy as np
import pandas as pd
import structlog
from sqlalchemy import func, select, text

from chalk.db.models import Game, Player, PlayerGameLog, TeamGameLog
from chalk.db.session import async_session_factory
from chalk.models.base import MAE_TARGETS
from chalk.models.player import PLAYER_STATS, train_player_stat_model
from chalk.models.quantile import QUANTILE_STATS, train_quantile_models
from chalk.models.registry import save_model, save_quantile_model
from chalk.models.team import train_team_total_model
from chalk.models.validation import TRAIN_SEASONS, VALID_SEASON, TEST_SEASON

log = structlog.get_logger()

MATRIX_DIR = Path(".cache/matrices")
ALL_SEASONS = TRAIN_SEASONS + [VALID_SEASON, TEST_SEASON]


async def build_master_player_matrix(session, min_games: int = 100) -> pd.DataFrame:
    """Build master feature matrix using bulk pandas rolling operations.

    Much faster than per-row DB queries (~2s vs ~40 min for 50 players).
    """
    cache_path = MATRIX_DIR / "fast_master_matrix.parquet"
    if cache_path.exists():
        log.info("master_matrix_cache_hit", path=str(cache_path))
        return pd.read_parquet(cache_path)

    log.info("building_master_matrix_fast")

    # Load all data in bulk
    r = await session.execute(
        select(PlayerGameLog).where(PlayerGameLog.season.in_(ALL_SEASONS))
        .order_by(PlayerGameLog.game_date.asc())
    )
    logs = r.scalars().all()

    r2 = await session.execute(select(Game).where(Game.season.in_(ALL_SEASONS)))
    games = {g.game_id: g for g in r2.scalars().all()}

    r3 = await session.execute(select(Player))
    players = {p.player_id: p for p in r3.scalars().all()}

    r4 = await session.execute(
        select(TeamGameLog).where(TeamGameLog.season.in_(ALL_SEASONS))
        .order_by(TeamGameLog.game_date.asc())
    )
    team_logs = r4.scalars().all()

    # Build base dataframe
    rows = []
    for l in logs:
        game = games.get(l.game_id)
        player = players.get(l.player_id)
        if not game or not player:
            continue
        is_home = game.home_team_id == l.team_id
        opp_team_id = game.away_team_id if is_home else game.home_team_id
        rows.append({
            "player_id": l.player_id, "game_id": l.game_id,
            "game_date": pd.Timestamp(l.game_date), "season": l.season,
            "team_id": l.team_id, "opp_team_id": opp_team_id,
            "is_home": int(is_home),
            "min_played": l.min_played, "pts": l.pts, "reb": l.reb, "ast": l.ast,
            "stl": l.stl, "blk": l.blk, "to_committed": l.to_committed,
            "fg3m": l.fg3m, "fg3a": l.fg3a, "fgm": l.fgm, "fga": l.fga,
            "ftm": l.ftm, "fta": l.fta, "plus_minus": l.plus_minus,
        })
    df = pd.DataFrame(rows).sort_values(["player_id", "game_date"]).reset_index(drop=True)

    # Filter to qualified players
    game_counts = df.groupby("player_id").size()
    qualified = game_counts[game_counts >= min_games].index
    df = df[df["player_id"].isin(qualified)].reset_index(drop=True)
    log.info("qualified_players", count=df["player_id"].nunique(), rows=len(df))

    # Opponent team features
    tgl_rows = [{
        "team_id": t.team_id, "game_date": pd.Timestamp(t.game_date),
        "opp_pts": t.pts, "opp_ast": t.ast,
        "opp_to": t.to_committed, "opp_oreb": t.oreb, "opp_dreb": t.dreb,
    } for t in team_logs]
    tgl = pd.DataFrame(tgl_rows).sort_values(["team_id", "game_date"]).reset_index(drop=True)

    for window in [10, 15]:
        for col in ["opp_pts", "opp_ast", "opp_to"]:
            shifted = tgl.groupby("team_id")[col].shift(1)
            rolled = shifted.groupby(tgl["team_id"]).rolling(window, min_periods=3).mean()
            tgl[f"{col}_avg_{window}g"] = rolled.reset_index(level=0, drop=True)

    # Player rolling features (shifted by 1 for as_of_date gate)
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

    # Home/away splits
    for split_val, split_name in [(1, "home"), (0, "away")]:
        mask = df["is_home"] == split_val
        for col in ["pts", "reb", "ast"]:
            vals = df[col].where(mask)
            shifted = vals.groupby(df["player_id"]).shift(1)
            rolled = shifted.groupby(df["player_id"]).rolling(10, min_periods=1).mean()
            df[f"{col}_avg_10g_{split_name}"] = rolled.reset_index(level=0, drop=True)

    # Rest days
    df["prev_game_date"] = df.groupby("player_id")["game_date"].shift(1)
    df["days_rest"] = (df["game_date"] - df["prev_game_date"]).dt.days.fillna(3).clip(0, 10)
    df["is_back_to_back"] = (df["days_rest"] <= 1).astype(float)
    df["is_well_rested"] = (df["days_rest"] >= 3).astype(float)

    # Season context
    df["game_number_in_season"] = df.groupby(["player_id", "season"]).cumcount() + 1
    df["is_second_half_season"] = (df["game_number_in_season"] > 41).astype(float)

    # Derived features
    df["pts_momentum"] = df["pts_avg_5g"] - df["pts_avg_20g"]
    df["min_trend"] = df["min_played_avg_5g"] - df["min_played_avg_20g"]
    df["fg_pct_10g"] = df["fgm_avg_10g"] / df["fga_avg_10g"].replace(0, 1)
    df["fg3_pct_10g"] = df["fg3m_avg_10g"] / df["fg3a_avg_10g"].replace(0, 1)
    df["ft_pct_10g"] = df["ftm_avg_10g"] / df["fta_avg_10g"].replace(0, 1)
    df["ts_pct_10g"] = df["pts_avg_10g"] / (2 * (df["fga_avg_10g"] + 0.44 * df["fta_avg_10g"])).replace(0, 1)
    df["pts_trend_10g"] = df["pts_avg_5g"] - df["pts_avg_10g"]
    df["reb_trend_10g"] = df["reb_avg_5g"] - df["reb_avg_10g"]
    df["ast_trend_10g"] = df["ast_avg_5g"] - df["ast_avg_10g"]
    df["ast_to_ratio_10g"] = df["ast_avg_10g"] / df["to_committed_avg_10g"].replace(0, 1)
    df["fg3a_rate_10g"] = df["fg3a_avg_10g"] / df["fga_avg_10g"].replace(0, 1)
    df["ft_rate_10g"] = df["fta_avg_10g"] / df["fga_avg_10g"].replace(0, 1)

    # Usage rate & opportunity score
    team_fga = df.groupby(["team_id", "game_date"])["fga"].transform("sum").replace(0, 1)
    df["usage_rate_approx"] = df["fga"] / team_fga
    shifted_usage = df.groupby("player_id")["usage_rate_approx"].shift(1)
    df["usage_rate_10g"] = shifted_usage.groupby(df["player_id"]).rolling(10, min_periods=1).mean().reset_index(level=0, drop=True)
    df["opportunity_score"] = df["min_played_avg_10g"] * df["usage_rate_10g"]

    # Minutes share
    team_min = df.groupby(["team_id", "game_date"])["min_played"].transform("sum").replace(0, 1)
    df["min_share_raw"] = df["min_played"] / team_min
    shifted_ms = df.groupby("player_id")["min_share_raw"].shift(1)
    df["min_share_10g"] = shifted_ms.groupby(df["player_id"]).rolling(10, min_periods=1).mean().reset_index(level=0, drop=True)

    # Starter rate
    df["was_starter"] = (df["min_played"] >= 20).astype(float)
    shifted_start = df.groupby("player_id")["was_starter"].shift(1)
    df["starter_rate_10g"] = shifted_start.groupby(df["player_id"]).rolling(10, min_periods=1).mean().reset_index(level=0, drop=True)

    # Merge opponent features
    opp_feat_cols = [c for c in tgl.columns if c.endswith(("_avg_10g", "_avg_15g"))]
    tgl_merge = tgl[["team_id", "game_date"] + opp_feat_cols].rename(columns={"team_id": "opp_team_id"})
    df = df.merge(tgl_merge, on=["opp_team_id", "game_date"], how="left", suffixes=("", "_dup"))
    for c in opp_feat_cols:
        if c in df.columns:
            df[c] = df[c].fillna(0)

    # Target columns
    for stat in ["pts", "reb", "ast", "fg3m", "stl", "blk", "to_committed"]:
        df[f"target_{stat}"] = df[stat].astype(float)

    # Feature columns (exclude raw stats, metadata, targets)
    raw_stats = {"pts", "reb", "ast", "stl", "blk", "to_committed", "fg3m", "fg3a",
                 "fgm", "fga", "ftm", "fta", "min_played", "plus_minus"}
    meta = {"player_id", "game_id", "game_date", "season", "team_id", "opp_team_id",
            "prev_game_date", "is_home", "usage_rate_approx", "min_share_raw", "was_starter"} | raw_stats
    targets = {c for c in df.columns if c.startswith("target_")}
    dups = {c for c in df.columns if c.endswith("_dup")}
    feat_cols = sorted([c for c in df.columns if c not in meta and c not in targets and c not in dups])

    df = df.dropna(subset=feat_cols).reset_index(drop=True)

    MATRIX_DIR.mkdir(parents=True, exist_ok=True)
    save_cols = feat_cols + list(targets) + ["player_id", "game_id", "game_date", "season"]
    df[save_cols].to_parquet(cache_path, index=False)
    log.info("master_matrix_built", rows=len(df), features=len(feat_cols),
             players=df["player_id"].nunique())
    return df[save_cols]


def extract_stat_matrix(master_df: pd.DataFrame, stat: str) -> pd.DataFrame:
    """Extract a single-stat matrix from the master matrix.

    Renames target_{stat} to 'target' and drops other target columns.
    """
    target_col = f"target_{stat}"
    if target_col not in master_df.columns:
        raise ValueError(f"Target column {target_col} not in master matrix")

    df = master_df.dropna(subset=[target_col]).copy()
    target_cols = [c for c in df.columns if c.startswith("target_")]
    df = df.drop(columns=[c for c in target_cols if c != target_col])
    df = df.rename(columns={target_col: "target"})
    return df


async def build_team_matrix(session) -> pd.DataFrame:
    """Build feature matrix for team total points model.

    Uses aggregated player_game_logs for shooting efficiency + team_game_logs
    for box score rolling averages. All computed in pandas for speed.
    """
    cache_path = MATRIX_DIR / "team_total_matrix.parquet"
    if cache_path.exists():
        log.info("team_matrix_cache_hit", path=str(cache_path))
        return pd.read_parquet(cache_path)

    log.info("building_team_matrix")

    # 1. Load all team game logs into pandas
    result = await session.execute(
        select(TeamGameLog)
        .where(TeamGameLog.season.in_(ALL_SEASONS))
        .order_by(TeamGameLog.game_date.asc())
    )
    tgl_rows = [
        {
            "game_id": r.game_id, "team_id": r.team_id, "game_date": r.game_date,
            "season": r.season, "pts": r.pts, "ast": r.ast,
            "to_committed": r.to_committed, "oreb": r.oreb, "dreb": r.dreb,
        }
        for r in result.scalars().all()
    ]
    tgl = pd.DataFrame(tgl_rows)
    if tgl.empty:
        return pd.DataFrame()

    # 2. Aggregate player_game_logs by game+team for shooting stats
    result = await session.execute(
        select(
            PlayerGameLog.game_id,
            PlayerGameLog.team_id,
            func.sum(PlayerGameLog.fgm).label("fgm"),
            func.sum(PlayerGameLog.fga).label("fga"),
            func.sum(PlayerGameLog.fg3m).label("fg3m"),
            func.sum(PlayerGameLog.fg3a).label("fg3a"),
            func.sum(PlayerGameLog.ftm).label("ftm"),
            func.sum(PlayerGameLog.fta).label("fta"),
        )
        .where(PlayerGameLog.season.in_(ALL_SEASONS))
        .group_by(PlayerGameLog.game_id, PlayerGameLog.team_id)
    )
    shoot_rows = [dict(r._mapping) for r in result.all()]
    shoot_df = pd.DataFrame(shoot_rows)

    # Merge shooting stats into team game logs
    tgl = tgl.merge(shoot_df, on=["game_id", "team_id"], how="left")
    for col in ["fgm", "fga", "fg3m", "fg3a", "ftm", "fta"]:
        tgl[col] = tgl[col].fillna(0).astype(float)

    # Compute efficiency metrics per team-game
    tgl["fg_pct"] = (tgl["fgm"] / tgl["fga"].replace(0, 1)).clip(0, 1)
    tgl["fg3_pct"] = (tgl["fg3m"] / tgl["fg3a"].replace(0, 1)).clip(0, 1)
    tgl["ft_pct"] = (tgl["ftm"] / tgl["fta"].replace(0, 1)).clip(0, 1)
    tgl["efg_pct"] = ((tgl["fgm"] + 0.5 * tgl["fg3m"]) / tgl["fga"].replace(0, 1)).clip(0, 1)
    tgl["ts_pct_calc"] = (tgl["pts"] / (2 * (tgl["fga"] + 0.44 * tgl["fta"])).replace(0, 1)).clip(0, 1)
    tgl["reb"] = tgl["oreb"] + tgl["dreb"]
    # Pace proxy: possessions ≈ FGA - OREB + TO + 0.44*FTA
    tgl["pace_proxy"] = tgl["fga"] - tgl["oreb"] + tgl["to_committed"] + 0.44 * tgl["fta"]

    # 3. Sort and compute rolling features per team
    tgl["game_date"] = pd.to_datetime(tgl["game_date"])
    tgl = tgl.sort_values(["team_id", "game_date"]).reset_index(drop=True)

    # Rest days between games
    tgl["prev_game_date"] = tgl.groupby("team_id")["game_date"].shift(1)
    tgl["rest_days"] = (tgl["game_date"] - tgl["prev_game_date"]).dt.days.fillna(3).clip(0, 10)
    tgl["is_back_to_back"] = (tgl["rest_days"] <= 1).astype(float)

    # Game number within season (proxy for early vs late season)
    tgl["season_game_num"] = tgl.groupby(["team_id", "season"]).cumcount() + 1

    stat_cols = [
        "pts", "ast", "to_committed", "oreb", "dreb", "reb",
        "fg_pct", "fg3_pct", "ft_pct", "efg_pct", "ts_pct_calc", "pace_proxy",
        "fga", "fg3a", "fta",
    ]
    for window in [5, 10, 20]:
        rolled = (
            tgl.groupby("team_id")[stat_cols]
            .shift(1)  # shift so we don't include current game (as_of_date gate)
            .groupby(tgl["team_id"])
            .rolling(window, min_periods=1)
            .mean()
            .reset_index(level=0, drop=True)
        )
        for col in stat_cols:
            tgl[f"{col}_avg_{window}g"] = rolled[col]

    # Pts std over last 10
    tgl["pts_std_10g"] = (
        tgl.groupby("team_id")["pts"]
        .shift(1)
        .groupby(tgl["team_id"])
        .rolling(10, min_periods=3)
        .std()
        .reset_index(level=0, drop=True)
    )
    tgl["pts_std_10g"] = tgl["pts_std_10g"].fillna(0)

    # 4. Load games to get home/away mapping
    result = await session.execute(
        select(Game).where(Game.season.in_(ALL_SEASONS))
    )
    games_list = [
        {"game_id": g.game_id, "game_date": g.date, "season": g.season,
         "home_team_id": g.home_team_id, "away_team_id": g.away_team_id}
        for g in result.scalars().all()
    ]
    games_df = pd.DataFrame(games_list)

    # 5. Build final matrix: one row per game with home/away features
    # Get home team stats
    home_tgl = tgl.copy()
    home_tgl = home_tgl.rename(columns={"team_id": "home_team_id"})
    rolling_cols = [c for c in home_tgl.columns if c.endswith(("_avg_5g", "_avg_10g", "_avg_20g", "_std_10g"))]
    extra_cols = ["rest_days", "is_back_to_back", "season_game_num"]
    feature_cols_to_join = rolling_cols + extra_cols
    home_cols = {c: f"home_{c}" for c in feature_cols_to_join}
    home_join = home_tgl[["game_id", "home_team_id", "pts"] + feature_cols_to_join].rename(columns={**home_cols, "pts": "home_pts"})

    away_tgl = tgl.copy()
    away_tgl = away_tgl.rename(columns={"team_id": "away_team_id"})
    away_cols = {c: f"away_{c}" for c in feature_cols_to_join}
    away_join = away_tgl[["game_id", "away_team_id", "pts"] + feature_cols_to_join].rename(columns={**away_cols, "pts": "away_pts"})

    final = games_df.merge(home_join, on=["game_id", "home_team_id"], how="inner")
    final = final.merge(away_join, on=["game_id", "away_team_id"], how="inner")

    # Target: total points
    final["target"] = final["home_pts"].astype(float) + final["away_pts"].astype(float)

    # Derived features
    for w in ["5g", "10g", "20g"]:
        final[f"combined_pts_avg_{w}"] = final[f"home_pts_avg_{w}"] + final[f"away_pts_avg_{w}"]
        final[f"combined_pace_proxy_{w}"] = final[f"home_pace_proxy_avg_{w}"] + final[f"away_pace_proxy_avg_{w}"]
        final[f"combined_efg_{w}"] = final[f"home_efg_pct_avg_{w}"] + final[f"away_efg_pct_avg_{w}"]
        final[f"pts_diff_{w}"] = final[f"home_pts_avg_{w}"] - final[f"away_pts_avg_{w}"]
    final["total_rest_days"] = final["home_rest_days"] + final["away_rest_days"]
    final["both_b2b"] = final["home_is_back_to_back"] * final["away_is_back_to_back"]

    # Drop join keys and raw pts, keep features + metadata
    drop_cols = ["home_team_id", "away_team_id", "home_pts", "away_pts"]
    final = final.drop(columns=drop_cols, errors="ignore")
    final["game_date"] = final["game_date"].astype(str)

    # Drop rows with NaN features (first few games of each season)
    feature_only = [c for c in final.columns if c not in {"target", "season", "game_id", "game_date"}]
    final = final.dropna(subset=feature_only).reset_index(drop=True)

    MATRIX_DIR.mkdir(parents=True, exist_ok=True)
    final.to_parquet(cache_path, index=False)
    log.info("team_matrix_built", rows=len(final), features=len(feature_only))
    return final


async def run_training(
    stats: list[str],
    skip_quantile: bool,
    min_games: int,
) -> None:
    async with async_session_factory() as session:
        # Build master matrix using fast bulk approach
        master_df = await build_master_player_matrix(session, min_games=min_games)

        summary = []

        # Train player models using extracted sub-matrices
        for stat in stats:
            df = extract_stat_matrix(master_df, stat)
            if df.empty:
                log.warning("empty_matrix", stat=stat)
                continue

            model, results = train_player_stat_model(df, stat)
            save_model(model)
            summary.append(results)

            # Quantile models for selected stats
            if not skip_quantile and stat in QUANTILE_STATS:
                q_models, coverage = train_quantile_models(df, stat)
                for q, qm in q_models.items():
                    save_quantile_model(stat, q, qm)
                results["quantile_coverage"] = coverage

        # Team total model
        team_df = await build_team_matrix(session)
        if not team_df.empty:
            team_model, team_results = train_team_total_model(team_df)
            save_model(team_model)
            summary.append(team_results)

    # Print summary table
    print("\n" + "=" * 80)
    print(f"{'Stat':<15} {'Val MAE':>10} {'Test MAE':>10} {'Target':>10} {'Pass':>8}")
    print("-" * 80)
    for r in summary:
        mark = "YES" if r["meets_target"] else "NO"
        print(
            f"{r['stat']:<15} {r['val_mae']:>10.3f} {r['test_mae']:>10.3f} "
            f"{r['target_mae']:>10.1f} {mark:>8}"
        )
    print("=" * 80)


def main():
    parser = argparse.ArgumentParser(description="Train all models")
    parser.add_argument("--stats", nargs="+", default=["pts", "reb", "ast", "fg3m"])
    parser.add_argument("--skip-quantile", action="store_true")
    parser.add_argument("--min-games", type=int, default=100,
                        help="Minimum games for a player to be included")
    parser.add_argument("--build-matrix", action="store_true",
                        help="Only build matrices, don't train")
    args = parser.parse_args()

    asyncio.run(run_training(args.stats, args.skip_quantile, args.min_games))


if __name__ == "__main__":
    main()
