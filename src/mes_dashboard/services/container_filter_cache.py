# -*- coding: utf-8 -*-
"""Cache for DWH.DW_MES_CONTAINER filter values (packages + pj_types).

Caches PRODUCTLINENAME and PJ_TYPE from DWH.DW_MES_CONTAINER using a single
combined SQL query. L1 memory + L2 Redis, TTL 24 hours.
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime
from typing import List, Optional

from mes_dashboard.config.constants import CACHE_TTL_FILTER_GENERAL
from mes_dashboard.core.cache_plane import snapshot_redis_ttl
from mes_dashboard.core.database import read_sql_df
from mes_dashboard.core.redis_client import (
    get_key,
    get_redis_client,
    REDIS_ENABLED,
)

logger = logging.getLogger("mes_dashboard.container_filter_cache")

_REDIS_KEY = get_key("container_filter_cache:data")
_LOCK_NAME = "container_filter_cache_refresh"
# Refresh check interval (24 hours); Redis TTL uses snapshot-plane policy (2x).
_TTL = CACHE_TTL_FILTER_GENERAL
_REDIS_TTL = snapshot_redis_ttl(_TTL)

_CACHE_LOCK = threading.Lock()
_CACHE: dict = {
    "packages": None,
    "pj_types": None,
    "loaded": False,
    "updated_at": None,
}

_CONTAINER_VIEW = "DWH.DW_MES_CONTAINER"

# Combined SQL: two DISTINCT queries in one round-trip using UNION ALL + tag
_SQL = f"""
SELECT 'PACKAGE' AS KIND, TRIM(PRODUCTLINENAME) AS VALUE
FROM {_CONTAINER_VIEW}
WHERE PRODUCTLINENAME IS NOT NULL
UNION ALL
SELECT 'PJ_TYPE' AS KIND, TRIM(PJ_TYPE) AS VALUE
FROM {_CONTAINER_VIEW}
WHERE PJ_TYPE IS NOT NULL
"""


# ============================================================
# Public API
# ============================================================

def init() -> None:
    """Initialize cache at application startup."""
    logger.info("Initializing container_filter_cache...")
    _load()


def get_packages() -> List[str]:
    """Return cached list of distinct PRODUCTLINENAME values."""
    _ensure_loaded()
    with _CACHE_LOCK:
        return list(_CACHE.get("packages") or [])


def get_pj_types() -> List[str]:
    """Return cached list of distinct PJ_TYPE values."""
    _ensure_loaded()
    with _CACHE_LOCK:
        return list(_CACHE.get("pj_types") or [])


def refresh() -> bool:
    """Force re-query from Oracle and update L1 + L2 cache."""
    return _load(force=True)


# ============================================================
# Internal helpers
# ============================================================

def _ensure_loaded() -> None:
    with _CACHE_LOCK:
        if _CACHE["loaded"]:
            return
    _load()


def _load(force: bool = False) -> bool:
    """Load from Redis L2, then Oracle if needed.

    Returns True on success, False on failure.
    """
    if not force:
        # Try Redis L2
        redis_data = _read_from_redis()
        if redis_data is not None:
            with _CACHE_LOCK:
                _CACHE["packages"] = redis_data.get("packages", [])
                _CACHE["pj_types"] = redis_data.get("pj_types", [])
                _CACHE["loaded"] = True
                _CACHE["updated_at"] = redis_data.get("updated_at")
            logger.info(
                "container_filter_cache populated from Redis (%d packages, %d pj_types)",
                len(_CACHE["packages"]),
                len(_CACHE["pj_types"]),
            )
            return True

    # Query Oracle
    try:
        df = read_sql_df(_SQL, caller="container_filter_cache:refresh")
        if df is None or df.empty:
            logger.warning("container_filter_cache: Oracle returned empty result")
            return False

        packages = sorted(set(
            str(r).strip() for r in df.loc[df["KIND"] == "PACKAGE", "VALUE"].dropna()
            if str(r).strip()
        ))
        pj_types = sorted(set(
            str(r).strip() for r in df.loc[df["KIND"] == "PJ_TYPE", "VALUE"].dropna()
            if str(r).strip()
        ))

        updated_at = datetime.now().isoformat()
        with _CACHE_LOCK:
            _CACHE["packages"] = packages
            _CACHE["pj_types"] = pj_types
            _CACHE["loaded"] = True
            _CACHE["updated_at"] = updated_at

        _write_to_redis(packages, pj_types, updated_at)
        logger.info(
            "container_filter_cache refreshed from Oracle (%d packages, %d pj_types)",
            len(packages),
            len(pj_types),
        )
        return True

    except Exception as exc:
        logger.error("container_filter_cache Oracle refresh failed: %s", exc)
        # fail-open: keep previous values
        return False


def _read_from_redis() -> Optional[dict]:
    if not REDIS_ENABLED:
        return None
    try:
        client = get_redis_client()
        if client is None:
            return None
        raw = client.get(_REDIS_KEY)
        if raw is None:
            return None
        return json.loads(raw)
    except Exception as exc:
        logger.warning("container_filter_cache: Redis read failed: %s", exc)
        return None


def _write_to_redis(packages: List[str], pj_types: List[str], updated_at: str) -> None:
    if not REDIS_ENABLED:
        return
    try:
        client = get_redis_client()
        if client is None:
            return
        payload = json.dumps({
            "packages": packages,
            "pj_types": pj_types,
            "updated_at": updated_at,
        })
        client.set(_REDIS_KEY, payload, ex=_REDIS_TTL)
        logger.debug("container_filter_cache written to Redis (TTL=%ds)", _REDIS_TTL)
    except Exception as exc:
        logger.warning("container_filter_cache: Redis write failed: %s", exc)
