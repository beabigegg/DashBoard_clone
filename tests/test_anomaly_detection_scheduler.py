# -*- coding: utf-8 -*-
"""Tests for anomaly_detection_scheduler spool seed log-level handling."""

import logging
import pytest
from unittest.mock import patch, MagicMock


class TestSpoolSeedLogLevel:
    """Verify _seed_spool logs single_flight_timeout at WARNING, other errors at ERROR."""

    def _run_seed_with_exception(self, exc_message: str):
        """Run _seed_spool with a patched execute_primary_query that raises the given exception."""
        import mes_dashboard.services.anomaly_detection_scheduler as sched

        with patch.object(sched, '_has_spool', return_value=False):
            with patch(
                'mes_dashboard.services.yield_alert_dataset_cache.execute_primary_query',
                side_effect=Exception(exc_message),
            ):
                return sched._seed_spool("yield_alert_dataset", "anomaly_yield_dataset", 14)

    def test_single_flight_timeout_logs_at_warning(self, caplog):
        """single_flight_timeout exception should log at WARNING level."""
        with caplog.at_level(logging.WARNING, logger="mes_dashboard.anomaly_detection_scheduler"):
            result = self._run_seed_with_exception(
                "single_flight_timeout: 查詢已有另一個 worker 正在執行"
            )

        assert result is False
        warning_msgs = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert any("single_flight_timeout" in r.message or "contention" in r.message.lower()
                   for r in warning_msgs), (
            f"Expected WARNING with 'single_flight_timeout', got: {[r.message for r in caplog.records]}"
        )
        error_msgs = [r for r in caplog.records if r.levelno == logging.ERROR]
        assert not error_msgs, f"Expected no ERROR logs, got: {[r.message for r in error_msgs]}"

    def test_other_exception_logs_at_error(self, caplog):
        """Non-single_flight_timeout exceptions should log at ERROR level."""
        with caplog.at_level(logging.ERROR, logger="mes_dashboard.anomaly_detection_scheduler"):
            result = self._run_seed_with_exception("ORA-12345: connection timeout")

        assert result is False
        error_msgs = [r for r in caplog.records if r.levelno == logging.ERROR]
        assert error_msgs, f"Expected ERROR log, got: {[r.message for r in caplog.records]}"
