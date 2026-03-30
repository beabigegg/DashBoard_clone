# -*- coding: utf-8 -*-
"""Tests for anomaly_detection_scheduler spool seed log-level handling."""

import logging
import pytest
from unittest.mock import patch, MagicMock


class TestSpoolSeedLogLevel:
    """Verify _seed_spool consumer-only behavior: no Oracle triggers, correct log levels."""

    def test_source_spool_missing_logs_info_and_returns_false(self, caplog):
        """When source spool is absent, _seed_spool should log at INFO and return False
        without triggering any Oracle queries (consumer-only, task 5.1)."""
        import mes_dashboard.services.anomaly_detection_scheduler as sched

        with caplog.at_level(logging.INFO, logger="mes_dashboard.anomaly_detection_scheduler"):
            with patch.object(sched, '_has_spool', return_value=False):
                result = sched._seed_spool("yield_alert_dataset", "anomaly_yield_dataset", 14)

        assert result is False
        # Should not log at ERROR (no exceptions thrown)
        error_msgs = [r for r in caplog.records if r.levelno == logging.ERROR]
        assert not error_msgs, f"Expected no ERROR logs, got: {[r.message for r in error_msgs]}"
        # Should log at INFO explaining the skip
        info_msgs = [r for r in caplog.records if r.levelno == logging.INFO]
        assert any("missing" in r.message.lower() or "skip" in r.message.lower()
                   for r in info_msgs), (
            f"Expected INFO about missing spool, got: {[r.message for r in caplog.records]}"
        )

    def test_copy_failure_logs_warning_and_returns_false(self, caplog):
        """If copy fails (returns False), _seed_spool should log at WARNING level."""
        import mes_dashboard.services.anomaly_detection_scheduler as sched

        with caplog.at_level(logging.WARNING, logger="mes_dashboard.anomaly_detection_scheduler"):
            with patch.object(sched, '_has_spool', return_value=True), \
                 patch.object(sched, '_copy_to_anomaly_namespace', return_value=False):
                result = sched._seed_spool("yield_alert_dataset", "anomaly_yield_dataset", 14)

        assert result is False
        warning_msgs = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert warning_msgs, f"Expected WARNING log on copy failure, got: {[r.message for r in caplog.records]}"
