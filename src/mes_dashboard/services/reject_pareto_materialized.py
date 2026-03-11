# -*- coding: utf-8 -*-
"""Reject-history Pareto materialized aggregate layer.

Pre-computes dimension aggregates from cached LOT-level DataFrames so that
interactive Pareto requests read from compact snapshots instead of re-scanning
detail rows on every filter change.

Snapshot lifecycle:
  build_snapshot()  → creates 6-dim metric cube from filtered DataFrame
  store_snapshot()  → writes to L1 process cache (keyed by filter context)
  read_snapshot()   → reads from L1 with freshness/version validation
  evaluate()        → runs cross-filter + scope on the in-memory cube

Feature flags (env):
  PARETO_MATERIALIZATION_ENABLED    – allow building snapshots  (default: false)
  PARETO_MATERIALIZATION_READ_ENABLED – serve from snapshots    (default: false)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sys
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from mes_dashboard.core.feature_flags import resolve_bool_flag

logger = logging.getLogger("mes_dashboard.reject_pareto_materialized")

# ---------------------------------------------------------------------------
# Schema & configuration
# ---------------------------------------------------------------------------

SCHEMA_VERSION = 1

_SNAPSHOT_TTL_SECONDS = max(60, int(os.getenv("PARETO_SNAPSHOT_TTL_SECONDS", "600")))
_SNAPSHOT_MAX_CUBE_ROWS = max(100, int(os.getenv("PARETO_SNAPSHOT_MAX_CUBE_ROWS", "100000")))
_SNAPSHOT_MAX_PAYLOAD_BYTES = max(
    1024 * 1024,
    int(float(os.getenv("PARETO_SNAPSHOT_MAX_PAYLOAD_MB", "8")) * 1024 * 1024),
)
_SNAPSHOT_L1_MAX_SIZE = max(1, int(os.getenv("PARETO_SNAPSHOT_L1_MAX_SIZE", "16")))

# Single-flight build timeout: how long a waiter will block for a concurrent build
_BUILD_WAIT_TIMEOUT_SECONDS = float(os.getenv("PARETO_BUILD_WAIT_TIMEOUT", "10"))

# ---------------------------------------------------------------------------
# Feature flags (evaluated once at import; restart to change)
# ---------------------------------------------------------------------------

MATERIALIZATION_ENABLED = resolve_bool_flag(
    "PARETO_MATERIALIZATION_ENABLED", default=False,
)
MATERIALIZATION_READ_ENABLED = resolve_bool_flag(
    "PARETO_MATERIALIZATION_READ_ENABLED", default=False,
)

# ---------------------------------------------------------------------------
# L1 snapshot cache
# ---------------------------------------------------------------------------

from mes_dashboard.core.cache import ProcessLevelCache, register_process_cache  # noqa: E402

_snapshot_cache = ProcessLevelCache(
    ttl_seconds=_SNAPSHOT_TTL_SECONDS,
    max_size=_SNAPSHOT_L1_MAX_SIZE,
)
register_process_cache("pareto_snapshot", _snapshot_cache, "Pareto Snapshot (L1)")


# ---------------------------------------------------------------------------
# Telemetry counters (thread-safe)
# ---------------------------------------------------------------------------

class _Telemetry:
    """In-process counters for materialized Pareto cache behaviour."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.hit = 0
        self.miss = 0
        self.build = 0
        self.build_ok = 0
        self.build_fail = 0
        self.fallback = 0
        self.fallback_reasons: Dict[str, int] = {}
        self.rejected_oversize = 0
        self.last_build_latency: Optional[float] = None
        self.last_snapshot_payload_bytes: Optional[int] = None
        self.last_snapshot_built_at: Optional[float] = None

    # -- recording helpers ---------------------------------------------------

    def record_hit(self) -> None:
        with self._lock:
            self.hit += 1

    def record_miss(self) -> None:
        with self._lock:
            self.miss += 1

    def record_build_start(self) -> None:
        with self._lock:
            self.build += 1

    def record_build_ok(self, latency: float, payload_bytes: int) -> None:
        with self._lock:
            self.build_ok += 1
            self.last_build_latency = latency
            self.last_snapshot_payload_bytes = payload_bytes
            self.last_snapshot_built_at = time.time()

    def record_build_fail(self) -> None:
        with self._lock:
            self.build_fail += 1

    def record_fallback(self, reason: str) -> None:
        with self._lock:
            self.fallback += 1
            self.fallback_reasons[reason] = self.fallback_reasons.get(reason, 0) + 1

    def record_rejected_oversize(self) -> None:
        with self._lock:
            self.rejected_oversize += 1

    # -- snapshot for telemetry API ------------------------------------------

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            total_reads = self.hit + self.miss
            return {
                "hit": self.hit,
                "miss": self.miss,
                "hit_rate": round(self.hit / total_reads, 4) if total_reads else 0,
                "miss_rate": round(self.miss / total_reads, 4) if total_reads else 0,
                "build": self.build,
                "build_ok": self.build_ok,
                "build_fail": self.build_fail,
                "fallback": self.fallback,
                "fallback_reasons": dict(self.fallback_reasons),
                "rejected_oversize": self.rejected_oversize,
                "last_build_latency_s": self.last_build_latency,
                "last_snapshot_payload_bytes": self.last_snapshot_payload_bytes,
                "last_snapshot_built_at": self.last_snapshot_built_at,
            }


_telemetry = _Telemetry()


def get_telemetry() -> Dict[str, Any]:
    """Return current materialization telemetry for operations diagnostics."""
    return _telemetry.snapshot()


# ---------------------------------------------------------------------------
# Fallback reason codes (stable, for alert correlation)
# ---------------------------------------------------------------------------

FALLBACK_MISS = "miss"
FALLBACK_STALE = "stale"
FALLBACK_VERSION_MISMATCH = "version_mismatch"
FALLBACK_BUILD_FAILED = "build_failed"
FALLBACK_BUILD_TIMEOUT = "build_timeout"
FALLBACK_DISABLED = "disabled"
FALLBACK_OVERSIZE = "oversize"

# ---------------------------------------------------------------------------
# Single-flight guard
# ---------------------------------------------------------------------------

_building_events: Dict[str, threading.Event] = {}
_building_lock = threading.Lock()


def _acquire_build(key: str) -> Tuple[bool, Optional[threading.Event]]:
    """Try to become the builder for *key*.

    Returns (is_builder, event).
    - (True, event): caller should build, then call event.set().
    - (False, event): another thread is building; caller should event.wait().
    """
    with _building_lock:
        existing = _building_events.get(key)
        if existing is not None:
            return False, existing
        event = threading.Event()
        _building_events[key] = event
        return True, event


def _release_build(key: str) -> None:
    """Signal that the build for *key* is done (success or failure)."""
    with _building_lock:
        event = _building_events.pop(key, None)
    if event is not None:
        event.set()


# ---------------------------------------------------------------------------
# Key builder
# ---------------------------------------------------------------------------

def build_snapshot_key(
    query_id: str,
    *,
    include_excluded_scrap: bool = False,
    exclude_material_scrap: bool = True,
    exclude_pb_diode: bool = True,
    packages: Optional[List[str]] = None,
    workcenter_groups: Optional[List[str]] = None,
    reasons: Optional[List[str]] = None,
    trend_dates: Optional[List[str]] = None,
) -> str:
    """Build a canonical snapshot key encoding query identity and filter context.

    Key structure: ``pareto_mat:<query_id>:<context_hash>:v<schema_version>``

    The *context_hash* is a truncated SHA-256 of a JSON object that captures
    policy toggles, supplementary filters, trend dates, and schema version so
    that different filter contexts never collide.
    """
    context = {
        "qid": query_id,
        "ies": bool(include_excluded_scrap),
        "ems": bool(exclude_material_scrap),
        "epd": bool(exclude_pb_diode),
        "pkg": sorted(packages) if packages else None,
        "wcg": sorted(workcenter_groups) if workcenter_groups else None,
        "rsn": sorted(reasons) if reasons else None,
        "td": sorted(trend_dates) if trend_dates else None,
        "sv": SCHEMA_VERSION,
    }
    raw = json.dumps(context, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
    return f"pareto_mat:{query_id}:{digest}:v{SCHEMA_VERSION}"


# ---------------------------------------------------------------------------
# Snapshot read / write / validate
# ---------------------------------------------------------------------------

def read_snapshot(key: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Read a snapshot from L1 cache, validating freshness and version.

    Returns ``(snapshot, None)`` on hit, or ``(None, fallback_reason)`` on miss.
    """
    payload = _snapshot_cache.get(key)
    if payload is None:
        return None, FALLBACK_MISS

    # Version check
    if payload.get("schema_version") != SCHEMA_VERSION:
        _snapshot_cache.invalidate(key)
        return None, FALLBACK_VERSION_MISMATCH

    # Freshness check (belt-and-suspenders; ProcessLevelCache also has TTL)
    built_at = payload.get("built_at", 0)
    if time.time() - built_at > _SNAPSHOT_TTL_SECONDS:
        _snapshot_cache.invalidate(key)
        return None, FALLBACK_STALE

    return payload, None


def store_snapshot(key: str, snapshot: Dict[str, Any]) -> bool:
    """Write a validated snapshot to L1 cache.

    Returns False and logs a warning if the payload exceeds size guardrails.
    """
    # Payload-size guardrail
    try:
        payload_bytes = len(json.dumps(snapshot, separators=(",", ":")).encode())
    except (TypeError, ValueError):
        logger.warning("Snapshot serialization failed for key=%s", key)
        return False

    if payload_bytes > _SNAPSHOT_MAX_PAYLOAD_BYTES:
        logger.warning(
            "Snapshot payload exceeds guardrail (key=%s, bytes=%d, limit=%d) – rejected",
            key, payload_bytes, _SNAPSHOT_MAX_PAYLOAD_BYTES,
        )
        _telemetry.record_rejected_oversize()
        return False

    snapshot["_payload_bytes"] = payload_bytes
    _snapshot_cache.set(key, snapshot)
    return True


# ---------------------------------------------------------------------------
# Snapshot build
# ---------------------------------------------------------------------------

def _empty_snapshot() -> Dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "built_at": time.time(),
        "cube": [],
        "dim_columns": {},
    }


def build_snapshot(
    df,  # pd.DataFrame – imported lazily to keep module importable w/o pandas
    *,
    include_excluded_scrap: bool = False,
    exclude_material_scrap: bool = True,
    exclude_pb_diode: bool = True,
    packages: Optional[List[str]] = None,
    workcenter_groups: Optional[List[str]] = None,
    reasons: Optional[List[str]] = None,
    trend_dates: Optional[List[str]] = None,
) -> Optional[Dict[str, Any]]:
    """Build a materialized Pareto snapshot from a cached reject DataFrame.

    Returns the snapshot dict on success, ``None`` if the DataFrame is too
    large for materialization (size guardrail), or an empty snapshot when
    filtering yields zero rows.
    """
    import pandas as pd  # local import: keep module bootstrap light

    from mes_dashboard.services.reject_dataset_cache import (
        _DIM_TO_DF_COLUMN,
        _apply_policy_filters,
        _apply_supplementary_filters,
        _normalize_text,
        _to_date_str,
    )

    if df is None or (hasattr(df, "empty") and df.empty):
        return None

    # ---- 1. Apply policy filters ------------------------------------------
    filtered = _apply_policy_filters(
        df,
        include_excluded_scrap=include_excluded_scrap,
        exclude_material_scrap=exclude_material_scrap,
        exclude_pb_diode=exclude_pb_diode,
    )
    if filtered is None or filtered.empty:
        return _empty_snapshot()

    # ---- 2. Apply supplementary filters -----------------------------------
    filtered = _apply_supplementary_filters(
        filtered,
        packages=packages,
        workcenter_groups=workcenter_groups,
        reasons=reasons,
    )
    if filtered is None or filtered.empty:
        return _empty_snapshot()

    # ---- 3. Apply trend date filter ---------------------------------------
    if trend_dates and "TXN_DAY" in filtered.columns:
        date_set = set(trend_dates)
        filtered = filtered[
            filtered["TXN_DAY"].apply(lambda d: _to_date_str(d) in date_set)
        ]
        if filtered.empty:
            return _empty_snapshot()

    # ---- 4. Build the 6-dimension metric cube -----------------------------
    dim_cols = [col for dim, col in _DIM_TO_DF_COLUMN.items() if col in filtered.columns]
    metric_cols = [c for c in ("REJECT_TOTAL_QTY", "DEFECT_QTY", "MOVEIN_QTY") if c in filtered.columns]

    if not dim_cols or not metric_cols:
        return _empty_snapshot()

    # Normalize dimension values (align with _build_dimension_pareto_items)
    work = filtered.copy()
    for col in dim_cols:
        work[col] = work[col].apply(lambda v: _normalize_text(v) or "(未知)")

    # Aggregate: groupby all 6 dims → sum metrics + count unique lots
    agg_spec: Dict[str, Any] = {col: "sum" for col in metric_cols}
    has_container = "CONTAINERID" in work.columns
    if has_container:
        agg_spec["CONTAINERID"] = "nunique"

    cube_df = work.groupby(dim_cols, sort=False).agg(agg_spec).reset_index()

    if has_container:
        cube_df = cube_df.rename(columns={"CONTAINERID": "lot_count"})
    else:
        cube_df["lot_count"] = 0

    # ---- 5. Size guardrail ------------------------------------------------
    if len(cube_df) > _SNAPSHOT_MAX_CUBE_ROWS:
        logger.warning(
            "Snapshot cube exceeds row guardrail (rows=%d, limit=%d) – rejected",
            len(cube_df), _SNAPSHOT_MAX_CUBE_ROWS,
        )
        _telemetry.record_rejected_oversize()
        return None

    # Build dim name → column mapping (used at evaluation time)
    dim_columns = {dim: col for dim, col in _DIM_TO_DF_COLUMN.items() if col in dim_cols}

    # Convert to list-of-dicts for JSON-safe storage
    cube_rows = cube_df.to_dict("records")

    return {
        "schema_version": SCHEMA_VERSION,
        "built_at": time.time(),
        "cube": cube_rows,
        "dim_columns": dim_columns,
    }


# ---------------------------------------------------------------------------
# Cross-filter evaluation on the materialized cube
# ---------------------------------------------------------------------------

# Dimensions that support top-20 display truncation
_PARETO_TOP20_DIMENSIONS = {"type"}


def evaluate(
    snapshot: Dict[str, Any],
    *,
    metric_mode: str = "reject_total",
    pareto_scope: str = "top80",
    pareto_display_scope: str = "all",
    pareto_selections: Optional[Dict[str, List[str]]] = None,
) -> Dict[str, Any]:
    """Evaluate batch Pareto from a materialized snapshot.

    Runs cross-filter (exclude-self) on the in-memory cube, computes
    metrics, pct, cumPct, and applies scope truncation.

    Returns the same ``{"dimensions": {...}, ...}`` structure as the legacy
    ``compute_batch_pareto`` function.
    """
    from mes_dashboard.services.reject_history_service import _as_float, _as_int

    cube = snapshot.get("cube", [])
    dim_columns = snapshot.get("dim_columns", {})
    selections = pareto_selections or {}

    metric_col = "DEFECT_QTY" if metric_mode == "defect" else "REJECT_TOTAL_QTY"

    dimensions: Dict[str, Dict[str, Any]] = {}

    for dim, col in dim_columns.items():
        # Apply cross-filter: keep rows matching all OTHER dimensions' selections
        filtered_rows = cube
        for other_dim, other_col in dim_columns.items():
            if other_dim == dim:
                continue  # exclude-self
            sel_values = selections.get(other_dim)
            if not sel_values:
                continue
            value_set = set(sel_values)
            filtered_rows = [r for r in filtered_rows if r.get(col_for_dim(other_dim, dim_columns)) in value_set]

        # Group by target dimension → sum metrics
        groups: Dict[str, Dict[str, Any]] = {}
        for row in filtered_rows:
            dim_value = row.get(col) or "(未知)"
            if dim_value not in groups:
                groups[dim_value] = {
                    "REJECT_TOTAL_QTY": 0,
                    "DEFECT_QTY": 0,
                    "MOVEIN_QTY": 0,
                    "lot_count": 0,
                }
            g = groups[dim_value]
            for mc in ("REJECT_TOTAL_QTY", "DEFECT_QTY", "MOVEIN_QTY"):
                g[mc] += _as_int(row.get(mc, 0))
            g["lot_count"] += _as_int(row.get("lot_count", 0))

        # Build sorted items (descending by metric)
        items_raw = []
        for dim_value, agg in groups.items():
            mv = _as_float(agg.get(metric_col, 0))
            if mv <= 0:
                continue
            items_raw.append({
                "dim_value": dim_value,
                "metric_value": mv,
                "REJECT_TOTAL_QTY": agg["REJECT_TOTAL_QTY"],
                "DEFECT_QTY": agg["DEFECT_QTY"],
                "MOVEIN_QTY": agg["MOVEIN_QTY"],
                "lot_count": agg["lot_count"],
            })

        items_raw.sort(key=lambda x: x["metric_value"], reverse=True)

        # Compute pct, cumPct
        total_metric = sum(x["metric_value"] for x in items_raw) or 1.0
        cum_pct = 0.0
        items: List[Dict[str, Any]] = []
        for it in items_raw:
            pct = round(it["metric_value"] / total_metric * 100, 4)
            cum_pct = round(cum_pct + pct, 4)
            items.append({
                "reason": it["dim_value"],
                "metric_value": it["metric_value"],
                "MOVEIN_QTY": it["MOVEIN_QTY"],
                "REJECT_TOTAL_QTY": it["REJECT_TOTAL_QTY"],
                "DEFECT_QTY": it["DEFECT_QTY"],
                "count": it["lot_count"],
                "pct": pct,
                "cumPct": cum_pct,
            })

        # Apply pareto_scope
        if pareto_scope == "top80" and items:
            top_items = [i for i in items if i["cumPct"] <= 80.0]
            if not top_items:
                top_items = [items[0]]
            items = top_items

        # Apply pareto_display_scope
        if pareto_display_scope == "top20" and dim in _PARETO_TOP20_DIMENSIONS:
            items = items[:20]

        dimensions[dim] = {
            "items": items,
            "dimension": dim,
            "metric_mode": metric_mode,
        }

    return {
        "dimensions": dimensions,
        "metric_mode": metric_mode,
        "pareto_scope": pareto_scope,
        "pareto_display_scope": pareto_display_scope,
    }


def col_for_dim(dim: str, dim_columns: Dict[str, str]) -> str:
    """Resolve the DataFrame column name for a Pareto dimension."""
    return dim_columns.get(dim, dim)


# ---------------------------------------------------------------------------
# Evaluate single-dimension pareto from snapshot
# ---------------------------------------------------------------------------

def evaluate_single_dimension(
    snapshot: Dict[str, Any],
    *,
    dimension: str = "reason",
    metric_mode: str = "reject_total",
    pareto_scope: str = "top80",
) -> Optional[Dict[str, Any]]:
    """Evaluate a single-dimension Pareto from a materialized snapshot.

    Returns the same ``{"items": [...], "dimension": ..., "metric_mode": ...}``
    structure as the legacy ``compute_dimension_pareto`` function.
    """
    result = evaluate(
        snapshot,
        metric_mode=metric_mode,
        pareto_scope=pareto_scope,
        pareto_display_scope="all",
        pareto_selections=None,
    )
    dim_data = result.get("dimensions", {}).get(dimension)
    if dim_data is not None:
        return dim_data
    return {"items": [], "dimension": dimension, "metric_mode": metric_mode}


# ---------------------------------------------------------------------------
# Orchestration: read-through with build-on-miss
# ---------------------------------------------------------------------------

def try_materialized_batch_pareto(
    query_id: str,
    df_loader,  # callable() -> Optional[pd.DataFrame]
    *,
    metric_mode: str = "reject_total",
    pareto_scope: str = "top80",
    pareto_display_scope: str = "all",
    pareto_selections: Optional[Dict[str, List[str]]] = None,
    include_excluded_scrap: bool = False,
    exclude_material_scrap: bool = True,
    exclude_pb_diode: bool = True,
    packages: Optional[List[str]] = None,
    workcenter_groups: Optional[List[str]] = None,
    reasons: Optional[List[str]] = None,
    trend_dates: Optional[List[str]] = None,
) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """Try to serve batch-pareto from a materialized snapshot.

    Returns ``(result, meta)`` where *result* is the Pareto payload on hit,
    or ``None`` when the caller should fall back to legacy compute.
    *meta* always contains source/freshness/fallback information.
    """
    if not MATERIALIZATION_READ_ENABLED:
        _telemetry.record_fallback(FALLBACK_DISABLED)
        return None, _meta(source="legacy", fallback_reason=FALLBACK_DISABLED)

    key = build_snapshot_key(
        query_id,
        include_excluded_scrap=include_excluded_scrap,
        exclude_material_scrap=exclude_material_scrap,
        exclude_pb_diode=exclude_pb_diode,
        packages=packages,
        workcenter_groups=workcenter_groups,
        reasons=reasons,
        trend_dates=trend_dates,
    )

    # ---- 1. Try read -------------------------------------------------------
    snapshot, miss_reason = read_snapshot(key)
    if snapshot is not None:
        _telemetry.record_hit()
        result = evaluate(
            snapshot,
            metric_mode=metric_mode,
            pareto_scope=pareto_scope,
            pareto_display_scope=pareto_display_scope,
            pareto_selections=pareto_selections,
        )
        return result, _meta(
            source="materialized",
            snapshot_built_at=snapshot.get("built_at"),
            schema_version=snapshot.get("schema_version"),
            payload_bytes=snapshot.get("_payload_bytes"),
        )

    # ---- 2. Snapshot miss – attempt build ----------------------------------
    _telemetry.record_miss()

    if not MATERIALIZATION_ENABLED:
        _telemetry.record_fallback(FALLBACK_DISABLED)
        return None, _meta(source="legacy", fallback_reason=FALLBACK_DISABLED)

    is_builder, event = _acquire_build(key)

    if not is_builder:
        # Another thread is building – wait or give up
        if event is not None and event.wait(timeout=_BUILD_WAIT_TIMEOUT_SECONDS):
            # Re-read after build
            snapshot, _ = read_snapshot(key)
            if snapshot is not None:
                _telemetry.record_hit()
                result = evaluate(
                    snapshot,
                    metric_mode=metric_mode,
                    pareto_scope=pareto_scope,
                    pareto_display_scope=pareto_display_scope,
                    pareto_selections=pareto_selections,
                )
                return result, _meta(
                    source="materialized",
                    snapshot_built_at=snapshot.get("built_at"),
                    schema_version=snapshot.get("schema_version"),
                    payload_bytes=snapshot.get("_payload_bytes"),
                )
        _telemetry.record_fallback(FALLBACK_BUILD_TIMEOUT)
        return None, _meta(source="legacy", fallback_reason=FALLBACK_BUILD_TIMEOUT)

    # We are the builder
    _telemetry.record_build_start()
    t0 = time.time()
    try:
        df = df_loader()
        if df is None:
            _telemetry.record_build_fail()
            _telemetry.record_fallback(miss_reason or FALLBACK_MISS)
            return None, _meta(source="legacy", fallback_reason=miss_reason or FALLBACK_MISS)

        snapshot = build_snapshot(
            df,
            include_excluded_scrap=include_excluded_scrap,
            exclude_material_scrap=exclude_material_scrap,
            exclude_pb_diode=exclude_pb_diode,
            packages=packages,
            workcenter_groups=workcenter_groups,
            reasons=reasons,
            trend_dates=trend_dates,
        )

        if snapshot is None:
            _telemetry.record_build_fail()
            _telemetry.record_fallback(FALLBACK_OVERSIZE)
            return None, _meta(source="legacy", fallback_reason=FALLBACK_OVERSIZE)

        latency = time.time() - t0
        stored = store_snapshot(key, snapshot)
        if not stored:
            _telemetry.record_build_fail()
            _telemetry.record_fallback(FALLBACK_OVERSIZE)
            logger.warning(
                "Snapshot build completed but storage rejected (key=%s, latency=%.3fs)",
                key, latency,
            )
            return None, _meta(source="legacy", fallback_reason=FALLBACK_OVERSIZE)

        _telemetry.record_build_ok(latency, snapshot.get("_payload_bytes", 0))
        logger.info(
            "Snapshot built (key=%s, cube_rows=%d, latency=%.3fs, bytes=%d)",
            key, len(snapshot.get("cube", [])), latency,
            snapshot.get("_payload_bytes", 0),
        )

        result = evaluate(
            snapshot,
            metric_mode=metric_mode,
            pareto_scope=pareto_scope,
            pareto_display_scope=pareto_display_scope,
            pareto_selections=pareto_selections,
        )
        return result, _meta(
            source="materialized",
            snapshot_built_at=snapshot.get("built_at"),
            schema_version=snapshot.get("schema_version"),
            payload_bytes=snapshot.get("_payload_bytes"),
            build_latency=latency,
        )
    except Exception:
        _telemetry.record_build_fail()
        _telemetry.record_fallback(FALLBACK_BUILD_FAILED)
        logger.exception("Snapshot build failed (key=%s)", key)
        return None, _meta(source="legacy", fallback_reason=FALLBACK_BUILD_FAILED)
    finally:
        _release_build(key)


def try_materialized_dimension_pareto(
    query_id: str,
    df_loader,
    *,
    dimension: str = "reason",
    metric_mode: str = "reject_total",
    pareto_scope: str = "top80",
    include_excluded_scrap: bool = False,
    exclude_material_scrap: bool = True,
    exclude_pb_diode: bool = True,
    packages: Optional[List[str]] = None,
    workcenter_groups: Optional[List[str]] = None,
    reasons: Optional[List[str]] = None,
    trend_dates: Optional[List[str]] = None,
) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """Try to serve single-dimension pareto from a materialized snapshot.

    Returns ``(result, meta)`` – same contract as ``try_materialized_batch_pareto``.
    """
    if not MATERIALIZATION_READ_ENABLED:
        return None, _meta(source="legacy", fallback_reason=FALLBACK_DISABLED)

    key = build_snapshot_key(
        query_id,
        include_excluded_scrap=include_excluded_scrap,
        exclude_material_scrap=exclude_material_scrap,
        exclude_pb_diode=exclude_pb_diode,
        packages=packages,
        workcenter_groups=workcenter_groups,
        reasons=reasons,
        trend_dates=trend_dates,
    )

    snapshot, miss_reason = read_snapshot(key)
    if snapshot is not None:
        _telemetry.record_hit()
        result = evaluate_single_dimension(
            snapshot,
            dimension=dimension,
            metric_mode=metric_mode,
            pareto_scope=pareto_scope,
        )
        return result, _meta(
            source="materialized",
            snapshot_built_at=snapshot.get("built_at"),
            schema_version=snapshot.get("schema_version"),
        )

    # No build-on-miss for single dimension – fall back to legacy
    _telemetry.record_miss()
    _telemetry.record_fallback(miss_reason or FALLBACK_MISS)
    return None, _meta(source="legacy", fallback_reason=miss_reason or FALLBACK_MISS)


# ---------------------------------------------------------------------------
# Response metadata helpers
# ---------------------------------------------------------------------------

def _meta(
    *,
    source: str,
    fallback_reason: Optional[str] = None,
    snapshot_built_at: Optional[float] = None,
    schema_version: Optional[int] = None,
    payload_bytes: Optional[int] = None,
    build_latency: Optional[float] = None,
) -> Dict[str, Any]:
    """Build response metadata dict for materialization context."""
    m: Dict[str, Any] = {"pareto_source": source}
    if fallback_reason:
        m["pareto_fallback_reason"] = fallback_reason
    if snapshot_built_at is not None:
        m["pareto_snapshot_built_at"] = snapshot_built_at
        m["pareto_snapshot_age_s"] = round(time.time() - snapshot_built_at, 1)
    if schema_version is not None:
        m["pareto_schema_version"] = schema_version
    if payload_bytes is not None:
        m["pareto_snapshot_bytes"] = payload_bytes
    if build_latency is not None:
        m["pareto_build_latency_s"] = round(build_latency, 3)
    return m
