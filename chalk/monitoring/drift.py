"""Model drift monitoring — compares predictions to actuals over time."""
from dataclasses import dataclass
from datetime import date, timedelta

import structlog
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from chalk.db.models import PlayerGameLog, Prediction
from chalk.models.base import MAE_TARGETS

log = structlog.get_logger()

# Baseline MAEs from model training (Phase 3 test set results)
BASELINE_MAES = {
    "pts": 4.94,
    "reb": 2.02,
    "ast": 1.47,
    "fg3m": 0.94,
}

DRIFT_THRESHOLD = 0.15  # 15% degradation triggers alert


@dataclass
class DriftReport:
    stat: str
    rolling_mae: float
    baseline_mae: float
    drift_pct: float
    is_drifting: bool
    n_predictions: int


async def compute_daily_mae(
    session: AsyncSession,
    game_date: date,
) -> dict[str, float]:
    """Compute MAE for each stat on a specific game date.

    Compares predictions (p50) to actual values from player_game_logs.
    """
    results: dict[str, float] = {}

    for stat in BASELINE_MAES:
        # Get predictions and actuals for this date
        result = await session.execute(
            select(
                Prediction.p50,
                getattr(PlayerGameLog, stat),
            )
            .join(
                PlayerGameLog,
                and_(
                    Prediction.game_id == PlayerGameLog.game_id,
                    Prediction.player_id == PlayerGameLog.player_id,
                ),
            )
            .where(PlayerGameLog.game_date == game_date)
            .where(Prediction.stat == stat)
        )
        rows = result.all()

        if not rows:
            continue

        mae = sum(abs(pred - actual) for pred, actual in rows) / len(rows)
        results[stat] = round(mae, 3)

    log.info("daily_mae_computed", game_date=str(game_date), maes=results)
    return results


async def check_for_drift(
    session: AsyncSession,
    stat: str,
    window_days: int = 30,
) -> DriftReport:
    """Check if a stat's model is drifting from its baseline performance.

    Compares rolling MAE over the last window_days to the baseline MAE
    from model training.
    """
    cutoff = date.today() - timedelta(days=window_days)
    baseline = BASELINE_MAES.get(stat, MAE_TARGETS.get(stat, 5.0))

    result = await session.execute(
        select(
            Prediction.p50,
            getattr(PlayerGameLog, stat),
        )
        .join(
            PlayerGameLog,
            and_(
                Prediction.game_id == PlayerGameLog.game_id,
                Prediction.player_id == PlayerGameLog.player_id,
            ),
        )
        .where(PlayerGameLog.game_date >= cutoff)
        .where(Prediction.stat == stat)
    )
    rows = result.all()

    if not rows:
        return DriftReport(
            stat=stat,
            rolling_mae=0.0,
            baseline_mae=baseline,
            drift_pct=0.0,
            is_drifting=False,
            n_predictions=0,
        )

    rolling_mae = sum(abs(pred - actual) for pred, actual in rows) / len(rows)
    drift_pct = (rolling_mae - baseline) / baseline if baseline > 0 else 0.0

    report = DriftReport(
        stat=stat,
        rolling_mae=round(rolling_mae, 3),
        baseline_mae=baseline,
        drift_pct=round(drift_pct, 3),
        is_drifting=drift_pct > DRIFT_THRESHOLD,
        n_predictions=len(rows),
    )

    if report.is_drifting:
        log.warning(
            "model_drift_detected",
            stat=stat,
            rolling_mae=report.rolling_mae,
            baseline_mae=report.baseline_mae,
            drift_pct=f"{report.drift_pct * 100:.1f}%",
        )

    return report
