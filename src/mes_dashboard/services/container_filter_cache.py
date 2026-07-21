# -*- coding: utf-8 -*-
"""Cache for DWH.DW_MES_CONTAINER filter values — 4-tuple cross-filter (v2).

Caches the DISTINCT 4-tuple ``(PJ_TYPE, PRODUCTLINENAME, PJ_BOP,
PJ_FUNCTION)`` set from ``DWH.DW_MES_CONTAINER`` so the production-history
filter-options endpoint can perform Oracle-free cross-filter narrowing
(business-rules.md PHF-01).

Payload schema version 2 (data-shape-contract §2.8):
    {
        "schema_version": 2,
        "tuples": [[PJ_TYPE, PRODUCTLINENAME, PJ_BOP, PJ_FUNCTION], ...],
        "indices": {"pj_types": [...], "packages": [...],
                    "bops": [...], "pj_functions": [...]},
        "updated_at": "<ISO 8601 UTC>",
    }

Backward-compatibility helpers ``get_packages()`` / ``get_pj_types()`` are
preserved (used by ``production_history_service.get_type_options``); they
now read from the v2 ``indices`` block.

Multi-worker startup lock (PHF-05): file-based ``O_CREAT|O_EXCL`` lock at
``tmp/container_filter_cache.loading`` (pattern lifted from
``resource_history_duckdb_cache._try_lock``). Loser workers poll Redis L2
every 5 s up to 18 iterations (90 s total) before falling through to
Oracle in degraded mode.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from mes_dashboard.config.constants import CACHE_TTL_FILTER_GENERAL
from mes_dashboard.core.cache_plane import snapshot_redis_ttl
from mes_dashboard.core.database import read_sql_df
from mes_dashboard.core.redis_client import (
    REDIS_ENABLED,
    get_key,
    get_redis_client,
)

logger = logging.getLogger("mes_dashboard.container_filter_cache")

# ──────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────

SCHEMA_VERSION = 2  # Bump to invalidate L2 entries on next deploy (PHF-04).

_REDIS_KEY = get_key("container_filter_cache:data")
_TTL = CACHE_TTL_FILTER_GENERAL
_REDIS_TTL = snapshot_redis_ttl(_TTL)

_CONTAINER_VIEW = "DWH.DW_MES_CONTAINER"

# Oracle source SQL — single round trip producing the 4-tuple co-occurrence
# set. Filters preserve the prior behaviour of dropping NULL low-cardinality
# columns; PJ_FUNCTION is allowed to be NULL because not every product family
# carries a function code (data-boundary case in test-plan).
_SQL = f"""
SELECT DISTINCT
    TRIM(PJ_TYPE)         AS PJ_TYPE,
    TRIM(PRODUCTLINENAME) AS PRODUCTLINENAME,
    TRIM(PJ_BOP)          AS PJ_BOP,
    TRIM(PJ_FUNCTION)     AS PJ_FUNCTION
FROM {_CONTAINER_VIEW}
WHERE PJ_TYPE IS NOT NULL
  AND PRODUCTLINENAME IS NOT NULL
  AND PJ_BOP IS NOT NULL
"""

# Multi-worker rebuild lock (PHF-05).
_LOCK_RAW_PATH = os.getenv(
    "CONTAINER_FILTER_CACHE_LOCK_PATH",
    "tmp/container_filter_cache.loading",
)
_LOCK_PATH = (
    Path(_LOCK_RAW_PATH)
    if Path(_LOCK_RAW_PATH).is_absolute()
    else Path.cwd() / _LOCK_RAW_PATH
)
_LOCK_POLL_INTERVAL_S = 5
_LOCK_MAX_POLL_ITERATIONS = 18  # 5s × 18 = 90s total bound

# ──────────────────────────────────────────────────────────────────────────
# In-process L1 state
# ──────────────────────────────────────────────────────────────────────────

_CACHE_LOCK = threading.Lock()
_CACHE: dict = {
    # New v2 fields
    "schema_version": None,        # int once loaded
    "tuples": None,                # list[tuple[str, str, str, str]]
    "indices": None,               # dict[str, list[str]]
    "updated_at": None,            # ISO string
    # Legacy compatibility slots populated from indices
    "packages": None,
    "pj_types": None,
    "loaded": False,
}


# ============================================================
# Public API
# ============================================================

def init() -> None:
    """Initialise cache at application startup."""
    logger.info("Initializing container_filter_cache (schema v%d)...", SCHEMA_VERSION)
    _load()


def get_packages() -> List[str]:
    """Return cached distinct PRODUCTLINENAME values (back-compat)."""
    _ensure_loaded()
    with _CACHE_LOCK:
        return list(_CACHE.get("packages") or [])


def get_pj_types() -> List[str]:
    """Return cached distinct PJ_TYPE values (back-compat)."""
    _ensure_loaded()
    with _CACHE_LOCK:
        return list(_CACHE.get("pj_types") or [])


def refresh() -> bool:
    """Force re-query from Oracle and update L1 + L2 caches."""
    return _load(force=True)


def get_filter_options(
    selected: Optional[Dict[str, List[str]]] = None,
) -> Dict[str, Any]:
    """Cross-filter narrowing over the cached 4-tuple set (PHF-01).

    Args:
        selected: Optional dict ``{"pj_types": [...], "packages": [...],
            "bops": [...], "pj_functions": [...]}``. Unknown keys are
            silently ignored; values not present in the cache are
            silently dropped (fail-open picker — data-shape §2.7).

    Returns:
        ``{"pj_types": [...], "packages": [...], "bops": [...],
        "pj_functions": [...], "updated_at": <iso>,
        "schema_version": int}``. Each value list is sorted ascending,
        deduplicated. When ``selected`` is empty/missing, returns the full
        ``indices`` set (AC-1). A dimension's own current selection never
        narrows its own returned option list — only the OTHER three
        dimensions narrow it (self-exclusion) — so the user can keep
        adding values to the same multi-select instead of every
        not-yet-selected sibling vanishing the moment one value is picked.
    """
    _ensure_loaded()
    with _CACHE_LOCK:
        tuples = list(_CACHE.get("tuples") or [])
        indices = dict(_CACHE.get("indices") or {})
        updated_at = _CACHE.get("updated_at")

    base_result = {
        "pj_types": list(indices.get("pj_types") or []),
        "packages": list(indices.get("packages") or []),
        "bops": list(indices.get("bops") or []),
        "pj_functions": list(indices.get("pj_functions") or []),
        "updated_at": updated_at,
        "schema_version": SCHEMA_VERSION,
    }

    if not selected:
        return base_result

    # Normalise the selection — accept only the four known keys; ignore others.
    sel_pj_types = set(_clean_list(selected.get("pj_types")))
    sel_packages = set(_clean_list(selected.get("packages")))
    sel_bops = set(_clean_list(selected.get("bops")))
    sel_pj_functions = set(_clean_list(selected.get("pj_functions")))

    # Fail-open: drop selection values not present in cache so they don't
    # collapse the entire result to empty (data-shape §2.7).
    sel_pj_types &= set(base_result["pj_types"])
    sel_packages &= set(base_result["packages"])
    sel_bops &= set(base_result["bops"])
    sel_pj_functions &= set(base_result["pj_functions"])

    if not (sel_pj_types or sel_packages or sel_bops or sel_pj_functions):
        # All selections were unknown — fall back to full set.
        return base_result

    # Field index within each tuple: (PJ_TYPE, PRODUCTLINENAME, PJ_BOP, PJ_FUNCTION).
    _PJ_TYPES, _PACKAGES, _BOPS, _PJ_FUNCTIONS = 0, 1, 2, 3

    def _narrow(field: int) -> set[str]:
        # Narrow `field`'s option list by every OTHER dimension's current
        # selection, but never by its own (self-exclusion) — otherwise
        # picking one value would immediately hide every other value from
        # the same multi-select.
        out: set[str] = set()
        for tup in tuples:
            if sel_pj_types and field != _PJ_TYPES and tup[_PJ_TYPES] not in sel_pj_types:
                continue
            if sel_packages and field != _PACKAGES and tup[_PACKAGES] not in sel_packages:
                continue
            if sel_bops and field != _BOPS and tup[_BOPS] not in sel_bops:
                continue
            if (
                sel_pj_functions
                and field != _PJ_FUNCTIONS
                and (tup[_PJ_FUNCTIONS] or "") not in sel_pj_functions
            ):
                continue
            value = tup[field]
            if value:
                out.add(value)
        return out

    return {
        "pj_types": sorted(_narrow(_PJ_TYPES)),
        "packages": sorted(_narrow(_PACKAGES)),
        "bops": sorted(_narrow(_BOPS)),
        "pj_functions": sorted(_narrow(_PJ_FUNCTIONS)),
        "updated_at": updated_at,
        "schema_version": SCHEMA_VERSION,
    }


# ============================================================
# Internal helpers
# ============================================================

def _clean_list(value: Any) -> List[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return [str(v).strip() for v in value if str(v).strip()]


def _ensure_loaded() -> None:
    with _CACHE_LOCK:
        if _CACHE["loaded"]:
            return
    _load()


def _try_lock() -> bool:
    """Create lock file exclusively; returns True if this process won the lock.

    Pattern lifted from ``resource_history_duckdb_cache._try_lock``
    (PHF-05).
    """
    try:
        _LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(_LOCK_PATH), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(fd)
        return True
    except FileExistsError:
        return False
    except OSError:
        return True  # Can't create lock — proceed to avoid silent skip.


def _release_lock() -> None:
    try:
        _LOCK_PATH.unlink(missing_ok=True)
    except Exception:
        pass


def _try_reuse_existing() -> Optional[dict]:
    """Loser-path helper: re-read Redis L2 once."""
    return _read_from_redis()


def _load(force: bool = False) -> bool:
    """Load from Redis L2, then Oracle (under lock) if needed.

    Returns True on success, False on failure (existing values preserved).
    """
    if not force:
        # Try Redis L2 first.
        redis_data = _read_from_redis()
        if redis_data is not None:
            _apply_payload(redis_data)
            logger.info(
                "container_filter_cache populated from Redis L2 "
                "(%d tuples, schema v%d)",
                len(redis_data.get("tuples") or []),
                redis_data.get("schema_version"),
            )
            return True

    # Cache miss — acquire the rebuild lock.
    got_lock = _try_lock()
    if not got_lock:
        # Loser path: poll Redis L2 up to 90 s waiting for the winner.
        logger.info(
            "container_filter_cache: lock held by another worker — polling L2"
        )
        for _ in range(_LOCK_MAX_POLL_ITERATIONS):
            time.sleep(_LOCK_POLL_INTERVAL_S)
            reused = _try_reuse_existing()
            if reused is not None:
                _apply_payload(reused)
                logger.info(
                    "container_filter_cache: reused L2 payload after lock wait"
                )
                return True
        logger.warning(
            "container_filter_cache: lock wait exceeded 90 s — falling "
            "through to direct Oracle (degraded mode)"
        )
        # Fall through to Oracle without holding the lock (degraded path).
        return _query_oracle_and_apply(release_lock=False)

    # Winner path: query Oracle, write L1 + L2, release lock in finally.
    try:
        return _query_oracle_and_apply(release_lock=False)
    finally:
        _release_lock()


def _query_oracle_and_apply(release_lock: bool) -> bool:
    """Run the Oracle query, build payload, write to L1/L2."""
    try:
        df = read_sql_df(_SQL, caller="container_filter_cache:refresh")
        if df is None or df.empty:
            logger.warning("container_filter_cache: Oracle returned empty result")
            return False

        import pandas as _pd

        def _clean_cell(value: Any) -> str:
            if value is None:
                return ""
            try:
                if _pd.isna(value):
                    return ""
            except (TypeError, ValueError):
                pass
            return str(value).strip()

        tuples_raw: List[Tuple[str, str, str, str]] = []
        for _, r in df.iterrows():
            t_type = _clean_cell(r.get("PJ_TYPE"))
            t_pkg = _clean_cell(r.get("PRODUCTLINENAME"))
            t_bop = _clean_cell(r.get("PJ_BOP"))
            t_fn = _clean_cell(r.get("PJ_FUNCTION"))
            if not (t_type and t_pkg and t_bop):
                continue
            tuples_raw.append((t_type, t_pkg, t_bop, t_fn))

        # Dedup at the application layer too (DISTINCT in SQL already handles
        # this; this is a defence-in-depth against driver quirks).
        tuples_set = list(dict.fromkeys(tuples_raw))

        indices = _derive_indices(tuples_set)
        payload = {
            "schema_version": SCHEMA_VERSION,
            "tuples": [list(t) for t in tuples_set],
            "indices": indices,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        _apply_payload(payload)
        _write_to_redis(payload)

        logger.info(
            "container_filter_cache refreshed from Oracle "
            "(%d tuples, %d types / %d packages / %d bops / %d functions)",
            len(tuples_set),
            len(indices["pj_types"]),
            len(indices["packages"]),
            len(indices["bops"]),
            len(indices["pj_functions"]),
        )
        return True
    except Exception as exc:
        logger.error("container_filter_cache Oracle refresh failed: %s", exc)
        return False
    finally:
        if release_lock:
            _release_lock()


def _derive_indices(
    tuples_set: List[Tuple[str, str, str, str]],
) -> Dict[str, List[str]]:
    pj_types: set[str] = set()
    packages: set[str] = set()
    bops: set[str] = set()
    pj_functions: set[str] = set()
    for (t_type, t_pkg, t_bop, t_fn) in tuples_set:
        pj_types.add(t_type)
        packages.add(t_pkg)
        bops.add(t_bop)
        if t_fn:
            pj_functions.add(t_fn)
    return {
        "pj_types": sorted(pj_types),
        "packages": sorted(packages),
        "bops": sorted(bops),
        "pj_functions": sorted(pj_functions),
    }


def _apply_payload(payload: dict) -> None:
    """Replace in-process L1 state with the given payload."""
    schema_version = payload.get("schema_version")
    if schema_version != SCHEMA_VERSION:
        # Defensive — should already be filtered by _read_from_redis.
        logger.warning(
            "container_filter_cache: refusing to apply payload with "
            "schema_version=%r (expected %d)",
            schema_version, SCHEMA_VERSION,
        )
        return

    tuples_in = payload.get("tuples") or []
    tuples_norm: List[Tuple[str, str, str, str]] = []
    for row in tuples_in:
        if not isinstance(row, (list, tuple)) or len(row) < 3:
            continue
        t_type = str(row[0] or "").strip()
        t_pkg = str(row[1] or "").strip()
        t_bop = str(row[2] or "").strip()
        t_fn = str(row[3] or "").strip() if len(row) > 3 else ""
        tuples_norm.append((t_type, t_pkg, t_bop, t_fn))

    indices = payload.get("indices") or _derive_indices(tuples_norm)
    # Coerce indices to clean string lists.
    indices_clean = {
        "pj_types": sorted({str(v).strip() for v in (indices.get("pj_types") or []) if str(v).strip()}),
        "packages": sorted({str(v).strip() for v in (indices.get("packages") or []) if str(v).strip()}),
        "bops": sorted({str(v).strip() for v in (indices.get("bops") or []) if str(v).strip()}),
        "pj_functions": sorted({str(v).strip() for v in (indices.get("pj_functions") or []) if str(v).strip()}),
    }

    with _CACHE_LOCK:
        _CACHE["schema_version"] = SCHEMA_VERSION
        _CACHE["tuples"] = tuples_norm
        _CACHE["indices"] = indices_clean
        _CACHE["updated_at"] = payload.get("updated_at")
        # Back-compat slots
        _CACHE["packages"] = indices_clean["packages"]
        _CACHE["pj_types"] = indices_clean["pj_types"]
        _CACHE["loaded"] = True


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
        payload = json.loads(raw)
    except Exception as exc:
        logger.warning("container_filter_cache: Redis read failed: %s", exc)
        return None

    if not isinstance(payload, dict):
        logger.info(
            "container_filter_cache: ignoring malformed Redis payload "
            "(not a dict)"
        )
        return None

    schema_version = payload.get("schema_version")
    if schema_version != SCHEMA_VERSION:
        logger.info(
            "container_filter_cache: Redis payload schema_version=%r mismatch "
            "(expected %d) — forcing rebuild (PHF-04)",
            schema_version, SCHEMA_VERSION,
        )
        return None
    return payload


def _write_to_redis(payload: dict) -> None:
    if not REDIS_ENABLED:
        return
    try:
        client = get_redis_client()
        if client is None:
            return
        client.set(_REDIS_KEY, json.dumps(payload), ex=_REDIS_TTL)
        logger.debug(
            "container_filter_cache written to Redis (TTL=%ds, schema v%d)",
            _REDIS_TTL, SCHEMA_VERSION,
        )
    except Exception as exc:
        logger.warning("container_filter_cache: Redis write failed: %s", exc)
