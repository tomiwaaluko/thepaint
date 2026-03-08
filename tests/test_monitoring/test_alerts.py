"""Tests for alerting module."""
from unittest.mock import AsyncMock, patch

import pytest

from chalk.monitoring.alerts import (
    alert_drift,
    alert_dag_failure,
    alert_predictions_ready,
    send_slack_alert,
)
from chalk.monitoring.drift import DriftReport


class TestSendSlackAlert:
    @pytest.mark.asyncio
    @patch("chalk.monitoring.alerts.SLACK_WEBHOOK_URL", "")
    async def test_noop_when_no_webhook(self):
        # Should not raise when webhook is not configured
        await send_slack_alert("test message", level="info")

    @pytest.mark.asyncio
    @patch("chalk.monitoring.alerts.SLACK_WEBHOOK_URL", "https://hooks.slack.com/test")
    @patch("chalk.monitoring.alerts.httpx.AsyncClient")
    async def test_sends_when_webhook_configured(self, mock_client_cls):
        mock_client = AsyncMock()
        mock_resp = AsyncMock()
        mock_resp.raise_for_status = lambda: None
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        await send_slack_alert("test", level="warning")
        mock_client.post.assert_called_once()


class TestAlertDrift:
    @pytest.mark.asyncio
    @patch("chalk.monitoring.alerts.send_slack_alert")
    async def test_formats_drift_message(self, mock_send):
        mock_send.return_value = None
        report = DriftReport(
            stat="pts", rolling_mae=6.0, baseline_mae=4.94,
            drift_pct=0.214, is_drifting=True, n_predictions=50,
        )
        await alert_drift(report)
        mock_send.assert_called_once()
        msg = mock_send.call_args[0][0]
        assert "pts" in msg
        assert "6.000" in msg
        assert "retraining" in msg


class TestAlertDagFailure:
    @pytest.mark.asyncio
    @patch("chalk.monitoring.alerts.send_slack_alert")
    async def test_formats_failure_message(self, mock_send):
        mock_send.return_value = None
        await alert_dag_failure("daily_ingest", "validate_row_counts", "0 rows")
        msg = mock_send.call_args[0][0]
        assert "daily_ingest" in msg
        assert "validate_row_counts" in msg


class TestAlertPredictionsReady:
    @pytest.mark.asyncio
    @patch("chalk.monitoring.alerts.send_slack_alert")
    async def test_formats_ready_message(self, mock_send):
        mock_send.return_value = None
        await alert_predictions_ready(5, 120)
        msg = mock_send.call_args[0][0]
        assert "120" in msg
        assert "5" in msg
