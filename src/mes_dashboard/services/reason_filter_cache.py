# -*- coding: utf-8 -*-
"""Cache for reject loss reason filter values (LOSSREASONNAME).

Queries DWH.DW_MES_LOTREJECTHISTORY for DISTINCT LOSSREASONNAME values from
the last 365 days. L1 memory + L2 Redis, TTL 24 hours. Fail-open on refresh error.
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

logger = logging.getLogger("mes_dashboard.reason_filter_cache")

_REDIS_KEY = get_key("reason_filter_cache:data")
# Refresh check interval (24 hours); Redis TTL uses snapshot-plane policy (2x).
_TTL = CACHE_TTL_FILTER_GENERAL
_REDIS_TTL = snapshot_redis_ttl(_TTL)

_CACHE_LOCK = threading.Lock()
_CACHE: dict = {
    "reject_reasons": None,
    "loaded": False,
    "updated_at": None,
}

_REJECT_HISTORY_VIEW = "DWH.DW_MES_LOTREJECTHISTORY"

_SQL = f"""
SELECT DISTINCT TRIM(LOSSREASONNAME) AS LOSSREASONNAME
FROM {_REJECT_HISTORY_VIEW}
WHERE TXNDATE >= SYSDATE - 365
  AND LOSSREASONNAME IS NOT NULL
"""


# ============================================================
# Public API
# ============================================================

def init() -> None:
    """Initialize cache at application startup."""
    logger.info("Initializing reason_filter_cache...")
    _load()


def get_reject_reasons() -> List[str]:
    """Return cached list of distinct LOSSREASONNAME values."""
    _ensure_loaded()
    with _CACHE_LOCK:
        return list(_CACHE.get("reject_reasons") or [])


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
    """Load from Redis L2, then Oracle if needed. Fail-open on error."""
    if not force:
        redis_data = _read_from_redis()
        if redis_data is not None:
            with _CACHE_LOCK:
                _CACHE["reject_reasons"] = redis_data.get("reject_reasons", [])
                _CACHE["loaded"] = True
                _CACHE["updated_at"] = redis_data.get("updated_at")
            logger.info(
                "reason_filter_cache populated from Redis (%d reasons)",
                len(_CACHE["reject_reasons"]),
            )
            return True

    try:
        df = read_sql_df(_SQL, caller="reason_filter_cache:refresh")
        if df is None or df.empty:
            logger.warning("reason_filter_cache: Oracle returned empty result")
            # fail-open: mark loaded with empty list rather than blocking
            with _CACHE_LOCK:
                if not _CACHE["loaded"]:
                    _CACHE["reject_reasons"] = []
                    _CACHE["loaded"] = True
            return False

        reasons = sorted(
            str(r).strip()
            for r in df["LOSSREASONNAME"].dropna()
            if str(r).strip()
        )

        updated_at = datetime.now().isoformat()
        with _CACHE_LOCK:
            _CACHE["reject_reasons"] = reasons
            _CACHE["loaded"] = True
            _CACHE["updated_at"] = updated_at

        _write_to_redis(reasons, updated_at)
        logger.info("reason_filter_cache refreshed from Oracle (%d reasons)", len(reasons))
        return True

    except Exception as exc:
        logger.warning("reason_filter_cache Oracle refresh failed (fail-open): %s", exc)
        # fail-open: retain previous values, mark loaded if not already
        with _CACHE_LOCK:
            if not _CACHE["loaded"]:
                _CACHE["reject_reasons"] = []
                _CACHE["loaded"] = True
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
        logger.warning("reason_filter_cache: Redis read failed: %s", exc)
        return None


def _write_to_redis(reasons: List[str], updated_at: str) -> None:
    if not REDIS_ENABLED:
        return
    try:
        client = get_redis_client()
        if client is None:
            return
        payload = json.dumps({"reject_reasons": reasons, "updated_at": updated_at})
        client.set(_REDIS_KEY, payload, ex=_REDIS_TTL)
        logger.debug("reason_filter_cache written to Redis (TTL=%ds)", _TTL)
    except Exception as exc:
        logger.warning("reason_filter_cache: Redis write failed: %s", exc)
