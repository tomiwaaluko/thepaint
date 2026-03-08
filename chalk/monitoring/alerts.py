"""Alerting — Slack webhook notifications for drift and DAG status."""
import os

import httpx
import structlog

from chalk.monitoring.drift import DriftReport

log = structlog.get_logger()

SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL", "")

LEVEL_EMOJI = {
    "info": "ℹ️",
    "warning": "⚠️",
    "error": "🚨",
}


async def send_slack_alert(message: str, level: str = "info") -> None:
    """Send a Slack webhook notification.

    No-ops gracefully if SLACK_WEBHOOK_URL is not configured.
    """
    if not SLACK_WEBHOOK_URL:
        log.info("slack_alert_skipped", reason="no webhook configured", level=level)
        return

    emoji = LEVEL_EMOJI.get(level, "ℹ️")
    payload = {"text": f"{emoji} *[Chalk]* {message}"}

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(SLACK_WEBHOOK_URL, json=payload)
            resp.raise_for_status()
        log.info("slack_alert_sent", level=level)
    except Exception as e:
        log.error("slack_alert_failed", error=str(e))


async def alert_drift(report: DriftReport) -> None:
    """Send drift alert for a stat model."""
    message = (
        f"Model drift detected for *{report.stat}*\n"
        f"Rolling MAE: {report.rolling_mae:.3f} "
        f"(baseline: {report.baseline_mae:.3f}, +{report.drift_pct * 100:.1f}%)\n"
        f"Based on {report.n_predictions} predictions over last 30 days\n"
        f"Action: retraining recommended"
    )
    await send_slack_alert(message, level="warning")


async def alert_dag_failure(dag_id: str, task_id: str, error: str) -> None:
    """Send alert when a DAG task fails."""
    message = (
        f"DAG *{dag_id}* failed at task `{task_id}`\n"
        f"Error: {error}"
    )
    await send_slack_alert(message, level="error")


async def alert_predictions_ready(game_count: int, player_count: int) -> None:
    """Send notification when daily predictions are complete."""
    message = (
        f"Daily predictions complete\n"
        f"{player_count} players across {game_count} games"
    )
    await send_slack_alert(message, level="info")
