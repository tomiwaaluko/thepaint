"""Edge tracking — model vs. market performance over time."""
from datetime import date, timedelta

import structlog
from sqlalchemy import select, text, func
from sqlalchemy.ext.asyncio import AsyncSession

from chalk.db.models import BettingLine, PlayerGameLog, Prediction

log = structlog.get_logger()


async def log_prediction_vs_result(
    session: AsyncSession,
    pred_id: int,
    actual_value: float,
) -> None:
    """Record actual vs. predicted after a game is final.

    Used for drift monitoring in Phase 7.
    """
    pred = await session.get(Prediction, pred_id)
    if not pred:
        log.warning("prediction_not_found", pred_id=pred_id)
        return

    # Store the result — we'll add a result column later.
    # For now, log the comparison for tracking.
    error = actual_value - pred.p50
    log.info(
        "prediction_result",
        pred_id=pred_id,
        stat=pred.stat,
        predicted=pred.p50,
        actual=actual_value,
        error=error,
    )


async def calculate_clv(
    session: AsyncSession,
    player_id: int,
    stat: str,
    game_id: str,
) -> float | None:
    """Closing Line Value: compare model's prediction to Vegas closing line.

    Positive CLV means model was sharper than the market.
    Returns None if closing line not available.
    """
    # Get model prediction
    result = await session.execute(
        select(Prediction)
        .where(Prediction.game_id == game_id)
        .where(Prediction.player_id == player_id)
        .where(Prediction.stat == stat)
        .order_by(Prediction.created_at.desc())
        .limit(1)
    )
    pred = result.scalar_one_or_none()
    if not pred:
        return None

    # Get closing betting line
    result = await session.execute(
        select(BettingLine)
        .where(BettingLine.game_id == game_id)
        .where(BettingLine.player_id == player_id)
        .where(BettingLine.market == stat)
        .order_by(BettingLine.timestamp.desc())
        .limit(1)
    )
    line = result.scalar_one_or_none()
    if not line:
        return None

    # CLV = how much our line differs from market close
    # If we predicted over and the line moved up, that's positive CLV
    return round(pred.p50 - line.line, 2)


async def get_edge_summary(
    session: AsyncSession,
    days: int = 30,
) -> dict:
    """Rolling summary of model prediction accuracy.

    Returns hit rate, mean absolute error, and count of predictions.
    """
    cutoff = date.today() - timedelta(days=days)

    # Get recent predictions with actual results
    result = await session.execute(
        select(Prediction, PlayerGameLog)
        .join(
            PlayerGameLog,
            (Prediction.game_id == PlayerGameLog.game_id)
            & (Prediction.player_id == PlayerGameLog.player_id),
        )
        .where(Prediction.created_at >= cutoff)
        .where(Prediction.stat == "pts")
    )
    rows = result.all()

    if not rows:
        return {
            "hit_rate": 0.0,
            "mean_error": 0.0,
            "n_predictions": 0,
            "days": days,
        }

    errors = []
    for pred, actual_log in rows:
        actual = getattr(actual_log, pred.stat, None)
        if actual is not None:
            errors.append(abs(pred.p50 - actual))

    n = len(errors)
    return {
        "hit_rate": sum(1 for e in errors if e <= 5.0) / n if n else 0.0,
        "mean_error": round(sum(errors) / n, 2) if n else 0.0,
        "n_predictions": n,
        "days": days,
    }
