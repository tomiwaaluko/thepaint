"""Tests for Railway ingestion cron behavior."""

from scripts.railway_ingest import _missing_player_logs_should_fail


def test_missing_player_logs_warning_does_not_fail_by_default():
    assert _missing_player_logs_should_fail(False) is False


def test_missing_player_logs_can_fail_in_strict_mode():
    assert _missing_player_logs_should_fail(True) is True
