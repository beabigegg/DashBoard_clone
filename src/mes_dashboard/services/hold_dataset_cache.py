# -*- coding: utf-8 -*-
"""Two-phase hold-history dataset cache.

Primary query (POST /query) → Oracle → cache full hold/release DataFrame.
Supplementary view (GET /view) → read cache → pandas filter/derive.

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
from mes_dashboard.core.redis_client import get_key, get_redis_client
from mes_dashboard.core.redis_df_store import redis_load_df, redis_store_df
from mes_dashboard.services.filter_cache import get_workcenter_group as _get_wc_group
from mes_dashboard.services.hold_history_service import (
    _clean_text,
    _format_datetime,
    _safe_float,
    _safe_int,
)
from mes_dashboard.sql.filters import CommonFilters

logger = logging.getLogger("mes_dashboard.hold_dataset_cache")

from mes_dashboard.config.constants import CACHE_TTL_DATASET
_CACHE_TTL = CACHE_TTL_DATASET
_CACHE_MAX_SIZE = 8
_REDIS_NAMESPACE = "hold_dataset"
_DEFAULT_DETAIL_PER_PAGE = 20

_dataset_cache = ProcessLevelCache(ttl_seconds=_CACHE_TTL, max_size=_CACHE_MAX_SIZE)
register_process_cache("hold_dataset", _dataset_cache, "Hold Dataset (L1, 15min)")

_SQL_DIR = Path(__file__).resolve().parent.parent / "sql" / "hold_history"


# ============================================================
# SQL loading
# ============================================================


@lru_cache(maxsize=4)
def _load_sql(name: str) -> str:
    path = _SQL_DIR / f"{name}.sql"
    sql = path.read_text(encoding="utf-8")
    if "{{ NON_QUALITY_REASONS }}" in sql:
        sql = sql.replace(
            "{{ NON_QUALITY_REASONS }}",
            CommonFilters.get_non_quality_reasons_sql(),
        )
    return sql


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


def _store_query_dates(query_id: str, start_date: str, end_date: str) -> None:
    """Persist query date range in Redis for record_type='new' boundary computation."""
    client = get_redis_client()
    if client is None:
        return
    try:
        client.setex(
            get_key(f"{_REDIS_NAMESPACE}:{query_id}:dates"),
            _CACHE_TTL,
            json.dumps({"start": start_date, "end": end_date}),
        )
    except Exception:
        pass


def _get_query_dates(query_id: str) -> Optional[Dict[str, str]]:
    """Retrieve stored query date range from Redis."""
    client = get_redis_client()
    if client is None:
        return None
    try:
        raw = client.get(get_key(f"{_REDIS_NAMESPACE}:{query_id}:dates"))
        if raw:
            return json.loads(raw)
    except Exception:
        pass
    return None


def _get_cached_df(query_id: str) -> Optional[pd.DataFrame]:
    """Load DataFrame from Redis or spool on demand — NOT promoted to L1."""
    df = _redis_load_df(query_id)
    if df is not None:
        return df
    # Spool fallback (engine path writes spool instead of full Redis DataFrame)
    df = load_spooled_df(_REDIS_NAMESPACE, query_id)
    if df is not None:
        # Restore _QUERY_START/_QUERY_END for Pandas record_type='new' filter
        if "_QUERY_START" not in df.columns:
            dates = _get_query_dates(query_id)
            if dates:
                df = df.copy()
                df["_QUERY_START"] = pd.Timestamp(dates["start"])
                df["_QUERY_END"] = pd.Timestamp(dates["end"])
    return df


def _store_df(query_id: str, df: pd.DataFrame) -> None:
    """Write to Redis L2 only; L1 gets lightweight marker.

    Direct-path queries (≤10 days) are small — Redis is sufficient.
    DuckDB view path uses spool files from the engine path (long queries).
    """
    _dataset_cache.set(query_id, True)  # lightweight marker
    _redis_store_df(query_id, df)


# ============================================================
# Primary query
# ============================================================


def execute_primary_query(
    *,
    start_date: str,
    end_date: str,
    hold_type: str = "quality",
    record_type: str = "new",
) -> Dict[str, Any]:
    """Execute Oracle query -> cache DataFrame -> return structured result."""

    query_id = _make_query_id({"start_date": start_date, "end_date": end_date})

    cached_df = _get_cached_df(query_id)
    if cached_df is not None:
        logger.info("Hold dataset cache hit for query_id=%s", query_id)
    else:
        logger.info(
            "Hold dataset cache miss for query_id=%s, querying Oracle", query_id
        )

        from mes_dashboard.services.batch_query_engine import (
            decompose_by_time_range,
            execute_plan,
            merge_chunks_to_spool,
            compute_query_hash,
            should_decompose_by_time,
        )

        if should_decompose_by_time(start_date, end_date):
            # --- Engine path for long date ranges → stream to Parquet spool ---
            engine_chunks = decompose_by_time_range(start_date, end_date)
            engine_hash = compute_query_hash(
                {"start_date": start_date, "end_date": end_date}
            )
            base_sql = _load_sql("base_facts")

            def _run_hold_chunk(chunk, max_rows_per_chunk=None):
                params = {
                    "start_date": chunk["chunk_start"],
                    "end_date": chunk["chunk_end"],
                }
                result = read_sql_df(base_sql, params)
                return result if result is not None else pd.DataFrame()

            logger.info(
                "Engine activated for hold: %d chunks (query_id=%s)",
                len(engine_chunks), query_id,
            )
            execute_plan(
                engine_chunks, _run_hold_chunk,
                query_hash=engine_hash,
                cache_prefix="hold",
                chunk_ttl=_CACHE_TTL,
            )
            spool_tmp_path, spool_row_count = merge_chunks_to_spool(
                "hold",
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
                _store_query_dates(query_id, start_date, end_date)
                _loaded = load_spooled_df(_REDIS_NAMESPACE, query_id)
                df = _loaded if _loaded is not None else pd.DataFrame()
                if not df.empty and "_QUERY_START" not in df.columns:
                    df["_QUERY_START"] = pd.Timestamp(start_date)
                    df["_QUERY_END"] = pd.Timestamp(end_date)
            else:
                df = pd.DataFrame()
            # Spool already registered; skip Redis DataFrame store.
        else:
            # --- Direct path (short query) ---
            sql = _load_sql("base_facts")
            params = {"start_date": start_date, "end_date": end_date}
            df = read_sql_df(sql, params)
            if df is None:
                df = pd.DataFrame()
            if not df.empty:
                df["_QUERY_START"] = pd.Timestamp(start_date)
                df["_QUERY_END"] = pd.Timestamp(end_date)
                _store_df(query_id, df)

        cached_df = df

    views = _derive_all_views(
        cached_df,
        hold_type=hold_type,
        record_type=record_type,
        page=1,
        per_page=_DEFAULT_DETAIL_PER_PAGE,
    )

    # Release large DataFrame to free memory
    del cached_df

    return {"query_id": query_id, **views}


# ============================================================
# View (supplementary filtering on cache)
# ============================================================


def apply_view(
    *,
    query_id: str,
    hold_type: str = "quality",
    reason: Optional[str] = None,
    record_type: str = "new",
    duration_range: Optional[str] = None,
    page: int = 1,
    per_page: int = 50,
    _start_date: Optional[str] = None,
    _end_date: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Read cache -> apply filters -> return derived data. Returns None if expired.

    Tries DuckDB SQL runtime first (feature-flagged); falls back to Pandas.
    ``_start_date``/``_end_date`` are passed through to the SQL runtime for
    record_type='new' boundary computation.
    """
    resolved_start_date = _start_date
    resolved_end_date = _end_date
    if not resolved_start_date or not resolved_end_date:
        query_dates = _get_query_dates(query_id) or {}
        if not resolved_start_date:
            start = str(query_dates.get("start") or "").strip()
            resolved_start_date = start or None
        if not resolved_end_date:
            end = str(query_dates.get("end") or "").strip()
            resolved_end_date = end or None

    # ── Task 4.6: Try DuckDB SQL runtime path ─────────────────────────────
    try:
        from mes_dashboard.services.hold_history_sql_runtime import (
            try_compute_view_from_spool,
        )
        sql_result, sql_meta = try_compute_view_from_spool(
            query_id=query_id,
            hold_type=hold_type,
            reason=reason,
            record_type=record_type,
            duration_range=duration_range,
            page=page,
            per_page=per_page,
            start_date=resolved_start_date,
            end_date=resolved_end_date,
        )
        if sql_result is not None:
            return {**sql_result, "_meta": sql_meta}
        fallback_reason = sql_meta.get("view_sql_fallback_reason", "unknown")
        logger.debug(
            "hold apply_view: SQL runtime fallback (reason=%s query_id=%s)",
            fallback_reason, query_id,
        )
    except Exception as exc:
        logger.warning("hold apply_view: SQL runtime error: %s", exc)

    # ── Pandas fallback path ───────────────────────────────────────────────
    df = _get_cached_df(query_id)
    if df is None:
        return None

    return _derive_all_views(
        df,
        hold_type=hold_type,
        reason=reason,
        record_type=record_type,
        duration_range=duration_range,
        page=page,
        per_page=per_page,
    )


# ============================================================
# Master derivation
# ============================================================


def _derive_all_views(
    df: pd.DataFrame,
    *,
    hold_type: str = "quality",
    reason: Optional[str] = None,
    record_type: str = "new",
    duration_range: Optional[str] = None,
    page: int = 1,
    per_page: int = 50,
) -> Dict[str, Any]:
    """Derive trend, reason_pareto, duration, and list from cached DataFrame."""
    if df is None or df.empty:
        return _empty_views()

    # Trend uses full DF (no record_type/reason/duration filter, all hold_types)
    trend = _derive_trend(df)

    # Apply record_type filter for pareto, duration, list
    filtered = _apply_record_type_filter(df, record_type)

    # Apply hold_type filter
    if hold_type != "all":
        ht_value = "non-quality" if hold_type == "non-quality" else "quality"
        filtered = filtered[filtered["HOLD_TYPE"] == ht_value]

    reason_pareto = _derive_reason_pareto(filtered)
    duration = _derive_duration(filtered)

    # List: additional reason + duration_range filters
    list_df = filtered
    if reason:
        list_df = list_df[
            list_df["HOLDREASONNAME"].str.strip() == reason.strip()
        ]
    if duration_range:
        list_df = _apply_duration_range_filter(list_df, duration_range)

    detail = _derive_list(list_df, page=page, per_page=per_page)

    return {
        "trend": trend,
        "reason_pareto": reason_pareto,
        "duration": duration,
        "list": detail,
    }


def _empty_views() -> Dict[str, Any]:
    return {
        "trend": {"days": []},
        "reason_pareto": {"items": []},
        "duration": {"items": []},
        "list": {
            "items": [],
            "pagination": {
                "page": 1,
                "perPage": _DEFAULT_DETAIL_PER_PAGE,
                "total": 0,
                "totalPages": 1,
            },
        },
    }


# ============================================================
# Record-type & duration-range filters
# ============================================================


def _apply_record_type_filter(
    df: pd.DataFrame, record_type: str
) -> pd.DataFrame:
    if df is None or df.empty:
        return df

    types = {t.strip().lower() for t in str(record_type or "new").split(",")}
    if types >= {"new", "on_hold", "released"}:
        return df

    mask = pd.Series(False, index=df.index)

    if "new" in types:
        if "_QUERY_START" in df.columns and "_QUERY_END" in df.columns:
            qs = df["_QUERY_START"].iloc[0]
            qe = df["_QUERY_END"].iloc[0]
            mask |= (df["HOLD_DAY"] >= qs) & (df["HOLD_DAY"] <= qe)
        else:
            mask |= pd.Series(True, index=df.index)

    if "on_hold" in types:
        mask |= df["RELEASETXNDATE"].isna()

    if "released" in types:
        mask |= df["RELEASETXNDATE"].notna()

    return df[mask]


def _apply_duration_range_filter(
    df: pd.DataFrame, duration_range: str
) -> pd.DataFrame:
    if df is None or df.empty or not duration_range:
        return df

    hours = df["HOLD_HOURS"]
    if duration_range == "<4h":
        return df[hours < 4]
    if duration_range == "4-24h":
        return df[(hours >= 4) & (hours < 24)]
    if duration_range == "1-3d":
        return df[(hours >= 24) & (hours < 72)]
    if duration_range == ">3d":
        return df[hours >= 72]
    return df


# ============================================================
# Derivation: Trend
# ============================================================


def _derive_trend(df: pd.DataFrame) -> Dict[str, Any]:
    """Derive daily trend with quality / non_quality / all variants."""
    if df is None or df.empty:
        return {"days": []}

    if "_QUERY_START" in df.columns:
        start = pd.Timestamp(df["_QUERY_START"].iloc[0])
        end = pd.Timestamp(df["_QUERY_END"].iloc[0])
    else:
        start = df["HOLD_DAY"].min()
        end = df["HOLD_DAY"].max()

    dates = pd.date_range(start, end, freq="D")

    type_map: List[tuple] = [
        ("quality", "quality"),
        ("non_quality", "non-quality"),
        ("all", None),
    ]

    days: List[Dict[str, Any]] = []
    for d in dates:
        day_data: Dict[str, Any] = {"date": d.strftime("%Y-%m-%d")}

        for key, type_filter in type_map:
            tdf = df if type_filter is None else df[df["HOLD_TYPE"] == type_filter]

            if tdf.empty:
                day_data[key] = _empty_trend_metrics()
                continue

            # holdQty: total QTY on hold as of this day
            on_hold = (tdf["HOLD_DAY"] <= d) & (
                tdf["RELEASE_DAY"].isna() | (tdf["RELEASE_DAY"] > d)
            )
            hold_qty = _safe_int(tdf.loc[on_hold, "QTY"].sum())

            # newHoldQty: QTY of new holds arriving this day (dedup)
            new_mask = (tdf["HOLD_DAY"] == d) & (tdf["RN_HOLD_DAY"] == 1)
            new_hold_qty = _safe_int(tdf.loc[new_mask, "QTY"].sum())

            # releaseQty: QTY released on this day
            release_mask = tdf["RELEASE_DAY"] == d
            release_qty = _safe_int(tdf.loc[release_mask, "QTY"].sum())

            # futureHoldQty: QTY of future holds on this day
            future_mask = (
                (tdf["HOLD_DAY"] == d)
                & (tdf["IS_FUTURE_HOLD"] == 1)
                & (tdf["FUTURE_HOLD_FLAG"] == 1)
            )
            future_hold_qty = _safe_int(tdf.loc[future_mask, "QTY"].sum())

            day_data[key] = {
                "holdQty": hold_qty,
                "newHoldQty": new_hold_qty,
                "releaseQty": release_qty,
                "futureHoldQty": future_hold_qty,
            }

        days.append(day_data)

    return {"days": days}


def _empty_trend_metrics() -> Dict[str, int]:
    return {"holdQty": 0, "newHoldQty": 0, "releaseQty": 0, "futureHoldQty": 0}


# ============================================================
# Derivation: Reason Pareto
# ============================================================


def _derive_reason_pareto(df: pd.DataFrame) -> Dict[str, Any]:
    """Group by HOLDREASONNAME -> count, qty, pct, cumPct."""
    if df is None or df.empty:
        return {"items": []}

    grouped = (
        df.groupby("HOLDREASONNAME", sort=False)
        .agg(count=("CONTAINERID", "count"), qty=("QTY", "sum"))
        .reset_index()
    )
    grouped = grouped.sort_values("qty", ascending=False)
    total_qty = grouped["qty"].sum()

    items: List[Dict[str, Any]] = []
    cumulative = 0.0
    for _, row in grouped.iterrows():
        count = _safe_int(row["count"])
        qty = _safe_int(row["qty"])
        pct = round((qty / total_qty * 100) if total_qty > 0 else 0, 2)
        cumulative += pct
        items.append(
            {
                "reason": _clean_text(row["HOLDREASONNAME"]) or "(未填寫)",
                "count": count,
                "qty": qty,
                "pct": pct,
                "cumPct": round(cumulative, 2),
            }
        )

    return {"items": items}


# ============================================================
# Derivation: Duration
# ============================================================


def _derive_duration(df: pd.DataFrame) -> Dict[str, Any]:
    """Bucket released holds into <4h / 4-24h / 1-3d / >3d."""
    if df is None or df.empty:
        return {"items": []}

    released = df[df["RELEASETXNDATE"].notna()]
    if released.empty:
        return {"items": []}

    hours = released["HOLD_HOURS"]
    total_qty = _safe_int(released["QTY"].sum())

    buckets = [
        ("<4h", hours < 4),
        ("4-24h", (hours >= 4) & (hours < 24)),
        ("1-3d", (hours >= 24) & (hours < 72)),
        (">3d", hours >= 72),
    ]

    items: List[Dict[str, Any]] = []
    for label, mask in buckets:
        count = int(mask.sum())
        qty = _safe_int(released.loc[mask, "QTY"].sum())
        pct = round((qty / total_qty * 100) if total_qty > 0 else 0, 2)
        items.append({"range": label, "count": count, "qty": qty, "pct": pct})

    return {"items": items}


# ============================================================
# Derivation: Paginated list
# ============================================================


def _derive_list(
    df: pd.DataFrame,
    *,
    page: int = 1,
    per_page: int = 50,
) -> Dict[str, Any]:
    """Sort by HOLDTXNDATE desc and paginate."""
    if df is None or df.empty:
        return {
            "items": [],
            "pagination": {
                "page": 1,
                "perPage": per_page,
                "total": 0,
                "totalPages": 1,
            },
        }

    page = max(int(page), 1)
    per_page = min(max(int(per_page), 1), 200)

    sorted_df = df.sort_values("HOLDTXNDATE", ascending=False)
    total = len(sorted_df)
    total_pages = max((total + per_page - 1) // per_page, 1)
    offset = (page - 1) * per_page
    page_df = sorted_df.iloc[offset : offset + per_page]

    items: List[Dict[str, Any]] = []
    for _, row in page_df.iterrows():
        wc_name = _clean_text(row.get("WORKCENTERNAME"))
        wc_group = _get_wc_group(wc_name) if wc_name else None

        items.append(
            {
                "lotId": _clean_text(row.get("LOT_ID")),
                "workorder": _clean_text(row.get("PJ_WORKORDER")),
                "product": _clean_text(row.get("PRODUCTNAME")),
                "workcenter": wc_group or wc_name,
                "holdReason": _clean_text(row.get("HOLDREASONNAME")),
                "qty": _safe_int(row.get("QTY")),
                "holdDate": _format_datetime(row.get("HOLDTXNDATE")),
                "holdEmp": _clean_text(row.get("HOLDEMP")),
                "holdComment": _clean_text(row.get("HOLDCOMMENTS")),
                "releaseDate": _format_datetime(row.get("RELEASETXNDATE")),
                "releaseEmp": _clean_text(row.get("RELEASEEMP")),
                "releaseComment": _clean_text(row.get("RELEASECOMMENTS")),
                "holdHours": round(_safe_float(row.get("HOLD_HOURS")), 2),
                "ncr": _clean_text(row.get("NCRID")),
                "futureHoldComment": _clean_text(row.get("FUTUREHOLDCOMMENTS")),
            }
        )

    return {
        "items": items,
        "pagination": {
            "page": page,
            "perPage": per_page,
            "total": total,
            "totalPages": total_pages,
        },
    }
