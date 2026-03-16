# -*- coding: utf-8 -*-
"""WIP (Work In Progress) query services for MES Dashboard.

Provides functions to query WIP data from DWH.DW_MES_LOT_V view.
This view provides real-time WIP information updated every 5 minutes.

Now uses Redis cache when available, with fallback to Oracle direct query.
"""

import logging
import threading
from collections import Counter
from datetime import datetime
from typing import Optional, Dict, List, Any

import numpy as np
import pandas as pd

from mes_dashboard.core.database import (
    read_sql_df,
    DatabasePoolExhaustedError,
    DatabaseCircuitOpenError,
)
from mes_dashboard.core.cache import (
    get_cached_wip_data,
    get_cached_sys_date,
    get_cache_updated_at,
)
from mes_dashboard.sql import SQLLoader, QueryBuilder
from mes_dashboard.sql.filters import CommonFilters, NON_QUALITY_HOLD_REASONS

logger = logging.getLogger('mes_dashboard.wip_service')

_wip_search_index_lock = threading.Lock()
_wip_search_index_cache: Dict[str, Dict[str, Any]] = {}
_wip_snapshot_lock = threading.Lock()
_wip_snapshot_cache: Dict[str, Dict[str, Any]] = {}
_wip_index_metrics_lock = threading.Lock()
_wip_index_metrics: Dict[str, Any] = {
    "snapshot_hits": 0,
    "snapshot_misses": 0,
    "search_index_hits": 0,
    "search_index_misses": 0,
    "search_index_rebuilds": 0,
    "search_index_incremental_updates": 0,
    "search_index_reconciliation_fallbacks": 0,
}

_EMPTY_INT_INDEX = np.array([], dtype=np.int64)


def _safe_value(val):
    """Convert pandas NaN/NaT to None and numpy types to native Python types for JSON serialization."""
    if pd.isna(val):
        return None
    # Convert numpy types to native Python types for JSON serialization
    if hasattr(val, 'item'):  # numpy scalar types have .item() method
        return val.item()
    return val


def _build_base_conditions_builder(
    include_dummy: bool = False,
    workorder: Optional[str] = None,
    lotid: Optional[str] = None,
    builder: Optional[QueryBuilder] = None
) -> QueryBuilder:
    """Build base WHERE conditions for WIP queries using QueryBuilder.

    Args:
        include_dummy: If False (default), exclude LOTID containing 'DUMMY'
        workorder: Optional WORKORDER filter (fuzzy match)
        lotid: Optional LOTID filter (fuzzy match)
        builder: Optional existing QueryBuilder to add conditions to

    Returns:
        QueryBuilder with base conditions and parameters
    """
    if builder is None:
        builder = QueryBuilder()

    # Exclude raw materials (NULL WORKORDER)
    builder.add_is_not_null("WORKORDER")

    # DUMMY exclusion (default behavior)
    if not include_dummy:
        builder.add_condition("LOTID NOT LIKE '%DUMMY%'")

    # WORKORDER filter (fuzzy match)
    workorders = _split_csv_values(workorder)
    if workorders:
        builder.add_or_like_conditions("WORKORDER", workorders, position="both", case_insensitive=True)

    # LOTID filter (fuzzy match)
    lotids = _split_csv_values(lotid)
    if lotids:
        builder.add_or_like_conditions("LOTID", lotids, position="both", case_insensitive=True)

    return builder


# ============================================================
# Hold Type Classification
# ============================================================
# NON_QUALITY_HOLD_REASONS is imported from sql.filters


def is_quality_hold(reason: str) -> bool:
    """Check if a hold reason is quality-related.

    Wrapper for CommonFilters.is_quality_hold for backwards compatibility.
    """
    return CommonFilters.is_quality_hold(reason)


def _add_hold_type_conditions(
    builder: QueryBuilder,
    hold_type: Optional[str] = None
) -> QueryBuilder:
    """Add hold type filter conditions to QueryBuilder.

    Args:
        builder: QueryBuilder to add conditions to
        hold_type: 'quality' for quality holds, 'non-quality' for non-quality holds

    Returns:
        QueryBuilder with hold type conditions added
    """
    if hold_type == 'quality':
        # Quality hold: HOLDREASONNAME is NULL or NOT in non-quality list
        builder.add_not_in_condition(
            "HOLDREASONNAME",
            list(NON_QUALITY_HOLD_REASONS),
            allow_null=True
        )
    elif hold_type == 'non-quality':
        # Non-quality hold: HOLDREASONNAME is in non-quality list
        builder.add_in_condition("HOLDREASONNAME", list(NON_QUALITY_HOLD_REASONS))
    return builder


# ============================================================
# Data Source Configuration
# ============================================================
# WIP view for real-time lot data
WIP_VIEW = "DWH.DW_MES_LOT_V"


# ============================================================
# Cache Data Helper Functions
# ============================================================

def _get_wip_dataframe() -> Optional[pd.DataFrame]:
    """Get WIP data from cache or return None if unavailable.

    Returns:
        DataFrame with WIP data from Redis cache, or None if cache miss.
    """
    df = get_cached_wip_data()
    if df is not None and not df.empty:
        logger.debug(f"Using cached WIP data ({len(df)} rows)")
        return df
    return None


def _get_wip_cache_version() -> str:
    """Build a lightweight cache version marker for derived index refresh."""
    updated_at = get_cache_updated_at() or ""
    sys_date = get_cached_sys_date() or ""
    return f"{updated_at}|{sys_date}"


def _increment_wip_metric(metric: str, value: int = 1) -> None:
    with _wip_index_metrics_lock:
        _wip_index_metrics[metric] = int(_wip_index_metrics.get(metric, 0)) + value


def _estimate_dataframe_bytes(df: pd.DataFrame) -> int:
    if df is None:
        return 0
    try:
        return int(df.memory_usage(index=True, deep=True).sum())
    except Exception:
        return 0


def _estimate_counter_payload_bytes(counter: Counter) -> int:
    total = 0
    for key, count in counter.items():
        total += len(str(key)) + 16 + int(count)
    return total


def _normalize_text_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    text = str(value).strip()
    return text


def _split_csv_values(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    values: List[str] = []
    seen = set()
    for token in str(raw).split(","):
        text = token.strip()
        if not text or text in seen:
            continue
        values.append(text)
        seen.add(text)
    return values


def _contains_any_mask(series: pd.Series, raw_values: Optional[str]) -> pd.Series:
    values = _split_csv_values(raw_values)
    if not values:
        return pd.Series(True, index=series.index)

    text_series = series.astype(str)
    mask = pd.Series(False, index=series.index)
    for value in values:
        mask |= text_series.str.contains(value, case=False, na=False)
    return mask


def _add_exact_filter_conditions(builder: QueryBuilder, column: str, raw_values: Optional[str]) -> QueryBuilder:
    values = _split_csv_values(raw_values)
    if not values:
        return builder
    if len(values) == 1:
        builder.add_param_condition(column, values[0])
        return builder
    builder.add_in_condition(column, values)
    return builder


def _lookup_positions(index_map: Dict[str, np.ndarray], raw_values: Optional[str]) -> Optional[np.ndarray]:
    values = _split_csv_values(raw_values)
    if not values:
        return None

    buckets = [index_map.get(str(value)) for value in values]
    buckets = [bucket for bucket in buckets if bucket is not None and len(bucket) > 0]
    if not buckets:
        return _EMPTY_INT_INDEX
    if len(buckets) == 1:
        return buckets[0]
    return np.unique(np.concatenate(buckets))


def _build_filter_mask(
    df: pd.DataFrame,
    *,
    include_dummy: bool,
    workorder: Optional[str] = None,
    lotid: Optional[str] = None,
) -> pd.Series:
    if df.empty:
        return pd.Series(dtype=bool)

    mask = df['WORKORDER'].notna()

    if not include_dummy and 'LOTID' in df.columns:
        mask &= ~df['LOTID'].astype(str).str.contains('DUMMY', case=False, na=False)

    if workorder and 'WORKORDER' in df.columns:
        mask &= _contains_any_mask(df['WORKORDER'], workorder)

    if lotid and 'LOTID' in df.columns:
        mask &= _contains_any_mask(df['LOTID'], lotid)

    return mask


def _build_value_index(df: pd.DataFrame, column: str) -> Dict[str, np.ndarray]:
    if column not in df.columns or df.empty:
        return {}
    grouped = df.groupby(column, dropna=True, sort=False).indices
    return {str(key): np.asarray(indices, dtype=np.int64) for key, indices in grouped.items()}


def _intersect_positions(current: Optional[np.ndarray], candidate: Optional[np.ndarray]) -> np.ndarray:
    if candidate is None:
        return _EMPTY_INT_INDEX
    if current is None:
        return candidate
    if len(current) == 0 or len(candidate) == 0:
        return _EMPTY_INT_INDEX
    return np.intersect1d(current, candidate, assume_unique=False)


def _select_with_snapshot_indexes(
    include_dummy: bool = False,
    workorder: Optional[str] = None,
    lotid: Optional[str] = None,
    package: Optional[str] = None,
    pj_type: Optional[str] = None,
    firstname: Optional[str] = None,
    waferdesc: Optional[str] = None,
    workcenter: Optional[str] = None,
    status: Optional[str] = None,
    hold_type: Optional[str] = None,
) -> Optional[pd.DataFrame]:
    snapshot = _get_wip_snapshot(include_dummy=include_dummy)
    if snapshot is None:
        return None

    df = snapshot["frame"]
    indexes = snapshot["indexes"]
    selected_positions: Optional[np.ndarray] = None

    if workcenter:
        selected_positions = _intersect_positions(
            selected_positions,
            _lookup_positions(indexes["workcenter"], workcenter),
        )
    if package:
        selected_positions = _intersect_positions(
            selected_positions,
            _lookup_positions(indexes["package"], package),
        )
    if pj_type:
        selected_positions = _intersect_positions(
            selected_positions,
            _lookup_positions(indexes["pj_type"], pj_type),
        )
    if firstname:
        selected_positions = _intersect_positions(
            selected_positions,
            _lookup_positions(indexes["firstname"], firstname),
        )
    if waferdesc:
        selected_positions = _intersect_positions(
            selected_positions,
            _lookup_positions(indexes["waferdesc"], waferdesc),
        )
    if status:
        selected_positions = _intersect_positions(
            selected_positions,
            indexes["wip_status"].get(str(status).upper()),
        )
    if hold_type:
        selected_positions = _intersect_positions(
            selected_positions,
            indexes["hold_type"].get(str(hold_type).lower()),
        )

    if selected_positions is None:
        result = df
    elif len(selected_positions) == 0:
        result = df.iloc[0:0]
    else:
        result = df.iloc[selected_positions]

    if workorder:
        result = result[_contains_any_mask(result['WORKORDER'], workorder)]
    if lotid:
        result = result[_contains_any_mask(result['LOTID'], lotid)]
    return result


def _build_search_signatures(
    df: pd.DataFrame,
) -> tuple[Counter, Dict[str, tuple[str, str, str, str, str, str]]]:
    if df.empty:
        return Counter(), {}

    workorders = df.get("WORKORDER", pd.Series(index=df.index, dtype=object)).map(_normalize_text_value)
    lotids = df.get("LOTID", pd.Series(index=df.index, dtype=object)).map(_normalize_text_value)
    packages = df.get("PACKAGE_LEF", pd.Series(index=df.index, dtype=object)).map(_normalize_text_value)
    types = df.get("PJ_TYPE", pd.Series(index=df.index, dtype=object)).map(_normalize_text_value)
    firstnames = df.get("FIRSTNAME", pd.Series(index=df.index, dtype=object)).map(_normalize_text_value)
    waferdescs = df.get("WAFERDESC", pd.Series(index=df.index, dtype=object)).map(_normalize_text_value)

    signatures = (
        workorders
        + "\x1f"
        + lotids
        + "\x1f"
        + packages
        + "\x1f"
        + types
        + "\x1f"
        + firstnames
        + "\x1f"
        + waferdescs
    ).tolist()
    signature_counter = Counter(signatures)

    signature_fields: Dict[str, tuple[str, str, str, str, str, str]] = {}
    for signature, wo, lot, pkg, pj, first, wafer in zip(
        signatures,
        workorders,
        lotids,
        packages,
        types,
        firstnames,
        waferdescs,
    ):
        if signature not in signature_fields:
            signature_fields[signature] = (wo, lot, pkg, pj, first, wafer)
    return signature_counter, signature_fields


def _decode_signature_fields(signature: str) -> tuple[str, str, str, str, str, str]:
    parts = [str(value) for value in str(signature).split("\x1f")]
    if len(parts) < 6:
        parts.extend([""] * (6 - len(parts)))
    return tuple(parts[:6])


def _build_field_counters(
    signature_counter: Counter,
    signature_fields: Dict[str, tuple[str, str, str, str, str, str]],
) -> Dict[str, Counter]:
    counters = {
        "workorders": Counter(),
        "lotids": Counter(),
        "packages": Counter(),
        "types": Counter(),
        "firstnames": Counter(),
        "waferdescs": Counter(),
    }
    for signature, count in signature_counter.items():
        wo, lot, pkg, pj, first, wafer = signature_fields.get(signature, ("", "", "", "", "", ""))
        if wo:
            counters["workorders"][wo] += count
        if lot:
            counters["lotids"][lot] += count
        if pkg:
            counters["packages"][pkg] += count
        if pj:
            counters["types"][pj] += count
        if first:
            counters["firstnames"][first] += count
        if wafer:
            counters["waferdescs"][wafer] += count
    return counters


def _materialize_search_payload(
    *,
    version: str,
    row_count: int,
    signature_counter: Counter,
    field_counters: Dict[str, Counter],
    mode: str,
    added_rows: int = 0,
    removed_rows: int = 0,
    drift_ratio: float = 0.0,
) -> Dict[str, Any]:
    workorders = sorted(field_counters["workorders"].keys())
    lotids = sorted(field_counters["lotids"].keys())
    packages = sorted(field_counters["packages"].keys())
    types = sorted(field_counters["types"].keys())
    firstnames = sorted(field_counters["firstnames"].keys())
    waferdescs = sorted(field_counters["waferdescs"].keys())
    memory_bytes = (
        _estimate_counter_payload_bytes(field_counters["workorders"])
        + _estimate_counter_payload_bytes(field_counters["lotids"])
        + _estimate_counter_payload_bytes(field_counters["packages"])
        + _estimate_counter_payload_bytes(field_counters["types"])
        + _estimate_counter_payload_bytes(field_counters["firstnames"])
        + _estimate_counter_payload_bytes(field_counters["waferdescs"])
    )
    return {
        "version": version,
        "built_at": datetime.now().isoformat(),
        "row_count": int(row_count),
        "workorders": workorders,
        "lotids": lotids,
        "packages": packages,
        "types": types,
        "firstnames": firstnames,
        "waferdescs": waferdescs,
        "sync_mode": mode,
        "sync_added_rows": int(added_rows),
        "sync_removed_rows": int(removed_rows),
        "drift_ratio": round(float(drift_ratio), 6),
        "memory_bytes": int(memory_bytes),
        "_signature_counter": dict(signature_counter),
        "_field_counters": {
            "workorders": dict(field_counters["workorders"]),
            "lotids": dict(field_counters["lotids"]),
            "packages": dict(field_counters["packages"]),
            "types": dict(field_counters["types"]),
            "firstnames": dict(field_counters["firstnames"]),
            "waferdescs": dict(field_counters["waferdescs"]),
        },
    }


def _build_wip_search_index(df: pd.DataFrame, include_dummy: bool) -> Dict[str, Any]:
    filtered = _filter_base_conditions(df, include_dummy=include_dummy)
    signatures, signature_fields = _build_search_signatures(filtered)
    field_counters = _build_field_counters(signatures, signature_fields)
    return _materialize_search_payload(
        version=_get_wip_cache_version(),
        row_count=len(filtered),
        signature_counter=signatures,
        field_counters=field_counters,
        mode="full",
    )


def _try_incremental_search_sync(
    previous: Dict[str, Any],
    *,
    version: str,
    row_count: int,
    signature_counter: Counter,
    signature_fields: Dict[str, tuple[str, str, str, str, str, str]],
) -> Optional[Dict[str, Any]]:
    if not previous:
        return None
    old_signature_counter = Counter(previous.get("_signature_counter") or {})
    old_field_counters_raw = previous.get("_field_counters") or {}
    if not old_signature_counter or not old_field_counters_raw:
        return None

    added = signature_counter - old_signature_counter
    removed = old_signature_counter - signature_counter
    total_delta = sum(added.values()) + sum(removed.values())
    drift_ratio = total_delta / max(int(row_count), 1)
    if drift_ratio > 0.6:
        _increment_wip_metric("search_index_reconciliation_fallbacks")
        return None

    field_counters = {
        "workorders": Counter(old_field_counters_raw.get("workorders") or {}),
        "lotids": Counter(old_field_counters_raw.get("lotids") or {}),
        "packages": Counter(old_field_counters_raw.get("packages") or {}),
        "types": Counter(old_field_counters_raw.get("types") or {}),
        "firstnames": Counter(old_field_counters_raw.get("firstnames") or {}),
        "waferdescs": Counter(old_field_counters_raw.get("waferdescs") or {}),
    }

    for signature, count in added.items():
        wo, lot, pkg, pj, first, wafer = signature_fields.get(signature, ("", "", "", "", "", ""))
        if wo:
            field_counters["workorders"][wo] += count
        if lot:
            field_counters["lotids"][lot] += count
        if pkg:
            field_counters["packages"][pkg] += count
        if pj:
            field_counters["types"][pj] += count
        if first:
            field_counters["firstnames"][first] += count
        if wafer:
            field_counters["waferdescs"][wafer] += count

    previous_fields = {sig: _decode_signature_fields(sig) for sig in old_signature_counter.keys()}
    for signature, count in removed.items():
        wo, lot, pkg, pj, first, wafer = previous_fields.get(signature, ("", "", "", "", "", ""))
        if wo:
            field_counters["workorders"][wo] -= count
            if field_counters["workorders"][wo] <= 0:
                field_counters["workorders"].pop(wo, None)
        if lot:
            field_counters["lotids"][lot] -= count
            if field_counters["lotids"][lot] <= 0:
                field_counters["lotids"].pop(lot, None)
        if pkg:
            field_counters["packages"][pkg] -= count
            if field_counters["packages"][pkg] <= 0:
                field_counters["packages"].pop(pkg, None)
        if pj:
            field_counters["types"][pj] -= count
            if field_counters["types"][pj] <= 0:
                field_counters["types"].pop(pj, None)
        if first:
            field_counters["firstnames"][first] -= count
            if field_counters["firstnames"][first] <= 0:
                field_counters["firstnames"].pop(first, None)
        if wafer:
            field_counters["waferdescs"][wafer] -= count
            if field_counters["waferdescs"][wafer] <= 0:
                field_counters["waferdescs"].pop(wafer, None)

    _increment_wip_metric("search_index_incremental_updates")
    return _materialize_search_payload(
        version=version,
        row_count=row_count,
        signature_counter=signature_counter,
        field_counters=field_counters,
        mode="incremental",
        added_rows=sum(added.values()),
        removed_rows=sum(removed.values()),
        drift_ratio=drift_ratio,
    )


def _build_wip_snapshot(df: pd.DataFrame, include_dummy: bool, version: str) -> Dict[str, Any]:
    filtered = _filter_base_conditions(df, include_dummy=include_dummy)
    filtered = _add_wip_status_columns(filtered).reset_index(drop=True)

    hold_type_series = pd.Series(index=filtered.index, dtype=object)
    if not filtered.empty:
        hold_type_series = pd.Series("", index=filtered.index, dtype=object)
        hold_type_series.loc[filtered["IS_QUALITY_HOLD"]] = "quality"
        hold_type_series.loc[filtered["IS_NON_QUALITY_HOLD"]] = "non-quality"

    indexes = {
        "workcenter": _build_value_index(filtered, "WORKCENTER_GROUP"),
        "package": _build_value_index(filtered, "PACKAGE_LEF"),
        "pj_type": _build_value_index(filtered, "PJ_TYPE"),
        "firstname": _build_value_index(filtered, "FIRSTNAME"),
        "waferdesc": _build_value_index(filtered, "WAFERDESC"),
        "wip_status": _build_value_index(filtered, "WIP_STATUS"),
        "hold_type": _build_value_index(pd.DataFrame({"HOLD_TYPE": hold_type_series}), "HOLD_TYPE"),
    }

    exact_bucket_count = sum(len(bucket) for bucket in indexes.values())
    return {
        "version": version,
        "built_at": datetime.now().isoformat(),
        "row_count": int(len(filtered)),
        "frame": filtered,
        "indexes": indexes,
        "frame_bytes": _estimate_dataframe_bytes(filtered),
        "index_bucket_count": int(exact_bucket_count),
    }


def _get_wip_snapshot(include_dummy: bool) -> Optional[Dict[str, Any]]:
    cache_key = "with_dummy" if include_dummy else "without_dummy"
    version = _get_wip_cache_version()

    with _wip_snapshot_lock:
        cached = _wip_snapshot_cache.get(cache_key)
        if cached and cached.get("version") == version:
            _increment_wip_metric("snapshot_hits")
            return cached

    _increment_wip_metric("snapshot_misses")
    with _wip_snapshot_lock:
        existing = _wip_snapshot_cache.get(cache_key)
        if existing and existing.get("version") == version:
            _increment_wip_metric("snapshot_hits")
            return existing

        df = _get_wip_dataframe()
        if df is None:
            return None

        snapshot = _build_wip_snapshot(df, include_dummy=include_dummy, version=version)
        _wip_snapshot_cache[cache_key] = snapshot
        return snapshot


def _get_wip_search_index(include_dummy: bool) -> Optional[Dict[str, Any]]:
    cache_key = "with_dummy" if include_dummy else "without_dummy"
    version = _get_wip_cache_version()

    with _wip_search_index_lock:
        cached = _wip_search_index_cache.get(cache_key)
        if cached and cached.get("version") == version:
            _increment_wip_metric("search_index_hits")
            return cached

    _increment_wip_metric("search_index_misses")
    snapshot = _get_wip_snapshot(include_dummy=include_dummy)
    if snapshot is None:
        return None

    filtered = snapshot["frame"]
    signature_counter, signature_fields = _build_search_signatures(filtered)

    with _wip_search_index_lock:
        previous = _wip_search_index_cache.get(cache_key)

    index_payload = _try_incremental_search_sync(
        previous or {},
        version=version,
        row_count=int(snapshot.get("row_count", 0)),
        signature_counter=signature_counter,
        signature_fields=signature_fields,
    )
    if index_payload is None:
        field_counters = _build_field_counters(signature_counter, signature_fields)
        index_payload = _materialize_search_payload(
            version=version,
            row_count=int(snapshot.get("row_count", 0)),
            signature_counter=signature_counter,
            field_counters=field_counters,
            mode="full",
        )
        _increment_wip_metric("search_index_rebuilds")

    with _wip_search_index_lock:
        _wip_search_index_cache[cache_key] = index_payload
        return index_payload


def _search_values_from_index(values: List[str], query: str, limit: int) -> List[str]:
    query_lower = query.lower()
    matched = [value for value in values if query_lower in value.lower()]
    return matched[:limit]


def get_wip_search_index_status() -> Dict[str, Any]:
    """Expose WIP derived search-index freshness for diagnostics."""
    with _wip_search_index_lock:
        search_snapshot = {}
        for key, payload in _wip_search_index_cache.items():
            search_snapshot[key] = {
                "version": payload.get("version"),
                "built_at": payload.get("built_at"),
                "row_count": payload.get("row_count", 0),
                "workorders": len(payload.get("workorders", [])),
                "lotids": len(payload.get("lotids", [])),
                "packages": len(payload.get("packages", [])),
                "types": len(payload.get("types", [])),
                "firstnames": len(payload.get("firstnames", [])),
                "waferdescs": len(payload.get("waferdescs", [])),
                "sync_mode": payload.get("sync_mode"),
                "sync_added_rows": payload.get("sync_added_rows", 0),
                "sync_removed_rows": payload.get("sync_removed_rows", 0),
                "drift_ratio": payload.get("drift_ratio", 0.0),
                "memory_bytes": payload.get("memory_bytes", 0),
            }
    with _wip_snapshot_lock:
        frame_snapshot = {}
        for key, payload in _wip_snapshot_cache.items():
            frame_snapshot[key] = {
                "version": payload.get("version"),
                "built_at": payload.get("built_at"),
                "row_count": payload.get("row_count", 0),
                "frame_bytes": payload.get("frame_bytes", 0),
                "index_bucket_count": payload.get("index_bucket_count", 0),
            }
    with _wip_index_metrics_lock:
        metrics = dict(_wip_index_metrics)

    total_frame_bytes = sum(item.get("frame_bytes", 0) for item in frame_snapshot.values())
    total_search_bytes = sum(item.get("memory_bytes", 0) for item in search_snapshot.values())
    amplification_ratio = round((total_frame_bytes + total_search_bytes) / max(total_frame_bytes, 1), 4)

    return {
        "derived_search_index": search_snapshot,
        "derived_frame_snapshot": frame_snapshot,
        "metrics": metrics,
        "memory": {
            "frame_bytes_total": int(total_frame_bytes),
            "search_bytes_total": int(total_search_bytes),
            "amplification_ratio": amplification_ratio,
        },
    }


def _add_wip_status_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Add computed WIP status columns to DataFrame.

    Adds columns:
    - WIP_STATUS: 'RUN', 'HOLD', or 'QUEUE'
    - IS_QUALITY_HOLD: True if quality hold
    - IS_NON_QUALITY_HOLD: True if non-quality hold

    Args:
        df: DataFrame with EQUIPMENTCOUNT, CURRENTHOLDCOUNT, HOLDREASONNAME columns

    Returns:
        DataFrame with additional status columns
    """
    required = {'WIP_STATUS', 'IS_QUALITY_HOLD', 'IS_NON_QUALITY_HOLD'}
    if required.issubset(df.columns):
        return df

    working = df.copy()

    # Ensure numeric columns
    working['EQUIPMENTCOUNT'] = pd.to_numeric(working['EQUIPMENTCOUNT'], errors='coerce').fillna(0)
    working['CURRENTHOLDCOUNT'] = pd.to_numeric(working['CURRENTHOLDCOUNT'], errors='coerce').fillna(0)
    working['QTY'] = pd.to_numeric(working['QTY'], errors='coerce').fillna(0)

    # Compute WIP status
    working['WIP_STATUS'] = 'QUEUE'  # Default
    working.loc[working['EQUIPMENTCOUNT'] > 0, 'WIP_STATUS'] = 'RUN'
    working.loc[
        (working['EQUIPMENTCOUNT'] == 0) & (working['CURRENTHOLDCOUNT'] > 0),
        'WIP_STATUS'
    ] = 'HOLD'

    # Compute hold type
    non_quality_flags = working['HOLDREASONNAME'].isin(NON_QUALITY_HOLD_REASONS)
    working['IS_QUALITY_HOLD'] = (working['WIP_STATUS'] == 'HOLD') & ~non_quality_flags
    working['IS_NON_QUALITY_HOLD'] = (working['WIP_STATUS'] == 'HOLD') & non_quality_flags

    return working


def _filter_base_conditions(
    df: pd.DataFrame,
    include_dummy: bool = False,
    workorder: Optional[str] = None,
    lotid: Optional[str] = None
) -> pd.DataFrame:
    """Apply base filter conditions to DataFrame.

    Args:
        df: DataFrame to filter
        include_dummy: If False (default), exclude LOTID containing 'DUMMY'
        workorder: Optional WORKORDER filter (fuzzy match)
        lotid: Optional LOTID filter (fuzzy match)

    Returns:
        Filtered DataFrame
    """
    if df is None or df.empty:
        return df.iloc[0:0] if isinstance(df, pd.DataFrame) else pd.DataFrame()

    mask = _build_filter_mask(
        df,
        include_dummy=include_dummy,
        workorder=workorder,
        lotid=lotid,
    )
    if mask.empty:
        return df.iloc[0:0]
    return df.loc[mask]


# ============================================================
# Overview API Functions
# ============================================================

def get_wip_summary(
    include_dummy: bool = False,
    workorder: Optional[str] = None,
    lotid: Optional[str] = None,
    package: Optional[str] = None,
    pj_type: Optional[str] = None,
    firstname: Optional[str] = None,
    waferdesc: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Get WIP KPI summary for overview dashboard.

    Uses Redis cache when available, falls back to Oracle direct query.

    Args:
        include_dummy: If True, include DUMMY lots (default: False)
        workorder: Optional WORKORDER filter (fuzzy match)
        lotid: Optional LOTID filter (fuzzy match)
        package: Optional PACKAGE_LEF filter (exact match)
        pj_type: Optional PJ_TYPE filter (exact match)
        firstname: Optional FIRSTNAME filter (exact match)
        waferdesc: Optional WAFERDESC filter (exact match)

    Returns:
        Dict with summary stats (camelCase):
        - totalLots: Total number of lots
        - totalQtyPcs: Total quantity
        - byWipStatus: Grouped counts for RUN/QUEUE/HOLD
        - dataUpdateDate: Data timestamp
    """
    # Try cache first
    cached_df = _get_wip_dataframe()
    if cached_df is not None:
        try:
            df = _select_with_snapshot_indexes(
                include_dummy=include_dummy,
                workorder=workorder,
                lotid=lotid,
                package=package,
                pj_type=pj_type,
                firstname=firstname,
                waferdesc=waferdesc,
            )
            if df is None:
                return _get_wip_summary_from_oracle(
                    include_dummy,
                    workorder,
                    lotid,
                    package,
                    pj_type,
                    firstname,
                    waferdesc,
                )

            if df.empty:
                return {
                    'totalLots': 0,
                    'totalQtyPcs': 0,
                    'byWipStatus': {
                        'run': {'lots': 0, 'qtyPcs': 0},
                        'queue': {'lots': 0, 'qtyPcs': 0},
                        'hold': {'lots': 0, 'qtyPcs': 0},
                        'qualityHold': {'lots': 0, 'qtyPcs': 0},
                        'nonQualityHold': {'lots': 0, 'qtyPcs': 0}
                    },
                    'dataUpdateDate': get_cached_sys_date()
                }

            # Calculate summary from cached data
            run_df = df[df['WIP_STATUS'] == 'RUN']
            queue_df = df[df['WIP_STATUS'] == 'QUEUE']
            hold_df = df[df['WIP_STATUS'] == 'HOLD']
            quality_hold_df = df[df['IS_QUALITY_HOLD']]
            non_quality_hold_df = df[df['IS_NON_QUALITY_HOLD']]

            return {
                'totalLots': len(df),
                'totalQtyPcs': int(df['QTY'].sum()),
                'byWipStatus': {
                    'run': {
                        'lots': len(run_df),
                        'qtyPcs': int(run_df['QTY'].sum())
                    },
                    'queue': {
                        'lots': len(queue_df),
                        'qtyPcs': int(queue_df['QTY'].sum())
                    },
                    'hold': {
                        'lots': len(hold_df),
                        'qtyPcs': int(hold_df['QTY'].sum())
                    },
                    'qualityHold': {
                        'lots': len(quality_hold_df),
                        'qtyPcs': int(quality_hold_df['QTY'].sum())
                    },
                    'nonQualityHold': {
                        'lots': len(non_quality_hold_df),
                        'qtyPcs': int(non_quality_hold_df['QTY'].sum())
                    }
                },
                'dataUpdateDate': get_cached_sys_date()
            }
        except (DatabasePoolExhaustedError, DatabaseCircuitOpenError):
            raise
        except Exception as exc:
            logger.warning(f"Cache-based summary calculation failed, falling back to Oracle: {exc}")

    # Fallback to Oracle direct query
    return _get_wip_summary_from_oracle(
        include_dummy,
        workorder,
        lotid,
        package,
        pj_type,
        firstname,
        waferdesc,
    )


def _get_wip_summary_from_oracle(
    include_dummy: bool = False,
    workorder: Optional[str] = None,
    lotid: Optional[str] = None,
    package: Optional[str] = None,
    pj_type: Optional[str] = None,
    firstname: Optional[str] = None,
    waferdesc: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Get WIP summary directly from Oracle (fallback)."""
    try:
        # Build conditions using QueryBuilder
        builder = _build_base_conditions_builder(include_dummy, workorder, lotid)

        _add_exact_filter_conditions(builder, "PACKAGE_LEF", package)
        _add_exact_filter_conditions(builder, "PJ_TYPE", pj_type)
        _add_exact_filter_conditions(builder, "FIRSTNAME", firstname)
        _add_exact_filter_conditions(builder, "WAFERDESC", waferdesc)

        # Load SQL template and build query
        base_sql = SQLLoader.load("wip/summary")
        builder.base_sql = base_sql

        # Replace NON_QUALITY_REASONS placeholder (must be literal values for CASE expressions)
        non_quality_list = CommonFilters.get_non_quality_reasons_sql()
        builder.base_sql = builder.base_sql.replace("{{ NON_QUALITY_REASONS }}", non_quality_list)

        sql, params = builder.build()
        df = read_sql_df(sql, params)

        if df is None or df.empty:
            return None

        row = df.iloc[0]
        return {
            'totalLots': int(row['TOTAL_LOTS'] or 0),
            'totalQtyPcs': int(row['TOTAL_QTY_PCS'] or 0),
            'byWipStatus': {
                'run': {
                    'lots': int(row['RUN_LOTS'] or 0),
                    'qtyPcs': int(row['RUN_QTY_PCS'] or 0)
                },
                'queue': {
                    'lots': int(row['QUEUE_LOTS'] or 0),
                    'qtyPcs': int(row['QUEUE_QTY_PCS'] or 0)
                },
                'hold': {
                    'lots': int(row['HOLD_LOTS'] or 0),
                    'qtyPcs': int(row['HOLD_QTY_PCS'] or 0)
                },
                'qualityHold': {
                    'lots': int(row['QUALITY_HOLD_LOTS'] or 0),
                    'qtyPcs': int(row['QUALITY_HOLD_QTY_PCS'] or 0)
                },
                'nonQualityHold': {
                    'lots': int(row['NON_QUALITY_HOLD_LOTS'] or 0),
                    'qtyPcs': int(row['NON_QUALITY_HOLD_QTY_PCS'] or 0)
                }
            },
            'dataUpdateDate': str(row['DATA_UPDATE_DATE']) if row['DATA_UPDATE_DATE'] else None
        }
    except (DatabasePoolExhaustedError, DatabaseCircuitOpenError):
        raise
    except Exception as exc:
        logger.error(f"WIP summary query failed: {exc}")
        return None


def get_wip_matrix(
    include_dummy: bool = False,
    workorder: Optional[str] = None,
    lotid: Optional[str] = None,
    status: Optional[str] = None,
    hold_type: Optional[str] = None,
    reason: Optional[str] = None,
    package: Optional[str] = None,
    pj_type: Optional[str] = None,
    firstname: Optional[str] = None,
    waferdesc: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Get workcenter x product line matrix for overview dashboard.

    Uses Redis cache when available, falls back to Oracle direct query.

    Args:
        include_dummy: If True, include DUMMY lots (default: False)
        workorder: Optional WORKORDER filter (fuzzy match)
        lotid: Optional LOTID filter (fuzzy match)
        status: Optional WIP status filter ('RUN', 'QUEUE', 'HOLD')
        hold_type: Optional hold type filter ('quality', 'non-quality')
                   Only effective when status='HOLD'
        reason: Optional HOLDREASONNAME filter
                Only effective when status='HOLD'
        package: Optional PACKAGE_LEF filter (exact match)
        pj_type: Optional PJ_TYPE filter (exact match)
        firstname: Optional FIRSTNAME filter (exact match)
        waferdesc: Optional WAFERDESC filter (exact match)

    Returns:
        Dict with matrix data:
        - workcenters: List of workcenter groups (sorted by WORKCENTERSEQUENCE_GROUP)
        - packages: List of product lines (sorted by total QTY desc)
        - matrix: Dict of {workcenter: {package: qty}}
        - workcenter_totals: Dict of {workcenter: total_qty}
        - package_totals: Dict of {package: total_qty}
        - grand_total: Overall total
    """
    # Try cache first
    cached_df = _get_wip_dataframe()
    if cached_df is not None:
        try:
            status_upper = status.upper() if status else None
            hold_type_filter = hold_type if status_upper == 'HOLD' else None
            reason_filter = reason if status_upper == 'HOLD' else None
            df = _select_with_snapshot_indexes(
                include_dummy=include_dummy,
                workorder=workorder,
                lotid=lotid,
                package=package,
                pj_type=pj_type,
                firstname=firstname,
                waferdesc=waferdesc,
                status=status_upper,
                hold_type=hold_type_filter,
            )
            if df is None:
                return _get_wip_matrix_from_oracle(
                    include_dummy,
                    workorder,
                    lotid,
                    status,
                    hold_type,
                    reason,
                    package,
                    pj_type,
                    firstname,
                    waferdesc,
                )

            if reason_filter:
                if isinstance(reason_filter, (list, tuple)):
                    df = df[df['HOLDREASONNAME'].isin(reason_filter)]
                else:
                    df = df[df['HOLDREASONNAME'] == reason_filter]

            # Filter by WORKCENTER_GROUP and PACKAGE_LEF
            df = df[df['WORKCENTER_GROUP'].notna() & df['PACKAGE_LEF'].notna()]

            if df.empty:
                return {
                    'workcenters': [],
                    'packages': [],
                    'matrix': {},
                    'workcenter_totals': {},
                    'package_totals': {},
                    'grand_total': 0
                }

            return _build_matrix_result(df)
        except (DatabasePoolExhaustedError, DatabaseCircuitOpenError):
            raise
        except Exception as exc:
            logger.warning(f"Cache-based matrix calculation failed, falling back to Oracle: {exc}")

    # Fallback to Oracle direct query
    return _get_wip_matrix_from_oracle(
        include_dummy,
        workorder,
        lotid,
        status,
        hold_type,
        reason,
        package,
        pj_type,
        firstname,
        waferdesc,
    )


def _build_matrix_result(df: pd.DataFrame) -> Dict[str, Any]:
    """Build matrix result from DataFrame."""
    # Group by workcenter and package
    grouped = df.groupby(['WORKCENTER_GROUP', 'WORKCENTERSEQUENCE_GROUP', 'PACKAGE_LEF'])['QTY'].sum().reset_index()

    if grouped.empty:
        return {
            'workcenters': [],
            'packages': [],
            'matrix': {},
            'workcenter_totals': {},
            'package_totals': {},
            'grand_total': 0
        }

    # Build matrix
    matrix = {}
    workcenter_totals = {}
    package_totals = {}

    # Get unique workcenters sorted by sequence
    wc_order = grouped.drop_duplicates('WORKCENTER_GROUP')[['WORKCENTER_GROUP', 'WORKCENTERSEQUENCE_GROUP']]
    wc_order = wc_order.sort_values('WORKCENTERSEQUENCE_GROUP')
    workcenters = wc_order['WORKCENTER_GROUP'].tolist()

    # Build matrix and totals
    for _, row in grouped.iterrows():
        wc = row['WORKCENTER_GROUP']
        pkg = row['PACKAGE_LEF']
        qty = int(row['QTY'] or 0)

        if wc not in matrix:
            matrix[wc] = {}
        matrix[wc][pkg] = qty

        workcenter_totals[wc] = workcenter_totals.get(wc, 0) + qty
        package_totals[pkg] = package_totals.get(pkg, 0) + qty

    # Sort packages by total qty desc
    packages = sorted(package_totals.keys(), key=lambda x: package_totals[x], reverse=True)

    grand_total = sum(workcenter_totals.values())

    return {
        'workcenters': workcenters,
        'packages': packages,
        'matrix': matrix,
        'workcenter_totals': workcenter_totals,
        'package_totals': package_totals,
        'grand_total': grand_total
    }


def _get_wip_matrix_from_oracle(
    include_dummy: bool = False,
    workorder: Optional[str] = None,
    lotid: Optional[str] = None,
    status: Optional[str] = None,
    hold_type: Optional[str] = None,
    reason: Optional[str] = None,
    package: Optional[str] = None,
    pj_type: Optional[str] = None,
    firstname: Optional[str] = None,
    waferdesc: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Get WIP matrix directly from Oracle (fallback)."""
    try:
        # Build conditions using QueryBuilder
        builder = _build_base_conditions_builder(include_dummy, workorder, lotid)
        builder.add_is_not_null("WORKCENTER_GROUP")
        builder.add_is_not_null("PACKAGE_LEF")

        _add_exact_filter_conditions(builder, "PACKAGE_LEF", package)
        _add_exact_filter_conditions(builder, "PJ_TYPE", pj_type)
        _add_exact_filter_conditions(builder, "FIRSTNAME", firstname)
        _add_exact_filter_conditions(builder, "WAFERDESC", waferdesc)

        # WIP status filter
        if status:
            status_upper = status.upper()
            if status_upper == 'RUN':
                builder.add_condition("COALESCE(EQUIPMENTCOUNT, 0) > 0")
            elif status_upper == 'HOLD':
                builder.add_condition("COALESCE(EQUIPMENTCOUNT, 0) = 0 AND COALESCE(CURRENTHOLDCOUNT, 0) > 0")
                # Hold type sub-filter
                if hold_type:
                    _add_hold_type_conditions(builder, hold_type)
                if reason:
                    builder.add_param_condition("HOLDREASONNAME", reason)
            elif status_upper == 'QUEUE':
                builder.add_condition("COALESCE(EQUIPMENTCOUNT, 0) = 0 AND COALESCE(CURRENTHOLDCOUNT, 0) = 0")

        # Load SQL template and build query
        base_sql = SQLLoader.load("wip/matrix")
        builder.base_sql = base_sql
        sql, params = builder.build()

        df = read_sql_df(sql, params)

        if df is None or df.empty:
            return {
                'workcenters': [],
                'packages': [],
                'matrix': {},
                'workcenter_totals': {},
                'package_totals': {},
                'grand_total': 0
            }

        return _build_matrix_result(df)
    except (DatabasePoolExhaustedError, DatabaseCircuitOpenError):
        raise
    except Exception as exc:
        logger.error(f"WIP matrix query failed: {exc}")
        import traceback
        traceback.print_exc()
        return None


def get_wip_hold_summary(
    include_dummy: bool = False,
    workorder: Optional[str] = None,
    lotid: Optional[str] = None,
    package: Optional[str] = None,
    pj_type: Optional[str] = None,
    firstname: Optional[str] = None,
    waferdesc: Optional[str] = None,
    workcenter: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Get hold summary grouped by hold reason.

    Uses Redis cache when available, falls back to Oracle direct query.

    Args:
        include_dummy: If True, include DUMMY lots (default: False)
        workorder: Optional WORKORDER filter (fuzzy match)
        lotid: Optional LOTID filter (fuzzy match)
        package: Optional PACKAGE_LEF filter (exact match)
        pj_type: Optional PJ_TYPE filter (exact match)
        firstname: Optional FIRSTNAME filter (exact match)
        waferdesc: Optional WAFERDESC filter (exact match)
        workcenter: Optional WORKCENTER_GROUP filter (exact match)

    Returns:
        Dict with hold items sorted by lots desc:
        - items: List of {reason, lots, qty}
    """
    # Try cache first
    cached_df = _get_wip_dataframe()
    if cached_df is not None:
        try:
            df = _select_with_snapshot_indexes(
                include_dummy=include_dummy,
                workorder=workorder,
                lotid=lotid,
                package=package,
                pj_type=pj_type,
                firstname=firstname,
                waferdesc=waferdesc,
                workcenter=workcenter,
                status='HOLD',
            )
            if df is None:
                return _get_wip_hold_summary_from_oracle(
                    include_dummy,
                    workorder,
                    lotid,
                    package,
                    pj_type,
                    firstname,
                    waferdesc,
                    workcenter,
                )

            # Filter for HOLD status with reason
            df = df[df['HOLDREASONNAME'].notna()]

            if df.empty:
                return {'items': []}

            # Group by hold reason
            grouped = df.groupby('HOLDREASONNAME').agg({
                'LOTID': 'count',
                'QTY': 'sum'
            }).reset_index()
            grouped.columns = ['REASON', 'LOTS', 'QTY']
            grouped = grouped.sort_values('LOTS', ascending=False)

            items = []
            for _, row in grouped.iterrows():
                reason = row['REASON']
                items.append({
                    'reason': reason,
                    'lots': int(row['LOTS'] or 0),
                    'qty': int(row['QTY'] or 0),
                    'holdType': 'quality' if is_quality_hold(reason) else 'non-quality'
                })

            return {'items': items}
        except (DatabasePoolExhaustedError, DatabaseCircuitOpenError):
            raise
        except Exception as exc:
            logger.warning(f"Cache-based hold summary calculation failed, falling back to Oracle: {exc}")

    # Fallback to Oracle direct query
    return _get_wip_hold_summary_from_oracle(
        include_dummy,
        workorder,
        lotid,
        package,
        pj_type,
        firstname,
        waferdesc,
        workcenter,
    )


def _get_wip_hold_summary_from_oracle(
    include_dummy: bool = False,
    workorder: Optional[str] = None,
    lotid: Optional[str] = None,
    package: Optional[str] = None,
    pj_type: Optional[str] = None,
    firstname: Optional[str] = None,
    waferdesc: Optional[str] = None,
    workcenter: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Get WIP hold summary directly from Oracle (fallback)."""
    try:
        # Build conditions using QueryBuilder
        builder = _build_base_conditions_builder(include_dummy, workorder, lotid)
        builder.add_param_condition("STATUS", "HOLD")
        builder.add_is_not_null("HOLDREASONNAME")
        _add_exact_filter_conditions(builder, "PACKAGE_LEF", package)
        _add_exact_filter_conditions(builder, "PJ_TYPE", pj_type)
        _add_exact_filter_conditions(builder, "FIRSTNAME", firstname)
        _add_exact_filter_conditions(builder, "WAFERDESC", waferdesc)
        _add_exact_filter_conditions(builder, "WORKCENTER_GROUP", workcenter)

        where_clause, params = builder.build_where_only()

        sql = f"""
            SELECT
                HOLDREASONNAME as REASON,
                COUNT(*) as LOTS,
                SUM(QTY) as QTY
            FROM {WIP_VIEW}
            {where_clause}
            GROUP BY HOLDREASONNAME
            ORDER BY COUNT(*) DESC
        """
        df = read_sql_df(sql, params)

        if df is None or df.empty:
            return {'items': []}

        items = []
        for _, row in df.iterrows():
            reason = row['REASON']
            items.append({
                'reason': reason,
                'lots': int(row['LOTS'] or 0),
                'qty': int(row['QTY'] or 0),
                'holdType': 'quality' if is_quality_hold(reason) else 'non-quality'
            })

        return {'items': items}
    except (DatabasePoolExhaustedError, DatabaseCircuitOpenError):
        raise
    except Exception as exc:
        logger.error(f"WIP hold summary query failed: {exc}")
        return None


# ============================================================
# Detail API Functions
# ============================================================

def get_wip_detail(
    workcenter: str,
    package: Optional[str] = None,
    pj_type: Optional[str] = None,
    firstname: Optional[str] = None,
    waferdesc: Optional[str] = None,
    status: Optional[str] = None,
    hold_type: Optional[str] = None,
    workorder: Optional[str] = None,
    lotid: Optional[str] = None,
    include_dummy: bool = False,
    page: int = 1,
    page_size: int = 100
) -> Optional[Dict[str, Any]]:
    """Get WIP detail for a specific workcenter group.

    Uses Redis cache when available, falls back to Oracle direct query.

    Args:
        workcenter: WORKCENTER_GROUP name
        package: Optional PACKAGE_LEF filter
        pj_type: Optional PJ_TYPE filter (exact match)
        firstname: Optional FIRSTNAME filter (exact match)
        waferdesc: Optional WAFERDESC filter (exact match)
        status: Optional WIP status filter ('RUN', 'QUEUE', 'HOLD')
        hold_type: Optional hold type filter ('quality', 'non-quality')
                   Only effective when status='HOLD'
        workorder: Optional WORKORDER filter (fuzzy match)
        lotid: Optional LOTID filter (fuzzy match)
        include_dummy: If True, include DUMMY lots (default: False)
        page: Page number (1-based)
        page_size: Number of records per page

    Returns:
        Dict with:
        - workcenter: The workcenter group name
        - summary: {totalLots, runLots, queueLots, holdLots, qualityHoldLots, nonQualityHoldLots}
        - specs: List of spec names (sorted by SPECSEQUENCE)
        - lots: List of lot details
        - pagination: {page, page_size, total_count, total_pages}
        - sys_date: Data timestamp
    """
    # Try cache first
    cached_df = _get_wip_dataframe()
    if cached_df is not None:
        try:
            summary_df = _select_with_snapshot_indexes(
                include_dummy=include_dummy,
                workorder=workorder,
                lotid=lotid,
                package=package,
                pj_type=pj_type,
                firstname=firstname,
                waferdesc=waferdesc,
                workcenter=workcenter,
            )
            if summary_df is None:
                return _get_wip_detail_from_oracle(
                    workcenter,
                    package,
                    pj_type,
                    firstname,
                    waferdesc,
                    status,
                    hold_type,
                    workorder,
                    lotid,
                    include_dummy,
                    page,
                    page_size,
                )

            if summary_df.empty:
                summary = {
                    'totalLots': 0,
                    'runLots': 0,
                    'queueLots': 0,
                    'holdLots': 0,
                    'qualityHoldLots': 0,
                    'nonQualityHoldLots': 0
                }
                df = summary_df
            else:
                df = summary_df

            # Calculate summary before status filter
            run_lots = len(summary_df[summary_df['WIP_STATUS'] == 'RUN'])
            queue_lots = len(summary_df[summary_df['WIP_STATUS'] == 'QUEUE'])
            hold_lots = len(summary_df[summary_df['WIP_STATUS'] == 'HOLD'])
            quality_hold_lots = len(summary_df[summary_df['IS_QUALITY_HOLD']])
            non_quality_hold_lots = len(summary_df[summary_df['IS_NON_QUALITY_HOLD']])
            total_lots = len(summary_df)

            summary = {
                'totalLots': total_lots,
                'runLots': run_lots,
                'queueLots': queue_lots,
                'holdLots': hold_lots,
                'qualityHoldLots': quality_hold_lots,
                'nonQualityHoldLots': non_quality_hold_lots
            }

            # Apply status filter for lots list
            if status:
                status_upper = status.upper()
                hold_type_filter = hold_type if status_upper == 'HOLD' else None
                filtered_df = _select_with_snapshot_indexes(
                    include_dummy=include_dummy,
                    workorder=workorder,
                    lotid=lotid,
                    package=package,
                    pj_type=pj_type,
                    firstname=firstname,
                    waferdesc=waferdesc,
                    workcenter=workcenter,
                    status=status_upper,
                    hold_type=hold_type_filter,
                )
                if filtered_df is None:
                    return _get_wip_detail_from_oracle(
                        workcenter,
                        package,
                        pj_type,
                        firstname,
                        waferdesc,
                        status,
                        hold_type,
                        workorder,
                        lotid,
                        include_dummy,
                        page,
                        page_size,
                    )
                df = filtered_df

            # Get specs (sorted by SPECSEQUENCE if available)
            specs_df = df[df['SPECNAME'].notna()][['SPECNAME', 'SPECSEQUENCE']].drop_duplicates()
            if 'SPECSEQUENCE' in specs_df.columns:
                specs_df = specs_df.sort_values('SPECSEQUENCE')
            specs = specs_df['SPECNAME'].tolist() if not specs_df.empty else []

            # Pagination
            filtered_count = len(df)
            total_pages = (filtered_count + page_size - 1) // page_size if filtered_count > 0 else 1
            offset = (page - 1) * page_size

            # Sort by LOTID and paginate
            df = df.sort_values('LOTID')
            page_df = df.iloc[offset:offset + page_size]

            lots = []
            for _, row in page_df.iterrows():
                lots.append({
                    'lotId': _safe_value(row.get('LOTID')),
                    'equipment': _safe_value(row.get('EQUIPMENTS')),
                    'wipStatus': _safe_value(row.get('WIP_STATUS')),
                    'holdReason': _safe_value(row.get('HOLDREASONNAME')),
                    'qty': int(row.get('QTY', 0) or 0),
                    'package': _safe_value(row.get('PACKAGE_LEF')),
                    'spec': _safe_value(row.get('SPECNAME'))
                })

            return {
                'workcenter': workcenter,
                'summary': summary,
                'specs': specs,
                'lots': lots,
                'pagination': {
                    'page': page,
                    'page_size': page_size,
                    'total_count': filtered_count,
                    'total_pages': total_pages
                },
                'sys_date': get_cached_sys_date()
            }
        except (DatabasePoolExhaustedError, DatabaseCircuitOpenError):
            raise
        except Exception as exc:
            logger.warning(f"Cache-based detail calculation failed, falling back to Oracle: {exc}")

    # Fallback to Oracle direct query
    return _get_wip_detail_from_oracle(
        workcenter,
        package,
        pj_type,
        firstname,
        waferdesc,
        status,
        hold_type,
        workorder,
        lotid,
        include_dummy,
        page,
        page_size,
    )


def _get_wip_detail_from_oracle(
    workcenter: str,
    package: Optional[str] = None,
    pj_type: Optional[str] = None,
    firstname: Optional[str] = None,
    waferdesc: Optional[str] = None,
    status: Optional[str] = None,
    hold_type: Optional[str] = None,
    workorder: Optional[str] = None,
    lotid: Optional[str] = None,
    include_dummy: bool = False,
    page: int = 1,
    page_size: int = 100
) -> Optional[Dict[str, Any]]:
    """Get WIP detail directly from Oracle (fallback)."""
    try:
        # Build WHERE conditions using QueryBuilder
        builder = _build_base_conditions_builder(include_dummy, workorder, lotid)
        builder.add_param_condition("WORKCENTER_GROUP", workcenter)

        _add_exact_filter_conditions(builder, "PACKAGE_LEF", package)
        _add_exact_filter_conditions(builder, "PJ_TYPE", pj_type)
        _add_exact_filter_conditions(builder, "FIRSTNAME", firstname)
        _add_exact_filter_conditions(builder, "WAFERDESC", waferdesc)

        # WIP status filter (RUN/QUEUE/HOLD based on EQUIPMENTCOUNT and CURRENTHOLDCOUNT)
        if status:
            status_upper = status.upper()
            if status_upper == 'RUN':
                builder.add_condition("COALESCE(EQUIPMENTCOUNT, 0) > 0")
            elif status_upper == 'HOLD':
                builder.add_condition("COALESCE(EQUIPMENTCOUNT, 0) = 0 AND COALESCE(CURRENTHOLDCOUNT, 0) > 0")
                # Hold type sub-filter
                if hold_type:
                    _add_hold_type_conditions(builder, hold_type)
            elif status_upper == 'QUEUE':
                builder.add_condition("COALESCE(EQUIPMENTCOUNT, 0) = 0 AND COALESCE(CURRENTHOLDCOUNT, 0) = 0")

        where_clause, params = builder.build_where_only()

        # Build summary conditions (without status/hold_type filter for full breakdown)
        summary_builder = _build_base_conditions_builder(include_dummy, workorder, lotid)
        summary_builder.add_param_condition("WORKCENTER_GROUP", workcenter)
        _add_exact_filter_conditions(summary_builder, "PACKAGE_LEF", package)
        _add_exact_filter_conditions(summary_builder, "PJ_TYPE", pj_type)
        _add_exact_filter_conditions(summary_builder, "FIRSTNAME", firstname)
        _add_exact_filter_conditions(summary_builder, "WAFERDESC", waferdesc)

        summary_where, summary_params = summary_builder.build_where_only()
        non_quality_list = CommonFilters.get_non_quality_reasons_sql()

        summary_sql = f"""
            SELECT
                COUNT(*) as TOTAL_LOTS,
                SUM(CASE WHEN COALESCE(EQUIPMENTCOUNT, 0) > 0 THEN 1 ELSE 0 END) as RUN_LOTS,
                SUM(CASE WHEN COALESCE(EQUIPMENTCOUNT, 0) = 0
                          AND COALESCE(CURRENTHOLDCOUNT, 0) = 0 THEN 1 ELSE 0 END) as QUEUE_LOTS,
                SUM(CASE WHEN COALESCE(EQUIPMENTCOUNT, 0) = 0
                          AND COALESCE(CURRENTHOLDCOUNT, 0) > 0 THEN 1 ELSE 0 END) as HOLD_LOTS,
                SUM(CASE WHEN COALESCE(EQUIPMENTCOUNT, 0) = 0
                          AND COALESCE(CURRENTHOLDCOUNT, 0) > 0
                          AND (HOLDREASONNAME IS NULL OR HOLDREASONNAME NOT IN ({non_quality_list}))
                          THEN 1 ELSE 0 END) as QUALITY_HOLD_LOTS,
                SUM(CASE WHEN COALESCE(EQUIPMENTCOUNT, 0) = 0
                          AND COALESCE(CURRENTHOLDCOUNT, 0) > 0
                          AND HOLDREASONNAME IN ({non_quality_list})
                          THEN 1 ELSE 0 END) as NON_QUALITY_HOLD_LOTS,
                MAX(SYS_DATE) as SYS_DATE
            FROM {WIP_VIEW}
            {summary_where}
        """

        summary_df = read_sql_df(summary_sql, summary_params)

        if summary_df is None or summary_df.empty:
            return None

        summary_row = summary_df.iloc[0]
        sys_date = str(summary_row['SYS_DATE']) if summary_row['SYS_DATE'] else None

        # Calculate counts from summary
        total_lots = int(summary_row['TOTAL_LOTS'] or 0)
        run_lots = int(summary_row['RUN_LOTS'] or 0)
        queue_lots = int(summary_row['QUEUE_LOTS'] or 0)
        hold_lots = int(summary_row['HOLD_LOTS'] or 0)
        quality_hold_lots = int(summary_row['QUALITY_HOLD_LOTS'] or 0)
        non_quality_hold_lots = int(summary_row['NON_QUALITY_HOLD_LOTS'] or 0)

        # Determine filtered count based on status filter
        if status:
            status_upper = status.upper()
            if status_upper == 'RUN':
                filtered_count = run_lots
            elif status_upper == 'QUEUE':
                filtered_count = queue_lots
            elif status_upper == 'HOLD':
                if hold_type == 'quality':
                    filtered_count = quality_hold_lots
                elif hold_type == 'non-quality':
                    filtered_count = non_quality_hold_lots
                else:
                    filtered_count = hold_lots
            else:
                filtered_count = total_lots
        else:
            filtered_count = total_lots

        summary = {
            'totalLots': total_lots,
            'runLots': run_lots,
            'queueLots': queue_lots,
            'holdLots': hold_lots,
            'qualityHoldLots': quality_hold_lots,
            'nonQualityHoldLots': non_quality_hold_lots
        }

        # Get unique specs for this workcenter (sorted by SPECSEQUENCE)
        specs_sql = f"""
            SELECT DISTINCT SPECNAME, SPECSEQUENCE
            FROM {WIP_VIEW}
            {where_clause}
              AND SPECNAME IS NOT NULL
            ORDER BY SPECSEQUENCE
        """

        specs_df = read_sql_df(specs_sql, params)
        specs = specs_df['SPECNAME'].tolist() if specs_df is not None and not specs_df.empty else []

        # Get paginated lot details using SQL file with bind variables
        offset = (page - 1) * page_size
        base_detail_sql = SQLLoader.load("wip/detail")
        detail_sql = base_detail_sql.replace("{{ WHERE_CLAUSE }}", where_clause)

        # Add pagination params to existing params
        detail_params = params.copy()
        detail_params['offset'] = offset
        detail_params['limit'] = page_size

        lots_df = read_sql_df(detail_sql, detail_params)

        lots = []
        if lots_df is not None and not lots_df.empty:
            for _, row in lots_df.iterrows():
                lots.append({
                    'lotId': _safe_value(row['LOTID']),
                    'equipment': _safe_value(row['EQUIPMENTS']),
                    'wipStatus': _safe_value(row['WIP_STATUS']),
                    'holdReason': _safe_value(row['HOLDREASONNAME']),
                    'qty': int(row['QTY'] or 0),
                    'package': _safe_value(row['PACKAGE_LEF']),
                    'spec': _safe_value(row['SPECNAME'])
                })

        total_pages = (filtered_count + page_size - 1) // page_size if filtered_count > 0 else 1

        return {
            'workcenter': workcenter,
            'summary': summary,
            'specs': specs,
            'lots': lots,
            'pagination': {
                'page': page,
                'page_size': page_size,
                'total_count': filtered_count,
                'total_pages': total_pages
            },
            'sys_date': sys_date
        }
    except (DatabasePoolExhaustedError, DatabaseCircuitOpenError):
        raise
    except Exception as exc:
        logger.error(f"WIP detail query failed: {exc}")
        import traceback
        traceback.print_exc()
        return None


# ============================================================
# Meta API Functions
# ============================================================

def get_workcenters(include_dummy: bool = False) -> Optional[List[Dict[str, Any]]]:
    """Get list of workcenter groups with lot counts.

    Uses Redis cache when available, falls back to Oracle direct query.

    Args:
        include_dummy: If True, include DUMMY lots (default: False)

    Returns:
        List of {name, lot_count} sorted by WORKCENTERSEQUENCE_GROUP
    """
    # Try cache first
    cached_df = _get_wip_dataframe()
    if cached_df is not None:
        try:
            df = _select_with_snapshot_indexes(include_dummy=include_dummy)
            if df is None:
                return _get_workcenters_from_oracle(include_dummy)
            df = df[df['WORKCENTER_GROUP'].notna()]

            if df.empty:
                return []

            # Group by workcenter with sequence
            grouped = df.groupby(['WORKCENTER_GROUP', 'WORKCENTERSEQUENCE_GROUP']).size().reset_index(name='LOT_COUNT')
            grouped = grouped.sort_values('WORKCENTERSEQUENCE_GROUP')

            result = []
            for _, row in grouped.iterrows():
                result.append({
                    'name': row['WORKCENTER_GROUP'],
                    'lot_count': int(row['LOT_COUNT'] or 0)
                })

            return result
        except (DatabasePoolExhaustedError, DatabaseCircuitOpenError):
            raise
        except Exception as exc:
            logger.warning(f"Cache-based workcenters calculation failed, falling back to Oracle: {exc}")

    # Fallback to Oracle direct query
    return _get_workcenters_from_oracle(include_dummy)


def _get_workcenters_from_oracle(include_dummy: bool = False) -> Optional[List[Dict[str, Any]]]:
    """Get workcenters directly from Oracle (fallback)."""
    try:
        builder = _build_base_conditions_builder(include_dummy)
        builder.add_is_not_null("WORKCENTER_GROUP")
        where_clause, params = builder.build_where_only()

        sql = f"""
            SELECT
                WORKCENTER_GROUP,
                WORKCENTERSEQUENCE_GROUP,
                COUNT(*) as LOT_COUNT
            FROM {WIP_VIEW}
            {where_clause}
            GROUP BY WORKCENTER_GROUP, WORKCENTERSEQUENCE_GROUP
            ORDER BY WORKCENTERSEQUENCE_GROUP
        """
        df = read_sql_df(sql, params)

        if df is None or df.empty:
            return []

        result = []
        for _, row in df.iterrows():
            result.append({
                'name': row['WORKCENTER_GROUP'],
                'lot_count': int(row['LOT_COUNT'] or 0)
            })

        return result
    except (DatabasePoolExhaustedError, DatabaseCircuitOpenError):
        raise
    except Exception as exc:
        logger.error(f"Workcenters query failed: {exc}")
        return None


def get_packages(include_dummy: bool = False) -> Optional[List[Dict[str, Any]]]:
    """Get list of packages (product lines) with lot counts.

    Uses Redis cache when available, falls back to Oracle direct query.

    Args:
        include_dummy: If True, include DUMMY lots (default: False)

    Returns:
        List of {name, lot_count} sorted by lot_count desc
    """
    # Try cache first
    cached_df = _get_wip_dataframe()
    if cached_df is not None:
        try:
            df = _select_with_snapshot_indexes(include_dummy=include_dummy)
            if df is None:
                return _get_packages_from_oracle(include_dummy)
            df = df[df['PACKAGE_LEF'].notna()]

            if df.empty:
                return []

            # Group by package and count
            grouped = df.groupby('PACKAGE_LEF').size().reset_index(name='LOT_COUNT')
            grouped = grouped.sort_values('LOT_COUNT', ascending=False)

            result = []
            for _, row in grouped.iterrows():
                result.append({
                    'name': row['PACKAGE_LEF'],
                    'lot_count': int(row['LOT_COUNT'] or 0)
                })

            return result
        except (DatabasePoolExhaustedError, DatabaseCircuitOpenError):
            raise
        except Exception as exc:
            logger.warning(f"Cache-based packages calculation failed, falling back to Oracle: {exc}")

    # Fallback to Oracle direct query
    return _get_packages_from_oracle(include_dummy)


def _get_packages_from_oracle(include_dummy: bool = False) -> Optional[List[Dict[str, Any]]]:
    """Get packages directly from Oracle (fallback)."""
    try:
        builder = _build_base_conditions_builder(include_dummy)
        builder.add_is_not_null("PACKAGE_LEF")
        where_clause, params = builder.build_where_only()

        sql = f"""
            SELECT
                PACKAGE_LEF,
                COUNT(*) as LOT_COUNT
            FROM {WIP_VIEW}
            {where_clause}
            GROUP BY PACKAGE_LEF
            ORDER BY COUNT(*) DESC
        """
        df = read_sql_df(sql, params)

        if df is None or df.empty:
            return []

        result = []
        for _, row in df.iterrows():
            result.append({
                'name': row['PACKAGE_LEF'],
                'lot_count': int(row['LOT_COUNT'] or 0)
            })

        return result
    except (DatabasePoolExhaustedError, DatabaseCircuitOpenError):
        raise
    except Exception as exc:
        logger.error(f"Packages query failed: {exc}")
        return None


def _distinct_non_empty_values(df: pd.DataFrame, column: str) -> List[str]:
    if df is None or df.empty or column not in df.columns:
        return []
    values = (
        df[column]
        .map(_normalize_text_value)
        .tolist()
    )
    return sorted({value for value in values if value})


def _build_filter_options_payload(df: pd.DataFrame) -> Dict[str, List[str]]:
    return {
        "workorders": _distinct_non_empty_values(df, "WORKORDER"),
        "lotids": _distinct_non_empty_values(df, "LOTID"),
        "packages": _distinct_non_empty_values(df, "PACKAGE_LEF"),
        "types": _distinct_non_empty_values(df, "PJ_TYPE"),
        "firstnames": _distinct_non_empty_values(df, "FIRSTNAME"),
        "waferdescs": _distinct_non_empty_values(df, "WAFERDESC"),
    }


def _query_distinct_values_from_oracle(
    column: str,
    include_dummy: bool = False,
    workorder: Optional[str] = None,
    lotid: Optional[str] = None,
    package: Optional[str] = None,
    pj_type: Optional[str] = None,
    firstname: Optional[str] = None,
    waferdesc: Optional[str] = None,
    exclude_field: Optional[str] = None,
) -> Optional[List[str]]:
    try:
        builder = _build_base_conditions_builder(
            include_dummy=include_dummy,
            workorder=None if exclude_field == "workorder" else workorder,
            lotid=None if exclude_field == "lotid" else lotid,
        )
        builder.add_is_not_null(column)
        if exclude_field != "package":
            _add_exact_filter_conditions(builder, "PACKAGE_LEF", package)
        if exclude_field != "pj_type":
            _add_exact_filter_conditions(builder, "PJ_TYPE", pj_type)
        if exclude_field != "firstname":
            _add_exact_filter_conditions(builder, "FIRSTNAME", firstname)
        if exclude_field != "waferdesc":
            _add_exact_filter_conditions(builder, "WAFERDESC", waferdesc)
        where_clause, params = builder.build_where_only()
        sql = f"""
            SELECT DISTINCT {column}
            FROM {WIP_VIEW}
            {where_clause}
            ORDER BY {column}
        """
        df = read_sql_df(sql, params)
        if df is None or df.empty:
            return []
        values = df[column].map(_normalize_text_value).tolist()
        return sorted({value for value in values if value})
    except (DatabasePoolExhaustedError, DatabaseCircuitOpenError):
        raise
    except Exception as exc:
        logger.error(f"Distinct value query failed for {column}: {exc}")
        return None


def _get_wip_filter_options_from_oracle(
    include_dummy: bool = False,
    workorder: Optional[str] = None,
    lotid: Optional[str] = None,
    package: Optional[str] = None,
    pj_type: Optional[str] = None,
    firstname: Optional[str] = None,
    waferdesc: Optional[str] = None,
) -> Optional[Dict[str, List[str]]]:
    columns = {
        "workorder": ("workorders", "WORKORDER"),
        "lotid": ("lotids", "LOTID"),
        "package": ("packages", "PACKAGE_LEF"),
        "pj_type": ("types", "PJ_TYPE"),
        "firstname": ("firstnames", "FIRSTNAME"),
        "waferdesc": ("waferdescs", "WAFERDESC"),
    }
    payload: Dict[str, List[str]] = {}
    for field, (key, column) in columns.items():
        values = _query_distinct_values_from_oracle(
            column,
            include_dummy=include_dummy,
            workorder=workorder,
            lotid=lotid,
            package=package,
            pj_type=pj_type,
            firstname=firstname,
            waferdesc=waferdesc,
            exclude_field=field,
        )
        if values is None:
            return None
        payload[key] = values
    return payload


def _get_filter_options_cache_payload(
    *,
    include_dummy: bool,
    workorder: Optional[str] = None,
    lotid: Optional[str] = None,
    package: Optional[str] = None,
    pj_type: Optional[str] = None,
    firstname: Optional[str] = None,
    waferdesc: Optional[str] = None,
) -> Optional[Dict[str, List[str]]]:
    by_field = {
        "workorder": ("workorders", "WORKORDER"),
        "lotid": ("lotids", "LOTID"),
        "package": ("packages", "PACKAGE_LEF"),
        "pj_type": ("types", "PJ_TYPE"),
        "firstname": ("firstnames", "FIRSTNAME"),
        "waferdesc": ("waferdescs", "WAFERDESC"),
    }

    payload: Dict[str, List[str]] = {}
    for field, (key, column) in by_field.items():
        df = _select_with_snapshot_indexes(
            include_dummy=include_dummy,
            workorder=None if field == "workorder" else workorder,
            lotid=None if field == "lotid" else lotid,
            package=None if field == "package" else package,
            pj_type=None if field == "pj_type" else pj_type,
            firstname=None if field == "firstname" else firstname,
            waferdesc=None if field == "waferdesc" else waferdesc,
        )
        if df is None:
            return None
        payload[key] = _distinct_non_empty_values(df, column)

    return payload


def get_wip_filter_options(
    include_dummy: bool = False,
    workorder: Optional[str] = None,
    lotid: Optional[str] = None,
    package: Optional[str] = None,
    pj_type: Optional[str] = None,
    firstname: Optional[str] = None,
    waferdesc: Optional[str] = None,
) -> Optional[Dict[str, List[str]]]:
    """Get interdependent filter option lists for WIP overview dropdowns."""
    has_filter = any(
        _split_csv_values(value)
        for value in (workorder, lotid, package, pj_type, firstname, waferdesc)
    )

    indexed = _get_wip_search_index(include_dummy=include_dummy)
    if indexed is not None and not has_filter:
        return {
            "workorders": list(indexed.get("workorders", [])),
            "lotids": list(indexed.get("lotids", [])),
            "packages": list(indexed.get("packages", [])),
            "types": list(indexed.get("types", [])),
            "firstnames": list(indexed.get("firstnames", [])),
            "waferdescs": list(indexed.get("waferdescs", [])),
        }

    cached_df = _get_wip_dataframe()
    if cached_df is not None:
        try:
            payload = _get_filter_options_cache_payload(
                include_dummy=include_dummy,
                workorder=workorder,
                lotid=lotid,
                package=package,
                pj_type=pj_type,
                firstname=firstname,
                waferdesc=waferdesc,
            )
            if payload is not None:
                return payload
        except (DatabasePoolExhaustedError, DatabaseCircuitOpenError):
            raise
        except Exception as exc:
            logger.warning(f"Cache-based filter options calculation failed, falling back to Oracle: {exc}")

    return _get_wip_filter_options_from_oracle(
        include_dummy=include_dummy,
        workorder=workorder,
        lotid=lotid,
        package=package,
        pj_type=pj_type,
        firstname=firstname,
        waferdesc=waferdesc,
    )


# ============================================================
# Search API Functions
# ============================================================

def search_workorders(
    q: str,
    limit: int = 20,
    include_dummy: bool = False,
    lotid: Optional[str] = None,
    package: Optional[str] = None,
    pj_type: Optional[str] = None
) -> Optional[List[str]]:
    """Search for WORKORDER values matching the query.

    Uses Redis cache when available, falls back to Oracle direct query.

    Args:
        q: Search query (minimum 2 characters)
        limit: Maximum number of results (default: 20, max: 50)
        include_dummy: If True, include DUMMY lots (default: False)
        lotid: Optional LOTID cross-filter (fuzzy match)
        package: Optional PACKAGE_LEF cross-filter (exact match)
        pj_type: Optional PJ_TYPE cross-filter (exact match)

    Returns:
        List of matching WORKORDER values (distinct)
    """
    # Validate input
    if not q or len(q) < 2:
        return []

    limit = min(limit, 50)  # Cap at 50

    if not lotid and not package and not pj_type:
        indexed = _get_wip_search_index(include_dummy=include_dummy)
        if indexed is not None:
            return _search_values_from_index(indexed.get("workorders", []), q, limit)

    # Try cache first
    cached_df = _get_wip_dataframe()
    if cached_df is not None:
        try:
            df = _select_with_snapshot_indexes(
                include_dummy=include_dummy,
                lotid=lotid,
                package=package,
                pj_type=pj_type,
            )
            if df is None:
                return _search_workorders_from_oracle(q, limit, include_dummy, lotid, package, pj_type)
            df = df[df['WORKORDER'].notna()]

            # Filter by search query (case-insensitive)
            df = df[df['WORKORDER'].str.contains(q, case=False, na=False)]

            if df.empty:
                return []

            # Get distinct, sorted, limited results
            result = df['WORKORDER'].drop_duplicates().sort_values().head(limit).tolist()
            return result
        except (DatabasePoolExhaustedError, DatabaseCircuitOpenError):
            raise
        except Exception as exc:
            logger.warning(f"Cache-based workorder search failed, falling back to Oracle: {exc}")

    # Fallback to Oracle direct query
    return _search_workorders_from_oracle(q, limit, include_dummy, lotid, package, pj_type)


def _search_workorders_from_oracle(
    q: str,
    limit: int = 20,
    include_dummy: bool = False,
    lotid: Optional[str] = None,
    package: Optional[str] = None,
    pj_type: Optional[str] = None
) -> Optional[List[str]]:
    """Search workorders directly from Oracle (fallback)."""
    try:
        builder = _build_base_conditions_builder(include_dummy, lotid=lotid)
        builder.add_like_condition("WORKORDER", q, position="both")
        builder.add_is_not_null("WORKORDER")

        # Apply cross-filters
        if package:
            builder.add_param_condition("PACKAGE_LEF", package)
        if pj_type:
            builder.add_param_condition("PJ_TYPE", pj_type)

        where_clause, params = builder.build_where_only()
        params['row_limit'] = limit

        sql = f"""
            SELECT DISTINCT WORKORDER
            FROM {WIP_VIEW}
            {where_clause}
            ORDER BY WORKORDER
            FETCH FIRST :row_limit ROWS ONLY
        """
        df = read_sql_df(sql, params)

        if df is None or df.empty:
            return []

        return df['WORKORDER'].tolist()
    except (DatabasePoolExhaustedError, DatabaseCircuitOpenError):
        raise
    except Exception as exc:
        logger.error(f"Search workorders failed: {exc}")
        return None


def search_lot_ids(
    q: str,
    limit: int = 20,
    include_dummy: bool = False,
    workorder: Optional[str] = None,
    package: Optional[str] = None,
    pj_type: Optional[str] = None
) -> Optional[List[str]]:
    """Search for LOTID values matching the query.

    Uses Redis cache when available, falls back to Oracle direct query.

    Args:
        q: Search query (minimum 2 characters)
        limit: Maximum number of results (default: 20, max: 50)
        include_dummy: If True, include DUMMY lots (default: False)
        workorder: Optional WORKORDER cross-filter (fuzzy match)
        package: Optional PACKAGE_LEF cross-filter (exact match)
        pj_type: Optional PJ_TYPE cross-filter (exact match)

    Returns:
        List of matching LOTID values
    """
    # Validate input
    if not q or len(q) < 2:
        return []

    limit = min(limit, 50)  # Cap at 50

    if not workorder and not package and not pj_type:
        indexed = _get_wip_search_index(include_dummy=include_dummy)
        if indexed is not None:
            return _search_values_from_index(indexed.get("lotids", []), q, limit)

    # Try cache first
    cached_df = _get_wip_dataframe()
    if cached_df is not None:
        try:
            df = _select_with_snapshot_indexes(
                include_dummy=include_dummy,
                workorder=workorder,
                package=package,
                pj_type=pj_type,
            )
            if df is None:
                return _search_lot_ids_from_oracle(q, limit, include_dummy, workorder, package, pj_type)

            # Filter by search query (case-insensitive)
            df = df[df['LOTID'].str.contains(q, case=False, na=False)]

            if df.empty:
                return []

            # Get sorted, limited results
            result = df['LOTID'].sort_values().head(limit).tolist()
            return result
        except (DatabasePoolExhaustedError, DatabaseCircuitOpenError):
            raise
        except Exception as exc:
            logger.warning(f"Cache-based lot ID search failed, falling back to Oracle: {exc}")

    # Fallback to Oracle direct query
    return _search_lot_ids_from_oracle(q, limit, include_dummy, workorder, package, pj_type)


def _search_lot_ids_from_oracle(
    q: str,
    limit: int = 20,
    include_dummy: bool = False,
    workorder: Optional[str] = None,
    package: Optional[str] = None,
    pj_type: Optional[str] = None
) -> Optional[List[str]]:
    """Search lot IDs directly from Oracle (fallback)."""
    try:
        builder = _build_base_conditions_builder(include_dummy, workorder=workorder)
        builder.add_like_condition("LOTID", q, position="both")

        # Apply cross-filters
        if package:
            builder.add_param_condition("PACKAGE_LEF", package)
        if pj_type:
            builder.add_param_condition("PJ_TYPE", pj_type)

        where_clause, params = builder.build_where_only()
        params['row_limit'] = limit

        sql = f"""
            SELECT LOTID
            FROM {WIP_VIEW}
            {where_clause}
            ORDER BY LOTID
            FETCH FIRST :row_limit ROWS ONLY
        """
        df = read_sql_df(sql, params)

        if df is None or df.empty:
            return []

        return df['LOTID'].tolist()
    except (DatabasePoolExhaustedError, DatabaseCircuitOpenError):
        raise
    except Exception as exc:
        logger.error(f"Search lot IDs failed: {exc}")
        return None


def search_packages(
    q: str,
    limit: int = 20,
    include_dummy: bool = False,
    workorder: Optional[str] = None,
    lotid: Optional[str] = None,
    pj_type: Optional[str] = None
) -> Optional[List[str]]:
    """Search for PACKAGE_LEF values matching the query.

    Uses Redis cache when available, falls back to Oracle direct query.

    Args:
        q: Search query (minimum 2 characters)
        limit: Maximum number of results (default: 20, max: 50)
        include_dummy: If True, include DUMMY lots (default: False)
        workorder: Optional WORKORDER cross-filter (fuzzy match)
        lotid: Optional LOTID cross-filter (fuzzy match)
        pj_type: Optional PJ_TYPE cross-filter (exact match)

    Returns:
        List of matching PACKAGE_LEF values (distinct)
    """
    # Validate input
    if not q or len(q) < 2:
        return []

    limit = min(limit, 50)  # Cap at 50

    if not workorder and not lotid and not pj_type:
        indexed = _get_wip_search_index(include_dummy=include_dummy)
        if indexed is not None:
            return _search_values_from_index(indexed.get("packages", []), q, limit)

    # Try cache first
    cached_df = _get_wip_dataframe()
    if cached_df is not None:
        try:
            df = _select_with_snapshot_indexes(
                include_dummy=include_dummy,
                workorder=workorder,
                lotid=lotid,
                pj_type=pj_type,
            )
            if df is None:
                return _search_packages_from_oracle(q, limit, include_dummy, workorder, lotid, pj_type)

            # Check if PACKAGE_LEF column exists
            if 'PACKAGE_LEF' not in df.columns:
                logger.warning("PACKAGE_LEF column not found in cache")
                return _search_packages_from_oracle(q, limit, include_dummy, workorder, lotid, pj_type)

            df = df[df['PACKAGE_LEF'].notna()]

            # Filter by search query (case-insensitive)
            df = df[df['PACKAGE_LEF'].str.contains(q, case=False, na=False)]

            if df.empty:
                return []

            # Get distinct values sorted
            result = df['PACKAGE_LEF'].drop_duplicates().sort_values().head(limit).tolist()
            return result
        except (DatabasePoolExhaustedError, DatabaseCircuitOpenError):
            raise
        except Exception as exc:
            logger.warning(f"Cache-based package search failed, falling back to Oracle: {exc}")

    # Fallback to Oracle direct query
    return _search_packages_from_oracle(q, limit, include_dummy, workorder, lotid, pj_type)


def _search_packages_from_oracle(
    q: str,
    limit: int = 20,
    include_dummy: bool = False,
    workorder: Optional[str] = None,
    lotid: Optional[str] = None,
    pj_type: Optional[str] = None
) -> Optional[List[str]]:
    """Search packages directly from Oracle (fallback)."""
    try:
        builder = _build_base_conditions_builder(include_dummy, workorder=workorder, lotid=lotid)
        builder.add_like_condition("PACKAGE_LEF", q, position="both")
        builder.add_is_not_null("PACKAGE_LEF")

        # Apply cross-filter
        if pj_type:
            builder.add_param_condition("PJ_TYPE", pj_type)

        where_clause, params = builder.build_where_only()
        params['row_limit'] = limit

        sql = f"""
            SELECT DISTINCT PACKAGE_LEF
            FROM {WIP_VIEW}
            {where_clause}
            ORDER BY PACKAGE_LEF
            FETCH FIRST :row_limit ROWS ONLY
        """
        df = read_sql_df(sql, params)

        if df is None or df.empty:
            return []

        return df['PACKAGE_LEF'].tolist()
    except (DatabasePoolExhaustedError, DatabaseCircuitOpenError):
        raise
    except Exception as exc:
        logger.error(f"Search packages failed: {exc}")
        return None


def search_types(
    q: str,
    limit: int = 20,
    include_dummy: bool = False,
    workorder: Optional[str] = None,
    lotid: Optional[str] = None,
    package: Optional[str] = None
) -> Optional[List[str]]:
    """Search for PJ_TYPE values matching the query.

    Uses Redis cache when available, falls back to Oracle direct query.

    Args:
        q: Search query (minimum 2 characters)
        limit: Maximum number of results (default: 20, max: 50)
        include_dummy: If True, include DUMMY lots (default: False)
        workorder: Optional WORKORDER cross-filter (fuzzy match)
        lotid: Optional LOTID cross-filter (fuzzy match)
        package: Optional PACKAGE_LEF cross-filter (exact match)

    Returns:
        List of matching PJ_TYPE values (distinct)
    """
    # Validate input
    if not q or len(q) < 2:
        return []

    limit = min(limit, 50)  # Cap at 50

    if not workorder and not lotid and not package:
        indexed = _get_wip_search_index(include_dummy=include_dummy)
        if indexed is not None:
            return _search_values_from_index(indexed.get("types", []), q, limit)

    # Try cache first
    cached_df = _get_wip_dataframe()
    if cached_df is not None:
        try:
            df = _select_with_snapshot_indexes(
                include_dummy=include_dummy,
                workorder=workorder,
                lotid=lotid,
                package=package,
            )
            if df is None:
                return _search_types_from_oracle(q, limit, include_dummy, workorder, lotid, package)

            # Check if PJ_TYPE column exists
            if 'PJ_TYPE' not in df.columns:
                logger.warning("PJ_TYPE column not found in cache")
                return _search_types_from_oracle(q, limit, include_dummy, workorder, lotid, package)

            df = df[df['PJ_TYPE'].notna()]

            # Filter by search query (case-insensitive)
            df = df[df['PJ_TYPE'].str.contains(q, case=False, na=False)]

            if df.empty:
                return []

            # Get distinct values sorted
            result = df['PJ_TYPE'].drop_duplicates().sort_values().head(limit).tolist()
            return result
        except (DatabasePoolExhaustedError, DatabaseCircuitOpenError):
            raise
        except Exception as exc:
            logger.warning(f"Cache-based type search failed, falling back to Oracle: {exc}")

    # Fallback to Oracle direct query
    return _search_types_from_oracle(q, limit, include_dummy, workorder, lotid, package)


def _search_types_from_oracle(
    q: str,
    limit: int = 20,
    include_dummy: bool = False,
    workorder: Optional[str] = None,
    lotid: Optional[str] = None,
    package: Optional[str] = None
) -> Optional[List[str]]:
    """Search types directly from Oracle (fallback)."""
    try:
        builder = _build_base_conditions_builder(include_dummy, workorder=workorder, lotid=lotid)
        builder.add_like_condition("PJ_TYPE", q, position="both")
        builder.add_is_not_null("PJ_TYPE")

        # Apply cross-filter
        if package:
            builder.add_param_condition("PACKAGE_LEF", package)

        where_clause, params = builder.build_where_only()
        params['row_limit'] = limit

        sql = f"""
            SELECT DISTINCT PJ_TYPE
            FROM {WIP_VIEW}
            {where_clause}
            ORDER BY PJ_TYPE
            FETCH FIRST :row_limit ROWS ONLY
        """
        df = read_sql_df(sql, params)

        if df is None or df.empty:
            return []

        return df['PJ_TYPE'].tolist()
    except (DatabasePoolExhaustedError, DatabaseCircuitOpenError):
        raise
    except Exception as exc:
        logger.error(f"Search types failed: {exc}")
        return None


# ============================================================
# Hold Detail API Functions
# ============================================================

def get_hold_detail_summary(
    reason: Optional[str] = None,
    hold_type: Optional[str] = None,
    workorder: Optional[str] = None,
    lotid: Optional[str] = None,
    pj_type: Optional[str] = None,
    firstname: Optional[str] = None,
    waferdesc: Optional[str] = None,
    include_dummy: bool = False,
) -> Optional[Dict[str, Any]]:
    """Get summary statistics for hold lots.

    Uses Redis cache when available, falls back to Oracle direct query.

    Args:
        reason: Optional HOLDREASONNAME filter
        hold_type: Optional hold type filter ('quality', 'non-quality')
        workorder: Optional WORKORDER filter
        lotid: Optional LOTID filter
        pj_type: Optional PJ_TYPE filter
        firstname: Optional FIRSTNAME filter
        waferdesc: Optional WAFERDESC filter
        include_dummy: If True, include DUMMY lots (default: False)

    Returns:
        Dict with totalLots, totalQty, avgAge, maxAge, workcenterCount, dataUpdateDate
    """
    # Try cache first
    cached_df = _get_wip_dataframe()
    if cached_df is not None:
        try:
            df = _select_with_snapshot_indexes(
                include_dummy=include_dummy,
                workorder=workorder,
                lotid=lotid,
                pj_type=pj_type,
                firstname=firstname,
                waferdesc=waferdesc,
                status='HOLD',
                hold_type=hold_type,
            )
            if df is None:
                return _get_hold_detail_summary_from_oracle(
                    reason=reason,
                    hold_type=hold_type,
                    workorder=workorder,
                    lotid=lotid,
                    pj_type=pj_type,
                    firstname=firstname,
                    waferdesc=waferdesc,
                    include_dummy=include_dummy,
                )

            # Extract all distinct reasons before applying reason filter
            top_reasons = sorted(
                df['HOLDREASONNAME'].dropna().astype(str).str.strip()
                .loc[lambda s: s != ''].unique().tolist()
            )

            if reason:
                if isinstance(reason, (list, tuple)):
                    df = df[df['HOLDREASONNAME'].isin(reason)]
                else:
                    df = df[df['HOLDREASONNAME'] == reason]

            if df.empty:
                return {
                    'totalLots': 0,
                    'totalQty': 0,
                    'avgAge': 0,
                    'maxAge': 0,
                    'workcenterCount': 0,
                    'topReasons': top_reasons,
                    'dataUpdateDate': get_cached_sys_date(),
                }

            # Ensure AGEBYDAYS is numeric
            df = df.copy()
            df['AGEBYDAYS'] = pd.to_numeric(df['AGEBYDAYS'], errors='coerce').fillna(0)

            return {
                'totalLots': len(df),
                'totalQty': int(df['QTY'].sum()),
                'avgAge': round(float(df['AGEBYDAYS'].mean()), 1),
                'maxAge': float(df['AGEBYDAYS'].max()),
                'workcenterCount': df['WORKCENTER_GROUP'].nunique(),
                'topReasons': top_reasons,
                'dataUpdateDate': get_cached_sys_date(),
            }
        except (DatabasePoolExhaustedError, DatabaseCircuitOpenError):
            raise
        except Exception as exc:
            logger.warning(f"Cache-based hold detail summary failed, falling back to Oracle: {exc}")

    # Fallback to Oracle direct query
    return _get_hold_detail_summary_from_oracle(
        reason=reason,
        hold_type=hold_type,
        workorder=workorder,
        lotid=lotid,
        pj_type=pj_type,
        firstname=firstname,
        waferdesc=waferdesc,
        include_dummy=include_dummy,
    )


def _get_hold_detail_summary_from_oracle(
    reason: Optional[str] = None,
    hold_type: Optional[str] = None,
    workorder: Optional[str] = None,
    lotid: Optional[str] = None,
    pj_type: Optional[str] = None,
    firstname: Optional[str] = None,
    waferdesc: Optional[str] = None,
    include_dummy: bool = False,
) -> Optional[Dict[str, Any]]:
    """Get hold detail summary directly from Oracle (fallback)."""
    try:
        builder = _build_base_conditions_builder(include_dummy)
        builder.add_param_condition("STATUS", "HOLD")
        builder.add_condition("CURRENTHOLDCOUNT > 0")
        if hold_type:
            _add_hold_type_conditions(builder, hold_type)
        if reason:
            builder.add_param_condition("HOLDREASONNAME", reason)
        if workorder:
            builder.add_like_condition("WORKORDER", workorder)
        if lotid:
            builder.add_like_condition("LOTID", lotid)
        if pj_type:
            builder.add_param_condition("PJ_TYPE", pj_type)
        if firstname:
            builder.add_param_condition("FIRSTNAME", firstname)
        if waferdesc:
            builder.add_param_condition("WAFERDESC", waferdesc)
        where_clause, params = builder.build_where_only()

        sql = f"""
            SELECT
                COUNT(*) AS TOTAL_LOTS,
                SUM(QTY) AS TOTAL_QTY,
                ROUND(AVG(AGEBYDAYS), 1) AS AVG_AGE,
                MAX(AGEBYDAYS) AS MAX_AGE,
                COUNT(DISTINCT WORKCENTER_GROUP) AS WORKCENTER_COUNT,
                MAX(SYS_DATE) AS DATA_UPDATE_DATE
            FROM {WIP_VIEW}
            {where_clause}
        """
        df = read_sql_df(sql, params)

        if df is None or df.empty:
            return None

        row = df.iloc[0]
        return {
            'totalLots': int(row['TOTAL_LOTS'] or 0),
            'totalQty': int(row['TOTAL_QTY'] or 0),
            'avgAge': float(row['AVG_AGE']) if row['AVG_AGE'] else 0,
            'maxAge': float(row['MAX_AGE']) if row['MAX_AGE'] else 0,
            'workcenterCount': int(row['WORKCENTER_COUNT'] or 0),
            'dataUpdateDate': str(row['DATA_UPDATE_DATE']) if row['DATA_UPDATE_DATE'] else None,
        }
    except (DatabasePoolExhaustedError, DatabaseCircuitOpenError):
        raise
    except Exception as exc:
        logger.error(f"Hold detail summary query failed: {exc}")
        import traceback
        traceback.print_exc()
        return None


def get_hold_detail_distribution(
    reason: str,
    include_dummy: bool = False
) -> Optional[Dict[str, Any]]:
    """Get distribution statistics for a specific hold reason.

    Uses Redis cache when available, falls back to Oracle direct query.

    Args:
        reason: The HOLDREASONNAME to filter by
        include_dummy: If True, include DUMMY lots (default: False)

    Returns:
        Dict with byWorkcenter, byPackage, byAge distributions
    """
    # Try cache first
    cached_df = _get_wip_dataframe()
    if cached_df is not None:
        try:
            df = _select_with_snapshot_indexes(
                include_dummy=include_dummy,
                status='HOLD',
            )
            if df is None:
                return _get_hold_detail_distribution_from_oracle(reason, include_dummy)

            # Filter for HOLD status with matching reason
            df = df[df['HOLDREASONNAME'] == reason]

            total_lots = len(df)

            if total_lots == 0:
                return {
                    'byWorkcenter': [],
                    'byPackage': [],
                    'byAge': []
                }

            # Ensure numeric columns
            df['AGEBYDAYS'] = pd.to_numeric(df['AGEBYDAYS'], errors='coerce').fillna(0)

            # By Workcenter
            wc_df = df[df['WORKCENTER_GROUP'].notna()].groupby('WORKCENTER_GROUP').agg({
                'LOTID': 'count',
                'QTY': 'sum'
            }).reset_index()
            wc_df.columns = ['NAME', 'LOTS', 'QTY']
            wc_df = wc_df.sort_values('LOTS', ascending=False)

            by_workcenter = []
            for _, row in wc_df.iterrows():
                lots = int(row['LOTS'] or 0)
                by_workcenter.append({
                    'name': row['NAME'],
                    'lots': lots,
                    'qty': int(row['QTY'] or 0),
                    'percentage': round(lots / total_lots * 100, 1) if total_lots > 0 else 0
                })

            # By Package
            pkg_df = df[df['PACKAGE_LEF'].notna()].groupby('PACKAGE_LEF').agg({
                'LOTID': 'count',
                'QTY': 'sum'
            }).reset_index()
            pkg_df.columns = ['NAME', 'LOTS', 'QTY']
            pkg_df = pkg_df.sort_values('LOTS', ascending=False)

            by_package = []
            for _, row in pkg_df.iterrows():
                lots = int(row['LOTS'] or 0)
                by_package.append({
                    'name': row['NAME'],
                    'lots': lots,
                    'qty': int(row['QTY'] or 0),
                    'percentage': round(lots / total_lots * 100, 1) if total_lots > 0 else 0
                })

            # By Age - compute age range
            def get_age_range(age):
                if age < 1:
                    return '0-1'
                elif age < 3:
                    return '1-3'
                elif age < 7:
                    return '3-7'
                else:
                    return '7+'

            df['AGE_RANGE'] = df['AGEBYDAYS'].apply(get_age_range)

            age_df = df.groupby('AGE_RANGE').agg({
                'LOTID': 'count',
                'QTY': 'sum'
            }).reset_index()
            age_df.columns = ['AGE_RANGE', 'LOTS', 'QTY']

            # Define age ranges in order
            age_labels = {
                '0-1': '0-1天',
                '1-3': '1-3天',
                '3-7': '3-7天',
                '7+': '7+天'
            }
            age_order = ['0-1', '1-3', '3-7', '7+']

            # Build age distribution with all ranges (even if 0)
            age_data = {r: {'lots': 0, 'qty': 0} for r in age_order}
            for _, row in age_df.iterrows():
                range_key = row['AGE_RANGE']
                if range_key in age_data:
                    age_data[range_key] = {
                        'lots': int(row['LOTS'] or 0),
                        'qty': int(row['QTY'] or 0)
                    }

            by_age = []
            for r in age_order:
                lots = age_data[r]['lots']
                by_age.append({
                    'range': r,
                    'label': age_labels[r],
                    'lots': lots,
                    'qty': age_data[r]['qty'],
                    'percentage': round(lots / total_lots * 100, 1) if total_lots > 0 else 0
                })

            return {
                'byWorkcenter': by_workcenter,
                'byPackage': by_package,
                'byAge': by_age
            }
        except (DatabasePoolExhaustedError, DatabaseCircuitOpenError):
            raise
        except Exception as exc:
            logger.warning(f"Cache-based hold detail distribution failed, falling back to Oracle: {exc}")

    # Fallback to Oracle direct query
    return _get_hold_detail_distribution_from_oracle(reason, include_dummy)


def _get_hold_detail_distribution_from_oracle(
    reason: str,
    include_dummy: bool = False
) -> Optional[Dict[str, Any]]:
    """Get hold detail distribution directly from Oracle (fallback)."""
    try:
        builder = _build_base_conditions_builder(include_dummy)
        builder.add_param_condition("STATUS", "HOLD")
        builder.add_condition("CURRENTHOLDCOUNT > 0")
        builder.add_param_condition("HOLDREASONNAME", reason)
        where_clause, params = builder.build_where_only()

        # Get total for percentage calculation
        total_sql = f"""
            SELECT COUNT(*) AS TOTAL_LOTS, SUM(QTY) AS TOTAL_QTY
            FROM {WIP_VIEW}
            {where_clause}
        """
        total_df = read_sql_df(total_sql, params)
        total_lots = int(total_df.iloc[0]['TOTAL_LOTS'] or 0) if total_df is not None else 0

        if total_lots == 0:
            return {
                'byWorkcenter': [],
                'byPackage': [],
                'byAge': []
            }

        # By Workcenter
        wc_sql = f"""
            SELECT
                WORKCENTER_GROUP AS NAME,
                COUNT(*) AS LOTS,
                SUM(QTY) AS QTY
            FROM {WIP_VIEW}
            {where_clause}
              AND WORKCENTER_GROUP IS NOT NULL
            GROUP BY WORKCENTER_GROUP
            ORDER BY COUNT(*) DESC
        """
        wc_df = read_sql_df(wc_sql, params)
        by_workcenter = []
        if wc_df is not None and not wc_df.empty:
            for _, row in wc_df.iterrows():
                lots = int(row['LOTS'] or 0)
                by_workcenter.append({
                    'name': row['NAME'],
                    'lots': lots,
                    'qty': int(row['QTY'] or 0),
                    'percentage': round(lots / total_lots * 100, 1) if total_lots > 0 else 0
                })

        # By Package
        pkg_sql = f"""
            SELECT
                PACKAGE_LEF AS NAME,
                COUNT(*) AS LOTS,
                SUM(QTY) AS QTY
            FROM {WIP_VIEW}
            {where_clause}
              AND PACKAGE_LEF IS NOT NULL
            GROUP BY PACKAGE_LEF
            ORDER BY COUNT(*) DESC
        """
        pkg_df = read_sql_df(pkg_sql, params)
        by_package = []
        if pkg_df is not None and not pkg_df.empty:
            for _, row in pkg_df.iterrows():
                lots = int(row['LOTS'] or 0)
                by_package.append({
                    'name': row['NAME'],
                    'lots': lots,
                    'qty': int(row['QTY'] or 0),
                    'percentage': round(lots / total_lots * 100, 1) if total_lots > 0 else 0
                })

        # By Age (station dwell time)
        age_sql = f"""
            SELECT
                CASE
                    WHEN AGEBYDAYS < 1 THEN '0-1'
                    WHEN AGEBYDAYS < 3 THEN '1-3'
                    WHEN AGEBYDAYS < 7 THEN '3-7'
                    ELSE '7+'
                END AS AGE_RANGE,
                COUNT(*) AS LOTS,
                SUM(QTY) AS QTY
            FROM {WIP_VIEW}
            {where_clause}
            GROUP BY CASE
                WHEN AGEBYDAYS < 1 THEN '0-1'
                WHEN AGEBYDAYS < 3 THEN '1-3'
                WHEN AGEBYDAYS < 7 THEN '3-7'
                ELSE '7+'
            END
        """
        age_df = read_sql_df(age_sql, params)

        # Define age ranges in order
        age_labels = {
            '0-1': '0-1天',
            '1-3': '1-3天',
            '3-7': '3-7天',
            '7+': '7+天'
        }
        age_order = ['0-1', '1-3', '3-7', '7+']

        # Build age distribution with all ranges (even if 0)
        age_data = {r: {'lots': 0, 'qty': 0} for r in age_order}
        if age_df is not None and not age_df.empty:
            for _, row in age_df.iterrows():
                range_key = row['AGE_RANGE']
                if range_key in age_data:
                    age_data[range_key] = {
                        'lots': int(row['LOTS'] or 0),
                        'qty': int(row['QTY'] or 0)
                    }

        by_age = []
        for r in age_order:
            lots = age_data[r]['lots']
            by_age.append({
                'range': r,
                'label': age_labels[r],
                'lots': lots,
                'qty': age_data[r]['qty'],
                'percentage': round(lots / total_lots * 100, 1) if total_lots > 0 else 0
            })

        return {
            'byWorkcenter': by_workcenter,
            'byPackage': by_package,
            'byAge': by_age
        }
    except (DatabasePoolExhaustedError, DatabaseCircuitOpenError):
        raise
    except Exception as exc:
        logger.error(f"Hold detail distribution query failed: {exc}")
        import traceback
        traceback.print_exc()
        return None


def get_hold_detail_lots(
    reason: Optional[str] = None,
    hold_type: Optional[str] = None,
    treemap_reason: Optional[str] = None,
    workcenter: Optional[str] = None,
    package: Optional[str] = None,
    workorder: Optional[str] = None,
    lotid: Optional[str] = None,
    pj_type: Optional[str] = None,
    firstname: Optional[str] = None,
    waferdesc: Optional[str] = None,
    age_range: Optional[str] = None,
    include_dummy: bool = False,
    page: int = 1,
    page_size: int = 50
) -> Optional[Dict[str, Any]]:
    """Get paginated lot details for hold lots.

    Uses Redis cache when available, falls back to Oracle direct query.

    Args:
        reason: Optional HOLDREASONNAME filter (from filter bar)
        hold_type: Optional hold type filter ('quality', 'non-quality')
        treemap_reason: Optional HOLDREASONNAME filter from treemap selection
        workcenter: Optional WORKCENTER_GROUP filter
        package: Optional PACKAGE_LEF filter
        workorder: Optional WORKORDER filter
        lotid: Optional LOTID filter
        pj_type: Optional PJ_TYPE filter
        firstname: Optional FIRSTNAME filter
        waferdesc: Optional WAFERDESC filter
        age_range: Optional age range filter ('0-1', '1-3', '3-7', '7+')
        include_dummy: If True, include DUMMY lots (default: False)
        page: Page number (1-based)
        page_size: Number of records per page

    Returns:
        Dict with lots list, pagination info, and active filters
    """
    page = max(int(page or 1), 1)
    page_size = max(int(page_size or 50), 1)

    # Try cache first
    cached_df = _get_wip_dataframe()
    if cached_df is not None:
        try:
            df = _select_with_snapshot_indexes(
                include_dummy=include_dummy,
                workcenter=workcenter,
                package=package,
                workorder=workorder,
                lotid=lotid,
                pj_type=pj_type,
                firstname=firstname,
                waferdesc=waferdesc,
                status='HOLD',
                hold_type=hold_type,
            )
            if df is None:
                return _get_hold_detail_lots_from_oracle(
                    reason=reason,
                    hold_type=hold_type,
                    treemap_reason=treemap_reason,
                    workcenter=workcenter,
                    package=package,
                    workorder=workorder,
                    lotid=lotid,
                    pj_type=pj_type,
                    firstname=firstname,
                    waferdesc=waferdesc,
                    age_range=age_range,
                    include_dummy=include_dummy,
                    page=page,
                    page_size=page_size,
                )

            if reason:
                if isinstance(reason, (list, tuple)):
                    df = df[df['HOLDREASONNAME'].isin(reason)]
                else:
                    df = df[df['HOLDREASONNAME'] == reason]
            if treemap_reason:
                df = df[df['HOLDREASONNAME'] == treemap_reason]

            # Ensure numeric columns
            df = df.copy()
            df['AGEBYDAYS'] = pd.to_numeric(df['AGEBYDAYS'], errors='coerce').fillna(0)

            # Optional age filter
            if age_range:
                if age_range == '0-1':
                    df = df[(df['AGEBYDAYS'] >= 0) & (df['AGEBYDAYS'] < 1)]
                elif age_range == '1-3':
                    df = df[(df['AGEBYDAYS'] >= 1) & (df['AGEBYDAYS'] < 3)]
                elif age_range == '3-7':
                    df = df[(df['AGEBYDAYS'] >= 3) & (df['AGEBYDAYS'] < 7)]
                elif age_range == '7+':
                    df = df[df['AGEBYDAYS'] >= 7]

            total = len(df)

            # Sort by age descending, then LOTID
            df = df.sort_values(['AGEBYDAYS', 'LOTID'], ascending=[False, True])

            # Pagination
            offset = (page - 1) * page_size
            page_df = df.iloc[offset:offset + page_size]

            lots = []
            for _, row in page_df.iterrows():
                lots.append({
                    'lotId': _safe_value(row.get('LOTID')),
                    'workorder': _safe_value(row.get('WORKORDER')),
                    'qty': int(row.get('QTY', 0) or 0),
                    'product': _safe_value(row.get('PRODUCT')),
                    'package': _safe_value(row.get('PACKAGE_LEF')),
                    'workcenter': _safe_value(row.get('WORKCENTER_GROUP')),
                    'holdReason': _safe_value(row.get('HOLDREASONNAME')),
                    'spec': _safe_value(row.get('SPECNAME')),
                    'age': round(float(row.get('AGEBYDAYS', 0) or 0), 1),
                    'holdBy': _safe_value(row.get('HOLDEMP')),
                    'dept': _safe_value(row.get('DEPTNAME')),
                    'holdComment': _safe_value(row.get('COMMENT_HOLD')),
                    'futureHoldComment': _safe_value(row.get('COMMENT_FUTURE')),
                })

            total_pages = (total + page_size - 1) // page_size if total > 0 else 1

            return {
                'lots': lots,
                'pagination': {
                    'page': page,
                    'perPage': page_size,
                    'total': total,
                    'totalPages': total_pages
                },
                'filters': {
                    'holdType': hold_type,
                    'reason': reason,
                    'treemapReason': treemap_reason,
                    'workcenter': workcenter,
                    'package': package,
                    'ageRange': age_range
                }
            }
        except (DatabasePoolExhaustedError, DatabaseCircuitOpenError):
            raise
        except Exception as exc:
            logger.warning(f"Cache-based hold detail lots failed, falling back to Oracle: {exc}")

    # Fallback to Oracle direct query
    return _get_hold_detail_lots_from_oracle(
        reason=reason,
        hold_type=hold_type,
        treemap_reason=treemap_reason,
        workcenter=workcenter,
        package=package,
        workorder=workorder,
        lotid=lotid,
        pj_type=pj_type,
        firstname=firstname,
        waferdesc=waferdesc,
        age_range=age_range,
        include_dummy=include_dummy,
        page=page,
        page_size=page_size,
    )


def _get_hold_detail_lots_from_oracle(
    reason: Optional[str] = None,
    hold_type: Optional[str] = None,
    treemap_reason: Optional[str] = None,
    workcenter: Optional[str] = None,
    package: Optional[str] = None,
    workorder: Optional[str] = None,
    lotid: Optional[str] = None,
    pj_type: Optional[str] = None,
    firstname: Optional[str] = None,
    waferdesc: Optional[str] = None,
    age_range: Optional[str] = None,
    include_dummy: bool = False,
    page: int = 1,
    page_size: int = 50
) -> Optional[Dict[str, Any]]:
    """Get hold detail lots directly from Oracle (fallback)."""
    try:
        builder = _build_base_conditions_builder(include_dummy)
        builder.add_param_condition("STATUS", "HOLD")
        builder.add_condition("CURRENTHOLDCOUNT > 0")
        if hold_type:
            _add_hold_type_conditions(builder, hold_type)
        if reason:
            builder.add_param_condition("HOLDREASONNAME", reason)
        if treemap_reason:
            builder.add_param_condition("HOLDREASONNAME", treemap_reason)

        # Optional filters
        if workcenter:
            builder.add_param_condition("WORKCENTER_GROUP", workcenter)
        if package:
            builder.add_param_condition("PACKAGE_LEF", package)
        if workorder:
            builder.add_like_condition("WORKORDER", workorder)
        if lotid:
            builder.add_like_condition("LOTID", lotid)
        if pj_type:
            builder.add_param_condition("PJ_TYPE", pj_type)
        if firstname:
            builder.add_param_condition("FIRSTNAME", firstname)
        if waferdesc:
            builder.add_param_condition("WAFERDESC", waferdesc)
        if age_range:
            if age_range == '0-1':
                builder.add_condition("AGEBYDAYS >= 0 AND AGEBYDAYS < 1")
            elif age_range == '1-3':
                builder.add_condition("AGEBYDAYS >= 1 AND AGEBYDAYS < 3")
            elif age_range == '3-7':
                builder.add_condition("AGEBYDAYS >= 3 AND AGEBYDAYS < 7")
            elif age_range == '7+':
                builder.add_condition("AGEBYDAYS >= 7")

        where_clause, params = builder.build_where_only()

        # Get total count
        count_sql = f"""
            SELECT COUNT(*) AS TOTAL
            FROM {WIP_VIEW}
            {where_clause}
        """
        count_df = read_sql_df(count_sql, params)
        total = int(count_df.iloc[0]['TOTAL'] or 0) if count_df is not None else 0

        # Get paginated lots with bind variables
        offset = (page - 1) * page_size
        lots_params = params.copy()
        lots_params['offset'] = offset
        lots_params['limit'] = page_size

        lots_sql = f"""
            SELECT * FROM (
                SELECT
                    LOTID,
                    WORKORDER,
                    QTY,
                    PRODUCT,
                    PACKAGE_LEF AS PACKAGE,
                    WORKCENTER_GROUP AS WORKCENTER,
                    HOLDREASONNAME AS HOLD_REASON,
                    SPECNAME AS SPEC,
                    ROUND(AGEBYDAYS, 1) AS AGE,
                    HOLDEMP AS HOLD_BY,
                    DEPTNAME AS DEPT,
                    COMMENT_HOLD AS HOLD_COMMENT,
                    COMMENT_FUTURE AS FUTURE_HOLD_COMMENT,
                    ROW_NUMBER() OVER (ORDER BY AGEBYDAYS DESC, LOTID) AS RN
                FROM {WIP_VIEW}
                {where_clause}
            )
            WHERE RN > :offset AND RN <= :offset + :limit
            ORDER BY RN
        """
        lots_df = read_sql_df(lots_sql, lots_params)

        lots = []
        if lots_df is not None and not lots_df.empty:
            for _, row in lots_df.iterrows():
                lots.append({
                    'lotId': _safe_value(row['LOTID']),
                    'workorder': _safe_value(row['WORKORDER']),
                    'qty': int(row['QTY'] or 0),
                    'product': _safe_value(row['PRODUCT']),
                    'package': _safe_value(row['PACKAGE']),
                    'workcenter': _safe_value(row['WORKCENTER']),
                    'holdReason': _safe_value(row['HOLD_REASON']),
                    'spec': _safe_value(row['SPEC']),
                    'age': float(row['AGE']) if row['AGE'] else 0,
                    'holdBy': _safe_value(row['HOLD_BY']),
                    'dept': _safe_value(row['DEPT']),
                    'holdComment': _safe_value(row['HOLD_COMMENT']),
                    'futureHoldComment': _safe_value(row['FUTURE_HOLD_COMMENT']),
                })

        total_pages = (total + page_size - 1) // page_size if total > 0 else 1

        return {
            'lots': lots,
            'pagination': {
                'page': page,
                'perPage': page_size,
                'total': total,
                'totalPages': total_pages
            },
            'filters': {
                'holdType': hold_type,
                'reason': reason,
                'treemapReason': treemap_reason,
                'workcenter': workcenter,
                'package': package,
                'ageRange': age_range
            }
        }
    except (DatabasePoolExhaustedError, DatabaseCircuitOpenError):
        raise
    except Exception as exc:
        logger.error(f"Hold detail lots query failed: {exc}")
        import traceback
        traceback.print_exc()
        return None


# ============================================================
# Hold Overview API Functions
# ============================================================

def get_hold_overview_treemap(
    hold_type: Optional[str] = None,
    reason: Optional[str] = None,
    workcenter: Optional[str] = None,
    package: Optional[str] = None,
    include_dummy: bool = False,
) -> Optional[Dict[str, Any]]:
    """Get hold overview treemap aggregation grouped by workcenter and reason."""
    cached_df = _get_wip_dataframe()
    if cached_df is not None:
        try:
            df = _select_with_snapshot_indexes(
                include_dummy=include_dummy,
                workcenter=workcenter,
                package=package,
                status='HOLD',
                hold_type=hold_type,
            )
            if df is None:
                return _get_hold_overview_treemap_from_oracle(
                    hold_type=hold_type,
                    reason=reason,
                    workcenter=workcenter,
                    package=package,
                    include_dummy=include_dummy,
                )

            if reason:
                if isinstance(reason, (list, tuple)):
                    df = df[df['HOLDREASONNAME'].isin(reason)]
                else:
                    df = df[df['HOLDREASONNAME'] == reason]

            df = df[df['WORKCENTER_GROUP'].notna() & df['HOLDREASONNAME'].notna()]
            if df.empty:
                return {'items': []}

            df = df.copy()
            df['AGEBYDAYS'] = pd.to_numeric(df['AGEBYDAYS'], errors='coerce').fillna(0)
            df['QTY'] = pd.to_numeric(df['QTY'], errors='coerce').fillna(0)

            grouped = df.groupby(
                ['WORKCENTER_GROUP', 'WORKCENTERSEQUENCE_GROUP', 'HOLDREASONNAME'],
                dropna=False,
            ).agg(
                LOTS=('LOTID', 'count'),
                QTY=('QTY', 'sum'),
                AVG_AGE=('AGEBYDAYS', 'mean'),
            ).reset_index()
            grouped = grouped.sort_values(
                ['WORKCENTERSEQUENCE_GROUP', 'QTY'],
                ascending=[True, False],
            )

            items = []
            for _, row in grouped.iterrows():
                items.append({
                    'workcenter': _safe_value(row.get('WORKCENTER_GROUP')),
                    'reason': _safe_value(row.get('HOLDREASONNAME')),
                    'lots': int(row.get('LOTS', 0) or 0),
                    'qty': int(row.get('QTY', 0) or 0),
                    'avgAge': round(float(row.get('AVG_AGE', 0) or 0), 1),
                })
            return {'items': items}
        except (DatabasePoolExhaustedError, DatabaseCircuitOpenError):
            raise
        except Exception as exc:
            logger.warning(f"Cache-based hold overview treemap failed, falling back to Oracle: {exc}")

    return _get_hold_overview_treemap_from_oracle(
        hold_type=hold_type,
        reason=reason,
        workcenter=workcenter,
        package=package,
        include_dummy=include_dummy,
    )


def _get_hold_overview_treemap_from_oracle(
    hold_type: Optional[str] = None,
    reason: Optional[str] = None,
    workcenter: Optional[str] = None,
    package: Optional[str] = None,
    include_dummy: bool = False,
) -> Optional[Dict[str, Any]]:
    """Get hold overview treemap aggregation directly from Oracle (fallback)."""
    try:
        builder = _build_base_conditions_builder(include_dummy)
        builder.add_param_condition("STATUS", "HOLD")
        builder.add_condition("CURRENTHOLDCOUNT > 0")
        if hold_type:
            _add_hold_type_conditions(builder, hold_type)
        if reason:
            builder.add_param_condition("HOLDREASONNAME", reason)
        if workcenter:
            builder.add_param_condition("WORKCENTER_GROUP", workcenter)
        if package:
            builder.add_param_condition("PACKAGE_LEF", package)

        where_clause, params = builder.build_where_only()
        sql = f"""
            SELECT
                WORKCENTER_GROUP,
                WORKCENTERSEQUENCE_GROUP,
                HOLDREASONNAME,
                COUNT(*) AS LOTS,
                SUM(QTY) AS QTY,
                ROUND(AVG(AGEBYDAYS), 1) AS AVG_AGE
            FROM {WIP_VIEW}
            {where_clause}
              AND WORKCENTER_GROUP IS NOT NULL
              AND HOLDREASONNAME IS NOT NULL
            GROUP BY WORKCENTER_GROUP, WORKCENTERSEQUENCE_GROUP, HOLDREASONNAME
            ORDER BY WORKCENTERSEQUENCE_GROUP, SUM(QTY) DESC
        """
        df = read_sql_df(sql, params)

        if df is None or df.empty:
            return {'items': []}

        items = []
        for _, row in df.iterrows():
            items.append({
                'workcenter': _safe_value(row.get('WORKCENTER_GROUP')),
                'reason': _safe_value(row.get('HOLDREASONNAME')),
                'lots': int(row.get('LOTS', 0) or 0),
                'qty': int(row.get('QTY', 0) or 0),
                'avgAge': round(float(row.get('AVG_AGE', 0) or 0), 1),
            })
        return {'items': items}
    except (DatabasePoolExhaustedError, DatabaseCircuitOpenError):
        raise
    except Exception as exc:
        logger.error(f"Hold overview treemap query failed: {exc}")
        import traceback
        traceback.print_exc()
        return None


# ============================================================
# Lot Detail API Functions
# ============================================================

# Field labels mapping for lot detail display (PowerBI naming convention)
LOT_DETAIL_FIELD_LABELS = {
    'lotId': 'Run Card Lot ID',
    'workorder': 'Work Order ID',
    'qty': 'Lot Qty(pcs)',
    'qty2': 'Lot Qty(Wafer pcs)',
    'status': 'Run Card Status',
    'holdReason': 'Hold Reason',
    'holdCount': 'Hold Count',
    'owner': 'Work Order Owner',
    'startDate': 'Run Card Start Date',
    'uts': 'UTS',
    'product': 'Product P/N',
    'productLine': 'Package',
    'packageLef': 'Package(LF)',
    'pjFunction': 'Product Function',
    'pjType': 'Product Type',
    'bop': 'BOP',
    'waferLotId': 'Wafer Lot ID',
    'waferPn': 'Wafer P/N',
    'waferLotPrefix': 'Wafer Lot ID(Prefix)',
    'spec': 'Spec',
    'specSequence': 'Spec Sequence',
    'workcenter': 'Work Center',
    'workcenterSequence': 'Work Center Sequence',
    'workcenterGroup': 'Work Center(Group)',
    'workcenterShort': 'Work Center(Short)',
    'ageByDays': 'Age By Days',
    'equipment': 'Equipment ID',
    'equipmentCount': 'Equipment Count',
    'workflow': 'Work Flow Name',
    'dateCode': 'Product Date Code',
    'leadframeName': 'LF Material Part',
    'leadframeOption': 'LF Option ID',
    'compoundName': 'Compound Material Part',
    'location': 'Run Card Location',
    'ncrId': 'NCR ID',
    'ncrDate': 'NCR-issued Time',
    'releaseTime': 'Release Time',
    'releaseEmp': 'Release Employee',
    'releaseComment': 'Release Comment',
    'holdComment': 'Hold Comment',
    'comment': 'Comment',
    'commentDate': 'Run Card Comment',
    'commentEmp': 'Run Card Comment Employee',
    'futureHoldComment': 'Future Hold Comment',
    'holdEmp': 'Hold Employee',
    'holdDept': 'Hold Employee Dept',
    'produceRegion': 'Produce Region',
    'priority': 'Work Order Priority',
    'tmttRemaining': 'TMTT Remaining',
    'dieConsumption': 'Die Consumption Qty',
    'leadframeDesc': 'LF Description',
    'waferDesc': 'Wafer Description',
    'wipStatus': 'WIP Status',
    'dataUpdateDate': 'Data Update Date'
}


def get_lot_detail(lotid: str) -> Optional[Dict[str, Any]]:
    """Get detailed information for a specific lot.

    Uses Redis cache when available, falls back to Oracle direct query.

    Args:
        lotid: The LOTID to retrieve

    Returns:
        Dict with lot details or None if not found
    """
    # Try cache first
    cached_df = _get_wip_dataframe()
    if cached_df is not None:
        try:
            df = cached_df[cached_df['LOTID'] == lotid]

            if df.empty:
                return None

            row = df.iloc[0]
            if len(df) > 1:
                row = row.copy()
                for col in ('LEADFRAMEDESC', 'WAFERDESC'):
                    if col in df.columns:
                        vals = df[col].dropna().unique()
                        row[col] = ', '.join(str(v) for v in vals) if len(vals) > 0 else None
            return _build_lot_detail_response(row)
        except (DatabasePoolExhaustedError, DatabaseCircuitOpenError):
            raise
        except Exception as exc:
            logger.warning(f"Cache-based lot detail failed, falling back to Oracle: {exc}")

    # Fallback to Oracle direct query
    return _get_lot_detail_from_oracle(lotid)


def _get_lot_detail_from_oracle(lotid: str) -> Optional[Dict[str, Any]]:
    """Get lot detail directly from Oracle (fallback)."""
    try:
        sql = f"""
            SELECT
                LOTID,
                WORKORDER,
                QTY,
                QTY2,
                STATUS,
                HOLDREASONNAME,
                CURRENTHOLDCOUNT,
                OWNER,
                STARTDATE,
                UTS,
                PRODUCT,
                PRODUCTLINENAME,
                PACKAGE_LEF,
                PJ_FUNCTION,
                PJ_TYPE,
                BOP,
                FIRSTNAME,
                WAFERNAME,
                WAFERLOT,
                SPECNAME,
                SPECSEQUENCE,
                WORKCENTERNAME,
                WORKCENTERSEQUENCE,
                WORKCENTER_GROUP,
                WORKCENTER_SHORT,
                AGEBYDAYS,
                EQUIPMENTS,
                EQUIPMENTCOUNT,
                WORKFLOWNAME,
                DATECODE,
                LEADFRAMENAME,
                LEADFRAMEOPTION,
                COMNAME,
                LOCATIONNAME,
                EVENTNAME,
                OCCURRENCEDATE,
                RELEASETIME,
                RELEASEEMP,
                RELEASEREASON,
                COMMENT_HOLD,
                CONTAINERCOMMENTS,
                COMMENT_DATE,
                COMMENT_EMP,
                COMMENT_FUTURE,
                HOLDEMP,
                DEPTNAME,
                PJ_PRODUCEREGION,
                PRIORITYCODENAME,
                TMTT_R,
                WAFER_FACTOR,
                SYS_DATE,
                LEADFRAMEDESC,
                WAFERDESC
            FROM {WIP_VIEW}
            WHERE LOTID = :lotid
        """
        df = read_sql_df(sql, {'lotid': lotid})

        if df is None or df.empty:
            return None

        row = df.iloc[0]
        if len(df) > 1:
            row = row.copy()
            for col in ('LEADFRAMEDESC', 'WAFERDESC'):
                if col in df.columns:
                    vals = df[col].dropna().unique()
                    row[col] = ', '.join(str(v) for v in vals) if len(vals) > 0 else None
        return _build_lot_detail_response(row)
    except (DatabasePoolExhaustedError, DatabaseCircuitOpenError):
        raise
    except Exception as exc:
        logger.error(f"Lot detail query failed: {exc}")
        import traceback
        traceback.print_exc()
        return None


def _build_lot_detail_response(row) -> Dict[str, Any]:
    """Build lot detail response from DataFrame row."""
    # Helper to safely get value from row (handles NaN and missing columns)
    def safe_get(col, default=None):
        try:
            val = row.get(col)
            if pd.isna(val):
                return default
            return val
        except Exception:
            return default

    # Helper to safely get int value
    def safe_int(col, default=0):
        val = safe_get(col)
        if val is None:
            return default
        try:
            return int(val)
        except (ValueError, TypeError):
            return default

    # Helper to safely get float value
    def safe_float(col, default=0.0):
        val = safe_get(col)
        if val is None:
            return default
        try:
            return float(val)
        except (ValueError, TypeError):
            return default

    # Helper to format date value
    def format_date(col):
        val = safe_get(col)
        if val is None:
            return None
        try:
            return str(val)
        except Exception:
            return None

    # Compute WIP status
    equipment_count = safe_int('EQUIPMENTCOUNT')
    hold_count = safe_int('CURRENTHOLDCOUNT')

    if equipment_count > 0:
        wip_status = 'RUN'
    elif hold_count > 0:
        wip_status = 'HOLD'
    else:
        wip_status = 'QUEUE'

    return {
        'lotId': _safe_value(safe_get('LOTID')),
        'workorder': _safe_value(safe_get('WORKORDER')),
        'qty': safe_int('QTY'),
        'qty2': safe_int('QTY2') if safe_get('QTY2') is not None else None,
        'status': _safe_value(safe_get('STATUS')),
        'holdReason': _safe_value(safe_get('HOLDREASONNAME')),
        'holdCount': hold_count,
        'owner': _safe_value(safe_get('OWNER')),
        'startDate': format_date('STARTDATE'),
        'uts': _safe_value(safe_get('UTS')),
        'product': _safe_value(safe_get('PRODUCT')),
        'productLine': _safe_value(safe_get('PRODUCTLINENAME')),
        'packageLef': _safe_value(safe_get('PACKAGE_LEF')),
        'pjFunction': _safe_value(safe_get('PJ_FUNCTION')),
        'pjType': _safe_value(safe_get('PJ_TYPE')),
        'bop': _safe_value(safe_get('BOP')),
        'waferLotId': _safe_value(safe_get('FIRSTNAME')),
        'waferPn': _safe_value(safe_get('WAFERNAME')),
        'waferLotPrefix': _safe_value(safe_get('WAFERLOT')),
        'spec': _safe_value(safe_get('SPECNAME')),
        'specSequence': safe_int('SPECSEQUENCE') if safe_get('SPECSEQUENCE') is not None else None,
        'workcenter': _safe_value(safe_get('WORKCENTERNAME')),
        'workcenterSequence': safe_int('WORKCENTERSEQUENCE') if safe_get('WORKCENTERSEQUENCE') is not None else None,
        'workcenterGroup': _safe_value(safe_get('WORKCENTER_GROUP')),
        'workcenterShort': _safe_value(safe_get('WORKCENTER_SHORT')),
        'ageByDays': round(safe_float('AGEBYDAYS'), 2),
        'equipment': _safe_value(safe_get('EQUIPMENTS')),
        'equipmentCount': equipment_count,
        'workflow': _safe_value(safe_get('WORKFLOWNAME')),
        'dateCode': _safe_value(safe_get('DATECODE')),
        'leadframeName': _safe_value(safe_get('LEADFRAMENAME')),
        'leadframeOption': _safe_value(safe_get('LEADFRAMEOPTION')),
        'leadframeDesc': _safe_value(safe_get('LEADFRAMEDESC')),
        'compoundName': _safe_value(safe_get('COMNAME')),
        'waferDesc': _safe_value(safe_get('WAFERDESC')),
        'location': _safe_value(safe_get('LOCATIONNAME')),
        'ncrId': _safe_value(safe_get('EVENTNAME')),
        'ncrDate': format_date('OCCURRENCEDATE'),
        'releaseTime': format_date('RELEASETIME'),
        'releaseEmp': _safe_value(safe_get('RELEASEEMP')),
        'releaseComment': _safe_value(safe_get('RELEASEREASON')),
        'holdComment': _safe_value(safe_get('COMMENT_HOLD')),
        'comment': _safe_value(safe_get('CONTAINERCOMMENTS')),
        'commentDate': _safe_value(safe_get('COMMENT_DATE')),
        'commentEmp': _safe_value(safe_get('COMMENT_EMP')),
        'futureHoldComment': _safe_value(safe_get('COMMENT_FUTURE')),
        'holdEmp': _safe_value(safe_get('HOLDEMP')),
        'holdDept': _safe_value(safe_get('DEPTNAME')),
        'produceRegion': _safe_value(safe_get('PJ_PRODUCEREGION')),
        'priority': _safe_value(safe_get('PRIORITYCODENAME')),
        'tmttRemaining': _safe_value(safe_get('TMTT_R')),
        'dieConsumption': safe_int('WAFER_FACTOR') if safe_get('WAFER_FACTOR') is not None else None,
        'wipStatus': wip_status,
        'dataUpdateDate': format_date('SYS_DATE'),
        'fieldLabels': LOT_DETAIL_FIELD_LABELS
    }
