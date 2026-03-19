"""Phase 8 — Ensemble training pipeline.

Runs Optuna hyperparameter search, trains LightGBM alternatives,
builds stacking meta-learner, and benchmarks against Phase 3 baselines.

Usage:
    python scripts/train_ensemble.py [--stats pts reb ast fg3m] [--n-trials 50]
    python scripts/train_ensemble.py --tune-only   # Only run Optuna, skip ensemble
    python scripts/train_ensemble.py --skip-tune    # Skip Optuna, use default params
"""
import argparse
import asyncio
from pathlib import Path

import numpy as np
import pandas as pd
import structlog

from chalk.db.session import async_session_factory
from chalk.models.base import DEFAULT_XGB_PARAMS, MAE_TARGETS
from chalk.models.ensemble import StackedEnsemble
from chalk.models.lgbm import DEFAULT_LGBM_PARAMS, LGBMStatModel
from chalk.models.registry import save_ensemble_model, save_lgbm_model
from chalk.models.tuning import tune_stat
from chalk.models.validation import get_feature_cols, get_train_val_test_split

log = structlog.get_logger()

MATRIX_DIR = Path(".cache/matrices")

# Phase 3 baselines (test set MAE)
PHASE3_BASELINES = {
    "pts": 4.94,
    "reb": 2.02,
    "ast": 1.47,
    "fg3m": 0.94,
}


def load_matrix(stat: str) -> pd.DataFrame:
    """Load cached master matrix and extract stat-specific data."""
    cache_path = MATRIX_DIR / "fast_master_matrix.parquet"
    if not cache_path.exists():
        raise FileNotFoundError(
            f"Feature matrix not found at {cache_path}. "
            "Run 'python scripts/train_all.py --build-matrix' first."
        )

    master_df = pd.read_parquet(cache_path)

    # Extract stat matrix (same logic as train_all.extract_stat_matrix)
    target_col = f"target_{stat}"
    if target_col not in master_df.columns:
        raise ValueError(f"Target column {target_col} not in master matrix")

    df = master_df.dropna(subset=[target_col]).copy()
    target_cols = [c for c in df.columns if c.startswith("target_")]
    df = df.drop(columns=[c for c in target_cols if c != target_col])
    df = df.rename(columns={target_col: "target"})
    return df


def train_lgbm_model(
    df: pd.DataFrame,
    stat: str,
    lgbm_params: dict | None = None,
) -> tuple[LGBMStatModel, dict]:
    """Train a LightGBM model for a single stat."""
    feature_cols = get_feature_cols(df)
    params = lgbm_params or dict(DEFAULT_LGBM_PARAMS)

    model = LGBMStatModel(
        stat=stat,
        model_name=f"chalk_{stat}_lgbm",
        lgbm_params=params,
    )

    X_train, y_train, X_val, y_val, X_test, y_test = get_train_val_test_split(
        df, feature_cols
    )

    model.train(X_train, y_train, X_val, y_val)

    val_metrics = model.evaluate(X_val, y_val)
    test_metrics = model.evaluate(X_test, y_test)

    log.info(
        "lgbm_trained",
        stat=stat,
        val_mae=round(val_metrics["mae"], 4),
        test_mae=round(test_metrics["mae"], 4),
    )

    return model, {
        "stat": stat,
        "model_type": "lgbm",
        "val_mae": val_metrics["mae"],
        "test_mae": test_metrics["mae"],
        "test_rmse": test_metrics["rmse"],
        "test_bias": test_metrics["bias"],
    }


def train_ensemble(
    df: pd.DataFrame,
    stat: str,
    xgb_params: dict | None = None,
    lgbm_params: dict | None = None,
) -> tuple[StackedEnsemble, dict]:
    """Train a stacked ensemble for a single stat."""
    xgb_p = xgb_params or dict(DEFAULT_XGB_PARAMS)
    lgbm_p = lgbm_params or dict(DEFAULT_LGBM_PARAMS)

    feature_cols = get_feature_cols(df)
    X_train, y_train, X_val, y_val, X_test, y_test = get_train_val_test_split(
        df, feature_cols
    )

    ensemble = StackedEnsemble(stat=stat)
    oof_metrics = ensemble.train(df, xgb_p, lgbm_p)

    # Evaluate on validation and test sets
    val_metrics = ensemble.evaluate(X_val, y_val)
    test_metrics = ensemble.evaluate(X_test, y_test)

    baseline = PHASE3_BASELINES.get(stat)
    improvement = None
    if baseline:
        improvement = (baseline - test_metrics["ensemble_mae"]) / baseline * 100

    log.info(
        "ensemble_trained",
        stat=stat,
        val_ensemble_mae=round(val_metrics["ensemble_mae"], 4),
        test_ensemble_mae=round(test_metrics["ensemble_mae"], 4),
        test_xgb_mae=round(test_metrics["xgb_mae"], 4),
        test_lgbm_mae=round(test_metrics["lgbm_mae"], 4),
        improvement_pct=round(improvement, 2) if improvement else None,
    )

    return ensemble, {
        "stat": stat,
        "model_type": "ensemble",
        "oof_xgb_mae": oof_metrics["xgb_oof_mae"],
        "oof_lgbm_mae": oof_metrics["lgbm_oof_mae"],
        "oof_ensemble_mae": oof_metrics["ensemble_oof_mae"],
        "val_ensemble_mae": val_metrics["ensemble_mae"],
        "val_xgb_mae": val_metrics["xgb_mae"],
        "val_lgbm_mae": val_metrics["lgbm_mae"],
        "test_ensemble_mae": test_metrics["ensemble_mae"],
        "test_xgb_mae": test_metrics["xgb_mae"],
        "test_lgbm_mae": test_metrics["lgbm_mae"],
        "meta_weights": oof_metrics["meta_weights"],
        "baseline_mae": baseline,
        "improvement_pct": improvement,
    }


def run_pipeline(
    stats: list[str],
    n_trials: int = 50,
    tune_only: bool = False,
    skip_tune: bool = False,
) -> None:
    """Full Phase 8 pipeline: tune → LightGBM → ensemble → benchmark."""
    tuning_results = {}
    lgbm_results = {}
    ensemble_results = {}

    for stat in stats:
        log.info("phase8_stat_start", stat=stat)
        df = load_matrix(stat)

        # Step 1: Optuna hyperparameter search
        best_xgb_params = dict(DEFAULT_XGB_PARAMS)
        best_lgbm_params = dict(DEFAULT_LGBM_PARAMS)

        if not skip_tune:
            # Tune XGBoost
            xgb_tune = tune_stat(
                df, stat, model_type="xgb", n_trials=n_trials,
                storage="sqlite:///optuna.db",
            )
            tuning_results[f"{stat}_xgb"] = xgb_tune
            best_xgb_params.update(xgb_tune["best_params"])

            # Tune LightGBM
            lgbm_tune = tune_stat(
                df, stat, model_type="lgbm", n_trials=n_trials,
                storage="sqlite:///optuna.db",
            )
            tuning_results[f"{stat}_lgbm"] = lgbm_tune
            best_lgbm_params.update(lgbm_tune["best_params"])

        if tune_only:
            continue

        # Step 2: Train standalone LightGBM with best params
        lgbm_model, lgbm_res = train_lgbm_model(df, stat, best_lgbm_params)
        save_lgbm_model(lgbm_model)
        lgbm_results[stat] = lgbm_res

        # Step 3: Train stacked ensemble
        ens_model, ens_res = train_ensemble(df, stat, best_xgb_params, best_lgbm_params)
        save_ensemble_model(ens_model)
        ensemble_results[stat] = ens_res

    # Print summary
    print("\n" + "=" * 100)
    print("PHASE 8 — ENSEMBLE RESULTS")
    print("=" * 100)

    if tuning_results:
        print("\n--- Optuna Tuning ---")
        print(f"{'Study':<20} {'Best MAE':>10} {'Trials':>8}")
        print("-" * 40)
        for name, res in tuning_results.items():
            print(f"{name:<20} {res['best_mae']:>10.4f} {res['n_trials']:>8}")

    if lgbm_results:
        print("\n--- LightGBM Standalone ---")
        print(f"{'Stat':<10} {'Test MAE':>10}")
        print("-" * 22)
        for stat, res in lgbm_results.items():
            print(f"{stat:<10} {res['test_mae']:>10.4f}")

    if ensemble_results:
        print("\n--- Stacked Ensemble vs Baselines ---")
        print(f"{'Stat':<10} {'XGB MAE':>10} {'LGBM MAE':>10} {'Ensemble':>10} {'Baseline':>10} {'Improve%':>10}")
        print("-" * 62)
        for stat, res in ensemble_results.items():
            baseline = res.get("baseline_mae", 0) or 0
            improve = res.get("improvement_pct", 0) or 0
            mark = "PASS" if improve >= 2.0 else "FAIL"
            print(
                f"{stat:<10} {res['test_xgb_mae']:>10.4f} {res['test_lgbm_mae']:>10.4f} "
                f"{res['test_ensemble_mae']:>10.4f} {baseline:>10.4f} {improve:>9.2f}% {mark}"
            )

        print(f"\n{'Meta-learner weights (XGB, LGBM, hist_median):'}")
        for stat, res in ensemble_results.items():
            weights = [round(w, 4) for w in res["meta_weights"]]
            print(f"  {stat}: {weights}")

    print("=" * 100)


def main():
    parser = argparse.ArgumentParser(description="Phase 8 — Ensemble Training")
    parser.add_argument("--stats", nargs="+", default=["pts", "reb", "ast", "fg3m"])
    parser.add_argument("--n-trials", type=int, default=50)
    parser.add_argument("--tune-only", action="store_true",
                        help="Only run Optuna tuning, skip model training")
    parser.add_argument("--skip-tune", action="store_true",
                        help="Skip Optuna, use default hyperparameters")
    args = parser.parse_args()

    run_pipeline(
        stats=args.stats,
        n_trials=args.n_trials,
        tune_only=args.tune_only,
        skip_tune=args.skip_tune,
    )


if __name__ == "__main__":
    main()
