# -*- coding: utf-8 -*-
"""SQLite-based metrics history store for admin performance dashboard.

Periodically snapshots system metrics (pool, redis, cache, latency)
into a SQLite database for historical trend visualization.
Follows the LogStore pattern from core/log_store.py.
"""

from __future__ import annotations

import logging
import os
import socket
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

logger = logging.getLogger('mes_dashboard.metrics_history')

# ============================================================
# Configuration
# ============================================================

METRICS_HISTORY_PATH = os.getenv(
    'METRICS_HISTORY_PATH',
    'logs/metrics_history.sqlite',
)
METRICS_HISTORY_INTERVAL = int(os.getenv('METRICS_HISTORY_INTERVAL', '30'))
METRICS_HISTORY_RETENTION_DAYS = int(os.getenv('METRICS_HISTORY_RETENTION_DAYS', '3'))
METRICS_HISTORY_MAX_ROWS = int(os.getenv('METRICS_HISTORY_MAX_ROWS', '50000'))

ARCHIVE_LOG_DIR = os.getenv('ARCHIVE_LOG_DIR', 'logs/archive')
ARCHIVE_LOG_KEEP_COUNT = int(os.getenv('ARCHIVE_LOG_KEEP_COUNT', '20'))

# ============================================================
# Database Schema
# ============================================================

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS metrics_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    worker_pid INTEGER NOT NULL,
    pool_saturation REAL,
    pool_checked_out INTEGER,
    pool_checked_in INTEGER,
    pool_overflow INTEGER,
    pool_max_capacity INTEGER,
    redis_used_memory INTEGER,
    redis_hit_rate REAL,
    rc_l1_hit_rate REAL,
    rc_l2_hit_rate REAL,
    rc_miss_rate REAL,
    latency_p50_ms REAL,
    latency_p95_ms REAL,
    latency_p99_ms REAL,
    latency_count INTEGER,
    slow_query_active INTEGER,
    slow_query_waiting INTEGER,
    worker_rss_bytes INTEGER,
    service_rss_bytes INTEGER,
    system_mem_available_mb REAL,
    system_mem_used_pct REAL,
    rq_workers_total INTEGER,
    rq_workers_busy INTEGER,
    rq_queue_depth INTEGER,
    heavy_query_slots_active INTEGER,
    heavy_query_guard_reject_total INTEGER,
    heavy_query_memory_error_total INTEGER,
    heavy_query_async_fallback_total INTEGER,
    cache_hit_count INTEGER,
    cache_miss_count INTEGER,
    online_count INTEGER,
    sync_id TEXT,
    synced INTEGER DEFAULT 0
);
"""

# New columns added after initial schema — used for ALTER TABLE migration.
_MIGRATION_COLUMNS = [
    ("slow_query_active", "INTEGER"),
    ("slow_query_waiting", "INTEGER"),
    ("worker_rss_bytes", "INTEGER"),
    ("service_rss_bytes", "INTEGER"),
    ("system_mem_available_mb", "REAL"),
    ("system_mem_used_pct", "REAL"),
    ("rq_workers_total", "INTEGER"),
    ("rq_workers_busy", "INTEGER"),
    ("rq_queue_depth", "INTEGER"),
    ("heavy_query_slots_active", "INTEGER"),
    ("heavy_query_guard_reject_total", "INTEGER"),
    ("heavy_query_memory_error_total", "INTEGER"),
    ("heavy_query_async_fallback_total", "INTEGER"),
    ("cache_hit_count", "INTEGER"),
    ("cache_miss_count", "INTEGER"),
    ("online_count", "INTEGER"),
    ("sync_id", "TEXT"),
    ("synced", "INTEGER DEFAULT 0"),
]

CREATE_INDEX_SQL = (
    "CREATE INDEX IF NOT EXISTS idx_metrics_ts ON metrics_snapshots(ts);"
)
CREATE_INDEX_SYNCED_SQL = (
    "CREATE INDEX IF NOT EXISTS idx_metrics_synced ON metrics_snapshots(synced);"
)

_HOSTNAME = socket.gethostname()

COLUMNS = [
    "ts", "worker_pid",
    "pool_saturation", "pool_checked_out", "pool_checked_in",
    "pool_overflow", "pool_max_capacity",
    "redis_used_memory", "redis_hit_rate",
    "rc_l1_hit_rate", "rc_l2_hit_rate", "rc_miss_rate",
    "latency_p50_ms", "latency_p95_ms", "latency_p99_ms", "latency_count",
    "slow_query_active", "slow_query_waiting", "worker_rss_bytes",
    "service_rss_bytes",
    "system_mem_available_mb", "system_mem_used_pct",
    "rq_workers_total", "rq_workers_busy", "rq_queue_depth",
    "heavy_query_slots_active",
    "heavy_query_guard_reject_total",
    "heavy_query_memory_error_total",
    "heavy_query_async_fallback_total",
    "cache_hit_count", "cache_miss_count",
    "online_count",
]


# ============================================================
# Archive Log Cleanup
# ============================================================

_ARCHIVE_LOG_PREFIXES = ("access_", "error_", "watchdog_", "rq_worker_", "startup_")


def cleanup_archive_logs(
    archive_dir: str = ARCHIVE_LOG_DIR,
    keep_per_type: int = ARCHIVE_LOG_KEEP_COUNT,
) -> int:
    """Delete old rotated log files from the archive directory.

    Keeps the most recent *keep_per_type* files per log type (by mtime).
    Returns the total number of files deleted.
    """
    archive_path = Path(archive_dir)
    if not archive_path.is_dir():
        return 0

    deleted = 0
    for prefix in _ARCHIVE_LOG_PREFIXES:
        files = sorted(
            (f for f in archive_path.iterdir() if f.name.startswith(prefix) and f.is_file()),
            key=lambda f: f.stat().st_mtime,
            reverse=True,
        )
        for old_file in files[keep_per_type:]:
            try:
                old_file.unlink()
                deleted += 1
            except OSError as exc:
                logger.warning("Failed to delete archive log %s: %s", old_file, exc)

    if deleted > 0:
        logger.info("Cleaned up %d archive log files from %s", deleted, archive_dir)
    return deleted


# ============================================================
# Metrics History Store
# ============================================================

class MetricsHistoryStore:
    """SQLite-based metrics history store (follows LogStore pattern)."""

    def __init__(self, db_path: str = METRICS_HISTORY_PATH):
        self.db_path = db_path
        self._local = threading.local()
        self._write_lock = threading.Lock()
        self._initialized = False

    def initialize(self) -> None:
        if self._initialized:
            return
        db_dir = Path(self.db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(CREATE_TABLE_SQL)
            # Migrate existing databases: add new columns if missing.
            # Must run BEFORE index creation (indexes may reference new columns).
            for col_name, col_type in _MIGRATION_COLUMNS:
                try:
                    cursor.execute(
                        f"ALTER TABLE metrics_snapshots ADD COLUMN {col_name} {col_type}"
                    )
                except sqlite3.OperationalError:
                    pass  # Column already exists — tolerate duplicate column error.
            cursor.execute(CREATE_INDEX_SQL)
            cursor.execute(CREATE_INDEX_SYNCED_SQL)
            conn.commit()
        self._initialized = True
        logger.info("Metrics history store initialized at %s", self.db_path)

    @contextmanager
    def _get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        if not hasattr(self._local, 'connection') or self._local.connection is None:
            self._local.connection = sqlite3.connect(
                self.db_path, timeout=10.0, check_same_thread=False,
            )
            self._local.connection.row_factory = sqlite3.Row
        try:
            yield self._local.connection
        except sqlite3.Error as exc:
            logger.error("Metrics history DB error: %s", exc)
            try:
                self._local.connection.close()
            except Exception:
                pass
            self._local.connection = None
            raise

    def _generate_sync_id(self, rowid: int) -> str:
        return f"{_HOSTNAME}_metrics_snapshots_{rowid}"

    def write_snapshot(self, data: Dict[str, Any]) -> bool:
        if not self._initialized:
            self.initialize()
        ts = datetime.now().isoformat()
        pid = os.getpid()
        pool = data.get("pool") or {}
        redis = data.get("redis") or {}
        rc = data.get("route_cache") or {}
        lat = data.get("latency") or {}
        try:
            with self._write_lock:
                with self._get_connection() as conn:
                    cursor = conn.execute(
                        """
                        INSERT INTO metrics_snapshots
                            (ts, worker_pid,
                             pool_saturation, pool_checked_out, pool_checked_in,
                             pool_overflow, pool_max_capacity,
                             redis_used_memory, redis_hit_rate,
                             rc_l1_hit_rate, rc_l2_hit_rate, rc_miss_rate,
                             latency_p50_ms, latency_p95_ms, latency_p99_ms, latency_count,
                             slow_query_active, slow_query_waiting, worker_rss_bytes,
                             service_rss_bytes,
                             system_mem_available_mb, system_mem_used_pct,
                             rq_workers_total, rq_workers_busy,
                             rq_queue_depth, heavy_query_slots_active,
                             heavy_query_guard_reject_total,
                             heavy_query_memory_error_total,
                             heavy_query_async_fallback_total,
                             cache_hit_count, cache_miss_count,
                             online_count,
                             synced)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0)
                        """,
                        (
                            ts, pid,
                            pool.get("saturation"),
                            pool.get("checked_out"),
                            pool.get("checked_in"),
                            pool.get("overflow"),
                            pool.get("max_capacity"),
                            redis.get("used_memory"),
                            redis.get("hit_rate"),
                            rc.get("l1_hit_rate"),
                            rc.get("l2_hit_rate"),
                            rc.get("miss_rate"),
                            lat.get("p50_ms"),
                            lat.get("p95_ms"),
                            lat.get("p99_ms"),
                            lat.get("count"),
                            data.get("slow_query_active"),
                            data.get("slow_query_waiting"),
                            data.get("worker_rss_bytes"),
                            data.get("service_rss_bytes"),
                            data.get("system_mem_available_mb"),
                            data.get("system_mem_used_pct"),
                            data.get("rq_workers_total"),
                            data.get("rq_workers_busy"),
                            data.get("rq_queue_depth"),
                            data.get("heavy_query_slots_active"),
                            data.get("heavy_query_guard_reject_total"),
                            data.get("heavy_query_memory_error_total"),
                            data.get("heavy_query_async_fallback_total"),
                            data.get("cache_hit_count"),
                            data.get("cache_miss_count"),
                            data.get("online_count"),
                        ),
                    )
                    rowid = cursor.lastrowid
                    conn.execute(
                        "UPDATE metrics_snapshots SET sync_id = ? WHERE id = ?",
                        (self._generate_sync_id(rowid), rowid)
                    )
                    conn.commit()
            return True
        except Exception as exc:
            logger.debug("Failed to write metrics snapshot: %s", exc)
            return False

    def query_snapshots(self, minutes: int = 30) -> List[Dict[str, Any]]:
        if not self._initialized:
            self.initialize()
        cutoff = (datetime.now() - timedelta(minutes=minutes)).isoformat()
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    "SELECT * FROM metrics_snapshots WHERE ts >= ? ORDER BY ts ASC",
                    (cutoff,),
                )
                return [dict(row) for row in cursor.fetchall()]
        except Exception as exc:
            logger.error("Failed to query metrics snapshots: %s", exc)
            return []

    def query_snapshots_aggregated(
        self, minutes: int = 30, bucket_seconds: int = 30,
    ) -> List[Dict[str, Any]]:
        """Return time-bucketed aggregated snapshots for trend charts.

        Groups raw rows into *bucket_seconds*-wide windows and returns
        MAX for gauge metrics, SUM for latency_count, and worker_count.
        """
        if not self._initialized:
            self.initialize()
        cutoff = (datetime.now() - timedelta(minutes=minutes)).isoformat()
        # NOTE: stored ts is naive local time (datetime.now().isoformat()).
        # SQLite strftime('%s', ts) treats input as UTC by default, so we
        # add 'utc' modifier to tell SQLite "this is local time → convert
        # to UTC first", then convert back with 'localtime' for display.
        sql = f"""
            SELECT
                datetime(
                    (CAST(strftime('%s', ts, 'utc') AS INTEGER) / {bucket_seconds}) * {bucket_seconds},
                    'unixepoch', 'localtime'
                ) AS ts,
                MAX(pool_saturation)    AS pool_saturation,
                MAX(pool_checked_out)   AS pool_checked_out,
                MAX(pool_checked_in)    AS pool_checked_in,
                MAX(pool_overflow)      AS pool_overflow,
                MAX(pool_max_capacity)  AS pool_max_capacity,
                MAX(redis_used_memory)  AS redis_used_memory,
                MAX(redis_hit_rate)     AS redis_hit_rate,
                MAX(rc_l1_hit_rate)     AS rc_l1_hit_rate,
                MAX(rc_l2_hit_rate)     AS rc_l2_hit_rate,
                MAX(rc_miss_rate)       AS rc_miss_rate,
                MAX(latency_p50_ms)     AS latency_p50_ms,
                MAX(latency_p95_ms)     AS latency_p95_ms,
                MAX(latency_p99_ms)     AS latency_p99_ms,
                SUM(latency_count)      AS latency_count,
                MAX(slow_query_active)  AS slow_query_active,
                MAX(slow_query_waiting) AS slow_query_waiting,
                MAX(worker_rss_bytes)   AS worker_rss_bytes,
                MAX(service_rss_bytes)  AS service_rss_bytes,
                MIN(system_mem_available_mb) AS system_mem_available_mb,
                MAX(system_mem_used_pct) AS system_mem_used_pct,
                MAX(rq_workers_total)   AS rq_workers_total,
                MAX(rq_workers_busy)    AS rq_workers_busy,
                MAX(rq_queue_depth)     AS rq_queue_depth,
                MAX(heavy_query_slots_active) AS heavy_query_slots_active,
                MAX(heavy_query_guard_reject_total) AS heavy_query_guard_reject_total,
                MAX(heavy_query_memory_error_total) AS heavy_query_memory_error_total,
                MAX(heavy_query_async_fallback_total) AS heavy_query_async_fallback_total,
                SUM(cache_hit_count)    AS cache_hit_count,
                SUM(cache_miss_count)   AS cache_miss_count,
                MAX(online_count)       AS online_count,
                COUNT(DISTINCT worker_pid) AS worker_count,
                ROUND(MAX(redis_used_memory) / 1048576.0, 2) AS redis_used_memory_mb
            FROM metrics_snapshots
            WHERE ts >= ? AND synced = 0
            GROUP BY (CAST(strftime('%s', ts, 'utc') AS INTEGER) / {bucket_seconds})
            ORDER BY ts ASC
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(sql, (cutoff,))
                return [dict(row) for row in cursor.fetchall()]
        except Exception as exc:
            logger.error("Failed to query aggregated metrics snapshots: %s", exc)
            return []

    def cleanup(self) -> int:
        if not self._initialized:
            return 0
        deleted = 0
        try:
            with self._write_lock:
                with self._get_connection() as conn:
                    cutoff = (
                        datetime.now() - timedelta(days=METRICS_HISTORY_RETENTION_DAYS)
                    ).isoformat()
                    cursor = conn.execute(
                        "DELETE FROM metrics_snapshots WHERE ts < ?", (cutoff,),
                    )
                    deleted += cursor.rowcount
                    row = conn.execute(
                        "SELECT COUNT(*) FROM metrics_snapshots",
                    ).fetchone()
                    count = row[0] if row else 0
                    if count > METRICS_HISTORY_MAX_ROWS:
                        excess = count - METRICS_HISTORY_MAX_ROWS
                        cursor = conn.execute(
                            """
                            DELETE FROM metrics_snapshots WHERE id IN (
                                SELECT id FROM metrics_snapshots ORDER BY ts ASC LIMIT ?
                            )
                            """,
                            (excess,),
                        )
                        deleted += cursor.rowcount
                    conn.commit()
            if deleted > 0:
                logger.info("Cleaned up %d metrics history rows", deleted)
        except Exception as exc:
            logger.error("Failed to cleanup metrics history: %s", exc)
        return deleted

    def get_unsynced(self, batch_size: int = 500) -> List[Dict[str, Any]]:
        """Return up to batch_size unsynced metrics rows (synced=0)."""
        if not self._initialized:
            self.initialize()
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    "SELECT * FROM metrics_snapshots WHERE synced = 0 ORDER BY id ASC LIMIT ?",
                    (batch_size,)
                )
                return [dict(row) for row in cursor.fetchall()]
        except Exception as exc:
            logger.error("Failed to get_unsynced metrics: %s", exc)
            return []

    def mark_synced(self, rowids: List[int]) -> None:
        """Mark the given metrics row ids as synced=1."""
        if not rowids or not self._initialized:
            return
        try:
            with self._write_lock:
                with self._get_connection() as conn:
                    placeholders = ",".join("?" * len(rowids))
                    conn.execute(
                        f"UPDATE metrics_snapshots SET synced = 1 WHERE id IN ({placeholders})",
                        rowids
                    )
                    conn.commit()
        except Exception as exc:
            logger.error("Failed to mark_synced metrics: %s", exc)

    def cleanup_synced(self, older_than_hours: int = 1) -> int:
        """Delete synced=1 metrics older than older_than_hours. Returns deleted count."""
        if not self._initialized:
            return 0
        cutoff = (datetime.now() - timedelta(hours=older_than_hours)).isoformat()
        try:
            with self._write_lock:
                with self._get_connection() as conn:
                    cursor = conn.execute(
                        "DELETE FROM metrics_snapshots WHERE synced = 1 AND ts < ?",
                        (cutoff,)
                    )
                    deleted = cursor.rowcount
                    conn.commit()
            if deleted > 0:
                logger.info("Cleaned up %d synced metrics rows", deleted)
            return deleted
        except Exception as exc:
            logger.error("Failed to cleanup_synced metrics: %s", exc)
            return 0

    def purge(self) -> int:
        """Delete ALL rows from the metrics_snapshots table.

        Useful after schema/measurement fixes to discard stale data
        (e.g. peak-RSS or timezone-shifted timestamps).
        """
        if not self._initialized:
            self.initialize()
        try:
            with self._write_lock:
                with self._get_connection() as conn:
                    cursor = conn.execute("DELETE FROM metrics_snapshots")
                    deleted = cursor.rowcount
                    conn.commit()
            logger.info("Purged all %d metrics history rows", deleted)
            return deleted
        except Exception as exc:
            logger.error("Failed to purge metrics history: %s", exc)
            return 0


# ============================================================
# Background Collector
# ============================================================

class MetricsHistoryCollector:
    """Daemon thread that snapshots metrics at a fixed interval."""

    def __init__(
        self,
        app: Any = None,
        store: Optional[MetricsHistoryStore] = None,
        interval: int = METRICS_HISTORY_INTERVAL,
    ):
        self._app = app
        self._store = store or get_metrics_history_store()
        self.interval = interval
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._cleanup_counter = 0

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="metrics-history-collector",
        )
        self._thread.start()
        logger.info(
            "Metrics history collector started (interval=%ds)", self.interval,
        )

    def stop(self) -> None:
        if self._thread and self._thread.is_alive():
            self._stop_event.set()
            self._thread.join(timeout=5)
            logger.info("Metrics history collector stopped")

    def _run(self) -> None:
        # Collect immediately on start, then loop.
        self._collect_snapshot()
        while not self._stop_event.wait(self.interval):
            self._collect_snapshot()
            # Run cleanup every ~100 intervals (~50 min at 30s).
            self._cleanup_counter += 1
            if self._cleanup_counter >= 100:
                self._cleanup_counter = 0
                self._store.cleanup()
                try:
                    cleanup_archive_logs()
                except Exception as exc:
                    logger.debug("Archive log cleanup failed: %s", exc)

    def _reset_route_cache_hit_miss_counts(self) -> Dict[str, int]:
        backend = None
        try:
            if self._app is not None:
                with self._app.app_context():
                    from flask import current_app
                    backend = current_app.extensions.get("cache")
            else:
                from flask import current_app
                backend = current_app.extensions.get("cache")
        except Exception:
            backend = None

        if backend is None:
            return {"hits": 0, "misses": 0}

        reset_fn = getattr(backend, "reset_hit_miss_counts", None)
        if callable(reset_fn):
            try:
                payload = reset_fn()
                return {
                    "hits": int(payload.get("hits", 0)),
                    "misses": int(payload.get("misses", 0)),
                }
            except Exception:
                return {"hits": 0, "misses": 0}

        l1 = getattr(backend, "_l1", None)
        reset_l1_fn = getattr(l1, "reset_hit_miss_counts", None) if l1 is not None else None
        if callable(reset_l1_fn):
            try:
                payload = reset_l1_fn()
                return {
                    "hits": int(payload.get("hits", 0)),
                    "misses": int(payload.get("misses", 0)),
                }
            except Exception:
                return {"hits": 0, "misses": 0}

        return {"hits": 0, "misses": 0}

    def _collect_snapshot(self) -> None:
        try:
            data: Dict[str, Any] = {}

            # Pool status (includes slow_query_active and slow_query_waiting)
            try:
                from mes_dashboard.core.database import get_pool_status
                pool_status = get_pool_status()
                data["pool"] = pool_status
                data["slow_query_active"] = pool_status.get("slow_query_active", 0)
                data["slow_query_waiting"] = pool_status.get("slow_query_waiting", 0)
            except Exception:
                data["pool"] = {}
                data["slow_query_active"] = 0
                data["slow_query_waiting"] = 0

            # Worker RSS memory (current, not peak)
            try:
                from mes_dashboard.core.interactive_memory_guard import process_rss_mb
                rss_mb = process_rss_mb()
                data["worker_rss_bytes"] = int(rss_mb * 1024 * 1024) if rss_mb is not None else 0
            except Exception:
                data["worker_rss_bytes"] = 0

            try:
                from mes_dashboard.core.worker_memory_guard import get_service_memory_snapshot
                service_memory = get_service_memory_snapshot()
                data["service_rss_bytes"] = int(service_memory.get("total_rss_bytes", 0) or 0)
            except Exception:
                data["service_rss_bytes"] = 0

            # System memory (total machine memory)
            try:
                import psutil
                vm = psutil.virtual_memory()
                data["system_mem_available_mb"] = round(vm.available / (1024 * 1024), 1)
                data["system_mem_used_pct"] = round(vm.percent, 1)
            except Exception:
                data["system_mem_available_mb"] = None
                data["system_mem_used_pct"] = None

            # Redis
            try:
                from mes_dashboard.core.redis_client import (
                    get_redis_client,
                    REDIS_ENABLED,
                )
                if REDIS_ENABLED:
                    client = get_redis_client()
                    if client is not None:
                        info = client.info(section="memory")
                        stats_info = client.info(section="stats")
                        hits = int(stats_info.get("keyspace_hits", 0))
                        misses = int(stats_info.get("keyspace_misses", 0))
                        total = hits + misses
                        data["redis"] = {
                            "used_memory": info.get("used_memory", 0),
                            "hit_rate": round(hits / total, 4) if total > 0 else 0,
                        }
                    else:
                        data["redis"] = {}
                else:
                    data["redis"] = {}
            except Exception:
                data["redis"] = {}

            # Route cache
            try:
                if self._app:
                    with self._app.app_context():
                        from mes_dashboard.routes.health_routes import (
                            get_route_cache_status,
                        )
                        rc = get_route_cache_status()
                else:
                    from mes_dashboard.routes.health_routes import (
                        get_route_cache_status,
                    )
                    rc = get_route_cache_status()
                data["route_cache"] = {
                    "l1_hit_rate": rc.get("l1_hit_rate"),
                    "l2_hit_rate": rc.get("l2_hit_rate"),
                    "miss_rate": rc.get("miss_rate"),
                }
            except Exception:
                data["route_cache"] = {}

            cache_counts = self._reset_route_cache_hit_miss_counts()
            data["cache_hit_count"] = cache_counts.get("hits", 0)
            data["cache_miss_count"] = cache_counts.get("misses", 0)

            # Query latency
            try:
                from mes_dashboard.core.metrics import get_metrics_summary
                summary = get_metrics_summary()
                data["latency"] = {
                    "p50_ms": summary.get("p50_ms", 0),
                    "p95_ms": summary.get("p95_ms", 0),
                    "p99_ms": summary.get("p99_ms", 0),
                    "count": summary.get("count", 0),
                }
            except Exception:
                data["latency"] = {}

            # RQ worker & queue metrics
            try:
                from mes_dashboard.services.rq_monitor_service import (
                    get_rq_worker_details,
                    get_rq_queue_details,
                )
                from mes_dashboard.core.global_concurrency import get_active_slot_count
                w = get_rq_worker_details().get("summary", {})
                data["rq_workers_total"] = w.get("total", 0)
                data["rq_workers_busy"] = w.get("busy", 0)
                data["rq_queue_depth"] = get_rq_queue_details().get("total_queued", 0)
                data["heavy_query_slots_active"] = get_active_slot_count()
                if (
                    int(data["rq_queue_depth"] or 0) > 0
                    and int(data["rq_workers_total"] or 0) == 0
                ):
                    logger.warning(
                        "RQ dead worker alert: queue_depth=%s but no workers available",
                        data["rq_queue_depth"],
                    )
            except Exception:
                pass  # columns stay None → SQLite stores NULL

            # Heavy query guard telemetry counters
            try:
                from mes_dashboard.core.heavy_query_telemetry import (
                    get_heavy_query_telemetry,
                )
                guard = get_heavy_query_telemetry()
                data["heavy_query_guard_reject_total"] = int(
                    guard.get("guard_reject_total", 0)
                )
                data["heavy_query_memory_error_total"] = int(
                    guard.get("memory_error_total", 0)
                )
                data["heavy_query_async_fallback_total"] = int(
                    guard.get("async_fallback_total", 0)
                )
            except Exception:
                data["heavy_query_guard_reject_total"] = 0
                data["heavy_query_memory_error_total"] = 0
                data["heavy_query_async_fallback_total"] = 0

            # Online count
            try:
                from mes_dashboard.core.login_session_store import get_login_session_store
                data["online_count"] = get_login_session_store().get_active_count()
            except Exception:
                data["online_count"] = None

            self._store.write_snapshot(data)
        except Exception as exc:
            logger.debug("Metrics snapshot collection failed: %s", exc)


# ============================================================
# Global Instance & Lifecycle
# ============================================================

_STORE: Optional[MetricsHistoryStore] = None
_COLLECTOR: Optional[MetricsHistoryCollector] = None


def get_metrics_history_store() -> MetricsHistoryStore:
    global _STORE
    if _STORE is None:
        _STORE = MetricsHistoryStore()
        _STORE.initialize()
    return _STORE


def start_metrics_history(app: Any = None) -> None:
    global _COLLECTOR
    store = get_metrics_history_store()
    _COLLECTOR = MetricsHistoryCollector(app=app, store=store)
    _COLLECTOR.start()


def stop_metrics_history() -> None:
    global _COLLECTOR
    if _COLLECTOR is not None:
        _COLLECTOR.stop()
        _COLLECTOR = None
