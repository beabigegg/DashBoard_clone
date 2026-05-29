# -*- coding: utf-8 -*-
"""Downtime Analysis dataset cache.

Type-A spool pattern (mirror of resource_dataset_cache.py).

Namespaces:
  downtime_analysis_dataset  — metadata pointer (Redis)
  downtime_analysis_events   — per-event spool parquet (Redis + disk)

Spool dir: tmp/query_spool/downtime_analysis/

Cache key INCLUDES DOWNTIME_BRIDGE_VERSION (DA-06) via make_downtime_query_id()
in downtime_analysis_service.py — bumping the version constant invalidates all
downtime_analysis_* entries without touching resource_dataset_* spools.

No startup pre-warm by default (design.md §Decision 3, IP-3).
"""

from __future__ import annotations

import logging
import os
from typing import Optional

import pandas as pd

from mes_dashboard.config.constants import CACHE_TTL_DATASET
from mes_dashboard.core.cache import ProcessLevelCache, register_process_cache
from mes_dashboard.core.query_spool_store import (
    get_spool_file_path,
    store_spooled_df,
)

logger = logging.getLogger("mes_dashboard.downtime_analysis_cache")

# ── TTL ──────────────────────────────────────────────────────────────────────
_CACHE_TTL = int(os.getenv("DOWNTIME_ANALYSIS_CACHE_TTL", str(CACHE_TTL_DATASET)))

# ── Redis / spool namespaces ──────────────────────────────────────────────────
_EVENTS_NAMESPACE = "downtime_analysis_events"

# ── In-process L1 cache (lightweight spool-presence marker) ──────────────────
_events_cache = ProcessLevelCache(ttl_seconds=_CACHE_TTL, max_size=32)

register_process_cache(
    "downtime_analysis_events",
    _events_cache,
    "Downtime Analysis Events (L1, TTL={})".format(_CACHE_TTL),
)


# ============================================================
# Spool write / read helpers
# ============================================================


def has_downtime_events(query_id: str) -> bool:
    """Return True if the events spool exists (L1 marker or Redis pointer)."""
    if _events_cache.get(query_id) is not None:
        return True
    return get_spool_file_path(_EVENTS_NAMESPACE, query_id) is not None


def store_downtime_events(
    query_id: str,
    df: pd.DataFrame,
    end_date: str = "",
) -> None:
    """Write events DataFrame to spool and set L1 marker."""
    _events_cache.set(query_id, True)
    store_spooled_df(
        _EVENTS_NAMESPACE,
        query_id,
        df,
        ttl_seconds=_CACHE_TTL,
    )


def load_downtime_events(query_id: str) -> Optional[pd.DataFrame]:
    """Read events DataFrame from spool. Returns None if expired."""
    try:
        spool_path = get_spool_file_path(_EVENTS_NAMESPACE, query_id)
        if spool_path is None:
            _events_cache.delete(query_id)
            return None
        df = pd.read_parquet(spool_path)
        return df
    except Exception as exc:
        logger.warning("load_downtime_events failed for query_id=%s: %s", query_id, exc)
        _events_cache.delete(query_id)
        return None
