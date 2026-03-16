# -*- coding: utf-8 -*-
"""Two-phase resource-history dataset cache.

Primary query (POST /query) → Oracle → cache full per-resource × per-day DataFrame.
Supplementary view (GET /view) → read cache → pandas derive kpi/trend/heatmap/comparison/detail.

Cache layers:
  L1: ProcessLevelCache (in-process, per-worker)
  L2: Redis (cross-worker, parquet bytes encoded as base64 string)
"""

from __future__ import annotations

import hashlib
import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from mes_dashboard.core.cache import ProcessLevelCache, register_process_cache
from mes_dashboard.core.database import read_sql_df_slow as read_sql_df
from mes_dashboard.core.query_spool_store import (
    QUERY_SPOOL_DIR,
    load_spooled_df,
    register_spool_file,
)
from mes_dashboard.core.redis_df_store import redis_load_df, redis_store_df

logger = logging.getLogger("mes_dashboard.resource_dataset_cache")

from mes_dashboard.config.constants import CACHE_TTL_DATASET
_CACHE_TTL = CACHE_TTL_DATASET
_CACHE_MAX_SIZE = 8
_REDIS_NAMESPACE = "resource_dataset"

_dataset_cache = ProcessLevelCache(ttl_seconds=_CACHE_TTL, max_size=_CACHE_MAX_SIZE)
register_process_cache(
    "resource_dataset", _dataset_cache, "Resource Dataset (L1, 15min)"
)

_SQL_DIR = Path(__file__).resolve().parent.parent / "sql" / "resource_history"


# ============================================================
# SQL loading
# ============================================================


@lru_cache(maxsize=4)
def _load_sql(name: str) -> str:
    path = _SQL_DIR / f"{name}.sql"
    return path.read_text(encoding="utf-8")


# ============================================================
# Query ID
# ============================================================


def _make_query_id(params: dict) -> str:
    """Deterministic hash from primary query params."""
    canonical = json.dumps(params, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


# ============================================================
# Redis L2 helpers (delegated to shared redis_df_store)
# ============================================================


def _redis_store_df(query_id: str, df: pd.DataFrame) -> None:
    redis_store_df(f"{_REDIS_NAMESPACE}:{query_id}", df, ttl=_CACHE_TTL)


def _redis_load_df(query_id: str) -> Optional[pd.DataFrame]:
    return redis_load_df(f"{_REDIS_NAMESPACE}:{query_id}")


# ============================================================
# Cache read (L1 -> L2 -> None)
# ============================================================


def _get_cached_df(query_id: str) -> Optional[pd.DataFrame]:
    """Load DataFrame from Redis or spool on demand — NOT promoted to L1."""
    marker = _dataset_cache.get(query_id)
    if marker is not None:
        # L1 marker exists — data is in Redis or spool
        pass
    df = _redis_load_df(query_id)
    if df is not None:
        return df
    # Spool fallback (engine path writes spool instead of full Redis DataFrame)
    df = load_spooled_df(_REDIS_NAMESPACE, query_id)
    return df


def _has_cached_df(query_id: str) -> bool:
    """Check if query_id has cached data (L1 marker or Redis key exists)."""
    if _dataset_cache.get(query_id) is not None:
        return True
    df = _redis_load_df(query_id)
    return df is not None


def _store_df(query_id: str, df: pd.DataFrame) -> None:
    """Store to Redis L2 only; L1 gets lightweight marker.

    Direct-path queries (≤10 days) are small — Redis is sufficient.
    DuckDB view path uses spool files from the engine path (long queries).
    """
    _dataset_cache.set(query_id, True)  # lightweight marker
    _redis_store_df(query_id, df)


# ============================================================
# Resource cache integration (reuse existing service)
# ============================================================


def _get_filtered_resources_and_lookup(
    *,
    workcenter_groups: Optional[List[str]] = None,
    families: Optional[List[str]] = None,
    resource_ids: Optional[List[str]] = None,
    is_production: bool = False,
    is_key: bool = False,
    is_monitor: bool = False,
) -> tuple:
    """Returns (resources_list, resource_lookup_dict, historyid_filter_sql)."""
    from mes_dashboard.services.resource_history_service import (
        _get_filtered_resources,
        _build_resource_lookup,
        _build_historyid_filter,
    )

    resources = _get_filtered_resources(
        workcenter_groups=workcenter_groups,
        families=families,
        resource_ids=resource_ids,
        is_production=is_production,
        is_key=is_key,
        is_monitor=is_monitor,
    )
    lookup = _build_resource_lookup(resources)
    historyid_filter = _build_historyid_filter(resources)
    return resources, lookup, historyid_filter


def _get_resource_lookup() -> Dict[str, Dict[str, Any]]:
    """Get current resource lookup from cache (for view-time dimension merge)."""
    from mes_dashboard.services.resource_history_service import (
        _get_filtered_resources,
        _build_resource_lookup,
    )

    resources = _get_filtered_resources()
    return _build_resource_lookup(resources)


def _get_workcenter_mapping() -> Dict[str, Dict[str, Any]]:
    from mes_dashboard.services.filter_cache import get_workcenter_mapping

    return get_workcenter_mapping() or {}


# ============================================================
# Primary query
# ============================================================


def execute_primary_query(
    *,
    start_date: str,
    end_date: str,
    granularity: str = "day",
    workcenter_groups: Optional[List[str]] = None,
    families: Optional[List[str]] = None,
    resource_ids: Optional[List[str]] = None,
    is_production: bool = False,
    is_key: bool = False,
    is_monitor: bool = False,
) -> Dict[str, Any]:
    """Execute single Oracle query -> cache DataFrame -> return structured result."""

    query_id_input = {
        "start_date": start_date,
        "end_date": end_date,
        "workcenter_groups": sorted(workcenter_groups or []),
        "families": sorted(families or []),
        "resource_ids": sorted(resource_ids or []),
        "is_production": is_production,
        "is_key": is_key,
        "is_monitor": is_monitor,
    }
    query_id = _make_query_id(query_id_input)

    cached_df = _get_cached_df(query_id)
    if cached_df is not None:
        logger.info("Resource dataset cache hit for query_id=%s", query_id)
    else:
        logger.info(
            "Resource dataset cache miss for query_id=%s, querying Oracle", query_id
        )

        resources, lookup, historyid_filter = _get_filtered_resources_and_lookup(
            workcenter_groups=workcenter_groups,
            families=families,
            resource_ids=resource_ids,
            is_production=is_production,
            is_key=is_key,
            is_monitor=is_monitor,
        )

        if not resources:
            return {
                "query_id": query_id,
                "summary": _empty_summary(),
                "detail": _empty_detail(),
            }

        from mes_dashboard.services.batch_query_engine import (
            decompose_by_time_range,
            execute_plan,
            merge_chunks_to_spool,
            compute_query_hash,
            should_decompose_by_time,
        )

        base_sql = _load_sql("base_facts")
        base_sql = base_sql.replace("{{ HISTORYID_FILTER }}", historyid_filter)

        if should_decompose_by_time(start_date, end_date):
            # --- Engine path for long date ranges → stream to Parquet spool ---
            engine_chunks = decompose_by_time_range(start_date, end_date)
            engine_hash = compute_query_hash(query_id_input)

            def _run_resource_chunk(chunk, max_rows_per_chunk=None):
                params = {
                    "start_date": chunk["chunk_start"],
                    "end_date": chunk["chunk_end"],
                }
                result = read_sql_df(base_sql, params)
                return result if result is not None else pd.DataFrame()

            logger.info(
                "Engine activated for resource: %d chunks (query_id=%s)",
                len(engine_chunks), query_id,
            )
            execute_plan(
                engine_chunks, _run_resource_chunk,
                query_hash=engine_hash,
                cache_prefix="resource",
                chunk_ttl=_CACHE_TTL,
            )
            spool_tmp_path, spool_row_count = merge_chunks_to_spool(
                "resource",
                engine_hash,
                spool_dir=QUERY_SPOOL_DIR,
            )
            if spool_tmp_path is not None:
                register_spool_file(
                    _REDIS_NAMESPACE,
                    query_id,
                    spool_tmp_path,
                    spool_row_count,
                    ttl_seconds=_CACHE_TTL,
                )
                _dataset_cache.set(query_id, True)  # L1 marker
                _loaded = load_spooled_df(_REDIS_NAMESPACE, query_id)
                df = _loaded if _loaded is not None else pd.DataFrame()
            else:
                df = pd.DataFrame()
            # Spool already registered; skip Redis DataFrame store.
        else:
            # --- Direct path (short query) ---
            params = {"start_date": start_date, "end_date": end_date}
            df = read_sql_df(base_sql, params)
            if df is None:
                df = pd.DataFrame()
            if not df.empty:
                _store_df(query_id, df)

        cached_df = df

    resource_lookup = _get_resource_lookup()
    wc_mapping = _get_workcenter_mapping()

    summary = _derive_summary(cached_df, resource_lookup, wc_mapping, granularity)
    detail = _derive_detail(cached_df, resource_lookup, wc_mapping)

    # Release large DataFrame to free memory
    del cached_df

    return {
        "query_id": query_id,
        "summary": summary,
        "detail": detail,
    }


# ============================================================
# View (supplementary — cache only)
# ============================================================


def apply_view(
    *,
    query_id: str,
    granularity: str = "day",
) -> Optional[Dict[str, Any]]:
    """Read cache -> derive views. Returns None if expired.

    Tries DuckDB SQL runtime first (feature-flagged); falls back to Pandas.
    """
    # ── Task 3.7: Try DuckDB SQL runtime path ─────────────────────────────
    try:
        from mes_dashboard.services.resource_history_sql_runtime import (
            try_compute_view_from_spool,
        )
        sql_result, sql_meta = try_compute_view_from_spool(
            query_id=query_id,
            granularity=granularity,
        )
        if sql_result is not None:
            return {**sql_result, "_meta": sql_meta}
        fallback_reason = sql_meta.get("view_sql_fallback_reason", "unknown")
        logger.debug(
            "resource apply_view: SQL runtime fallback (reason=%s query_id=%s)",
            fallback_reason, query_id,
        )
    except Exception as exc:
        logger.warning("resource apply_view: SQL runtime error: %s", exc)

    # ── Pandas fallback path ───────────────────────────────────────────────
    df = _get_cached_df(query_id)
    if df is None:
        return None

    resource_lookup = _get_resource_lookup()
    wc_mapping = _get_workcenter_mapping()

    summary = _derive_summary(df, resource_lookup, wc_mapping, granularity)
    detail = _derive_detail(df, resource_lookup, wc_mapping)

    return {
        "summary": summary,
        "detail": detail,
    }


# ============================================================
# Master derivation
# ============================================================


def _derive_summary(
    df: pd.DataFrame,
    resource_lookup: Dict[str, Dict[str, Any]],
    wc_mapping: Dict[str, Dict[str, Any]],
    granularity: str,
) -> Dict[str, Any]:
    if df is None or df.empty:
        return _empty_summary()

    return {
        "kpi": _derive_kpi(df),
        "trend": _derive_trend(df, granularity),
        "heatmap": _derive_heatmap(df, resource_lookup, wc_mapping, granularity),
        "workcenter_comparison": _derive_comparison(df, resource_lookup, wc_mapping),
    }


def _empty_summary() -> Dict[str, Any]:
    return {
        "kpi": _empty_kpi(),
        "trend": [],
        "heatmap": [],
        "workcenter_comparison": [],
    }


def _empty_detail() -> Dict[str, Any]:
    return {"data": [], "total": 0, "truncated": False, "max_records": None}


def _empty_kpi() -> Dict[str, Any]:
    return {
        "ou_pct": 0,
        "availability_pct": 0,
        "prd_hours": 0,
        "prd_pct": 0,
        "sby_hours": 0,
        "sby_pct": 0,
        "udt_hours": 0,
        "udt_pct": 0,
        "sdt_hours": 0,
        "sdt_pct": 0,
        "egt_hours": 0,
        "egt_pct": 0,
        "nst_hours": 0,
        "nst_pct": 0,
        "machine_count": 0,
    }


# ============================================================
# Helpers (reuse existing formulas)
# ============================================================


def _sf(value, default=0.0) -> float:
    """Safe float."""
    if value is None or pd.isna(value):
        return default
    return float(value)


def _calc_ou_pct(prd, sby, udt, sdt, egt) -> float:
    denom = prd + sby + udt + sdt + egt
    return round(prd / denom * 100, 1) if denom > 0 else 0


def _calc_avail_pct(prd, sby, udt, sdt, egt, nst) -> float:
    num = prd + sby + egt
    denom = prd + sby + egt + sdt + udt + nst
    return round(num / denom * 100, 1) if denom > 0 else 0


def _status_pct(val, total) -> float:
    return round(val / total * 100, 1) if total > 0 else 0


def _trunc_date(dt, granularity: str) -> str:
    """Truncate a date value to the given granularity period string."""
    if pd.isna(dt):
        return ""
    ts = pd.Timestamp(dt)
    if granularity == "year":
        return ts.strftime("%Y")
    if granularity == "month":
        return ts.strftime("%Y-%m")
    if granularity == "week":
        return (ts - pd.Timedelta(days=ts.weekday())).strftime("%Y-%m-%d")
    return ts.strftime("%Y-%m-%d")


# ============================================================
# Derivation: KPI
# ============================================================


def _derive_kpi(df: pd.DataFrame) -> Dict[str, Any]:
    if df is None or df.empty:
        return _empty_kpi()

    prd = _sf(df["PRD_HOURS"].sum())
    sby = _sf(df["SBY_HOURS"].sum())
    udt = _sf(df["UDT_HOURS"].sum())
    sdt = _sf(df["SDT_HOURS"].sum())
    egt = _sf(df["EGT_HOURS"].sum())
    nst = _sf(df["NST_HOURS"].sum())
    total = prd + sby + udt + sdt + egt + nst
    machine_count = int(df["HISTORYID"].nunique())

    return {
        "ou_pct": _calc_ou_pct(prd, sby, udt, sdt, egt),
        "availability_pct": _calc_avail_pct(prd, sby, udt, sdt, egt, nst),
        "prd_hours": round(prd, 1),
        "prd_pct": _status_pct(prd, total),
        "sby_hours": round(sby, 1),
        "sby_pct": _status_pct(sby, total),
        "udt_hours": round(udt, 1),
        "udt_pct": _status_pct(udt, total),
        "sdt_hours": round(sdt, 1),
        "sdt_pct": _status_pct(sdt, total),
        "egt_hours": round(egt, 1),
        "egt_pct": _status_pct(egt, total),
        "nst_hours": round(nst, 1),
        "nst_pct": _status_pct(nst, total),
        "machine_count": machine_count,
    }


# ============================================================
# Derivation: Trend
# ============================================================


def _derive_trend(df: pd.DataFrame, granularity: str) -> List[Dict[str, Any]]:
    if df is None or df.empty:
        return []

    df = df.copy()
    df["_period"] = df["DATA_DATE"].apply(lambda d: _trunc_date(d, granularity))

    grouped = (
        df.groupby("_period", sort=True)
        .agg(
            PRD_HOURS=("PRD_HOURS", "sum"),
            SBY_HOURS=("SBY_HOURS", "sum"),
            UDT_HOURS=("UDT_HOURS", "sum"),
            SDT_HOURS=("SDT_HOURS", "sum"),
            EGT_HOURS=("EGT_HOURS", "sum"),
            NST_HOURS=("NST_HOURS", "sum"),
        )
        .reset_index()
    )

    items: List[Dict[str, Any]] = []
    for _, row in grouped.iterrows():
        prd = _sf(row["PRD_HOURS"])
        sby = _sf(row["SBY_HOURS"])
        udt = _sf(row["UDT_HOURS"])
        sdt = _sf(row["SDT_HOURS"])
        egt = _sf(row["EGT_HOURS"])
        nst = _sf(row["NST_HOURS"])
        items.append(
            {
                "date": row["_period"],
                "ou_pct": _calc_ou_pct(prd, sby, udt, sdt, egt),
                "availability_pct": _calc_avail_pct(prd, sby, udt, sdt, egt, nst),
                "prd_hours": round(prd, 1),
                "sby_hours": round(sby, 1),
                "udt_hours": round(udt, 1),
                "sdt_hours": round(sdt, 1),
                "egt_hours": round(egt, 1),
                "nst_hours": round(nst, 1),
            }
        )

    return items


# ============================================================
# Derivation: Heatmap
# ============================================================


def _derive_heatmap(
    df: pd.DataFrame,
    resource_lookup: Dict[str, Dict[str, Any]],
    wc_mapping: Dict[str, Dict[str, Any]],
    granularity: str,
) -> List[Dict[str, Any]]:
    if df is None or df.empty:
        return []

    rows: List[Dict[str, Any]] = []
    wc_seq_map: Dict[str, int] = {}

    for _, row in df.iterrows():
        historyid = row["HISTORYID"]
        resource_info = resource_lookup.get(historyid, {})
        if not resource_info:
            continue

        wc_name = resource_info.get("WORKCENTERNAME", "")
        if not wc_name:
            continue

        wc_info = wc_mapping.get(wc_name, {})
        wc_group = wc_info.get("group", wc_name)
        wc_seq = wc_info.get("sequence", 999)
        wc_seq_map[wc_group] = wc_seq
        date_str = _trunc_date(row["DATA_DATE"], granularity)

        rows.append(
            {
                "wc": wc_group,
                "date": date_str,
                "prd": _sf(row["PRD_HOURS"]),
                "sby": _sf(row["SBY_HOURS"]),
                "udt": _sf(row["UDT_HOURS"]),
                "sdt": _sf(row["SDT_HOURS"]),
                "egt": _sf(row["EGT_HOURS"]),
            }
        )

    if not rows:
        return []

    tmp = pd.DataFrame(rows)
    agg = (
        tmp.groupby(["wc", "date"], sort=False)
        .agg(prd=("prd", "sum"), sby=("sby", "sum"), udt=("udt", "sum"), sdt=("sdt", "sum"), egt=("egt", "sum"))
        .reset_index()
    )

    items: List[Dict[str, Any]] = []
    for _, r in agg.iterrows():
        items.append(
            {
                "workcenter": r["wc"],
                "workcenter_seq": wc_seq_map.get(r["wc"], 999),
                "date": r["date"],
                "ou_pct": _calc_ou_pct(r["prd"], r["sby"], r["udt"], r["sdt"], r["egt"]),
            }
        )

    items.sort(key=lambda x: (x["workcenter_seq"], x["date"] or ""))
    return items


# ============================================================
# Derivation: Workcenter Comparison
# ============================================================


def _derive_comparison(
    df: pd.DataFrame,
    resource_lookup: Dict[str, Dict[str, Any]],
    wc_mapping: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    if df is None or df.empty:
        return []

    # Aggregate by HISTORYID first
    by_resource = (
        df.groupby("HISTORYID", sort=False)
        .agg(
            prd=("PRD_HOURS", "sum"),
            sby=("SBY_HOURS", "sum"),
            udt=("UDT_HOURS", "sum"),
            sdt=("SDT_HOURS", "sum"),
            egt=("EGT_HOURS", "sum"),
        )
        .reset_index()
    )

    # Then aggregate by workcenter group
    agg: Dict[str, Dict[str, float]] = {}
    for _, row in by_resource.iterrows():
        historyid = row["HISTORYID"]
        resource_info = resource_lookup.get(historyid, {})
        if not resource_info:
            continue

        wc_name = resource_info.get("WORKCENTERNAME", "")
        if not wc_name:
            continue

        wc_info = wc_mapping.get(wc_name, {})
        wc_group = wc_info.get("group", wc_name)

        if wc_group not in agg:
            agg[wc_group] = {"prd": 0, "sby": 0, "udt": 0, "sdt": 0, "egt": 0, "mc": 0}

        agg[wc_group]["prd"] += _sf(row["prd"])
        agg[wc_group]["sby"] += _sf(row["sby"])
        agg[wc_group]["udt"] += _sf(row["udt"])
        agg[wc_group]["sdt"] += _sf(row["sdt"])
        agg[wc_group]["egt"] += _sf(row["egt"])
        agg[wc_group]["mc"] += 1

    items = [
        {
            "workcenter": wc,
            "ou_pct": _calc_ou_pct(d["prd"], d["sby"], d["udt"], d["sdt"], d["egt"]),
            "prd_hours": round(d["prd"], 1),
            "machine_count": d["mc"],
        }
        for wc, d in agg.items()
    ]
    items.sort(key=lambda x: x["ou_pct"], reverse=True)
    return items


# ============================================================
# Derivation: Detail
# ============================================================


def _derive_detail(
    df: pd.DataFrame,
    resource_lookup: Dict[str, Dict[str, Any]],
    wc_mapping: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    if df is None or df.empty:
        return _empty_detail()

    by_resource = (
        df.groupby("HISTORYID", sort=False)
        .agg(
            PRD_HOURS=("PRD_HOURS", "sum"),
            SBY_HOURS=("SBY_HOURS", "sum"),
            UDT_HOURS=("UDT_HOURS", "sum"),
            SDT_HOURS=("SDT_HOURS", "sum"),
            EGT_HOURS=("EGT_HOURS", "sum"),
            NST_HOURS=("NST_HOURS", "sum"),
            TOTAL_HOURS=("TOTAL_HOURS", "sum"),
        )
        .reset_index()
    )

    data: List[Dict[str, Any]] = []
    for _, row in by_resource.iterrows():
        historyid = row["HISTORYID"]
        resource_info = resource_lookup.get(historyid, {})
        if not resource_info:
            continue

        prd = _sf(row["PRD_HOURS"])
        sby = _sf(row["SBY_HOURS"])
        udt = _sf(row["UDT_HOURS"])
        sdt = _sf(row["SDT_HOURS"])
        egt = _sf(row["EGT_HOURS"])
        nst = _sf(row["NST_HOURS"])
        total = _sf(row["TOTAL_HOURS"])

        wc_name = resource_info.get("WORKCENTERNAME", "")
        wc_info = wc_mapping.get(wc_name, {})
        wc_group = wc_info.get("group", wc_name)
        wc_seq = wc_info.get("sequence", 999)
        family = resource_info.get("RESOURCEFAMILYNAME", "")
        resource_name = resource_info.get("RESOURCENAME", "")

        data.append(
            {
                "workcenter": wc_group,
                "workcenter_seq": wc_seq,
                "family": family or "",
                "resource": resource_name or "",
                "ou_pct": _calc_ou_pct(prd, sby, udt, sdt, egt),
                "availability_pct": _calc_avail_pct(prd, sby, udt, sdt, egt, nst),
                "prd_hours": round(prd, 1),
                "prd_pct": _status_pct(prd, total),
                "sby_hours": round(sby, 1),
                "sby_pct": _status_pct(sby, total),
                "udt_hours": round(udt, 1),
                "udt_pct": _status_pct(udt, total),
                "sdt_hours": round(sdt, 1),
                "sdt_pct": _status_pct(sdt, total),
                "egt_hours": round(egt, 1),
                "egt_pct": _status_pct(egt, total),
                "nst_hours": round(nst, 1),
                "nst_pct": _status_pct(nst, total),
                "machine_count": 1,
            }
        )

    data.sort(key=lambda x: (x["workcenter_seq"], x["family"], x["resource"]))

    return {
        "data": data,
        "total": len(data),
        "truncated": False,
        "max_records": None,
    }
