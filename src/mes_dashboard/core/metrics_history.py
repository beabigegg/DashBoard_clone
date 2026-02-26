# -*- coding: utf-8 -*-
"""SQLite-based metrics history store for admin performance dashboard.

Periodically snapshots system metrics (pool, redis, cache, latency)
into a SQLite database for historical trend visualization.
Follows the LogStore pattern from core/log_store.py.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import threading
import time
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
    worker_rss_bytes INTEGER
);
"""

# New columns added after initial schema — used for ALTER TABLE migration.
_MIGRATION_COLUMNS = [
    ("slow_query_active", "INTEGER"),
    ("slow_query_waiting", "INTEGER"),
    ("worker_rss_bytes", "INTEGER"),
]

CREATE_INDEX_SQL = (
    "CREATE INDEX IF NOT EXISTS idx_metrics_ts ON metrics_snapshots(ts);"
)

COLUMNS = [
    "ts", "worker_pid",
    "pool_saturation", "pool_checked_out", "pool_checked_in",
    "pool_overflow", "pool_max_capacity",
    "redis_used_memory", "redis_hit_rate",
    "rc_l1_hit_rate", "rc_l2_hit_rate", "rc_miss_rate",
    "latency_p50_ms", "latency_p95_ms", "latency_p99_ms", "latency_count",
    "slow_query_active", "slow_query_waiting", "worker_rss_bytes",
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
            cursor.execute(CREATE_INDEX_SQL)
            # Migrate existing databases: add new columns if missing.
            for col_name, col_type in _MIGRATION_COLUMNS:
                try:
                    cursor.execute(
                        f"ALTER TABLE metrics_snapshots ADD COLUMN {col_name} {col_type}"
                    )
                except sqlite3.OperationalError:
                    pass  # Column already exists — tolerate duplicate column error.
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
                    conn.execute(
                        """
                        INSERT INTO metrics_snapshots
                            (ts, worker_pid,
                             pool_saturation, pool_checked_out, pool_checked_in,
                             pool_overflow, pool_max_capacity,
                             redis_used_memory, redis_hit_rate,
                             rc_l1_hit_rate, rc_l2_hit_rate, rc_miss_rate,
                             latency_p50_ms, latency_p95_ms, latency_p99_ms, latency_count,
                             slow_query_active, slow_query_waiting, worker_rss_bytes)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
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
                        ),
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

            # Worker RSS memory
            try:
                import resource
                # ru_maxrss is in KB on Linux
                data["worker_rss_bytes"] = resource.getrusage(
                    resource.RUSAGE_SELF
                ).ru_maxrss * 1024
            except Exception:
                data["worker_rss_bytes"] = 0

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
