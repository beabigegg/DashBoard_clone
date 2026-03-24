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
MYSQL_SYNC_ENABLED: bool = os.getenv('MYSQL_SYNC_ENABLED', 'true').lower() == 'true'

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
        login_store=None,
        interval: int = SYNC_WORKER_INTERVAL,
    ):
        from mes_dashboard.core.log_store import get_log_store
        from mes_dashboard.core.metrics_history import get_metrics_history_store
        from mes_dashboard.core.login_session_store import get_login_session_store

        self._log_store = log_store or get_log_store()
        self._metrics_store = metrics_store or get_metrics_history_store()
        self._login_store = login_store or get_login_session_store()
        self.interval = interval
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if not MYSQL_SYNC_ENABLED:
            logger.info("SyncWorker disabled (MYSQL_SYNC_ENABLED=false)")
            return
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
        self._ensure_mysql_tables()
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
                self._sync_login_sessions()
            except Exception as exc:
                logger.warning("SyncWorker: login session sync error: %s", exc)
            try:
                self._cleanup_synced()
            except Exception as exc:
                logger.warning("SyncWorker: cleanup error: %s", exc)

    # ----------------------------------------------------------
    # Auto-create MySQL tables
    # ----------------------------------------------------------

    def _ensure_mysql_tables(self) -> None:
        """Create MySQL tables if they don't exist yet."""
        from sqlalchemy import text

        if not MYSQL_OPS_ENABLED:
            return

        ddl_statements = [
            """
            CREATE TABLE IF NOT EXISTS dashboard_logs (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                sync_id VARCHAR(255) UNIQUE,
                timestamp DATETIME(3),
                level VARCHAR(20),
                logger_name VARCHAR(255),
                message TEXT,
                request_id VARCHAR(100),
                user VARCHAR(100),
                ip VARCHAR(45),
                extra TEXT,
                INDEX idx_timestamp (timestamp),
                INDEX idx_level (level)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """,
            """
            CREATE TABLE IF NOT EXISTS dashboard_metrics_snapshots (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                sync_id VARCHAR(255) UNIQUE,
                ts DATETIME(3),
                worker_pid INT,
                pool_saturation DOUBLE,
                pool_checked_out INT,
                pool_checked_in INT,
                pool_overflow INT,
                pool_max_capacity INT,
                redis_used_memory BIGINT,
                redis_hit_rate DOUBLE,
                rc_l1_hit_rate DOUBLE,
                rc_l2_hit_rate DOUBLE,
                rc_miss_rate DOUBLE,
                latency_p50_ms DOUBLE,
                latency_p95_ms DOUBLE,
                latency_p99_ms DOUBLE,
                latency_count INT,
                slow_query_active INT,
                slow_query_waiting INT,
                worker_rss_bytes BIGINT,
                system_mem_available_mb DOUBLE,
                system_mem_used_pct DOUBLE,
                rq_workers_total INT,
                rq_workers_busy INT,
                rq_queue_depth INT,
                heavy_query_slots_active INT,
                heavy_query_guard_reject_total INT,
                heavy_query_memory_error_total INT,
                heavy_query_async_fallback_total INT,
                INDEX idx_ts (ts)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """,
            """
            CREATE TABLE IF NOT EXISTS dashboard_login_sessions (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                sync_id VARCHAR(255) UNIQUE,
                session_id VARCHAR(100),
                emp_id VARCHAR(50),
                username VARCHAR(100),
                display_name VARCHAR(200),
                real_name VARCHAR(100),
                department VARCHAR(200),
                email VARCHAR(200),
                phone VARCHAR(50),
                domain VARCHAR(50),
                ip VARCHAR(45),
                login_time DATETIME(3),
                last_active DATETIME(3),
                logout_time DATETIME(3),
                duration_sec INT,
                is_admin TINYINT DEFAULT 0,
                INDEX idx_login_time (login_time),
                INDEX idx_emp_id (emp_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """,
        ]
        metric_migration_columns = [
            "heavy_query_guard_reject_total INT",
            "heavy_query_memory_error_total INT",
            "heavy_query_async_fallback_total INT",
        ]

        try:
            with get_mysql_connection() as conn:
                for ddl in ddl_statements:
                    conn.execute(text(ddl))
                for column_spec in metric_migration_columns:
                    try:
                        conn.execute(
                            text(
                                f"ALTER TABLE dashboard_metrics_snapshots "
                                f"ADD COLUMN {column_spec}"
                            )
                        )
                    except Exception:
                        # Tolerate duplicate-column errors for existing deployments.
                        pass
            logger.info("SyncWorker: MySQL tables verified/created")
        except Exception as exc:
            logger.warning("SyncWorker: cannot ensure MySQL tables, will retry on next sync: %s", exc)

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
                                 heavy_query_slots_active,
                                 heavy_query_guard_reject_total,
                                 heavy_query_memory_error_total,
                                 heavy_query_async_fallback_total)
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
                                 :heavy_query_slots_active,
                                 :heavy_query_guard_reject_total,
                                 :heavy_query_memory_error_total,
                                 :heavy_query_async_fallback_total)
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
                            "heavy_query_guard_reject_total": row.get("heavy_query_guard_reject_total"),
                            "heavy_query_memory_error_total": row.get("heavy_query_memory_error_total"),
                            "heavy_query_async_fallback_total": row.get("heavy_query_async_fallback_total"),
                        }
                    )
            self._metrics_store.mark_synced([r["id"] for r in rows])
            logger.debug("SyncWorker: synced %d metrics rows to MySQL", len(rows))
        except Exception as exc:
            logger.warning("SyncWorker: MySQL unavailable for metrics, will retry: %s", exc)

    # ----------------------------------------------------------
    # Login session sync
    # ----------------------------------------------------------

    def _sync_login_sessions(self) -> None:
        from sqlalchemy import text

        if not MYSQL_OPS_ENABLED:
            return

        rows = self._login_store.get_unsynced(batch_size=500)
        if not rows:
            return

        try:
            with get_mysql_connection() as conn:
                for row in rows:
                    conn.execute(
                        text("""
                            REPLACE INTO dashboard_login_sessions
                                (sync_id, session_id, emp_id, username, display_name,
                                 real_name, department, email, phone, domain, ip,
                                 login_time, last_active, logout_time, duration_sec, is_admin)
                            VALUES
                                (:sync_id, :session_id, :emp_id, :username, :display_name,
                                 :real_name, :department, :email, :phone, :domain, :ip,
                                 :login_time, :last_active, :logout_time, :duration_sec, :is_admin)
                        """),
                        {
                            "sync_id": row.get("sync_id"),
                            "session_id": row.get("session_id"),
                            "emp_id": row.get("emp_id"),
                            "username": row.get("username"),
                            "display_name": row.get("display_name"),
                            "real_name": row.get("real_name"),
                            "department": row.get("department"),
                            "email": row.get("email"),
                            "phone": row.get("phone"),
                            "domain": row.get("domain"),
                            "ip": row.get("ip"),
                            "login_time": _parse_ts(row.get("login_time")),
                            "last_active": _parse_ts(row.get("last_active")),
                            "logout_time": _parse_ts(row.get("logout_time")),
                            "duration_sec": row.get("duration_sec"),
                            "is_admin": row.get("is_admin"),
                        },
                    )
            self._login_store.mark_synced([r["id"] for r in rows])
            logger.debug("SyncWorker: synced %d login session rows to MySQL", len(rows))
        except Exception as exc:
            logger.warning("SyncWorker: MySQL unavailable for login sessions, will retry: %s", exc)

    # ----------------------------------------------------------
    # Cleanup
    # ----------------------------------------------------------

    def _cleanup_synced(self) -> None:
        self._log_store.cleanup_synced(older_than_hours=1)
        self._metrics_store.cleanup_synced(older_than_hours=1)
        self._login_store.cleanup_synced(older_than_hours=24)


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
