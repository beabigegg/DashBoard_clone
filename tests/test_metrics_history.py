# -*- coding: utf-8 -*-
"""Tests for core/metrics_history module.

Covers RSS measurement via process_rss_mb, multi-worker aggregation,
time-bucket grouping, redis_used_memory_mb calculation, and the
original (non-aggregated) query_snapshots API.
"""

from __future__ import annotations

import os
import tempfile
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from mes_dashboard.core.metrics_history import (
    MetricsHistoryCollector,
    MetricsHistoryStore,
)


# ============================================================
# Helpers
# ============================================================

def _insert_snapshot(store, ts_str, pid, rss_bytes, **kwargs):
    """Insert a metrics snapshot directly into the store's SQLite DB."""
    defaults = {
        'pool_saturation': 0.5, 'pool_checked_out': 0, 'pool_checked_in': 5,
        'pool_overflow': 0, 'pool_max_capacity': 10, 'redis_used_memory': 0,
        'redis_hit_rate': 0, 'rc_l1_hit_rate': 0, 'rc_l2_hit_rate': 0,
        'rc_miss_rate': 0, 'latency_p50_ms': 0, 'latency_p95_ms': 0,
        'latency_p99_ms': 0, 'latency_count': 0, 'slow_query_active': 0,
        'slow_query_waiting': 0,
    }
    defaults.update(kwargs)
    with store._write_lock:
        with store._get_connection() as conn:
            conn.execute(
                """INSERT INTO metrics_snapshots
                   (ts, worker_pid, worker_rss_bytes, pool_saturation, pool_checked_out,
                    pool_checked_in, pool_overflow, pool_max_capacity, redis_used_memory,
                    redis_hit_rate, rc_l1_hit_rate, rc_l2_hit_rate, rc_miss_rate,
                    latency_p50_ms, latency_p95_ms, latency_p99_ms, latency_count,
                    slow_query_active, slow_query_waiting)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (ts_str, pid, rss_bytes, defaults['pool_saturation'], defaults['pool_checked_out'],
                 defaults['pool_checked_in'], defaults['pool_overflow'], defaults['pool_max_capacity'],
                 defaults['redis_used_memory'], defaults['redis_hit_rate'], defaults['rc_l1_hit_rate'],
                 defaults['rc_l2_hit_rate'], defaults['rc_miss_rate'], defaults['latency_p50_ms'],
                 defaults['latency_p95_ms'], defaults['latency_p99_ms'], defaults['latency_count'],
                 defaults['slow_query_active'], defaults['slow_query_waiting']),
            )
            conn.commit()


# ============================================================
# Test RSS Measurement
# ============================================================

class TestRSSMeasurement:
    """Verify that _collect_snapshot reads RSS via process_rss_mb."""

    @patch("mes_dashboard.core.metrics_history.get_metrics_history_store")
    def test_rss_bytes_from_process_rss_mb(self, mock_get_store):
        """Mock process_rss_mb to return 512.5 MB, verify worker_rss_bytes
        in the stored snapshot equals int(512.5 * 1024 * 1024)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_rss.sqlite")
            store = MetricsHistoryStore(db_path=db_path)
            store.initialize()

            mock_get_store.return_value = store
            collector = MetricsHistoryCollector(app=None, store=store)

            with (
                patch(
                    "mes_dashboard.core.metrics_history.get_pool_status",
                    create=True,
                    side_effect=ImportError,
                ),
                patch(
                    "mes_dashboard.core.interactive_memory_guard.process_rss_mb",
                    return_value=512.5,
                ) as mock_rss,
            ):
                collector._collect_snapshot()
                mock_rss.assert_called_once()

            rows = store.query_snapshots(minutes=5)
            assert len(rows) >= 1
            last = rows[-1]
            expected_bytes = int(512.5 * 1024 * 1024)
            assert last["worker_rss_bytes"] == expected_bytes

    @patch("mes_dashboard.core.metrics_history.get_metrics_history_store")
    def test_resource_getrusage_not_called(self, mock_get_store):
        """Ensure that resource.getrusage is NOT called during snapshot
        collection -- we use psutil-based process_rss_mb instead."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_no_rusage.sqlite")
            store = MetricsHistoryStore(db_path=db_path)
            store.initialize()
            mock_get_store.return_value = store
            collector = MetricsHistoryCollector(app=None, store=store)

            with (
                patch(
                    "mes_dashboard.core.interactive_memory_guard.process_rss_mb",
                    return_value=100.0,
                ),
                patch("resource.getrusage") as mock_rusage,
            ):
                collector._collect_snapshot()
                mock_rusage.assert_not_called()


# ============================================================
# Test Multi-Worker Aggregation
# ============================================================

class TestMultiWorkerAggregation:
    """Two workers in the same 30s bucket must collapse into one row."""

    def test_same_bucket_aggregation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_agg.sqlite")
            store = MetricsHistoryStore(db_path=db_path)
            store.initialize()

            now = datetime.now()
            ts = now.isoformat()

            rss_a = 1770 * 1024 * 1024
            rss_b = 563 * 1024 * 1024

            _insert_snapshot(store, ts, pid=1001, rss_bytes=rss_a, pool_saturation=0.8)
            _insert_snapshot(store, ts, pid=1002, rss_bytes=rss_b, pool_saturation=0.3)

            rows = store.query_snapshots_aggregated(minutes=5)
            assert len(rows) == 1, f"Expected 1 aggregated row, got {len(rows)}"

            row = rows[0]
            assert row["worker_rss_bytes"] == rss_a  # MAX
            assert row["worker_count"] == 2


# ============================================================
# Test Different Time Buckets
# ============================================================

class TestDifferentTimeBuckets:
    """Snapshots 60 seconds apart must land in separate 30s buckets."""

    def test_two_buckets(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_buckets.sqlite")
            store = MetricsHistoryStore(db_path=db_path)
            store.initialize()

            now = datetime.now()
            ts1 = now.isoformat()
            ts2 = (now - timedelta(seconds=60)).isoformat()

            _insert_snapshot(store, ts1, pid=1001, rss_bytes=500 * 1024 * 1024)
            _insert_snapshot(store, ts2, pid=1001, rss_bytes=400 * 1024 * 1024)

            rows = store.query_snapshots_aggregated(minutes=5)
            assert len(rows) == 2, f"Expected 2 rows for different buckets, got {len(rows)}"


# ============================================================
# Test redis_used_memory_mb Calculation
# ============================================================

class TestRedisUsedMemoryMb:
    """Aggregated query must compute redis_used_memory_mb = bytes / 1048576."""

    def test_redis_memory_conversion(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_redis_mb.sqlite")
            store = MetricsHistoryStore(db_path=db_path)
            store.initialize()

            redis_bytes = 268435456  # 256 MB
            now = datetime.now()
            _insert_snapshot(
                store,
                now.isoformat(),
                pid=1001,
                rss_bytes=0,
                redis_used_memory=redis_bytes,
            )

            rows = store.query_snapshots_aggregated(minutes=5)
            assert len(rows) == 1
            assert rows[0]["redis_used_memory_mb"] == 256.0


# ============================================================
# Test Timezone Handling in Aggregation
# ============================================================

class TestTimezoneHandling:
    """Aggregated timestamps must match the original local-time ts,
    not be shifted by the server timezone offset."""

    def test_aggregated_ts_matches_local_time(self):
        """The bucketed ts should stay close to the original local time,
        not be shifted by ±timezone offset."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_tz.sqlite")
            store = MetricsHistoryStore(db_path=db_path)
            store.initialize()

            now = datetime.now()
            ts_str = now.isoformat()
            _insert_snapshot(store, ts_str, pid=1001, rss_bytes=100 * 1024 * 1024)

            rows = store.query_snapshots_aggregated(minutes=5)
            assert len(rows) == 1

            # Parse the aggregated ts back and check it's within 30s of original
            agg_ts = rows[0]["ts"]  # format: "YYYY-MM-DD HH:MM:SS"
            agg_dt = datetime.strptime(agg_ts, "%Y-%m-%d %H:%M:%S")
            delta = abs((now - agg_dt).total_seconds())
            assert delta < 30, (
                f"Aggregated ts '{agg_ts}' is {delta:.0f}s away from original "
                f"'{ts_str}' — likely a timezone double-conversion bug"
            )


# ============================================================
# Test Purge
# ============================================================

class TestPurge:
    """purge() must delete all rows from metrics_snapshots."""

    def test_purge_deletes_all(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_purge.sqlite")
            store = MetricsHistoryStore(db_path=db_path)
            store.initialize()

            now = datetime.now()
            for i in range(5):
                ts = (now - timedelta(seconds=i * 30)).isoformat()
                _insert_snapshot(store, ts, pid=1001, rss_bytes=100 * 1024 * 1024)

            assert len(store.query_snapshots(minutes=5)) == 5
            deleted = store.purge()
            assert deleted == 5
            assert len(store.query_snapshots(minutes=5)) == 0


# ============================================================
# Test Original query_snapshots Still Works
# ============================================================

class TestQuerySnapshotsNoAggregation:
    """The non-aggregated query_snapshots must return all rows as-is."""

    def test_no_aggregation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_raw.sqlite")
            store = MetricsHistoryStore(db_path=db_path)
            store.initialize()

            now = datetime.now()
            ts = now.isoformat()

            _insert_snapshot(store, ts, pid=2001, rss_bytes=100 * 1024 * 1024)
            _insert_snapshot(store, ts, pid=2002, rss_bytes=200 * 1024 * 1024)

            rows = store.query_snapshots(minutes=5)
            assert len(rows) == 2, f"Expected 2 raw rows, got {len(rows)}"


# ============================================================
# Test Sync Fields
# ============================================================

class TestMetricsSyncFields:
    """Test synced field, get_unsynced, mark_synced, cleanup_synced."""

    def test_write_snapshot_sets_synced_zero(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_sync.sqlite")
            store = MetricsHistoryStore(db_path=db_path)
            store.initialize()

            store.write_snapshot({"pool": {}, "redis": {}, "route_cache": {}, "latency": {}})

            rows = store.get_unsynced()
            assert len(rows) == 1
            assert rows[0]["synced"] == 0
            assert rows[0]["sync_id"] is not None
            assert "metrics_snapshots_" in rows[0]["sync_id"]

    def test_get_unsynced_returns_only_unsynced(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_unsynced.sqlite")
            store = MetricsHistoryStore(db_path=db_path)
            store.initialize()

            now = datetime.now()
            _insert_snapshot(store, now.isoformat(), pid=1, rss_bytes=0)
            _insert_snapshot(store, now.isoformat(), pid=2, rss_bytes=0)

            unsynced = store.get_unsynced()
            assert len(unsynced) == 2
            assert all(r["synced"] == 0 for r in unsynced)

    def test_mark_synced_sets_flag(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_mark.sqlite")
            store = MetricsHistoryStore(db_path=db_path)
            store.initialize()

            now = datetime.now()
            _insert_snapshot(store, now.isoformat(), pid=1, rss_bytes=0)

            unsynced = store.get_unsynced()
            assert len(unsynced) == 1

            store.mark_synced([unsynced[0]["id"]])

            still_unsynced = store.get_unsynced()
            assert len(still_unsynced) == 0

    def test_query_aggregated_excludes_synced(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_agg_excl.sqlite")
            store = MetricsHistoryStore(db_path=db_path)
            store.initialize()

            now = datetime.now()
            _insert_snapshot(store, now.isoformat(), pid=1, rss_bytes=100)
            _insert_snapshot(store, now.isoformat(), pid=2, rss_bytes=200)

            unsynced = store.get_unsynced()
            # Mark one as synced
            store.mark_synced([unsynced[0]["id"]])

            rows = store.query_snapshots_aggregated(minutes=5)
            # Only the unsynced row should contribute
            assert len(rows) == 1
            assert rows[0]["worker_count"] == 1

    def test_cleanup_synced_removes_old(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_cleanup.sqlite")
            store = MetricsHistoryStore(db_path=db_path)
            store.initialize()

            now = datetime.now()
            _insert_snapshot(store, now.isoformat(), pid=1, rss_bytes=0)

            unsynced = store.get_unsynced()
            store.mark_synced([unsynced[0]["id"]])

            # Backdate the ts to make it old
            old_ts = (now - timedelta(hours=2)).isoformat()
            conn = sqlite3.connect(db_path)
            conn.execute("UPDATE metrics_snapshots SET ts = ? WHERE synced = 1", (old_ts,))
            conn.commit()
            conn.close()

            deleted = store.cleanup_synced(older_than_hours=1)
            assert deleted == 1

    def test_get_unsynced_batch_size(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_batch.sqlite")
            store = MetricsHistoryStore(db_path=db_path)
            store.initialize()

            now = datetime.now()
            for i in range(10):
                _insert_snapshot(store, now.isoformat(), pid=i, rss_bytes=0)

            batch = store.get_unsynced(batch_size=4)
            assert len(batch) == 4
