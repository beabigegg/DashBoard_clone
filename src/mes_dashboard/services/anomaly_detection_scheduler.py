# -*- coding: utf-8 -*-
"""Scheduled anomaly detection computation daemon.

Runs anomaly detection on startup and daily at a configured hour (default 08:00).
Results are cached in Redis for all workers to read.

Pattern follows realtime_equipment_cache.py: daemon thread + Event stop signal.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime

logger = logging.getLogger("mes_dashboard.anomaly_detection_scheduler")

_WORKER_THREAD: threading.Thread | None = None
_STOP_EVENT = threading.Event()

# Configurable schedule hour (0-23), default 08:00 local time
_SCHEDULE_HOUR = int(os.getenv("ANOMALY_DETECTION_SCHEDULE_HOUR", "8"))
# Check interval for the scheduler loop (seconds)
_CHECK_INTERVAL = int(os.getenv("ANOMALY_DETECTION_CHECK_INTERVAL", "60"))


def _run_computation() -> bool:
    """Execute anomaly detection with distributed lock."""
    from mes_dashboard.core.redis_client import release_lock, try_acquire_lock
    from mes_dashboard.services.anomaly_detection_sql_runtime import compute_and_cache_all

    if not try_acquire_lock("anomaly_detection_compute", ttl_seconds=300):
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
    """Background loop: compute on startup, then daily at _SCHEDULE_HOUR."""
    logger.info(
        "Anomaly detection scheduler started (schedule_hour=%02d:00, check_interval=%ds)",
        _SCHEDULE_HOUR,
        _CHECK_INTERVAL,
    )

    # Initial computation on startup (delay 10s to let other services initialize)
    _STOP_EVENT.wait(10)
    if _STOP_EVENT.is_set():
        return
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
