# -*- coding: utf-8 -*-
"""Material trace service — bidirectional LOT/material query."""

from __future__ import annotations

import csv
import io
import json
import logging
import os
from decimal import Decimal
from typing import Any, Dict, Generator, List, Optional

import pandas as pd

from mes_dashboard.core.database import read_sql_df, read_sql_df_slow, read_sql_df_slow_iter
from mes_dashboard.core.interactive_memory_guard import (
    enforce_dataset_memory_guard,
    maybe_gc_collect,
)
from mes_dashboard.core.query_quality_contract import (
    QUALITY_SCOPE_EXPORT,
    QUALITY_SCOPE_QUERY,
    QUALITY_STATUS_COMPLETE,
    QUALITY_STATUS_PARTIAL,
    QUALITY_STATUS_TRUNCATED,
    build_quality_meta,
    normalize_quality_meta,
)
from mes_dashboard.core.redis_client import get_key, get_redis_client
from mes_dashboard.core.query_spool_store import load_spooled_df, store_spooled_df

MATERIAL_TRACE_QUEUE = os.getenv("TRACE_WORKER_QUEUE", "trace-events")
from mes_dashboard.services.batch_query_engine import compute_query_hash
from mes_dashboard.services.filter_cache import (
    get_workcenter_mapping,
    get_workcenters_for_groups,
)
from mes_dashboard.sql import QueryBuilder, SQLLoader

logger = logging.getLogger("mes_dashboard.material_trace")

# Safeguard: max DataFrame memory (MB) before aborting — same pattern as batch_query_engine
_MAX_RESULT_MB = int(os.getenv("MATERIAL_TRACE_MAX_RESULT_MB", "256"))

# Safeguard: IN-clause batch size — Oracle has practical limits on large IN lists
_IN_BATCH_SIZE = 1000

from mes_dashboard.config.constants import CACHE_TTL_MATERIAL_TRACE
_CACHE_TTL = CACHE_TTL_MATERIAL_TRACE
_META_SUFFIX = ":meta"

_CSV_COLUMNS = {
    "CONTAINERNAME": "LOT ID",
    "PJ_WORKORDER": "工單",
    "WORKCENTER_GROUP": "站群組",
    "WORKCENTERNAME": "站點",
    "MATERIALPARTNAME": "料號",
    "MATERIALLOTNAME": "物料批號",
    "VENDORLOTNUMBER": "供應商批號",
    "QTYREQUIRED": "應領量",
    "QTYCONSUMED": "實際消耗",
    "EQUIPMENTNAME": "機台",
    "TXNDATE": "交易日期",
    "PRIMARY_CATEGORY": "主分類",
    "SECONDARY_CATEGORY": "副分類",
}


# ============================================================
# Wildcard helpers (same pattern as query_tool_service)
# ============================================================


def _normalize_wildcard_token(value: str) -> str:
    """Normalize user wildcard syntax: * → %."""
    return str(value or "").replace("*", "%")


def _is_pattern_token(value: str) -> bool:
    token = _normalize_wildcard_token(value)
    return "%" in token or "_" in token


def _add_exact_or_pattern_condition(
    builder: QueryBuilder,
    column: str,
    values: List[str],
) -> None:
    """Add IN + LIKE mixed condition supporting exact and wildcard tokens.

    Replicates the proven pattern from query_tool_service.
    """
    if not values:
        return

    col_expr = f"NVL({column}, '')"
    conditions: List[str] = []

    exact_tokens = [v for v in values if not _is_pattern_token(v)]
    pattern_tokens = [v for v in values if _is_pattern_token(v)]

    if exact_tokens:
        placeholders: List[str] = []
        for token in exact_tokens:
            param = builder._next_param()
            placeholders.append(f":{param}")
            builder.params[param] = token
        conditions.append(f"{col_expr} IN ({', '.join(placeholders)})")

    for token in pattern_tokens:
        param = builder._next_param()
        builder.params[param] = _normalize_wildcard_token(token)
        conditions.append(f"{col_expr} LIKE :{param} ESCAPE '\\'")

    if conditions:
        builder.add_condition(f"({' OR '.join(conditions)})")


# ============================================================
# Shared helpers
# ============================================================


def _enrich_workcenter_group(df: pd.DataFrame) -> pd.DataFrame:
    """Add WORKCENTER_GROUP column based on filter_cache mapping."""
    df = df.copy()
    mapping = get_workcenter_mapping()
    if mapping and "WORKCENTERNAME" in df.columns:
        df["WORKCENTER_GROUP"] = df["WORKCENTERNAME"].map(
            lambda wc: (mapping.get(wc) or {}).get("group", "")
        )
    else:
        df["WORKCENTER_GROUP"] = ""
    return df


def _resolve_workcenter_names(workcenter_groups: Optional[List[str]]) -> Optional[List[str]]:
    """Resolve group names to a flat list of WORKCENTERNAME values."""
    if not workcenter_groups:
        return None
    names = get_workcenters_for_groups(workcenter_groups)
    return names or None


def _resolve_container_ids(
    lot_names: List[str],
) -> tuple[List[str], Dict[str, str], List[str]]:
    """Batch-resolve CONTAINERNAME → CONTAINERID (supports wildcards).

    Returns:
        (container_ids, name_to_id_map, unresolved_names)
        Note: wildcard tokens are never reported as "unresolved".
    """
    builder = QueryBuilder(base_sql=SQLLoader.load("material_trace/resolve_container_ids"))
    _add_exact_or_pattern_condition(builder, "c.CONTAINERNAME", lot_names)
    sql, params = builder.build()

    df = read_sql_df(sql, params)
    if df is None or df.empty:
        # Only exact tokens can be "unresolved"
        exact_unresolved = [n for n in lot_names if not _is_pattern_token(n)]
        return [], {}, exact_unresolved

    name_to_id: Dict[str, str] = {}
    for _, row in df.iterrows():
        name_to_id[str(row["CONTAINERNAME"])] = str(row["CONTAINERID"])

    resolved_ids = list(name_to_id.values())
    # Only report unresolved for exact tokens (wildcards can match 0 rows legitimately)
    unresolved = [n for n in lot_names if not _is_pattern_token(n) and n not in name_to_id]
    return resolved_ids, name_to_id, unresolved


def _check_memory_guard(df: pd.DataFrame, *, query_id: str = "") -> None:
    """Raise if DataFrame exceeds memory / RSS thresholds.

    Delegates to the shared interactive_memory_guard for two-fence protection.
    Kept as a thin wrapper so existing call-sites remain unchanged.
    """
    enforce_dataset_memory_guard(
        df,
        operation="物料追溯查詢",
        query_id=query_id,
        max_input_mb=float(_MAX_RESULT_MB),
        max_projected_rss_mb=1100.0,
        working_set_factor=1.8,
    )


def _execute_batched_query(
    sql_name: str,
    column: str,
    values: List[str],
    wc_names: Optional[List[str]] = None,
    *,
    allow_patterns: bool = True,
) -> pd.DataFrame:
    """Execute query in batches, using slow-query channel.

    When allow_patterns=True, values containing * or % are sent as LIKE clauses.
    When allow_patterns=False (e.g. resolved CONTAINERIDs), all values are treated
    as exact IN matches regardless of content.
    """
    base_sql = SQLLoader.load(sql_name)
    chunks: list[pd.DataFrame] = []

    if allow_patterns:
        exact_tokens = [v for v in values if not _is_pattern_token(v)]
        pattern_tokens = [v for v in values if _is_pattern_token(v)]
    else:
        exact_tokens = list(values)
        pattern_tokens = []

    # Batch exact tokens; include pattern tokens once in the first batch
    for i in range(0, max(len(exact_tokens), 1), _IN_BATCH_SIZE):
        batch = exact_tokens[i : i + _IN_BATCH_SIZE]
        combined = batch + (pattern_tokens if i == 0 else [])
        if not combined:
            continue

        builder = QueryBuilder(base_sql=base_sql)
        _add_exact_or_pattern_condition(builder, column, combined)
        if wc_names:
            builder.add_in_condition("m.WORKCENTERNAME", wc_names)

        sql, params = builder.build()
        df = read_sql_df_slow(sql, params)
        if df is not None and not df.empty:
            chunks.append(df)

    if not chunks:
        return pd.DataFrame()

    result = pd.concat(chunks, ignore_index=True) if len(chunks) > 1 else chunks[0]
    # Deduplicate — wildcards across batches may produce overlapping rows
    if len(chunks) > 1 and "CONTAINERID" in result.columns:
        result = result.drop_duplicates(subset=["CONTAINERID", "MATERIALLOTNAME", "WORKCENTERNAME", "TXNDATE"], ignore_index=True)
    _check_memory_guard(result)
    return result


def _execute_batched_query_to_parquet(
    sql_name: str,
    column: str,
    values: List[str],
    dest_path: "Any",
    wc_names: Optional[List[str]] = None,
    *,
    allow_patterns: bool = True,
    mapping: Optional[Dict[str, Any]] = None,
) -> int:
    """Execute query in batches and stream results directly to a parquet file.

    Uses ``read_sql_df_slow_iter`` + ``pyarrow.ParquetWriter`` so no large
    DataFrame is accumulated in memory.  ``WORKCENTER_GROUP`` is mapped
    inline per chunk.  ``_check_memory_guard()`` is NOT called (spool-safe
    path).  Writes an empty parquet when there are no rows.

    Returns the total row count written.
    """
    import pyarrow as pa
    import pyarrow.parquet as pq
    from pathlib import Path as _Path

    if mapping is None:
        mapping = get_workcenter_mapping() or {}

    base_sql = SQLLoader.load(sql_name)
    dest_path = _Path(str(dest_path))
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    if allow_patterns:
        exact_tokens = [v for v in values if not _is_pattern_token(v)]
        pattern_tokens = [v for v in values if _is_pattern_token(v)]
    else:
        exact_tokens = list(values)
        pattern_tokens = []

    writer = None
    schema = None
    total_rows = 0

    try:
        for i in range(0, max(len(exact_tokens), 1), _IN_BATCH_SIZE):
            batch = exact_tokens[i:i + _IN_BATCH_SIZE]
            combined = batch + (pattern_tokens if i == 0 else [])
            if not combined:
                continue

            builder = QueryBuilder(base_sql=base_sql)
            _add_exact_or_pattern_condition(builder, column, combined)
            if wc_names:
                builder.add_in_condition("m.WORKCENTERNAME", wc_names)

            sql, params = builder.build()
            for columns, rows in read_sql_df_slow_iter(sql, params):
                if not rows:
                    continue

                col_arrays: Dict[str, list] = {
                    col: [float(v) if isinstance(v, Decimal) else v for v in (row[j] for row in rows)]
                    for j, col in enumerate(columns)
                }

                # Inline WORKCENTER_GROUP enrichment
                if mapping and "WORKCENTERNAME" in col_arrays:
                    col_arrays["WORKCENTER_GROUP"] = [
                        (mapping.get(wc) or {}).get("group", "") for wc in col_arrays["WORKCENTERNAME"]
                    ]
                else:
                    col_arrays.setdefault("WORKCENTER_GROUP", [""] * len(rows))

                table = pa.table(col_arrays)
                if writer is None:
                    schema = table.schema
                    writer = pq.ParquetWriter(dest_path, schema)
                else:
                    try:
                        table = table.cast(schema, safe=False)
                    except Exception:
                        pass
                writer.write_table(table)
                total_rows += len(rows)
    finally:
        if writer is not None:
            writer.close()

    if writer is None:
        pq.write_table(pa.table({}), dest_path)

    return total_rows


def _paginate(df: pd.DataFrame, page: int, per_page: int) -> Dict[str, Any]:
    """Apply pagination to a DataFrame and return paginated dict."""
    total = len(df)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = min(page, total_pages)
    start = (page - 1) * per_page
    end = start + per_page
    page_df = df.iloc[start:end]

    # Replace NaN/NaT with None so JSON serialization produces null (not NaN).
    # Must convert to object dtype first — float64 columns coerce None back to NaN.
    page_df = page_df.astype(object).where(page_df.notna(), None)

    return {
        "rows": page_df.to_dict("records"),
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": total_pages,
        },
    }


def _build_query_quality_meta(
    *,
    truncated: bool = False,
    observed_rows: Optional[int] = None,
    max_rows: Optional[int] = None,
    reasons: Optional[List[str]] = None,
) -> Dict[str, Any]:
    return build_quality_meta(
        status=QUALITY_STATUS_TRUNCATED if truncated else QUALITY_STATUS_COMPLETE,
        scope=QUALITY_SCOPE_QUERY,
        reasons=reasons or ([] if not truncated else ["row_guard_truncated"]),
        observed_rows=observed_rows,
        max_rows=max_rows,
    )


def _to_export_quality_meta(
    query_quality_meta: Optional[Dict[str, Any]],
    *,
    observed_rows: int,
    max_rows: Optional[int] = None,
    reasons: Optional[List[str]] = None,
) -> Dict[str, Any]:
    base = normalize_quality_meta(query_quality_meta, default_scope=QUALITY_SCOPE_QUERY)
    base_status = str(base.get("status") or QUALITY_STATUS_COMPLETE).lower()
    merged_reasons = list(base.get("reasons") or [])
    for reason in reasons or []:
        if reason and reason not in merged_reasons:
            merged_reasons.append(reason)

    status = base_status
    if max_rows is not None:
        status = QUALITY_STATUS_TRUNCATED
    elif base_status not in {
        QUALITY_STATUS_COMPLETE,
        QUALITY_STATUS_TRUNCATED,
        QUALITY_STATUS_PARTIAL,
    }:
        status = QUALITY_STATUS_COMPLETE

    resolved_max_rows = max_rows if max_rows is not None else base.get("max_rows")
    resolved_observed_rows = (
        observed_rows
        if max_rows is not None
        else (base.get("observed_rows") or observed_rows)
    )

    return build_quality_meta(
        status=status,
        scope=QUALITY_SCOPE_EXPORT,
        reasons=merged_reasons,
        observed_rows=resolved_observed_rows,
        max_rows=resolved_max_rows,
        failed_domains=base.get("failed_domains") or [],
        failed_ranges=base.get("failed_ranges") or [],
        truncated_domains=base.get("truncated_domains") or [],
    )


def _meta_cache_key(cache_key: str) -> str:
    return f"{cache_key}{_META_SUFFIX}"


def _try_load_cached_meta(cache_key: str) -> Dict[str, Any]:
    client = get_redis_client()
    if client is None:
        return {}

    try:
        raw = client.get(get_key(_meta_cache_key(cache_key)))
    except Exception as exc:
        logger.debug("Redis meta load failed (%s): %s", cache_key, exc)
        return {}

    if not raw:
        return {}

    try:
        parsed = json.loads(raw)
    except Exception:
        return {}

    if not isinstance(parsed, dict):
        return {}

    return {
        "meta": parsed.get("meta") if isinstance(parsed.get("meta"), dict) else {},
        "quality_meta": normalize_quality_meta(
            parsed.get("quality_meta"),
            default_scope=QUALITY_SCOPE_QUERY,
        ),
    }


def _try_store_cached_meta(
    cache_key: str,
    *,
    meta: Optional[Dict[str, Any]],
    quality_meta: Optional[Dict[str, Any]],
    ttl: int = _CACHE_TTL,
) -> None:
    client = get_redis_client()
    if client is None:
        return
    payload = {
        "meta": meta if isinstance(meta, dict) else {},
        "quality_meta": normalize_quality_meta(
            quality_meta,
            default_scope=QUALITY_SCOPE_QUERY,
        ),
    }
    try:
        client.setex(
            get_key(_meta_cache_key(cache_key)),
            max(int(ttl), 1),
            json.dumps(payload, ensure_ascii=False, default=str),
        )
    except Exception as exc:
        logger.debug("Redis meta store failed (%s): %s", cache_key, exc)


def _csv_row_bytes(values: List[Any]) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(values)
    return buf.getvalue().encode("utf-8")


def _iter_csv_bytes(df: pd.DataFrame) -> Generator[bytes, None, None]:
    """Yield CSV bytes with UTF-8 BOM while preserving header order."""
    yield b"\xef\xbb\xbf"

    available_cols = [c for c in _CSV_COLUMNS if c in df.columns]
    if df.empty:
        selected_cols = list(_CSV_COLUMNS.keys())
    else:
        selected_cols = available_cols or list(_CSV_COLUMNS.keys())
    header_labels = [_CSV_COLUMNS[c] for c in selected_cols]
    yield _csv_row_bytes(header_labels)

    if df.empty:
        return

    export_df = df.reindex(columns=selected_cols).astype(object)
    export_df = export_df.where(export_df.notna(), "")
    for row in export_df.itertuples(index=False, name=None):
        yield _csv_row_bytes([value if value is not None else "" for value in row])


# ============================================================
# Redis result cache helpers
# ============================================================


def _compute_cache_key(
    mode: str,
    values: List[str],
    workcenter_groups: Optional[List[str]] = None,
) -> str:
    """Compute a deterministic Redis cache key for a query."""
    cache_hash = compute_query_hash({
        "mode": mode,
        "values": sorted(values),
        "workcenter_groups": sorted(workcenter_groups) if workcenter_groups else [],
    })
    return f"mt:result:{cache_hash}"


_MT_SPOOL_NAMESPACE = "material_trace"


def _mt_spool_id(cache_key: str) -> str:
    """Derive a valid spool query_id from cache_key (replaces ':' with '.')."""
    return cache_key.replace(":", ".")


def _try_load_cached_df(cache_key: str) -> Optional[pd.DataFrame]:
    """Attempt to load a cached DataFrame from Parquet spool."""
    try:
        return load_spooled_df(_MT_SPOOL_NAMESPACE, _mt_spool_id(cache_key))
    except Exception as exc:
        logger.debug("Spool cache load failed (%s): %s", cache_key, exc)
        return None


def _try_store_cached_df(cache_key: str, df: pd.DataFrame) -> None:
    """Persist a DataFrame to canonical Parquet spool (heavy-query plane)."""
    try:
        store_spooled_df(
            _MT_SPOOL_NAMESPACE,
            _mt_spool_id(cache_key),
            df,
            ttl_seconds=_CACHE_TTL,
        )
    except Exception as exc:
        logger.debug("Spool cache store failed (%s): %s", cache_key, exc)


# ============================================================
# Forward query (LOT ID / Work Order → Materials)
# ============================================================


def forward_query(
    mode: str,
    values: List[str],
    workcenter_groups: Optional[List[str]] = None,
    page: int = 1,
    per_page: int = 50,
) -> Dict[str, Any]:
    """Execute forward material trace query."""
    meta: Dict[str, Any] = {}
    quality_meta = _build_query_quality_meta()
    cache_key = _compute_cache_key(mode, values, workcenter_groups)

    # Try Redis cache first (pagination and re-queries skip Oracle)
    cached_df = _try_load_cached_df(cache_key)
    if cached_df is not None:
        logger.debug("Forward query cache hit: %s", cache_key)
        cached_meta = _try_load_cached_meta(cache_key)
        if isinstance(cached_meta.get("meta"), dict):
            meta.update(cached_meta.get("meta") or {})
        quality_meta = normalize_quality_meta(
            cached_meta.get("quality_meta"),
            default_scope=QUALITY_SCOPE_QUERY,
        )
        result = _paginate(cached_df, page, per_page)
        result["meta"] = meta
        result["quality_meta"] = quality_meta
        return result

    wc_names = _resolve_workcenter_names(workcenter_groups)

    if mode == "lot":
        container_ids, _name_map, unresolved = _resolve_container_ids(values)
        if unresolved:
            meta["unresolved"] = unresolved
        if not container_ids:
            return {
                "rows": [],
                "pagination": {"page": 1, "per_page": per_page, "total": 0, "total_pages": 0},
                "meta": meta,
                "quality_meta": quality_meta,
            }

        df = _execute_batched_query("material_trace/forward_by_lot", "m.CONTAINERID", container_ids, wc_names, allow_patterns=False)

    else:  # workorder
        df = _execute_batched_query("material_trace/forward_by_workorder", "m.PJ_WORKORDER", values, wc_names)

    maybe_gc_collect()

    if df.empty:
        return {
            "rows": [],
            "pagination": {"page": 1, "per_page": per_page, "total": 0, "total_pages": 0},
            "meta": meta,
            "quality_meta": quality_meta,
        }

    df = _enrich_workcenter_group(df)

    # Store enriched result in Redis for subsequent pagination / export
    _try_store_cached_df(cache_key, df)
    _try_store_cached_meta(cache_key, meta=meta, quality_meta=quality_meta)

    result = _paginate(df, page, per_page)
    result["meta"] = meta
    result["quality_meta"] = quality_meta
    return result


# ============================================================
# Reverse query (Material Lot → LOTs)
# ============================================================


def reverse_query(
    values: List[str],
    workcenter_groups: Optional[List[str]] = None,
    page: int = 1,
    per_page: int = 50,
) -> Dict[str, Any]:
    """Execute reverse material trace query."""
    meta: Dict[str, Any] = {}
    quality_meta = _build_query_quality_meta()
    cache_key = _compute_cache_key("material_lot", values, workcenter_groups)

    # Try Redis cache first
    cached_df = _try_load_cached_df(cache_key)
    if cached_df is not None:
        logger.debug("Reverse query cache hit: %s", cache_key)
        cached_meta = _try_load_cached_meta(cache_key)
        if isinstance(cached_meta.get("meta"), dict):
            meta.update(cached_meta.get("meta") or {})
        quality_meta = normalize_quality_meta(
            cached_meta.get("quality_meta"),
            default_scope=QUALITY_SCOPE_QUERY,
        )
        result = _paginate(cached_df, page, per_page)
        result["meta"] = meta
        result["quality_meta"] = quality_meta
        return result

    wc_names = _resolve_workcenter_names(workcenter_groups)

    df = _execute_batched_query("material_trace/reverse_by_material_lot", "m.MATERIALLOTNAME", values, wc_names)

    maybe_gc_collect()

    if df.empty:
        return {
            "rows": [],
            "pagination": {"page": 1, "per_page": per_page, "total": 0, "total_pages": 0},
            "meta": meta,
            "quality_meta": quality_meta,
        }

    df = _enrich_workcenter_group(df)

    # Store enriched result in Redis for subsequent pagination / export
    _try_store_cached_df(cache_key, df)
    _try_store_cached_meta(cache_key, meta=meta, quality_meta=quality_meta)

    result = _paginate(df, page, per_page)
    result["meta"] = meta
    result["quality_meta"] = quality_meta
    return result


# ============================================================
# CSV Export
# ============================================================


def export_csv(
    mode: str,
    values: List[str],
    workcenter_groups: Optional[List[str]] = None,
) -> tuple[Generator[bytes, None, None], Dict[str, Any]]:
    """Export query results as UTF-8 BOM CSV stream."""
    meta: Dict[str, Any] = {}
    base_query_quality = _build_query_quality_meta()

    # Try Redis cache first — avoids re-querying Oracle for export
    cache_key = _compute_cache_key(mode, values, workcenter_groups)
    df = _try_load_cached_df(cache_key)
    cached_meta = _try_load_cached_meta(cache_key)
    if isinstance(cached_meta.get("meta"), dict):
        meta.update(cached_meta.get("meta") or {})
    base_query_quality = normalize_quality_meta(
        cached_meta.get("quality_meta"),
        default_scope=QUALITY_SCOPE_QUERY,
    )

    if df is None:
        # Cache miss — execute query
        wc_names = _resolve_workcenter_names(workcenter_groups)

        if mode == "lot":
            container_ids, _name_map, unresolved = _resolve_container_ids(values)
            if unresolved:
                meta["unresolved"] = unresolved
            if not container_ids:
                export_quality_meta = _to_export_quality_meta(base_query_quality, observed_rows=0)
                return _empty_csv(), {"meta": meta, "quality_meta": export_quality_meta}

            df = _execute_batched_query("material_trace/forward_by_lot", "m.CONTAINERID", container_ids, wc_names, allow_patterns=False)

        elif mode == "workorder":
            df = _execute_batched_query("material_trace/forward_by_workorder", "m.PJ_WORKORDER", values, wc_names)

        else:  # material_lot
            df = _execute_batched_query("material_trace/reverse_by_material_lot", "m.MATERIALLOTNAME", values, wc_names)

        if df.empty:
            export_quality_meta = _to_export_quality_meta(base_query_quality, observed_rows=0)
            return _empty_csv(), {"meta": meta, "quality_meta": export_quality_meta}

        df = _enrich_workcenter_group(df)

        # Store in cache for potential subsequent requests
        _try_store_cached_df(cache_key, df)
        _try_store_cached_meta(cache_key, meta=meta, quality_meta=base_query_quality)

    if df.empty:
        export_quality_meta = _to_export_quality_meta(base_query_quality, observed_rows=0)
        return _empty_csv(), {"meta": meta, "quality_meta": export_quality_meta}

    observed_rows = len(df)
    export_quality_meta = _to_export_quality_meta(
        base_query_quality,
        observed_rows=observed_rows,
    )

    return _iter_csv_bytes(df), {"meta": meta, "quality_meta": export_quality_meta}


def _empty_csv() -> Generator[bytes, None, None]:
    """Return an empty CSV stream with headers only."""
    return _iter_csv_bytes(pd.DataFrame())


# ---------------------------------------------------------------------------
# Canonical query hash (task 2.5)
# ---------------------------------------------------------------------------
# material-trace on-demand spool identity: hash of the primary query params.
# When spool-backed execution is complete (task 8.1-8.4) the route will use
# this id to check for an existing spool before enqueuing an RQ job.
_MATERIAL_TRACE_QUERY_SCHEMA_VERSION = 1


def make_canonical_query_hash(
    direction: str,
    root_lot_ids: Optional[List[str]] = None,
    root_cids: Optional[List[str]] = None,
    depth: Optional[int] = None,
    **extra_params,
) -> str:
    """Return the canonical spool query id for a material trace query."""
    key: Dict[str, Any] = {
        "_v": _MATERIAL_TRACE_QUERY_SCHEMA_VERSION,
        "direction": direction,
        "root_lot_ids": sorted(root_lot_ids or []),
        "root_cids": sorted(root_cids or []),
    }
    if depth is not None:
        key["depth"] = depth
    if extra_params:
        key["extra"] = {k: v for k, v in sorted(extra_params.items())}
    return f"mtrace-{compute_query_hash(key)}"


# ---------------------------------------------------------------------------
# Spool-backed execution (task 8.1)
# ---------------------------------------------------------------------------

_SPOOL_NAMESPACE = "material_trace"
_SPOOL_SCHEMA_VERSION = 1


def make_route_query_hash(
    mode: str,
    values: List[str],
    workcenter_groups: Optional[List[str]] = None,
) -> str:
    """Compute the canonical spool query hash for a material trace route request.

    This is the spool key used by the route (mode/values/workcenter_groups).
    Distinct from make_canonical_query_hash which serves the lineage pipeline.
    """
    key = {
        "_v": _SPOOL_SCHEMA_VERSION,
        "mode": mode,
        "values": sorted(values or []),
        "workcenter_groups": sorted(workcenter_groups or []),
    }
    return f"mtrace-{compute_query_hash(key)}"


def execute_to_spool(
    mode: str,
    values: List[str],
    workcenter_groups: Optional[List[str]] = None,
) -> tuple:
    """Execute Oracle query and stream result to Parquet spool.

    Streaming spool-safe path: uses ``_execute_batched_query_to_parquet``
    (``read_sql_df_slow_iter`` + ``pyarrow.ParquetWriter``) so no large
    DataFrame is assembled in memory and ``_check_memory_guard()`` is not
    called.  Returns ``(query_hash, total_rows)``.

    Idempotent: if the spool already exists, returns immediately.
    """
    import tempfile
    from pathlib import Path as _Path

    from mes_dashboard.core.query_spool_store import (
        QUERY_SPOOL_DIR,
        get_spool_file_path,
        register_spool_file,
    )

    query_hash = make_route_query_hash(mode, values, workcenter_groups)

    # Idempotency: return immediately if spool already exists
    existing = get_spool_file_path(_SPOOL_NAMESPACE, query_hash)
    if existing and _Path(existing).exists():
        logger.info(
            "execute_to_spool: spool hit (query_hash=%s mode=%s)", query_hash, mode
        )
        try:
            from mes_dashboard.core.duckdb_runtime import create_heavy_query_connection
            conn = create_heavy_query_connection()
            path_lit = "'" + existing.replace("'", "''") + "'"
            row = conn.execute(f"SELECT COUNT(*) FROM read_parquet({path_lit})").fetchone()
            conn.close()
            return query_hash, int(row[0]) if row else 0
        except Exception:
            return query_hash, 0

    wc_names = _resolve_workcenter_names(workcenter_groups)
    mapping = get_workcenter_mapping() or {}

    spool_dir = QUERY_SPOOL_DIR / _SPOOL_NAMESPACE
    spool_dir.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path_str = tempfile.mkstemp(suffix=".parquet", dir=spool_dir)
    os.close(tmp_fd)
    tmp_path = _Path(tmp_path_str)

    try:
        if mode == "lot":
            container_ids, _name_map, unresolved = _resolve_container_ids(values)
            if not container_ids:
                tmp_path.unlink(missing_ok=True)
                return query_hash, 0
            row_count = _execute_batched_query_to_parquet(
                "material_trace/forward_by_lot", "m.CONTAINERID", container_ids,
                tmp_path, wc_names, allow_patterns=False, mapping=mapping,
            )
        elif mode == "workorder":
            row_count = _execute_batched_query_to_parquet(
                "material_trace/forward_by_workorder", "m.PJ_WORKORDER", values,
                tmp_path, wc_names, mapping=mapping,
            )
        else:  # material_lot (reverse)
            row_count = _execute_batched_query_to_parquet(
                "material_trace/reverse_by_material_lot", "m.MATERIALLOTNAME", values,
                tmp_path, wc_names, mapping=mapping,
            )

        if row_count == 0:
            tmp_path.unlink(missing_ok=True)
            return query_hash, 0

        registered = register_spool_file(
            _SPOOL_NAMESPACE,
            query_hash,
            tmp_path,
            row_count,
        )
        if not registered:
            logger.warning(
                "execute_to_spool: register_spool_file failed (query_hash=%s)", query_hash
            )
    except Exception as exc:
        logger.error("execute_to_spool: streaming write failed: %s", exc)
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise

    logger.info(
        "execute_to_spool: wrote spool (query_hash=%s mode=%s rows=%d)",
        query_hash, mode, row_count,
    )
    return query_hash, row_count


def rq_material_trace_job(job_id: str, mode: str, values: List[str], workcenter_groups: Optional[List[str]]) -> None:
    """RQ worker function: execute material trace query and write to spool.

    Called by the RQ worker when the route enqueues an async job.
    Updates job progress via async_query_job_service.
    """
    _PREFIX = "material_trace"
    try:
        from mes_dashboard.services.async_query_job_service import (
            update_job_progress,
            complete_job,
        )
        update_job_progress(_PREFIX, job_id, status="running", pct=10, message="查詢中...")
        query_hash, total_rows = execute_to_spool(mode, values, workcenter_groups)
        update_job_progress(_PREFIX, job_id, status="running", pct=90, message=f"寫入 spool ({total_rows} 筆)")
        complete_job(_PREFIX, job_id, query_id=query_hash)
        logger.info(
            "rq_material_trace_job: complete (job_id=%s query_hash=%s rows=%d)",
            job_id, query_hash, total_rows,
        )
    except Exception as exc:
        logger.error("rq_material_trace_job failed (job_id=%s): %s", job_id, exc)
        try:
            from mes_dashboard.services.async_query_job_service import complete_job
            complete_job("material_trace", job_id, error=str(exc))
        except Exception:
            pass
