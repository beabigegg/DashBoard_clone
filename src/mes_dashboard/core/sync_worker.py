# -*- coding: utf-8 -*-
"""Dual-layer SQLite → MySQL sync worker.

Runs as a daemon thread.  Every SYNC_WORKER_INTERVAL seconds:
  1. Reads unsynced rows from LogStore (SQLite)
  2. INSERT IGNORE them into MySQL dashboard_logs
  3. Marks them synced in SQLite
  4. Repeats for MetricsHistoryStore → dashboard_metrics_snapshots
  5. Cleans up old synced rows from both SQLite DBs

MySQL offline tolerance: any connection error is caught, a warning is logged,
and the next cycle retries automatically.
"""

from __future__ import annotations

import logging
import os
import threading
from datetime import datetime
from typing import List, Dict, Any, Optional

logger = logging.getLogger('mes_dashboard.sync_worker')

SYNC_WORKER_INTERVAL = int(os.getenv('SYNC_WORKER_INTERVAL', '600'))  # 10 min

# Import at module level so tests can patch these names on this module.
from mes_dashboard.core.mysql_client import (  # noqa: E402
    MYSQL_OPS_ENABLED,
    get_mysql_connection,
)

# ============================================================
# SyncWorker
# ============================================================

class SyncWorker:
    """Background daemon thread that syncs SQLite → MySQL."""

    def __init__(
        self,
        log_store=None,
        metrics_store=None,
        interval: int = SYNC_WORKER_INTERVAL,
    ):
        from mes_dashboard.core.log_store import get_log_store
        from mes_dashboard.core.metrics_history import get_metrics_history_store

        self._log_store = log_store or get_log_store()
        self._metrics_store = metrics_store or get_metrics_history_store()
        self.interval = interval
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="sync-worker"
        )
        self._thread.start()
        logger.info("SyncWorker started (interval=%ds)", self.interval)

    def stop(self) -> None:
        if self._thread and self._thread.is_alive():
            self._stop_event.set()
            self._thread.join(timeout=10)
            logger.info("SyncWorker stopped")

    def _run(self) -> None:
        while not self._stop_event.wait(self.interval):
            try:
                self._sync_logs()
            except Exception as exc:
                logger.warning("SyncWorker: log sync error: %s", exc)
            try:
                self._sync_metrics()
            except Exception as exc:
                logger.warning("SyncWorker: metrics sync error: %s", exc)
            try:
                self._cleanup_synced()
            except Exception as exc:
                logger.warning("SyncWorker: cleanup error: %s", exc)

    # ----------------------------------------------------------
    # Log sync
    # ----------------------------------------------------------

    def _sync_logs(self) -> None:
        from sqlalchemy import text

        if not MYSQL_OPS_ENABLED:
            return

        rows = self._log_store.get_unsynced(batch_size=500)
        if not rows:
            return

        try:
            with get_mysql_connection() as conn:
                for row in rows:
                    ts = _parse_ts(row.get("timestamp"))
                    conn.execute(
                        text("""
                            INSERT IGNORE INTO dashboard_logs
                                (sync_id, timestamp, level, logger_name, message,
                                 request_id, user, ip, extra)
                            VALUES
                                (:sync_id, :timestamp, :level, :logger_name, :message,
                                 :request_id, :user, :ip, :extra)
                        """),
                        {
                            "sync_id": row.get("sync_id"),
                            "timestamp": ts,
                            "level": row.get("level"),
                            "logger_name": row.get("logger_name"),
                            "message": row.get("message"),
                            "request_id": row.get("request_id"),
                            "user": row.get("user"),
                            "ip": row.get("ip"),
                            "extra": row.get("extra"),
                        }
                    )
            # Mark synced after successful MySQL write
            self._log_store.mark_synced([r["id"] for r in rows])
            logger.debug("SyncWorker: synced %d log rows to MySQL", len(rows))
        except Exception as exc:
            logger.warning("SyncWorker: MySQL unavailable for logs, will retry: %s", exc)

    # ----------------------------------------------------------
    # Metrics sync
    # ----------------------------------------------------------

    def _sync_metrics(self) -> None:
        from sqlalchemy import text

        if not MYSQL_OPS_ENABLED:
            return

        rows = self._metrics_store.get_unsynced(batch_size=500)
        if not rows:
            return

        try:
            with get_mysql_connection() as conn:
                for row in rows:
                    ts = _parse_ts(row.get("ts"))
                    conn.execute(
                        text("""
                            INSERT IGNORE INTO dashboard_metrics_snapshots
                                (sync_id, ts, worker_pid,
                                 pool_saturation, pool_checked_out, pool_checked_in,
                                 pool_overflow, pool_max_capacity,
                                 redis_used_memory, redis_hit_rate,
                                 rc_l1_hit_rate, rc_l2_hit_rate, rc_miss_rate,
                                 latency_p50_ms, latency_p95_ms, latency_p99_ms, latency_count,
                                 slow_query_active, slow_query_waiting, worker_rss_bytes,
                                 system_mem_available_mb, system_mem_used_pct,
                                 rq_workers_total, rq_workers_busy, rq_queue_depth,
                                 heavy_query_slots_active)
                            VALUES
                                (:sync_id, :ts, :worker_pid,
                                 :pool_saturation, :pool_checked_out, :pool_checked_in,
                                 :pool_overflow, :pool_max_capacity,
                                 :redis_used_memory, :redis_hit_rate,
                                 :rc_l1_hit_rate, :rc_l2_hit_rate, :rc_miss_rate,
                                 :latency_p50_ms, :latency_p95_ms, :latency_p99_ms, :latency_count,
                                 :slow_query_active, :slow_query_waiting, :worker_rss_bytes,
                                 :system_mem_available_mb, :system_mem_used_pct,
                                 :rq_workers_total, :rq_workers_busy, :rq_queue_depth,
                                 :heavy_query_slots_active)
                        """),
                        {
                            "sync_id": row.get("sync_id"),
                            "ts": ts,
                            "worker_pid": row.get("worker_pid"),
                            "pool_saturation": row.get("pool_saturation"),
                            "pool_checked_out": row.get("pool_checked_out"),
                            "pool_checked_in": row.get("pool_checked_in"),
                            "pool_overflow": row.get("pool_overflow"),
                            "pool_max_capacity": row.get("pool_max_capacity"),
                            "redis_used_memory": row.get("redis_used_memory"),
                            "redis_hit_rate": row.get("redis_hit_rate"),
                            "rc_l1_hit_rate": row.get("rc_l1_hit_rate"),
                            "rc_l2_hit_rate": row.get("rc_l2_hit_rate"),
                            "rc_miss_rate": row.get("rc_miss_rate"),
                            "latency_p50_ms": row.get("latency_p50_ms"),
                            "latency_p95_ms": row.get("latency_p95_ms"),
                            "latency_p99_ms": row.get("latency_p99_ms"),
                            "latency_count": row.get("latency_count"),
                            "slow_query_active": row.get("slow_query_active"),
                            "slow_query_waiting": row.get("slow_query_waiting"),
                            "worker_rss_bytes": row.get("worker_rss_bytes"),
                            "system_mem_available_mb": row.get("system_mem_available_mb"),
                            "system_mem_used_pct": row.get("system_mem_used_pct"),
                            "rq_workers_total": row.get("rq_workers_total"),
                            "rq_workers_busy": row.get("rq_workers_busy"),
                            "rq_queue_depth": row.get("rq_queue_depth"),
                            "heavy_query_slots_active": row.get("heavy_query_slots_active"),
                        }
                    )
            self._metrics_store.mark_synced([r["id"] for r in rows])
            logger.debug("SyncWorker: synced %d metrics rows to MySQL", len(rows))
        except Exception as exc:
            logger.warning("SyncWorker: MySQL unavailable for metrics, will retry: %s", exc)

    # ----------------------------------------------------------
    # Cleanup
    # ----------------------------------------------------------

    def _cleanup_synced(self) -> None:
        self._log_store.cleanup_synced(older_than_hours=1)
        self._metrics_store.cleanup_synced(older_than_hours=1)


# ============================================================
# Helpers
# ============================================================

def _parse_ts(ts_str) -> Optional[datetime]:
    """Convert ISO text timestamp to datetime for MySQL DATETIME(3)."""
    if ts_str is None:
        return None
    try:
        return datetime.fromisoformat(ts_str)
    except (ValueError, TypeError):
        return None


# ============================================================
# Global instance
# ============================================================

_SYNC_WORKER: Optional[SyncWorker] = None


def start_sync_worker() -> None:
    global _SYNC_WORKER
    if _SYNC_WORKER is None:
        _SYNC_WORKER = SyncWorker()
    _SYNC_WORKER.start()


def stop_sync_worker() -> None:
    global _SYNC_WORKER
    if _SYNC_WORKER is not None:
        _SYNC_WORKER.stop()
        _SYNC_WORKER = None
