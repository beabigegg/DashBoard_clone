# -*- coding: utf-8 -*-
"""Scheduled anomaly detection computation daemon.

Runs anomaly detection on startup and daily at a configured hour (default 08:00).
Before each run, ensures all required spool Parquet files exist by queuing
dataset queries sequentially (one at a time) to avoid memory pressure.
Results are cached in Redis for all workers to read.

Pattern follows realtime_equipment_cache.py: daemon thread + Event stop signal.
"""

from __future__ import annotations

import logging
import os
import re
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Tuple

logger = logging.getLogger("mes_dashboard.anomaly_detection_scheduler")

_WORKER_THREAD: threading.Thread | None = None
_STOP_EVENT = threading.Event()

# Configurable schedule hour (0-23), default 08:00 local time
_SCHEDULE_HOUR = int(os.getenv("ANOMALY_DETECTION_SCHEDULE_HOUR", "8"))
# Check interval for the scheduler loop (seconds)
_CHECK_INTERVAL = int(os.getenv("ANOMALY_DETECTION_CHECK_INTERVAL", "60"))
# Delay between sequential spool seed queries (seconds)
_SEED_QUERY_DELAY = int(os.getenv("ANOMALY_SEED_QUERY_DELAY", "5"))

# Dataset namespace → lookback days for seed queries
_SPOOL_SEED_CONFIG: List[Tuple[str, int]] = [
    ("yield_alert_dataset", 14),
    ("reject_dataset", 14),
    ("hold_dataset", 30),
    ("resource_dataset", 60),
]


def _has_spool(namespace: str) -> bool:
    """Check if a usable spool Parquet file exists for namespace."""
    from mes_dashboard.core.query_spool_store import QUERY_SPOOL_DIR

    ns = re.sub(r"[^A-Za-z0-9._-]", "_", namespace.strip()) or "default"
    ns_dir = QUERY_SPOOL_DIR.resolve() / ns
    if not ns_dir.exists():
        return False
    try:
        return any(ns_dir.glob("*.parquet"))
    except Exception:
        return False


def _seed_spool(namespace: str, lookback_days: int) -> bool:
    """Trigger a primary query for a single dataset to generate its spool file.

    Returns True if the seed completed (hit cache or queried Oracle).
    """
    today = datetime.now()
    start_date = (today - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    end_date = today.strftime("%Y-%m-%d")

    try:
        if namespace == "yield_alert_dataset":
            from mes_dashboard.services.yield_alert_dataset_cache import execute_primary_query
            execute_primary_query(start_date=start_date, end_date=end_date)

        elif namespace == "reject_dataset":
            from mes_dashboard.services.reject_dataset_cache import execute_primary_query
            execute_primary_query(
                mode="date_range", start_date=start_date, end_date=end_date,
            )

        elif namespace == "hold_dataset":
            from mes_dashboard.services.hold_dataset_cache import execute_primary_query
            execute_primary_query(start_date=start_date, end_date=end_date)

        elif namespace == "resource_dataset":
            from mes_dashboard.services.resource_dataset_cache import execute_primary_query
            execute_primary_query(start_date=start_date, end_date=end_date)

        else:
            logger.warning("Unknown spool namespace for seeding: %s", namespace)
            return False

        logger.info("Spool seed complete: %s (%dd lookback)", namespace, lookback_days)
        return True

    except Exception as exc:
        logger.error("Spool seed failed for %s: %s", namespace, exc)
        return False


def _ensure_spool_data() -> int:
    """Check all required spool files; seed missing ones sequentially.

    Returns the number of datasets seeded.
    """
    seeded = 0
    for namespace, lookback_days in _SPOOL_SEED_CONFIG:
        if _STOP_EVENT.is_set():
            break
        if _has_spool(namespace):
            logger.debug("Spool exists: %s", namespace)
            continue

        logger.info("Spool missing: %s — queuing seed query (%dd)", namespace, lookback_days)
        if _seed_spool(namespace, lookback_days):
            seeded += 1

        # Delay between queries to reduce memory pressure
        if not _STOP_EVENT.is_set():
            _STOP_EVENT.wait(_SEED_QUERY_DELAY)

    return seeded


def _run_computation() -> bool:
    """Execute anomaly detection with distributed lock."""
    from mes_dashboard.core.redis_client import release_lock, try_acquire_lock
    from mes_dashboard.services.anomaly_detection_sql_runtime import compute_and_cache_all

    if not try_acquire_lock("anomaly_detection_compute", ttl_seconds=600):
        logger.debug("Another worker is computing anomalies, skipping")
        return False

    try:
        result = compute_and_cache_all()
        total = result.get("data", {}).get("total_count", 0)
        logger.info("Anomaly detection scheduled run complete: %d anomalies", total)
        return True
    except Exception as exc:
        logger.error("Anomaly detection scheduled run failed: %s", exc)
        return False
    finally:
        release_lock("anomaly_detection_compute")


def _scheduler_loop() -> None:
    """Background loop: seed spool → compute on startup, then daily at _SCHEDULE_HOUR."""
    logger.info(
        "Anomaly detection scheduler started (schedule_hour=%02d:00, check_interval=%ds)",
        _SCHEDULE_HOUR,
        _CHECK_INTERVAL,
    )

    # Initial: delay 10s for other services, then ensure spool data → compute
    _STOP_EVENT.wait(10)
    if _STOP_EVENT.is_set():
        return

    logger.info("Anomaly detection: ensuring spool data for initial computation...")
    seeded = _ensure_spool_data()
    if seeded > 0:
        logger.info("Anomaly detection: seeded %d missing spool datasets", seeded)

    if not _STOP_EVENT.is_set():
        logger.info("Anomaly detection: running initial computation...")
        _run_computation()

    last_run_date: str | None = None

    while not _STOP_EVENT.is_set():
        _STOP_EVENT.wait(_CHECK_INTERVAL)
        if _STOP_EVENT.is_set():
            break

        now = datetime.now()
        today_str = now.strftime("%Y-%m-%d")

        # Run once per day at or after the scheduled hour
        if now.hour >= _SCHEDULE_HOUR and last_run_date != today_str:
            logger.info("Anomaly detection: daily run — ensuring spool freshness...")
            _ensure_spool_data()

            if _STOP_EVENT.is_set():
                break

            logger.info("Anomaly detection: daily scheduled run (hour=%02d)...", now.hour)
            if _run_computation():
                last_run_date = today_str

    logger.info("Anomaly detection scheduler stopped")


def init_anomaly_detection_scheduler(app=None) -> None:
    """Start the anomaly detection scheduler daemon thread."""
    global _WORKER_THREAD

    from mes_dashboard.core.feature_flags import resolve_bool_flag

    if not resolve_bool_flag("ANALYTICS_ANOMALY_DETECTION_ENABLED", default=False):
        logger.info("Anomaly detection scheduler disabled (ANALYTICS_ANOMALY_DETECTION_ENABLED=false)")
        return

    if _WORKER_THREAD is not None and _WORKER_THREAD.is_alive():
        logger.warning("Anomaly detection scheduler already running")
        return

    _STOP_EVENT.clear()
    _WORKER_THREAD = threading.Thread(
        target=_scheduler_loop,
        daemon=True,
        name="anomaly-detection-scheduler",
    )
    _WORKER_THREAD.start()


def stop_anomaly_detection_scheduler() -> None:
    """Stop the scheduler daemon thread gracefully."""
    global _WORKER_THREAD
    if _WORKER_THREAD is not None and _WORKER_THREAD.is_alive():
        logger.info("Stopping anomaly detection scheduler...")
        _STOP_EVENT.set()
        _WORKER_THREAD.join(timeout=5)
        _WORKER_THREAD = None


def trigger_recalculation() -> dict:
    """Manually trigger anomaly detection recalculation (admin endpoint)."""
    from mes_dashboard.services.anomaly_detection_sql_runtime import compute_and_cache_all

    started_at = time.time()
    result = compute_and_cache_all()
    result["meta"]["triggered_by"] = "admin_manual"
    result["meta"]["total_latency_s"] = round(time.time() - started_at, 3)
    return result
