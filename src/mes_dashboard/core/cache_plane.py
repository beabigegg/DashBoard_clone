# -*- coding: utf-8 -*-
"""Cache-plane architecture constants and terminology for MES Dashboard.

This module defines the four-plane model that governs where cached and
queryable data must live:

  snapshot      – Redis-backed realtime datasets (WIP, resource master,
                  equipment status, filter caches).  Refreshed on a
                  background cadence; Redis is the shared source of truth.

  heavy-query   – Historical, replayable, or exportable results.  Result
                  bodies live in Parquet spool; DuckDB is the canonical
                  runtime.  Redis holds only metadata, lifecycle state,
                  lightweight indexes, and locks.

  derived-result – Compact results computed from canonical source datasets
                  (e.g., anomaly summaries, pre-aggregated KPIs).  May be
                  stored in Redis but must not become the owner of source
                  dataset warmup.

  control       – Locks, inflight state, job status, progress, manifests,
                  and other correctness-critical metadata.  Must be
                  isolated from data-plane eviction pressure.

Modules covered by this architecture must not retain long-lived in-process
full DataFrame or equivalent payload caches as authoritative storage for
snapshot-plane or heavy-query-plane data.
"""

from __future__ import annotations

from enum import Enum


# ============================================================
# Plane Classification
# ============================================================

class CachePlane(str, Enum):
    """Canonical cache-plane identifiers."""

    SNAPSHOT = "snapshot"
    HEAVY_QUERY = "heavy-query"
    DERIVED_RESULT = "derived-result"
    CONTROL = "control"


# ============================================================
# Snapshot-Plane Policy Constants
# ============================================================

# Redis TTL for snapshot keys must be at least this many times the
# background refresh interval so that normal refresh cycles do not
# predictably expire the snapshot before the next write.
SNAPSHOT_REDIS_TTL_MULTIPLIER = 2

# Minimum Redis TTL floor for snapshot keys regardless of sync interval.
SNAPSHOT_REDIS_TTL_FLOOR_SECONDS = 600


def snapshot_redis_ttl(sync_interval_seconds: int) -> int:
    """Return the Redis TTL to use for a snapshot-plane dataset.

    The TTL exceeds the sync interval so that a healthy background
    refresh never races against Redis expiry.

    Args:
        sync_interval_seconds: The configured background refresh cadence.

    Returns:
        Redis TTL in seconds (always >= SNAPSHOT_REDIS_TTL_FLOOR_SECONDS).
    """
    return max(
        sync_interval_seconds * SNAPSHOT_REDIS_TTL_MULTIPLIER,
        SNAPSHOT_REDIS_TTL_FLOOR_SECONDS,
    )


# ============================================================
# Heavy-Query-Plane Status Values
# ============================================================

HEAVY_QUERY_STATUS_PENDING = "pending"
HEAVY_QUERY_STATUS_RUNNING = "running"
HEAVY_QUERY_STATUS_READY = "ready"
HEAVY_QUERY_STATUS_FAILED = "failed"
HEAVY_QUERY_STATUS_EXPIRED = "expired"

# ============================================================
# Control-Plane Key Prefix Convention
# ============================================================

# Control-plane keys should use this prefix segment so that separate
# Redis eviction policies can be applied to them.
CONTROL_PLANE_KEY_SEGMENT = "ctrl"
