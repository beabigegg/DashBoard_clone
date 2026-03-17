# -*- coding: utf-8 -*-
"""DuckDB SQL runtime for anomaly detection on existing Parquet spool files.

Extends the DuckDB-on-Parquet pattern from reject_cache_sql_runtime.py to provide
statistical anomaly detection:
  - Yield Z-score (yield_alert_dataset)
  - Reject rate spike (reject_dataset)
  - Hold duration outlier (hold_dataset)
  - Equipment OU% deviation (resource_dataset)

Entry points: detect_yield_anomalies, detect_reject_spikes,
              detect_hold_outliers, detect_equipment_deviations
"""

from __future__ import annotations

import logging
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from mes_dashboard.core.feature_flags import resolve_bool_flag
from mes_dashboard.core.query_spool_store import QUERY_SPOOL_DIR, get_spool_file_path

logger = logging.getLogger("mes_dashboard.anomaly_detection_sql_runtime")

_ANALYTICS_ENABLED = resolve_bool_flag("ANALYTICS_ANOMALY_DETECTION_ENABLED", default=False)

SQL_FALLBACK_DISABLED = "analytics_disabled"
SQL_FALLBACK_DEP_MISSING = "analytics_dependency_missing"
SQL_FALLBACK_SPOOL_MISS = "analytics_spool_miss"
SQL_FALLBACK_RUNTIME_ERROR = "analytics_runtime_error"

_NS_YIELD = "anomaly_yield_dataset"
_NS_REJECT = "anomaly_reject_dataset"
_NS_HOLD = "anomaly_hold_dataset"
_NS_RESOURCE = "anomaly_resource_dataset"

_DEFAULT_YIELD_THRESHOLD = 2.0
_DEFAULT_SPIKE_THRESHOLD = 50.0  # pct_change threshold
_DEFAULT_HOLD_PERCENTILE = 0.95
_DEFAULT_DEVIATION_THRESHOLD = 15.0  # OU% points

# Redis cache keys for scheduled anomaly detection results
_REDIS_KEY_SUMMARY = "analytics:anomaly_summary"
_REDIS_KEY_YIELD = "analytics:yield_anomalies"
_REDIS_KEY_REJECT = "analytics:reject_spikes"
_REDIS_KEY_HOLD = "analytics:hold_outliers"
_REDIS_KEY_EQUIPMENT = "analytics:equipment_deviations"
_REDIS_KEY_COMPUTED_AT = "analytics:computed_at"
_REDIS_CACHE_TTL = 90_000  # 25 hours

# DuckDB memory limit per connection to prevent OOM with multiple workers
_DUCKDB_MEMORY_LIMIT = os.getenv("DUCKDB_MEMORY_LIMIT", "256MB")


def _create_duckdb_conn():
    """Create a memory-limited DuckDB connection."""
    import duckdb  # type: ignore
    conn = duckdb.connect(database=":memory:")
    conn.execute(f"SET memory_limit = '{_DUCKDB_MEMORY_LIMIT}'")
    conn.execute("SET threads = 1")
    return conn


def _qid(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def _sql_str_literal(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _sf(val: Any, default: float = 0.0) -> float:
    try:
        return float(val) if val is not None else default
    except (TypeError, ValueError):
        return default


def _resolve_spool_path(namespace: str, query_id: Optional[str]) -> Optional[str]:
    """Resolve spool Parquet path: by query_id if given, else most recent file."""
    if query_id:
        path = get_spool_file_path(namespace, query_id)
        if path:
            return path
    ns = re.sub(r"[^A-Za-z0-9._-]", "_", str(namespace).strip()) or "default"
    ns_dir = QUERY_SPOOL_DIR.resolve() / ns
    if not ns_dir.exists():
        return None
    try:
        files = sorted(
            ns_dir.glob("*.parquet"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        return str(files[0]) if files else None
    except Exception:
        return None


def _fetch_dict_rows(
    conn: Any, sql: str, params: Optional[List[Any]] = None
) -> List[Dict[str, Any]]:
    cursor = conn.execute(sql, params or [])
    columns = [desc[0] for desc in (cursor.description or [])]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def detect_yield_anomalies(
    *,
    query_id: Optional[str] = None,
    threshold: float = _DEFAULT_YIELD_THRESHOLD,
) -> Tuple[Optional[List[Dict[str, Any]]], Dict[str, Any]]:
    """Detect yield drop anomalies via Z-score on yield_alert_dataset spool.

    Aggregates by WORKCENTER_GROUP (DEPARTMENT_GROUP) × PACKAGE × date.
    Only reports yield *drops* (negative Z-score). Uses T-1 (previous day).

    Returns (items, meta). items is None when detection cannot run.
    Each item: {workcenter_group, package, date, yield_pct, z_score, rolling_avg}
    """
    if not _ANALYTICS_ENABLED:
        return None, {"fallback_reason": SQL_FALLBACK_DISABLED}

    try:
        import duckdb  # type: ignore
    except Exception:
        return None, {"fallback_reason": SQL_FALLBACK_DEP_MISSING}

    parquet_path = _resolve_spool_path(_NS_YIELD, query_id)
    if not parquet_path:
        return None, {"fallback_reason": SQL_FALLBACK_SPOOL_MISS}

    started_at = time.time()
    conn = None
    try:
        conn = _create_duckdb_conn()
        conn.execute(
            "CREATE OR REPLACE TEMP VIEW yield_alert_src AS "
            f"SELECT * FROM read_parquet({_sql_str_literal(parquet_path)})"
        )

        sql = """
            WITH daily_yield AS (
                SELECT
                    strftime(CAST("DATE_BUCKET" AS DATE), '%Y-%m-%d') AS data_date,
                    TRIM(COALESCE(CAST("DEPARTMENT_GROUP" AS VARCHAR), '(NA)')) AS workcenter_group,
                    TRIM(COALESCE(CAST("PACKAGE_NAME" AS VARCHAR), '(NA)')) AS package,
                    SUM(COALESCE("TRANSACTION_QTY", 0)) AS transaction_qty,
                    SUM(COALESCE("SCRAP_QTY", 0)) AS scrap_qty
                FROM yield_alert_src
                WHERE CAST("DATE_BUCKET" AS DATE) >= CURRENT_DATE - INTERVAL '14' DAY
                GROUP BY 1, 2, 3
            ),
            yield_pct AS (
                SELECT
                    data_date, workcenter_group, package, transaction_qty, scrap_qty,
                    CASE WHEN transaction_qty = 0 THEN 100.0
                         ELSE ROUND((1.0 - scrap_qty / transaction_qty) * 100, 4)
                    END AS yield_pct
                FROM daily_yield
                WHERE transaction_qty > 0
            ),
            windowed AS (
                SELECT
                    data_date, workcenter_group, package, yield_pct,
                    AVG(yield_pct) OVER w AS rolling_avg,
                    STDDEV_POP(yield_pct) OVER w AS rolling_std,
                    COUNT(*) OVER w AS window_count
                FROM yield_pct
                WINDOW w AS (
                    PARTITION BY workcenter_group, package
                    ORDER BY data_date
                    ROWS BETWEEN 13 PRECEDING AND 1 PRECEDING
                )
            )
            SELECT
                data_date, workcenter_group, package, yield_pct,
                rolling_avg, rolling_std,
                ROUND((yield_pct - rolling_avg) / rolling_std, 3) AS z_score,
                window_count
            FROM windowed
            WHERE data_date = strftime(CURRENT_DATE - INTERVAL '1' DAY, '%Y-%m-%d')
              AND window_count >= 3
              AND rolling_std > 0
              AND (yield_pct - rolling_avg) / rolling_std < -?
            ORDER BY z_score ASC
        """
        rows = _fetch_dict_rows(conn, sql, [threshold])
        items = [
            {
                "workcenter_group": str(r.get("workcenter_group") or ""),
                "package": str(r.get("package") or ""),
                "date": str(r.get("data_date") or ""),
                "yield_pct": round(_sf(r.get("yield_pct")), 4),
                "z_score": round(_sf(r.get("z_score")), 3),
                "rolling_avg": round(_sf(r.get("rolling_avg")), 4),
            }
            for r in rows
        ]
        return items, {
            "source": "anomaly_detection_sql",
            "namespace": _NS_YIELD,
            "latency_s": round(time.time() - started_at, 3),
            "count": len(items),
        }
    except Exception as exc:
        logger.warning("detect_yield_anomalies failed: %s", exc)
        return None, {"fallback_reason": SQL_FALLBACK_RUNTIME_ERROR}
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def detect_reject_spikes(
    *,
    query_id: Optional[str] = None,
    spike_threshold_pct: float = _DEFAULT_SPIKE_THRESHOLD,
) -> Tuple[Optional[List[Dict[str, Any]]], Dict[str, Any]]:
    """Detect reject quantity spikes via Z-score on reject_dataset spool.

    Uses absolute reject quantity (not rate) as the metric.
    Baseline is the rolling average quantity over the previous 13 days.
    Reports T-1 (previous day) only. Only flags increases (Z > threshold).

    Returns (items, meta).
    Each item: {workcenter_group, date, current_qty, baseline_qty, z_score}
    """
    if not _ANALYTICS_ENABLED:
        return None, {"fallback_reason": SQL_FALLBACK_DISABLED}

    try:
        import duckdb  # type: ignore
    except Exception:
        return None, {"fallback_reason": SQL_FALLBACK_DEP_MISSING}

    parquet_path = _resolve_spool_path(_NS_REJECT, query_id)
    if not parquet_path:
        return None, {"fallback_reason": SQL_FALLBACK_SPOOL_MISS}

    started_at = time.time()
    conn = None
    try:
        conn = _create_duckdb_conn()
        conn.execute(
            "CREATE OR REPLACE TEMP VIEW reject_src AS "
            f"SELECT * FROM read_parquet({_sql_str_literal(parquet_path)})"
        )

        # Detect available columns to handle varying spool schemas
        cols_cursor = conn.execute("PRAGMA table_info('reject_src')")
        cols = {str(row[1]) for row in cols_cursor.fetchall() if len(row) > 1}

        wc_group_col = "WORKCENTER_GROUP" if "WORKCENTER_GROUP" in cols else None
        reject_col = "REJECT_TOTAL_QTY" if "REJECT_TOTAL_QTY" in cols else None
        day_col = "TXN_DAY" if "TXN_DAY" in cols else None

        if not all([wc_group_col, reject_col, day_col]):
            return None, {"fallback_reason": SQL_FALLBACK_RUNTIME_ERROR}

        sql = f"""
            WITH daily_qty AS (
                SELECT
                    strftime(CAST({_qid(day_col)} AS DATE), '%Y-%m-%d') AS data_date,
                    TRIM(COALESCE(CAST({_qid(wc_group_col)} AS VARCHAR), '(NA)')) AS workcenter_group,
                    SUM(COALESCE({_qid(reject_col)}, 0)) AS reject_qty
                FROM reject_src
                WHERE CAST({_qid(day_col)} AS DATE) >= CURRENT_DATE - INTERVAL '14' DAY
                GROUP BY 1, 2
            ),
            windowed AS (
                SELECT
                    data_date, workcenter_group, reject_qty,
                    AVG(reject_qty) OVER w AS baseline_qty,
                    STDDEV_POP(reject_qty) OVER w AS baseline_std,
                    COUNT(*) OVER w AS window_count
                FROM daily_qty
                WINDOW w AS (
                    PARTITION BY workcenter_group
                    ORDER BY data_date
                    ROWS BETWEEN 13 PRECEDING AND 1 PRECEDING
                )
            )
            SELECT
                data_date, workcenter_group,
                reject_qty AS current_qty,
                ROUND(baseline_qty, 0) AS baseline_qty,
                ROUND(baseline_std, 0) AS baseline_std,
                ROUND((reject_qty - baseline_qty) / baseline_std, 2) AS z_score,
                window_count
            FROM windowed
            WHERE data_date = strftime(CURRENT_DATE - INTERVAL '1' DAY, '%Y-%m-%d')
              AND window_count >= 3
              AND baseline_std > 0
              AND (reject_qty - baseline_qty) / baseline_std > ?
            ORDER BY z_score DESC
        """
        rows = _fetch_dict_rows(conn, sql, [_DEFAULT_YIELD_THRESHOLD])
        items = [
            {
                "workcenter_group": str(r.get("workcenter_group") or ""),
                "date": str(r.get("data_date") or ""),
                "current_qty": int(_sf(r.get("current_qty"))),
                "baseline_qty": int(_sf(r.get("baseline_qty"))),
                "z_score": round(_sf(r.get("z_score")), 2),
            }
            for r in rows
        ]
        return items, {
            "source": "anomaly_detection_sql",
            "namespace": _NS_REJECT,
            "latency_s": round(time.time() - started_at, 3),
            "count": len(items),
        }
    except Exception as exc:
        logger.warning("detect_reject_spikes failed: %s", exc)
        return None, {"fallback_reason": SQL_FALLBACK_RUNTIME_ERROR}
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def detect_hold_outliers(
    *,
    query_id: Optional[str] = None,
    percentile: float = _DEFAULT_HOLD_PERCENTILE,
) -> Tuple[Optional[List[Dict[str, Any]]], Dict[str, Any]]:
    """Detect hold duration outliers using percentile threshold on hold_dataset spool.

    Returns (items, meta).
    Each item: {lot_id, hold_reason, workcenter, hold_hours, percentile_threshold}
    """
    if not _ANALYTICS_ENABLED:
        return None, {"fallback_reason": SQL_FALLBACK_DISABLED}

    try:
        import duckdb  # type: ignore
    except Exception:
        return None, {"fallback_reason": SQL_FALLBACK_DEP_MISSING}

    parquet_path = _resolve_spool_path(_NS_HOLD, query_id)
    if not parquet_path:
        return None, {"fallback_reason": SQL_FALLBACK_SPOOL_MISS}

    started_at = time.time()
    conn = None
    try:
        conn = _create_duckdb_conn()
        conn.execute(
            "CREATE OR REPLACE TEMP VIEW hold_src AS "
            f"SELECT * FROM read_parquet({_sql_str_literal(parquet_path)})"
        )

        # Check columns exist
        cols_cursor = conn.execute("PRAGMA table_info('hold_src')")
        cols = {str(row[1]) for row in cols_cursor.fetchall() if len(row) > 1}

        if "HOLD_HOURS" not in cols or "LOT_ID" not in cols:
            return None, {"fallback_reason": SQL_FALLBACK_RUNTIME_ERROR}

        hold_day_expr = (
            "strftime(CAST(\"hold_day\" AS DATE), '%Y-%m-%d')"
            if "hold_day" in cols else "''"
        )
        reason_expr = (
            'TRIM(COALESCE(CAST("HOLDREASONNAME" AS VARCHAR), \'(未填寫)\'))'
            if "HOLDREASONNAME" in cols else "'(未填寫)'"
        )
        wc_expr = (
            'TRIM(COALESCE(CAST("WORKCENTERNAME" AS VARCHAR), \'(NA)\'))'
            if "WORKCENTERNAME" in cols else "'(NA)'"
        )

        pct_val = max(0.0, min(1.0, float(percentile)))
        date_filter = (
            'CAST("hold_day" AS DATE) >= CURRENT_DATE - INTERVAL \'14\' DAY'
            if "hold_day" in cols else "TRUE"
        )
        today_filter = (
            "hold_day = strftime(CURRENT_DATE, '%Y-%m-%d')"
            if "hold_day" in cols else "TRUE"
        )
        hold_type_filter = (
            "TRIM(LOWER(CAST(\"HOLD_TYPE\" AS VARCHAR))) = 'quality'"
            if "HOLD_TYPE" in cols else "TRUE"
        )
        sql = f"""
            WITH hold_base AS (
                SELECT
                    {hold_day_expr} AS hold_day,
                    TRIM(COALESCE(CAST("LOT_ID" AS VARCHAR), '(NA)')) AS lot_id,
                    {reason_expr} AS hold_reason,
                    {wc_expr} AS workcenter,
                    COALESCE("HOLD_HOURS", 0) AS hold_hours
                FROM hold_src
                WHERE COALESCE("HOLD_HOURS", 0) > 0
                  AND ({hold_type_filter})
                  AND ({date_filter})
            ),
            p_calc AS (
                SELECT PERCENTILE_CONT({pct_val}) WITHIN GROUP (ORDER BY hold_hours) AS p_threshold
                FROM hold_base
            )
            SELECT
                b.hold_day, b.lot_id, b.hold_reason, b.workcenter,
                ROUND(b.hold_hours, 2) AS hold_hours,
                ROUND(p.p_threshold, 2) AS percentile_threshold
            FROM hold_base b
            CROSS JOIN p_calc p
            WHERE b.hold_hours > p.p_threshold
              AND ({today_filter})
            ORDER BY b.hold_hours DESC
        """
        rows = _fetch_dict_rows(conn, sql)
        items = [
            {
                "hold_day": str(r.get("hold_day") or ""),
                "lot_id": str(r.get("lot_id") or ""),
                "hold_reason": str(r.get("hold_reason") or ""),
                "workcenter": str(r.get("workcenter") or ""),
                "hold_hours": round(_sf(r.get("hold_hours")), 2),
                "percentile_threshold": round(_sf(r.get("percentile_threshold")), 2),
            }
            for r in rows
        ]
        return items, {
            "source": "anomaly_detection_sql",
            "namespace": _NS_HOLD,
            "latency_s": round(time.time() - started_at, 3),
            "count": len(items),
        }
    except Exception as exc:
        logger.warning("detect_hold_outliers failed: %s", exc)
        return None, {"fallback_reason": SQL_FALLBACK_RUNTIME_ERROR}
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def get_anomaly_summary() -> Dict[str, Any]:
    """Aggregate anomaly counts from all 4 detectors for a single summary response.

    Each detector runs independently; failures fall back to count=0 and the
    detector name is appended to the ``degraded`` list in meta.
    Returns dict with 'data' and 'meta' keys suitable for success_response().
    """
    started_at = time.time()
    degraded: list[str] = []
    _SRANK = {"ok": 0, "warning": 1, "critical": 2}

    def _sev(count: int) -> str:
        if count == 0:
            return "ok"
        return "warning" if count <= 5 else "critical"

    def _extract_count(name: str, detector_fn: Any) -> int:
        try:
            items, _ = detector_fn()
            if items is None:
                degraded.append(name)
                return 0
            return len(items)
        except Exception:
            degraded.append(name)
            return 0

    breakdown: Dict[str, Any] = {}
    breakdown["yield"] = {"count": _extract_count("yield", detect_yield_anomalies), "label": "良率異常"}
    breakdown["reject"] = {"count": _extract_count("reject", detect_reject_spikes), "label": "報廢突增"}
    breakdown["hold"] = {"count": _extract_count("hold", detect_hold_outliers), "label": "Hold 離群"}
    breakdown["equipment"] = {"count": _extract_count("equipment", detect_equipment_deviations), "label": "稼動偏離"}

    for v in breakdown.values():
        v["severity"] = _sev(v["count"])

    total_count = sum(v["count"] for v in breakdown.values())
    overall_sev = max(breakdown.values(), key=lambda v: _SRANK.get(v["severity"], 0))["severity"]

    return {
        "data": {
            "total_count": total_count,
            "severity": overall_sev,
            "breakdown": breakdown,
        },
        "meta": {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "latency_s": round(time.time() - started_at, 3),
            "degraded": degraded,
        },
    }


def _build_resource_dimension() -> List[Tuple[str, str, str]]:
    """Build (resource_id, workcenter_group, resource_model) from resource_cache.

    Only includes machines registered in the cache.
    """
    try:
        from mes_dashboard.services.filter_cache import get_workcenter_mapping
        from mes_dashboard.services.resource_cache import get_all_resources

        wc_mapping = get_workcenter_mapping() or {}
        result = []
        for r in get_all_resources():
            rid = r.get("RESOURCEID", "")
            if not rid:
                continue
            wc_name = r.get("WORKCENTERNAME", "")
            group = (wc_mapping.get(wc_name) or {}).get("group", wc_name)
            model = r.get("RESOURCEFAMILYNAME", "") or "(NA)"
            result.append((rid, group, model))
        return result
    except Exception as exc:
        logger.warning("Failed to build resource dimension: %s", exc)
        return []


def detect_equipment_deviations(
    *,
    query_id: Optional[str] = None,
    deviation_threshold: float = _DEFAULT_DEVIATION_THRESHOLD,
) -> Tuple[Optional[List[Dict[str, Any]]], Dict[str, Any]]:
    """Detect equipment OU% deviations by workcenter_group × resource_model.

    Only considers machines in resource_cache. Aggregates OU% per group/model
    per day, then applies a rolling 13-day baseline window. Reports yesterday
    only.

    Returns (items, meta).
    Each item: {workcenter_group, resource_model, machine_count, date,
                current_ou_pct, baseline_ou_pct, deviation}
    """
    if not _ANALYTICS_ENABLED:
        return None, {"fallback_reason": SQL_FALLBACK_DISABLED}

    try:
        import duckdb  # type: ignore
    except Exception:
        return None, {"fallback_reason": SQL_FALLBACK_DEP_MISSING}

    parquet_path = _resolve_spool_path(_NS_RESOURCE, query_id)
    if not parquet_path:
        return None, {"fallback_reason": SQL_FALLBACK_SPOOL_MISS}

    # Build dimension: only cache-registered machines
    dim_rows = _build_resource_dimension()
    if not dim_rows:
        return None, {"fallback_reason": SQL_FALLBACK_RUNTIME_ERROR}

    started_at = time.time()
    conn = None
    try:
        conn = _create_duckdb_conn()
        conn.execute(
            "CREATE OR REPLACE TEMP VIEW resource_src AS "
            f"SELECT * FROM read_parquet({_sql_str_literal(parquet_path)})"
        )

        cols_cursor = conn.execute("PRAGMA table_info('resource_src')")
        cols = {str(row[1]) for row in cols_cursor.fetchall() if len(row) > 1}

        required = {"HISTORYID", "DATA_DATE", "PRD_HOURS"}
        if not required.issubset(cols):
            return None, {"fallback_reason": SQL_FALLBACK_RUNTIME_ERROR}

        # Load dimension table into DuckDB
        conn.execute(
            "CREATE TEMP TABLE resource_dim "
            "(resource_id VARCHAR, workcenter_group VARCHAR, resource_model VARCHAR)"
        )
        conn.executemany(
            "INSERT INTO resource_dim VALUES (?, ?, ?)", dim_rows
        )

        def _hours_col(name: str) -> str:
            return f'COALESCE("{name}", 0)' if name in cols else "0"

        prd = _hours_col("PRD_HOURS")
        sby = _hours_col("SBY_HOURS")
        udt = _hours_col("UDT_HOURS")
        sdt = _hours_col("SDT_HOURS")
        egt = _hours_col("EGT_HOURS")
        total = _hours_col("TOTAL_HOURS")

        sql = f"""
            WITH machine_ou AS (
                SELECT
                    strftime(CAST(s."DATA_DATE" AS DATE), '%Y-%m-%d') AS data_date,
                    d.workcenter_group,
                    d.resource_model,
                    CASE
                        WHEN ({prd}+{sby}+{udt}+{sdt}+{egt}) = 0 THEN 0.0
                        ELSE {prd} / ({prd}+{sby}+{udt}+{sdt}+{egt}) * 100
                    END AS ou_pct
                FROM resource_src s
                INNER JOIN resource_dim d ON TRIM(CAST(s."HISTORYID" AS VARCHAR)) = d.resource_id
                WHERE {total} > 0
                  AND CAST(s."DATA_DATE" AS DATE) >= CURRENT_DATE - INTERVAL '14' DAY
            ),
            group_daily AS (
                SELECT
                    data_date,
                    workcenter_group,
                    resource_model,
                    ROUND(AVG(ou_pct), 2) AS avg_ou_pct,
                    COUNT(*) AS machine_count
                FROM machine_ou
                GROUP BY data_date, workcenter_group, resource_model
            ),
            windowed AS (
                SELECT
                    data_date, workcenter_group, resource_model,
                    avg_ou_pct, machine_count,
                    AVG(avg_ou_pct) OVER w AS baseline_ou_pct,
                    COUNT(*) OVER w AS window_count
                FROM group_daily
                WINDOW w AS (
                    PARTITION BY workcenter_group, resource_model
                    ORDER BY data_date
                    ROWS BETWEEN 13 PRECEDING AND 1 PRECEDING
                )
            )
            SELECT
                data_date, workcenter_group, resource_model, machine_count,
                ROUND(avg_ou_pct, 2) AS current_ou_pct,
                ROUND(baseline_ou_pct, 2) AS baseline_ou_pct,
                ROUND(baseline_ou_pct - avg_ou_pct, 2) AS deviation,
                window_count
            FROM windowed
            WHERE data_date = strftime(CURRENT_DATE - INTERVAL '1' DAY, '%Y-%m-%d')
              AND window_count >= 7
              AND baseline_ou_pct - avg_ou_pct > ?
            ORDER BY deviation DESC
        """
        rows = _fetch_dict_rows(conn, sql, [deviation_threshold])

        items = [
            {
                "workcenter_group": str(r.get("workcenter_group") or ""),
                "resource_model": str(r.get("resource_model") or ""),
                "machine_count": int(r.get("machine_count") or 0),
                "date": str(r.get("data_date") or ""),
                "current_ou_pct": round(_sf(r.get("current_ou_pct")), 2),
                "baseline_ou_pct": round(_sf(r.get("baseline_ou_pct")), 2),
                "deviation": round(_sf(r.get("deviation")), 2),
            }
            for r in rows
        ]
        return items, {
            "source": "anomaly_detection_sql",
            "namespace": _NS_RESOURCE,
            "latency_s": round(time.time() - started_at, 3),
            "count": len(items),
        }
    except Exception as exc:
        logger.warning("detect_equipment_deviations failed: %s", exc)
        return None, {"fallback_reason": SQL_FALLBACK_RUNTIME_ERROR}
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Redis cache layer — scheduled results read/write
# ---------------------------------------------------------------------------

def _redis_write_json(key_suffix: str, data: Any) -> bool:
    """Write JSON data to Redis with standard prefix and TTL."""
    import json as _json

    try:
        from mes_dashboard.core.redis_client import REDIS_ENABLED, get_key, get_redis_client

        if not REDIS_ENABLED:
            return False
        client = get_redis_client()
        if client is None:
            return False
        payload = _json.dumps(data, ensure_ascii=False, default=str)
        client.setex(get_key(key_suffix), _REDIS_CACHE_TTL, payload)
        return True
    except Exception as exc:
        logger.warning("Redis write failed for %s: %s", key_suffix, exc)
        return False


def _redis_read_json(key_suffix: str) -> Optional[Any]:
    """Read JSON data from Redis."""
    import json as _json

    try:
        from mes_dashboard.core.redis_client import REDIS_ENABLED, get_key, get_redis_client

        if not REDIS_ENABLED:
            return None
        client = get_redis_client()
        if client is None:
            return None
        raw = client.get(get_key(key_suffix))
        if raw is None:
            return None
        return _json.loads(raw)
    except Exception as exc:
        logger.warning("Redis read failed for %s: %s", key_suffix, exc)
        return None


def compute_and_cache_all() -> Dict[str, Any]:
    """Run all 4 detectors and cache results to Redis.

    Called by the scheduler on startup and daily at 08:00.
    Returns the summary dict.
    """
    started_at = time.time()
    degraded: list[str] = []
    _SRANK = {"ok": 0, "warning": 1, "critical": 2}

    def _sev(count: int) -> str:
        if count == 0:
            return "ok"
        return "warning" if count <= 5 else "critical"

    # Run all 4 detectors
    detectors = [
        ("yield", detect_yield_anomalies, _REDIS_KEY_YIELD),
        ("reject", detect_reject_spikes, _REDIS_KEY_REJECT),
        ("hold", detect_hold_outliers, _REDIS_KEY_HOLD),
        ("equipment", detect_equipment_deviations, _REDIS_KEY_EQUIPMENT),
    ]

    breakdown: Dict[str, Any] = {}
    for name, detector_fn, redis_key in detectors:
        try:
            items, meta = detector_fn()
            if items is None:
                degraded.append(name)
                items = []
            _redis_write_json(redis_key, {"items": items, "count": len(items), "meta": meta})
        except Exception:
            degraded.append(name)
            items = []
            _redis_write_json(redis_key, {"items": [], "count": 0, "meta": {}})

        label_map = {"yield": "良率異常", "reject": "報廢突增", "hold": "Hold 離群", "equipment": "稼動偏離"}
        breakdown[name] = {"count": len(items), "severity": _sev(len(items)), "label": label_map[name]}

    total_count = sum(v["count"] for v in breakdown.values())
    overall_sev = max(breakdown.values(), key=lambda v: _SRANK.get(v["severity"], 0))["severity"]

    computed_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    summary = {
        "data": {
            "total_count": total_count,
            "severity": overall_sev,
            "breakdown": breakdown,
        },
        "meta": {
            "timestamp": computed_at,
            "latency_s": round(time.time() - started_at, 3),
            "degraded": degraded,
        },
    }
    _redis_write_json(_REDIS_KEY_SUMMARY, summary)
    _redis_write_json(_REDIS_KEY_COMPUTED_AT, computed_at)

    logger.info(
        "Anomaly detection computed: total=%d severity=%s degraded=%s latency=%.1fs",
        total_count, overall_sev, degraded or "none", time.time() - started_at,
    )
    return summary


def get_cached_summary() -> Optional[Dict[str, Any]]:
    """Read cached anomaly summary from Redis."""
    return _redis_read_json(_REDIS_KEY_SUMMARY)


def get_cached_detail(detector_name: str) -> Optional[Dict[str, Any]]:
    """Read cached detail results for a specific detector from Redis."""
    key_map = {
        "yield": _REDIS_KEY_YIELD,
        "reject": _REDIS_KEY_REJECT,
        "hold": _REDIS_KEY_HOLD,
        "equipment": _REDIS_KEY_EQUIPMENT,
    }
    redis_key = key_map.get(detector_name)
    if not redis_key:
        return None
    return _redis_read_json(redis_key)
