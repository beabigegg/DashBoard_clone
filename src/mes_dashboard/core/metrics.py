# -*- coding: utf-8 -*-
"""Performance metrics collection for MES Dashboard.

Collects query latency metrics using an in-memory sliding window.
Each worker maintains independent statistics.
"""

from __future__ import annotations

import logging
import os
import threading
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import Deque, List, Optional

logger = logging.getLogger('mes_dashboard.metrics')

# ============================================================
# Configuration
# ============================================================

# Maximum number of latency samples to keep
METRICS_WINDOW_SIZE = int(os.getenv('METRICS_WINDOW_SIZE', '1000'))

# Threshold for "slow" queries (seconds)
SLOW_QUERY_THRESHOLD = float(os.getenv('SLOW_QUERY_THRESHOLD', '1.0'))


# ============================================================
# Types
# ============================================================

@dataclass
class MetricsSummary:
    """Summary of collected metrics."""
    p50_ms: float
    p95_ms: float
    p99_ms: float
    count: int
    slow_count: int
    slow_rate: float
    worker_pid: int
    collected_at: str


# ============================================================
# Query Metrics Implementation
# ============================================================

class QueryMetrics:
    """Collects and summarizes query latency metrics.

    Uses a thread-safe sliding window to track the most recent
    query latencies. Provides percentile calculations for
    monitoring and alerting.

    Usage:
        metrics = QueryMetrics()

        # Record a query
        start = time.time()
        execute_query()
        metrics.record_latency(time.time() - start)

        # Get summary
        summary = metrics.get_summary()
    """

    def __init__(self, window_size: int = METRICS_WINDOW_SIZE):
        """Initialize query metrics collector.

        Args:
            window_size: Maximum number of samples to keep.
        """
        self.window_size = window_size
        self._latencies: Deque[float] = deque(maxlen=window_size)
        self._lock = threading.Lock()
        self._worker_pid = os.getpid()

    def record_latency(self, latency_seconds: float) -> None:
        """Record a query latency.

        Args:
            latency_seconds: Query execution time in seconds.
        """
        with self._lock:
            self._latencies.append(latency_seconds)

        # Log slow queries
        if latency_seconds > SLOW_QUERY_THRESHOLD:
            logger.warning(
                f"Slow query detected: {latency_seconds:.2f}s "
                f"(threshold: {SLOW_QUERY_THRESHOLD}s)"
            )

    def get_percentile(self, percentile: float) -> float:
        """Calculate a specific percentile from the latency data.

        Args:
            percentile: Percentile to calculate (0-100).

        Returns:
            Latency value at the given percentile in seconds.
        """
        with self._lock:
            if not self._latencies:
                return 0.0

            sorted_latencies = sorted(self._latencies)
            index = int((percentile / 100.0) * len(sorted_latencies))
            # Clamp index to valid range
            index = min(index, len(sorted_latencies) - 1)
            return sorted_latencies[index]

    def get_percentiles(self) -> dict:
        """Calculate P50, P95, and P99 percentiles.

        Returns:
            Dictionary with percentile values in milliseconds.
        """
        with self._lock:
            if not self._latencies:
                return {
                    "p50": 0.0,
                    "p95": 0.0,
                    "p99": 0.0,
                    "count": 0,
                    "slow_count": 0
                }

            sorted_latencies = sorted(self._latencies)
            count = len(sorted_latencies)

            def get_percentile_value(p: float) -> float:
                index = int((p / 100.0) * count)
                index = min(index, count - 1)
                return sorted_latencies[index]

            slow_count = sum(1 for v in sorted_latencies if v > SLOW_QUERY_THRESHOLD)

            return {
                "p50": get_percentile_value(50),
                "p95": get_percentile_value(95),
                "p99": get_percentile_value(99),
                "count": count,
                "slow_count": slow_count
            }

    def get_summary(self) -> MetricsSummary:
        """Get a complete metrics summary.

        Returns:
            MetricsSummary with all collected metrics.
        """
        percentiles = self.get_percentiles()

        slow_rate = 0.0
        if percentiles["count"] > 0:
            slow_rate = percentiles["slow_count"] / percentiles["count"]

        return MetricsSummary(
            p50_ms=round(percentiles["p50"] * 1000, 2),
            p95_ms=round(percentiles["p95"] * 1000, 2),
            p99_ms=round(percentiles["p99"] * 1000, 2),
            count=percentiles["count"],
            slow_count=percentiles["slow_count"],
            slow_rate=round(slow_rate, 4),
            worker_pid=self._worker_pid,
            collected_at=datetime.now().isoformat()
        )

    def get_latencies(self) -> List[float]:
        """Get a copy of all recorded latencies.

        Returns:
            List of latencies in seconds.
        """
        with self._lock:
            return list(self._latencies)

    def clear(self) -> None:
        """Clear all recorded metrics."""
        with self._lock:
            self._latencies.clear()
        logger.info(f"Metrics cleared for worker {self._worker_pid}")


# ============================================================
# Global Query Metrics Instance
# ============================================================

_QUERY_METRICS: Optional[QueryMetrics] = None


def get_query_metrics() -> QueryMetrics:
    """Get or create the global query metrics instance."""
    global _QUERY_METRICS
    if _QUERY_METRICS is None:
        _QUERY_METRICS = QueryMetrics()
    return _QUERY_METRICS


def get_metrics_summary() -> dict:
    """Get current metrics summary as a dictionary.

    Returns:
        Dictionary with metrics summary information.
    """
    metrics = get_query_metrics()
    summary = metrics.get_summary()
    return {
        "p50_ms": summary.p50_ms,
        "p95_ms": summary.p95_ms,
        "p99_ms": summary.p99_ms,
        "count": summary.count,
        "slow_count": summary.slow_count,
        "slow_rate": summary.slow_rate,
        "worker_pid": summary.worker_pid,
        "collected_at": summary.collected_at
    }


def record_query_latency(latency_seconds: float) -> None:
    """Record a query latency to the global metrics.

    Args:
        latency_seconds: Query execution time in seconds.
    """
    get_query_metrics().record_latency(latency_seconds)
