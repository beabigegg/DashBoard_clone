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
_SEED_QUERY_DELAY = int(os.getenv("ANOMALY_SEED_QUERY_DELAY", "10"))

# (source_namespace, anomaly_namespace, lookback_days)
# source_namespace: where execute_primary_query writes (shared with user pages)
# anomaly_namespace: isolated copy for anomaly detection (not affected by user queries)
_SPOOL_SEED_CONFIG: List[Tuple[str, str, int]] = [
    ("yield_alert_dataset", "anomaly_yield_dataset", 14),
    ("reject_dataset", "anomaly_reject_dataset", 14),
    ("hold_dataset", "anomaly_hold_dataset", 14),
    ("resource_dataset", "anomaly_resource_dataset", 14),
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


_ANOMALY_SPOOL_TTL = 90_000  # 25 hours — matches anomaly Redis cache TTL


def _copy_to_anomaly_namespace(source_ns: str, anomaly_ns: str) -> bool:
    """Copy the latest spool Parquet from source namespace to anomaly namespace.

    Also registers Redis metadata so the cleanup worker does not treat
    the copied file as an orphan.
    """
    import hashlib
    import json as _json
    import shutil

    from mes_dashboard.core.query_spool_store import QUERY_SPOOL_DIR

    src_dir = QUERY_SPOOL_DIR.resolve() / re.sub(r"[^A-Za-z0-9._-]", "_", source_ns)
    if not src_dir.exists():
        return False

    try:
        files = sorted(src_dir.glob("*.parquet"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not files:
            return False

        dest_dir = QUERY_SPOOL_DIR.resolve() / re.sub(r"[^A-Za-z0-9._-]", "_", anomaly_ns)
        dest_dir.mkdir(parents=True, exist_ok=True)

        # Remove old anomaly spool files before copying fresh data
        for old in dest_dir.glob("*.parquet"):
            old.unlink(missing_ok=True)

        # Use a stable query_id derived from the anomaly namespace
        query_id = hashlib.sha256(anomaly_ns.encode()).hexdigest()[:16]
        dest_path = dest_dir / f"{query_id}.parquet"
        shutil.copy2(str(files[0]), str(dest_path))

        # Register in Redis so cleanup worker recognizes it (not orphan)
        try:
            from mes_dashboard.core.redis_client import get_key, get_redis_client

            client = get_redis_client()
            if client is not None:
                now_ts = int(time.time())
                meta_key = get_key(f"{anomaly_ns}:spool_meta:{query_id}")
                metadata = {
                    "namespace": anomaly_ns,
                    "query_id": query_id,
                    "relative_path": str(dest_path.relative_to(QUERY_SPOOL_DIR.resolve())),
                    "row_count": -1,
                    "created_at": now_ts,
                    "expires_at": now_ts + _ANOMALY_SPOOL_TTL,
                    "file_size_bytes": int(dest_path.stat().st_size),
                }
                client.setex(meta_key, _ANOMALY_SPOOL_TTL, _json.dumps(metadata))
        except Exception as meta_exc:
            logger.warning("Failed to register anomaly spool metadata: %s", meta_exc)

        logger.info(
            "Copied spool %s -> %s (%s)",
            source_ns, anomaly_ns, dest_path.name,
        )
        return True
    except Exception as exc:
        logger.error("Failed to copy spool %s -> %s: %s", source_ns, anomaly_ns, exc)
        return False


def _seed_spool(source_ns: str, anomaly_ns: str, lookback_days: int) -> bool:
    """Ensure source spool exists, then copy to isolated anomaly namespace.

    Returns True if the anomaly spool was successfully created.
    """
    today = datetime.now()
    start_date = (today - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    end_date = today.strftime("%Y-%m-%d")

    # Step 1: Ensure source spool has data (trigger Oracle query if needed)
    if not _has_spool(source_ns):
        logger.info("Source spool missing: %s — querying Oracle (%dd)", source_ns, lookback_days)
        try:
            if source_ns == "yield_alert_dataset":
                from mes_dashboard.services.yield_alert_dataset_cache import execute_primary_query
                execute_primary_query(start_date=start_date, end_date=end_date)

            elif source_ns == "reject_dataset":
                from mes_dashboard.services.reject_dataset_cache import execute_primary_query
                execute_primary_query(
                    mode="date_range", start_date=start_date, end_date=end_date,
                )

            elif source_ns == "hold_dataset":
                from mes_dashboard.services.hold_dataset_cache import execute_primary_query
                execute_primary_query(start_date=start_date, end_date=end_date)

            elif source_ns == "resource_dataset":
                from mes_dashboard.services.resource_dataset_cache import execute_primary_query
                execute_primary_query(start_date=start_date, end_date=end_date)

            else:
                logger.warning("Unknown source namespace: %s", source_ns)
                return False
        except Exception as exc:
            logger.error("Spool seed Oracle query failed for %s: %s", source_ns, exc)
            return False

    # Step 2: Copy source spool to isolated anomaly namespace
    if _copy_to_anomaly_namespace(source_ns, anomaly_ns):
        logger.info("Spool seed complete: %s -> %s (%dd)", source_ns, anomaly_ns, lookback_days)
        return True

    logger.warning("Spool seed: copy failed for %s -> %s", source_ns, anomaly_ns)
    return False


def _ensure_spool_data() -> int:
    """Check all anomaly spool files; seed missing ones sequentially.

    Returns the number of datasets seeded.
    """
    seeded = 0
    for source_ns, anomaly_ns, lookback_days in _SPOOL_SEED_CONFIG:
        if _STOP_EVENT.is_set():
            break
        if _has_spool(anomaly_ns):
            logger.debug("Anomaly spool exists: %s", anomaly_ns)
            continue

        logger.info("Anomaly spool missing: %s — seeding from %s (%dd)", anomaly_ns, source_ns, lookback_days)
        if _seed_spool(source_ns, anomaly_ns, lookback_days):
            seeded += 1

        # Delay between queries to reduce memory pressure
        if not _STOP_EVENT.is_set():
            _STOP_EVENT.wait(_SEED_QUERY_DELAY)

    return seeded


def _refresh_all_spool() -> int:
    """Force-refresh all anomaly spools from source (daily scheduled use).

    Unlike _ensure_spool_data which skips existing spools, this always
    re-copies fresh data from source namespaces.
    """
    refreshed = 0
    for source_ns, anomaly_ns, lookback_days in _SPOOL_SEED_CONFIG:
        if _STOP_EVENT.is_set():
            break

        logger.info("Refreshing anomaly spool: %s from %s (%dd)", anomaly_ns, source_ns, lookback_days)
        if _seed_spool(source_ns, anomaly_ns, lookback_days):
            refreshed += 1

        if not _STOP_EVENT.is_set():
            _STOP_EVENT.wait(_SEED_QUERY_DELAY)

    return refreshed


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

    # Initial: delay 30s for other services and first user requests, then seed
    _STOP_EVENT.wait(30)
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
            logger.info("Anomaly detection: daily run — refreshing all anomaly spools...")
            _refresh_all_spool()

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
