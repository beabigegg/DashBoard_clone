# -*- coding: utf-8 -*-
"""Unit tests for performance metrics module."""

import pytest
from mes_dashboard.core.metrics import (
    QueryMetrics,
    MetricsSummary,
    get_query_metrics,
    get_metrics_summary,
    record_query_latency,
    SLOW_QUERY_THRESHOLD
)


class TestQueryMetrics:
    """Test QueryMetrics class."""

    def test_initial_state_empty(self):
        """New metrics instance has no data."""
        metrics = QueryMetrics(window_size=100)
        percentiles = metrics.get_percentiles()

        assert percentiles["count"] == 0
        assert percentiles["p50"] == 0.0
        assert percentiles["p95"] == 0.0
        assert percentiles["p99"] == 0.0

    def test_record_latency(self):
        """Latencies are recorded correctly."""
        metrics = QueryMetrics(window_size=100)

        metrics.record_latency(0.1)
        metrics.record_latency(0.2)
        metrics.record_latency(0.3)

        latencies = metrics.get_latencies()
        assert len(latencies) == 3
        assert latencies == [0.1, 0.2, 0.3]

    def test_window_size_limit(self):
        """Window size limits number of samples."""
        metrics = QueryMetrics(window_size=5)

        for i in range(10):
            metrics.record_latency(float(i))

        latencies = metrics.get_latencies()
        assert len(latencies) == 5
        # Should have last 5 values (5, 6, 7, 8, 9)
        assert latencies == [5.0, 6.0, 7.0, 8.0, 9.0]

    def test_percentile_calculation_p50(self):
        """P50 (median) is calculated correctly."""
        metrics = QueryMetrics(window_size=100)

        # Record 100 values: 1, 2, 3, ..., 100
        for i in range(1, 101):
            metrics.record_latency(float(i))

        percentiles = metrics.get_percentiles()
        # P50 of 1-100 should be around 50
        assert 49 <= percentiles["p50"] <= 51

    def test_percentile_calculation_p95(self):
        """P95 is calculated correctly."""
        metrics = QueryMetrics(window_size=100)

        # Record 100 values: 1, 2, 3, ..., 100
        for i in range(1, 101):
            metrics.record_latency(float(i))

        percentiles = metrics.get_percentiles()
        # P95 of 1-100 should be around 95
        assert 94 <= percentiles["p95"] <= 96

    def test_percentile_calculation_p99(self):
        """P99 is calculated correctly."""
        metrics = QueryMetrics(window_size=100)

        # Record 100 values: 1, 2, 3, ..., 100
        for i in range(1, 101):
            metrics.record_latency(float(i))

        percentiles = metrics.get_percentiles()
        # P99 of 1-100 should be around 99
        assert 98 <= percentiles["p99"] <= 100

    def test_slow_query_count(self):
        """Slow queries (> threshold) are counted."""
        metrics = QueryMetrics(window_size=100)

        # Record some fast and slow queries
        metrics.record_latency(0.1)   # Fast
        metrics.record_latency(0.5)   # Fast
        metrics.record_latency(1.5)   # Slow
        metrics.record_latency(2.0)   # Slow
        metrics.record_latency(0.8)   # Fast

        percentiles = metrics.get_percentiles()
        assert percentiles["slow_count"] == 2

    def test_get_summary(self):
        """Summary includes all required fields."""
        metrics = QueryMetrics(window_size=100)

        metrics.record_latency(0.1)
        metrics.record_latency(0.5)
        metrics.record_latency(1.5)

        summary = metrics.get_summary()

        assert isinstance(summary, MetricsSummary)
        assert summary.p50_ms >= 0
        assert summary.p95_ms >= 0
        assert summary.p99_ms >= 0
        assert summary.count == 3
        assert summary.slow_count == 1
        assert 0 <= summary.slow_rate <= 1
        assert summary.worker_pid > 0
        assert summary.collected_at is not None

    def test_slow_rate_calculation(self):
        """Slow rate is calculated correctly."""
        metrics = QueryMetrics(window_size=100)

        # 2 slow out of 4 = 50%
        metrics.record_latency(0.1)
        metrics.record_latency(1.5)
        metrics.record_latency(0.2)
        metrics.record_latency(2.0)

        summary = metrics.get_summary()
        assert summary.slow_rate == 0.5

    def test_clear_resets_metrics(self):
        """Clear removes all recorded latencies."""
        metrics = QueryMetrics(window_size=100)

        metrics.record_latency(0.1)
        metrics.record_latency(0.2)

        metrics.clear()

        assert len(metrics.get_latencies()) == 0
        assert metrics.get_percentiles()["count"] == 0


class TestGlobalMetrics:
    """Test global metrics functions."""

    def test_get_query_metrics_returns_singleton(self):
        """Global query metrics returns same instance."""
        metrics1 = get_query_metrics()
        metrics2 = get_query_metrics()

        assert metrics1 is metrics2

    def test_record_query_latency_uses_global(self):
        """record_query_latency uses global metrics instance."""
        metrics = get_query_metrics()
        initial_count = metrics.get_percentiles()["count"]

        record_query_latency(0.1)

        assert metrics.get_percentiles()["count"] == initial_count + 1

    def test_get_metrics_summary_returns_dict(self):
        """get_metrics_summary returns dictionary format."""
        summary = get_metrics_summary()

        assert isinstance(summary, dict)
        assert "p50_ms" in summary
        assert "p95_ms" in summary
        assert "p99_ms" in summary
        assert "count" in summary
        assert "slow_count" in summary
        assert "slow_rate" in summary
        assert "worker_pid" in summary
        assert "collected_at" in summary


class TestMetricsThreadSafety:
    """Test thread safety of metrics collection."""

    def test_concurrent_recording(self):
        """Metrics handle concurrent recording."""
        import threading

        metrics = QueryMetrics(window_size=1000)

        def record_many():
            for _ in range(100):
                metrics.record_latency(0.1)

        threads = [threading.Thread(target=record_many) for _ in range(10)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Should have 1000 entries
        assert metrics.get_percentiles()["count"] == 1000
