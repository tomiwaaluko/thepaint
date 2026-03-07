"""Distribution builder — assembles StatPrediction from model outputs."""
import numpy as np

from chalk.api.schemas import StatPrediction
from chalk.models.base import MAE_TARGETS

# Confidence spread thresholds per stat
_SPREAD_THRESHOLDS = {
    "pts": 14,
    "reb": 8,
    "ast": 6,
    "fg3m": 3,
    "stl": 2,
    "blk": 2,
    "to_committed": 3,
}


def compute_confidence(stat: str, p10: float, p90: float) -> str:
    """Determine confidence tier based on prediction spread."""
    spread = p90 - p10
    threshold = _SPREAD_THRESHOLDS.get(stat, 10)
    if spread < threshold * 0.7:
        return "high"
    if spread > threshold * 1.3:
        return "low"
    return "medium"


def fix_quantile_crossing(predictions: dict[float, float]) -> dict[float, float]:
    """Fix crossed quantile predictions via isotonic sort."""
    sorted_q = sorted(predictions.keys())
    values = [predictions[q] for q in sorted_q]
    # Isotonic regression: enforce non-decreasing
    fixed = list(np.maximum.accumulate(values))
    return dict(zip(sorted_q, fixed))


def estimate_interval_from_mae(p50: float, stat: str) -> dict[float, float]:
    """Estimate quantile intervals for stats without quantile models."""
    mae = MAE_TARGETS.get(stat, 2.0)
    return {
        0.10: max(0.0, p50 - 1.5 * mae),
        0.25: max(0.0, p50 - 0.8 * mae),
        0.50: p50,
        0.75: p50 + 0.8 * mae,
        0.90: p50 + 1.5 * mae,
    }


def build_stat_prediction(
    stat: str,
    quantile_preds: dict[float, float] | None,
    point_pred: float,
) -> StatPrediction:
    """Build a StatPrediction from model outputs.

    If quantile_preds is provided, uses those. Otherwise estimates intervals
    from the point prediction and known MAE targets.
    """
    if quantile_preds:
        preds = fix_quantile_crossing(quantile_preds)
    else:
        preds = estimate_interval_from_mae(point_pred, stat)

    p10 = round(max(0.0, preds[0.10]), 2)
    p25 = round(max(0.0, preds[0.25]), 2)
    p50 = round(max(0.0, preds[0.50]), 2)
    p75 = round(preds[0.75], 2)
    p90 = round(preds[0.90], 2)

    return StatPrediction(
        stat=stat,
        p10=p10,
        p25=p25,
        p50=p50,
        p75=p75,
        p90=p90,
        confidence=compute_confidence(stat, p10, p90),
    )
