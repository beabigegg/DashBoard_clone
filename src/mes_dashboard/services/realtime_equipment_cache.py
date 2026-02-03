# -*- coding: utf-8 -*-
"""Realtime Equipment Status Cache for MES Dashboard.

Provides cached equipment status from DW_MES_EQUIPMENTSTATUS_WIP_V.
Data is synced periodically (default 5 minutes) and stored in Redis.
"""

import json
import logging
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from mes_dashboard.core.database import read_sql_df
from mes_dashboard.core.redis_client import get_redis_client, get_key_prefix
from mes_dashboard.config.constants import (
    EQUIPMENT_STATUS_DATA_KEY,
    EQUIPMENT_STATUS_INDEX_KEY,
    EQUIPMENT_STATUS_META_UPDATED_KEY,
    EQUIPMENT_STATUS_META_COUNT_KEY,
    STATUS_CATEGORY_MAP,
)

logger = logging.getLogger('mes_dashboard.realtime_equipment_cache')

# ============================================================
# Process-Level Cache (Prevents redundant JSON parsing)
# ============================================================

class _ProcessLevelCache:
    """Thread-safe process-level cache for parsed equipment status data."""

    def __init__(self, ttl_seconds: int = 30):
        self._cache: Dict[str, Tuple[List[Dict[str, Any]], float]] = {}
        self._lock = threading.Lock()
        self._ttl = ttl_seconds

    def get(self, key: str) -> Optional[List[Dict[str, Any]]]:
        """Get cached data if not expired."""
        with self._lock:
            if key not in self._cache:
                return None
            data, timestamp = self._cache[key]
            if time.time() - timestamp > self._ttl:
                del self._cache[key]
                return None
            return data

    def set(self, key: str, data: List[Dict[str, Any]]) -> None:
        """Cache data with current timestamp."""
        with self._lock:
            self._cache[key] = (data, time.time())

    def invalidate(self, key: str) -> None:
        """Remove a key from cache."""
        with self._lock:
            self._cache.pop(key, None)


# Global process-level cache for equipment status (30s TTL)
_equipment_status_cache = _ProcessLevelCache(ttl_seconds=30)
_equipment_status_parse_lock = threading.Lock()

# ============================================================
# Module State
# ============================================================

_SYNC_THREAD: Optional[threading.Thread] = None
_STOP_EVENT = threading.Event()
_SYNC_LOCK = threading.Lock()


# ============================================================
# Oracle Query
# ============================================================

def _load_equipment_status_from_oracle() -> Optional[List[Dict[str, Any]]]:
    """Query DW_MES_EQUIPMENTSTATUS_WIP_V from Oracle.

    Returns:
        List of equipment status records, or None if query fails.
    """
    sql = """
        SELECT
            RESOURCEID,
            EQUIPMENTID,
            OBJECTCATEGORY,
            EQUIPMENTASSETSSTATUS,
            EQUIPMENTASSETSSTATUSREASON,
            JOBORDER,
            JOBMODEL,
            JOBSTAGE,
            JOBID,
            JOBSTATUS,
            CREATEDATE,
            CREATEUSERNAME,
            CREATEUSER,
            TECHNICIANUSERNAME,
            TECHNICIANUSER,
            SYMPTOMCODE,
            CAUSECODE,
            REPAIRCODE,
            RUNCARDLOTID,
            LOTTRACKINQTY_PCS,
            LOTTRACKINTIME,
            LOTTRACKINEMPLOYEE
        FROM DWH.DW_MES_EQUIPMENTSTATUS_WIP_V
    """
    try:
        df = read_sql_df(sql)
        if df is None or df.empty:
            logger.warning("No data returned from DW_MES_EQUIPMENTSTATUS_WIP_V")
            return []

        # Convert DataFrame to list of dicts
        records = df.to_dict('records')

        # Convert datetime columns to ISO format strings
        for record in records:
            for key in ['CREATEDATE', 'LOTTRACKINTIME']:
                if record.get(key) is not None:
                    try:
                        record[key] = record[key].isoformat()
                    except (AttributeError, TypeError):
                        pass

        logger.info(f"Loaded {len(records)} records from DW_MES_EQUIPMENTSTATUS_WIP_V")
        return records

    except Exception as exc:
        logger.error(f"Failed to load equipment status from Oracle: {exc}")
        return None


# ============================================================
# Data Aggregation
# ============================================================

def _classify_status(status: Optional[str]) -> str:
    """Classify equipment status into category.

    Args:
        status: Equipment status code (e.g., 'PRD', 'SBY')

    Returns:
        Status category string.
    """
    if not status:
        return 'OTHER'
    return STATUS_CATEGORY_MAP.get(status, 'OTHER')


def _is_valid_value(value) -> bool:
    """Check if a value is valid (not None, not NaN, not empty string).

    Args:
        value: The value to check.

    Returns:
        True if valid, False otherwise.
    """
    if value is None:
        return False
    if isinstance(value, str) and (not value.strip() or value == 'NaT'):
        return False
    # Check for NaN (pandas NaN or float NaN)
    try:
        if value != value:  # NaN != NaN is True
            return False
    except (TypeError, ValueError):
        pass
    return True


def _aggregate_by_resourceid(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Aggregate equipment status records by RESOURCEID.

    For each RESOURCEID:
    - Status fields: take first (should be same for all records)
    - LOT_COUNT: count of distinct RUNCARDLOTID values
    - LOT_DETAILS: list of LOT information for tooltip display
    - TOTAL_TRACKIN_QTY: sum of LOTTRACKINQTY_PCS
    - LATEST_TRACKIN_TIME: max of LOTTRACKINTIME

    Args:
        records: Raw records from Oracle query.

    Returns:
        Aggregated records, one per RESOURCEID.
    """
    if not records:
        return []

    # Group by RESOURCEID
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for record in records:
        resource_id = record.get('RESOURCEID')
        if resource_id:
            if resource_id not in grouped:
                grouped[resource_id] = []
            grouped[resource_id].append(record)

    # Aggregate each group
    aggregated = []
    for resource_id, group in grouped.items():
        first = group[0]

        # Collect unique LOTs by RUNCARDLOTID
        seen_lots = set()
        lot_details = []
        total_qty = 0

        for r in group:
            lot_id = r.get('RUNCARDLOTID')
            qty = r.get('LOTTRACKINQTY_PCS')
            # Sum only valid quantities
            if _is_valid_value(qty):
                total_qty += qty

            # Only add unique LOTs with valid RUNCARDLOTID
            if _is_valid_value(lot_id) and lot_id not in seen_lots:
                seen_lots.add(lot_id)
                trackin_time = r.get('LOTTRACKINTIME')
                trackin_employee = r.get('LOTTRACKINEMPLOYEE')
                lot_details.append({
                    'RUNCARDLOTID': lot_id,
                    'LOTTRACKINQTY_PCS': qty if _is_valid_value(qty) else None,
                    'LOTTRACKINTIME': trackin_time if _is_valid_value(trackin_time) else None,
                    'LOTTRACKINEMPLOYEE': trackin_employee if _is_valid_value(trackin_employee) else None,
                })

        # Find latest trackin time
        trackin_times = [
            r.get('LOTTRACKINTIME')
            for r in group
            if r.get('LOTTRACKINTIME')
        ]
        latest_trackin = max(trackin_times) if trackin_times else None

        # Build aggregated record
        status = first.get('EQUIPMENTASSETSSTATUS')
        aggregated.append({
            'RESOURCEID': resource_id,
            'EQUIPMENTID': first.get('EQUIPMENTID'),
            'OBJECTCATEGORY': first.get('OBJECTCATEGORY'),
            'EQUIPMENTASSETSSTATUS': status,
            'EQUIPMENTASSETSSTATUSREASON': first.get('EQUIPMENTASSETSSTATUSREASON'),
            'STATUS_CATEGORY': _classify_status(status),
            # JOB related fields
            'JOBORDER': first.get('JOBORDER'),
            'JOBMODEL': first.get('JOBMODEL'),
            'JOBSTAGE': first.get('JOBSTAGE'),
            'JOBID': first.get('JOBID'),
            'JOBSTATUS': first.get('JOBSTATUS'),
            'CREATEDATE': first.get('CREATEDATE'),
            'CREATEUSERNAME': first.get('CREATEUSERNAME'),
            'CREATEUSER': first.get('CREATEUSER'),
            'TECHNICIANUSERNAME': first.get('TECHNICIANUSERNAME'),
            'TECHNICIANUSER': first.get('TECHNICIANUSER'),
            'SYMPTOMCODE': first.get('SYMPTOMCODE'),
            'CAUSECODE': first.get('CAUSECODE'),
            'REPAIRCODE': first.get('REPAIRCODE'),
            # LOT related fields
            'LOT_COUNT': len(seen_lots),  # Count distinct RUNCARDLOTID
            'LOT_DETAILS': lot_details,   # LOT details for tooltip
            'TOTAL_TRACKIN_QTY': total_qty,
            'LATEST_TRACKIN_TIME': latest_trackin,
        })

    logger.debug(f"Aggregated {len(records)} records into {len(aggregated)} unique resources")
    return aggregated


# ============================================================
# Redis Storage
# ============================================================

def _save_to_redis(aggregated: List[Dict[str, Any]]) -> bool:
    """Save aggregated equipment status to Redis.

    Uses pipeline for atomic update of all keys.

    Args:
        aggregated: Aggregated equipment status records.

    Returns:
        True if save succeeded, False otherwise.
    """
    redis_client = get_redis_client()
    if not redis_client:
        logger.error("Redis client not available")
        return False

    try:
        prefix = get_key_prefix()
        data_key = f"{prefix}:{EQUIPMENT_STATUS_DATA_KEY}"
        index_key = f"{prefix}:{EQUIPMENT_STATUS_INDEX_KEY}"
        updated_key = f"{prefix}:{EQUIPMENT_STATUS_META_UPDATED_KEY}"
        count_key = f"{prefix}:{EQUIPMENT_STATUS_META_COUNT_KEY}"

        # Build index mapping: RESOURCEID -> array index
        index_mapping = {
            record['RESOURCEID']: str(idx)
            for idx, record in enumerate(aggregated)
        }

        # Serialize data
        data_json = json.dumps(aggregated, ensure_ascii=False, default=str)
        updated_at = datetime.now().isoformat()
        count = len(aggregated)

        # Atomic update using pipeline
        pipe = redis_client.pipeline()
        pipe.set(data_key, data_json)
        pipe.delete(index_key)
        if index_mapping:
            pipe.hset(index_key, mapping=index_mapping)
        pipe.set(updated_key, updated_at)
        pipe.set(count_key, str(count))
        pipe.execute()

        # Invalidate process-level cache so next request picks up new data
        _equipment_status_cache.invalidate("equipment_status_all")

        logger.info(f"Saved {count} equipment status records to Redis")
        return True

    except Exception as exc:
        logger.error(f"Failed to save equipment status to Redis: {exc}")
        return False


# ============================================================
# Query API
# ============================================================

def get_all_equipment_status() -> List[Dict[str, Any]]:
    """Get all equipment status from cache with process-level caching.

    Uses a two-tier cache strategy:
    1. Process-level cache: Parsed data (30s TTL) - fast, no parsing
    2. Redis cache: Raw JSON data - shared across workers

    This prevents redundant JSON parsing across concurrent requests.

    Returns:
        List of equipment status records, or empty list if unavailable.
    """
    cache_key = "equipment_status_all"

    # Tier 1: Check process-level cache first (fast path)
    cached_data = _equipment_status_cache.get(cache_key)
    if cached_data is not None:
        logger.debug(f"Process cache hit: {len(cached_data)} records")
        return cached_data

    # Tier 2: Parse from Redis (slow path - needs lock)
    redis_client = get_redis_client()
    if not redis_client:
        logger.warning("Redis client not available for equipment status query")
        return []

    # Use lock to prevent multiple threads from parsing simultaneously
    with _equipment_status_parse_lock:
        # Double-check after acquiring lock
        cached_data = _equipment_status_cache.get(cache_key)
        if cached_data is not None:
            logger.debug(f"Process cache hit (after lock): {len(cached_data)} records")
            return cached_data

        try:
            start_time = time.time()
            prefix = get_key_prefix()
            data_key = f"{prefix}:{EQUIPMENT_STATUS_DATA_KEY}"

            data_json = redis_client.get(data_key)
            if not data_json:
                logger.debug("No equipment status data in cache")
                return []

            data = json.loads(data_json)
            parse_time = time.time() - start_time

            # Store in process-level cache
            _equipment_status_cache.set(cache_key, data)

            logger.debug(f"Equipment status cache hit: {len(data)} records (parsed in {parse_time:.2f}s)")
            return data

        except Exception as exc:
            logger.error(f"Failed to get equipment status from cache: {exc}")
            return []


def get_equipment_status_by_id(resource_id: str) -> Optional[Dict[str, Any]]:
    """Get equipment status by RESOURCEID.

    Uses index hash for O(1) lookup.

    Args:
        resource_id: The RESOURCEID to look up.

    Returns:
        Equipment status record, or None if not found.
    """
    redis_client = get_redis_client()
    if not redis_client:
        return None

    try:
        prefix = get_key_prefix()
        index_key = f"{prefix}:{EQUIPMENT_STATUS_INDEX_KEY}"
        data_key = f"{prefix}:{EQUIPMENT_STATUS_DATA_KEY}"

        # Get index from hash
        idx_str = redis_client.hget(index_key, resource_id)
        if idx_str is None:
            return None

        idx = int(idx_str)

        # Get data array
        data_json = redis_client.get(data_key)
        if not data_json:
            return None

        data = json.loads(data_json)
        if 0 <= idx < len(data):
            return data[idx]

        return None

    except Exception as exc:
        logger.error(f"Failed to get equipment status by ID: {exc}")
        return None


def get_equipment_status_by_ids(resource_ids: List[str]) -> List[Dict[str, Any]]:
    """Get equipment status for multiple RESOURCEIDs.

    Args:
        resource_ids: List of RESOURCEIDs to look up.

    Returns:
        List of equipment status records (only existing ones).
    """
    if not resource_ids:
        return []

    redis_client = get_redis_client()
    if not redis_client:
        return []

    try:
        prefix = get_key_prefix()
        index_key = f"{prefix}:{EQUIPMENT_STATUS_INDEX_KEY}"
        data_key = f"{prefix}:{EQUIPMENT_STATUS_DATA_KEY}"

        # Get all indices at once
        indices = redis_client.hmget(index_key, resource_ids)

        # Get data array
        data_json = redis_client.get(data_key)
        if not data_json:
            return []

        data = json.loads(data_json)

        # Collect matching records
        results = []
        for idx_str in indices:
            if idx_str is not None:
                idx = int(idx_str)
                if 0 <= idx < len(data):
                    results.append(data[idx])

        return results

    except Exception as exc:
        logger.error(f"Failed to get equipment status by IDs: {exc}")
        return []


def get_equipment_status_cache_status() -> Dict[str, Any]:
    """Get equipment status cache status.

    Returns:
        Dict with cache status information.
    """
    from flask import current_app

    enabled = current_app.config.get('REALTIME_EQUIPMENT_CACHE_ENABLED', True)

    if not enabled:
        return {
            'enabled': False,
            'loaded': False,
            'count': 0,
            'updated_at': None,
        }

    redis_client = get_redis_client()
    if not redis_client:
        return {
            'enabled': True,
            'loaded': False,
            'count': 0,
            'updated_at': None,
        }

    try:
        prefix = get_key_prefix()
        updated_key = f"{prefix}:{EQUIPMENT_STATUS_META_UPDATED_KEY}"
        count_key = f"{prefix}:{EQUIPMENT_STATUS_META_COUNT_KEY}"

        updated_at = redis_client.get(updated_key)
        count_str = redis_client.get(count_key)

        return {
            'enabled': True,
            'loaded': updated_at is not None,
            'count': int(count_str) if count_str else 0,
            'updated_at': updated_at,
        }

    except Exception as exc:
        logger.error(f"Failed to get equipment status cache status: {exc}")
        return {
            'enabled': True,
            'loaded': False,
            'count': 0,
            'updated_at': None,
        }


# ============================================================
# Background Sync
# ============================================================

def refresh_equipment_status_cache(force: bool = False) -> bool:
    """Refresh equipment status cache.

    Args:
        force: If True, refresh immediately regardless of state.

    Returns:
        True if refresh succeeded, False otherwise.
    """
    with _SYNC_LOCK:
        logger.info("Refreshing equipment status cache...")
        start_time = time.time()

        # Load from Oracle
        records = _load_equipment_status_from_oracle()
        if records is None:
            logger.error("Failed to load equipment status from Oracle")
            return False

        # Aggregate
        aggregated = _aggregate_by_resourceid(records)

        # Save to Redis
        success = _save_to_redis(aggregated)

        elapsed = time.time() - start_time
        if success:
            logger.info(f"Equipment status cache refreshed in {elapsed:.2f}s")
        else:
            logger.error(f"Equipment status cache refresh failed after {elapsed:.2f}s")

        return success


def _sync_worker(interval: int):
    """Background worker that periodically syncs equipment status.

    Args:
        interval: Sync interval in seconds.
    """
    logger.info(f"Equipment status sync worker started (interval: {interval}s)")

    while not _STOP_EVENT.is_set():
        try:
            refresh_equipment_status_cache()
        except Exception as exc:
            logger.error(f"Equipment status sync error: {exc}")

        # Wait for next sync or stop signal
        _STOP_EVENT.wait(timeout=interval)

    logger.info("Equipment status sync worker stopped")


def _start_equipment_status_sync_worker(interval: int):
    """Start the background sync worker thread.

    Args:
        interval: Sync interval in seconds.
    """
    global _SYNC_THREAD

    if _SYNC_THREAD is not None and _SYNC_THREAD.is_alive():
        logger.warning("Equipment status sync worker already running")
        return

    _STOP_EVENT.clear()
    _SYNC_THREAD = threading.Thread(
        target=_sync_worker,
        args=(interval,),
        daemon=True,
        name="equipment-status-sync"
    )
    _SYNC_THREAD.start()


def stop_equipment_status_sync_worker():
    """Stop the background sync worker thread."""
    global _SYNC_THREAD

    if _SYNC_THREAD is None or not _SYNC_THREAD.is_alive():
        return

    logger.info("Stopping equipment status sync worker...")
    _STOP_EVENT.set()
    _SYNC_THREAD.join(timeout=5)
    _SYNC_THREAD = None


# ============================================================
# Initialization
# ============================================================

def init_realtime_equipment_cache(app=None):
    """Initialize the realtime equipment status cache.

    Should be called during app initialization.

    Args:
        app: Flask application instance (optional, uses current_app if None).
    """
    from flask import current_app

    config = app.config if app else current_app.config

    enabled = config.get('REALTIME_EQUIPMENT_CACHE_ENABLED', True)
    if not enabled:
        logger.info("Realtime equipment cache is disabled")
        return

    interval = config.get('EQUIPMENT_STATUS_SYNC_INTERVAL', 300)

    logger.info("Initializing realtime equipment cache...")

    # Initial sync
    refresh_equipment_status_cache()

    # Start background worker
    _start_equipment_status_sync_worker(interval)
