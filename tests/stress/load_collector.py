# -*- coding: utf-8 -*-
"""Load monitoring infrastructure for stress tests.

Polls the application's /health and /admin/api/performance-detail endpoints
in a background thread during stress test execution to collect system metrics.
"""

import threading
import time
import requests
from dataclasses import dataclass
from typing import Dict, List, Optional


# RQ queues monitored during stress runs
RQ_QUEUES = [
    "trace-events",
    "reject-query",
    "msd-analysis",
    "production-history-query",
    "yield-alert-query",
]


@dataclass
class LoadSample:
    """A single snapshot of system metrics at one point in time."""
    timestamp: float
    cpu_percent: Optional[float] = None
    memory_used_pct: Optional[float] = None
    memory_available_mb: Optional[float] = None
    memory_pressure: Optional[str] = None
    db_pool_active: Optional[int] = None
    db_pool_size: Optional[int] = None
    db_pool_utilization_pct: Optional[float] = None
    # Per-queue RQ depth: queue_name -> depth
    rq_queue_depths: Optional[Dict[str, int]] = None
    is_null: bool = False


@dataclass
class TelemetryDiff:
    """Delta of heavy-query telemetry counters between two snapshots."""
    guard_reject_total: int = 0
    async_fallback_total: int = 0
    memory_error_total: int = 0
    spool_cache_hit: int = 0
    spool_cache_miss: int = 0
    endpoint_unavailable: bool = False

    @classmethod
    def compute(cls, before: Optional[dict], after: Optional[dict]) -> "TelemetryDiff":
        """Compute the delta between two telemetry counter snapshots."""
        if before is None or after is None:
            return cls(endpoint_unavailable=True)
        return cls(
            guard_reject_total=_counter_delta(after, before, "guard_reject_total"),
            async_fallback_total=_counter_delta(after, before, "async_fallback_total"),
            memory_error_total=_counter_delta(after, before, "memory_error_total"),
            spool_cache_hit=_counter_delta(after, before, "spool_cache_hit"),
            spool_cache_miss=_counter_delta(after, before, "spool_cache_miss"),
        )

    @property
    def all_zero(self) -> bool:
        return (
            self.guard_reject_total == 0
            and self.async_fallback_total == 0
            and self.memory_error_total == 0
            and self.spool_cache_hit == 0
            and self.spool_cache_miss == 0
        )


def _counter_delta(after: dict, before: dict, key: str) -> int:
    a = after.get(key, 0) or 0
    b = before.get(key, 0) or 0
    return max(0, a - b)


@dataclass
class LoadSummary:
    """Aggregate statistics computed from a collection of LoadSamples."""
    peak_cpu_pct: Optional[float] = None
    avg_cpu_pct: Optional[float] = None
    peak_mem_pct: Optional[float] = None
    avg_mem_pct: Optional[float] = None
    peak_db_pool_pct: Optional[float] = None
    # Per-queue peak depths: queue_name -> peak_depth
    peak_queue_depths: Optional[Dict[str, int]] = None
    sample_count: int = 0
    null_sample_count: int = 0
    duration_sec: float = 0.0
    telemetry_diff: Optional[TelemetryDiff] = None

    def assert_within(
        self,
        max_cpu_pct: Optional[float] = None,
        max_mem_pct: Optional[float] = None,
        max_db_pool_pct: Optional[float] = None,
    ) -> None:
        """Assert that peak metrics do not exceed the given thresholds.

        Skips any assertion when the corresponding metric is None (unavailable).
        Raises AssertionError with details when a threshold is breached.
        """
        violations = []
        if max_cpu_pct is not None and self.peak_cpu_pct is not None:
            if self.peak_cpu_pct > max_cpu_pct:
                violations.append(
                    f"peak_cpu_pct={self.peak_cpu_pct:.1f}% exceeds threshold {max_cpu_pct:.1f}%"
                )
        if max_mem_pct is not None and self.peak_mem_pct is not None:
            if self.peak_mem_pct > max_mem_pct:
                violations.append(
                    f"peak_mem_pct={self.peak_mem_pct:.1f}% exceeds threshold {max_mem_pct:.1f}%"
                )
        if max_db_pool_pct is not None and self.peak_db_pool_pct is not None:
            if self.peak_db_pool_pct > max_db_pool_pct:
                violations.append(
                    f"peak_db_pool_pct={self.peak_db_pool_pct:.1f}% exceeds threshold {max_db_pool_pct:.1f}%"
                )
        if violations:
            raise AssertionError("Load thresholds exceeded:\n" + "\n".join(f"  - {v}" for v in violations))

    @classmethod
    def from_samples(
        cls,
        samples: List[LoadSample],
        duration_sec: float,
        telemetry_diff: Optional[TelemetryDiff] = None,
    ) -> "LoadSummary":
        valid = [s for s in samples if not s.is_null]
        null_count = len(samples) - len(valid)

        if not valid:
            return cls(
                sample_count=0,
                null_sample_count=null_count,
                duration_sec=duration_sec,
                telemetry_diff=telemetry_diff,
            )

        cpu_values = [s.cpu_percent for s in valid if s.cpu_percent is not None]
        mem_values = [s.memory_used_pct for s in valid if s.memory_used_pct is not None]
        pool_values = [s.db_pool_utilization_pct for s in valid if s.db_pool_utilization_pct is not None]

        # Per-queue peak depths
        peak_queue_depths: Optional[Dict[str, int]] = None
        queue_samples = [s.rq_queue_depths for s in valid if s.rq_queue_depths is not None]
        if queue_samples:
            peak_queue_depths = {}
            for q in RQ_QUEUES:
                depths = [qs[q] for qs in queue_samples if q in qs]
                peak_queue_depths[q] = max(depths) if depths else 0

        return cls(
            peak_cpu_pct=max(cpu_values) if cpu_values else None,
            avg_cpu_pct=sum(cpu_values) / len(cpu_values) if cpu_values else None,
            peak_mem_pct=max(mem_values) if mem_values else None,
            avg_mem_pct=sum(mem_values) / len(mem_values) if mem_values else None,
            peak_db_pool_pct=max(pool_values) if pool_values else None,
            peak_queue_depths=peak_queue_depths,
            sample_count=len(valid),
            null_sample_count=null_count,
            duration_sec=duration_sec,
            telemetry_diff=telemetry_diff,
        )


class LoadCollector:
    """Context manager that collects system metrics in a background daemon thread.

    Usage::

        with LoadCollector(base_url, interval=2.0) as collector:
            # run stress test
            ...
        summary = collector.summary  # LoadSummary dataclass
    """

    def __init__(self, base_url: str, interval: float = 2.0):
        self._base_url = base_url.rstrip("/")
        self._interval = interval
        self._samples: List[LoadSample] = []
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._start_time: float = 0.0
        self._end_time: float = 0.0
        self._telemetry_before: Optional[dict] = None
        self._telemetry_after: Optional[dict] = None
        self.summary: Optional[LoadSummary] = None

    def __enter__(self) -> "LoadCollector":
        self._start_time = time.monotonic()
        self._telemetry_before = self._fetch_telemetry()
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=self._interval + 1.0)
        self._end_time = time.monotonic()
        self._telemetry_after = self._fetch_telemetry()
        telemetry_diff = TelemetryDiff.compute(self._telemetry_before, self._telemetry_after)
        self.summary = LoadSummary.from_samples(
            self._samples,
            duration_sec=self._end_time - self._start_time,
            telemetry_diff=telemetry_diff,
        )

    def _run(self) -> None:
        """Daemon thread: poll at interval until stop event is set."""
        while not self._stop_event.wait(timeout=self._interval):
            sample = self._collect_sample()
            self._samples.append(sample)
        # Final sample on exit
        sample = self._collect_sample()
        self._samples.append(sample)

    def _collect_sample(self) -> LoadSample:
        ts = time.monotonic()
        sample = self._fetch_health(ts)
        if not sample.is_null:
            self._enrich_from_admin(sample)
        return sample

    def _fetch_health(self, ts: float) -> LoadSample:
        """Poll /health and parse system metrics."""
        try:
            resp = requests.get(f"{self._base_url}/health", timeout=self._interval)
            if resp.status_code != 200:
                return LoadSample(timestamp=ts, is_null=True)
            data = resp.json()
            mem = data.get("system_memory") or {}
            cpu = data.get("cpu_percent") or data.get("cpu") or None
            # Also check nested cpu_info
            if cpu is None:
                cpu_info = data.get("cpu_info") or {}
                cpu = cpu_info.get("cpu_percent")
            return LoadSample(
                timestamp=ts,
                cpu_percent=_to_float(cpu),
                memory_used_pct=_to_float(mem.get("used_pct")),
                memory_available_mb=_to_float(mem.get("available_mb")),
                memory_pressure=mem.get("pressure"),
            )
        except Exception:
            return LoadSample(timestamp=ts, is_null=True)

    def _enrich_from_admin(self, sample: LoadSample) -> None:
        """Optionally enrich sample with DB pool and RQ queue data from admin endpoint."""
        try:
            resp = requests.get(
                f"{self._base_url}/admin/api/performance-detail", timeout=self._interval
            )
            if resp.status_code != 200:
                return
            data = resp.json()
            payload = data.get("data") or data

            # DB pool
            db_pool = payload.get("db_pool") or {}
            active = _to_int(db_pool.get("db_pool_active") or db_pool.get("checked_out"))
            size = _to_int(db_pool.get("db_pool_size") or db_pool.get("pool_size"))
            if active is not None and size and size > 0:
                sample.db_pool_active = active
                sample.db_pool_size = size
                sample.db_pool_utilization_pct = (active / size) * 100.0

            # RQ queue depths
            rq_data = payload.get("rq_queues") or payload.get("queues") or {}
            depths: Dict[str, int] = {}
            for q in RQ_QUEUES:
                q_info = rq_data.get(q) or {}
                depth = _to_int(q_info.get("queued") or q_info.get("depth") or q_info.get("count"))
                depths[q] = depth if depth is not None else 0
            if depths:
                sample.rq_queue_depths = depths
        except Exception:
            pass  # Admin metrics are optional

    def _fetch_telemetry(self) -> Optional[dict]:
        """Snapshot heavy_query_telemetry counters from admin endpoint."""
        try:
            resp = requests.get(
                f"{self._base_url}/admin/api/performance-detail", timeout=5.0
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
            payload = data.get("data") or data
            return payload.get("heavy_query_telemetry") or {}
        except Exception:
            return None


def _to_float(value) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
