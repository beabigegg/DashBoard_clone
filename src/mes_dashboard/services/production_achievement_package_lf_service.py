# -*- coding: utf-8 -*-
"""Direct-MySQL persistence for the production-achievement PACKAGE_LF
merge-mapping table (`production_achievement_package_lf_map`, data-shape
§3.30, D1 -- sparse exceptions-only, fallback-to-self on absence).

Read/written directly via ``core/mysql_client.get_mysql_connection()`` --
NEVER via ``core/sync_worker.py`` (same immediate-consistency rationale as
``production_achievement_target_service.py``, whose ``text()`` +
``get_mysql_connection()`` idiom this module mirrors exactly).

D1 vs D2 (business-rules.md PA-09/PA-10): this table's default-on-absence is
fallback-to-self (a raw PACKAGE_LF with no row here groups under itself) --
the OPPOSITE default from ``production_achievement_workcenter_merge_service``
(D2, exclude-by-absence). Do NOT normalize the two to the same join kind.

Oracle default layer (production-achievement-oracle-plan-source, PA-09
amendment): ``DWH.MES_WIP_OUTPUTPLAN_DETAIL`` (the same table PA-11's plan
targets resolve their Package Group names through) is now consulted as the
DEFAULT source for the raw->merged mapping -- this table's manual rows are a
sparse OVERRIDE layer on top of it, not the primary source anymore. Merge
order in ``get_package_lf_map()``: Oracle defaults, then manual D1 rows
overwrite any Oracle value for the same raw code, then absence of both falls
back to the raw value itself (client-side COALESCE, unchanged). This keeps
D1 genuinely sparse/exceptions-only instead of requiring a manual row for
every one of the ~46 Oracle-known codes.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, List, Optional

from mes_dashboard.config.constants import (
    CACHE_TTL_PRODUCTION_ACHIEVEMENT_PACKAGE_LF_ORACLE,
)
from mes_dashboard.core.database import read_sql_df
from mes_dashboard.core.mysql_client import MYSQL_OPS_ENABLED, get_mysql_connection
from mes_dashboard.sql import SQLLoader

logger = logging.getLogger("mes_dashboard.production_achievement_package_lf_service")

_UNCLASSIFIED_SENTINEL = "(未分類)"

_ORACLE_CACHE_TTL_SECONDS = CACHE_TTL_PRODUCTION_ACHIEVEMENT_PACKAGE_LF_ORACLE
# {"map": {raw: oracle_group}, "loaded_at": epoch_seconds} once populated
_ORACLE_CACHE: Dict[str, Any] = {}
_ORACLE_CACHE_LOCK = threading.Lock()


class MySQLUnavailableError(RuntimeError):
    """Raised by write operations when MySQL OPS is disabled or unreachable."""


def resolve_package_lf_group(raw_package_lf: Optional[str], mapping: Dict[str, str]) -> str:
    """Python mirror of the client-side D1 LEFT JOIN + COALESCE resolution
    (business-rules.md PA-09) -- unit-test / parity-verification helper
    ONLY. The real resolution runs client-side in DuckDB-WASM
    (``useProductionAchievementDuckDB.ts``); this service never performs the
    join on the request path (ADR-0016 extended -- rollup stays client-side).

    LEFT JOIN semantics (never INNER JOIN -- that is PA-10's opposite
    default): a raw value absent from ``mapping`` is NOT excluded, it falls
    back to itself. NULL/blank resolves to the sentinel group "(未分類)".
    """
    if raw_package_lf is None or not str(raw_package_lf).strip():
        return _UNCLASSIFIED_SENTINEL
    return mapping.get(raw_package_lf, raw_package_lf)


def get_package_lf_entries() -> List[Dict[str, Any]]:
    """Return all package_lf_map rows (full shape incl. updated_at/updated_by).

    Used by ``GET /api/production-achievement/package-lf-map``. Degrades to
    [] when MYSQL_OPS_ENABLED=false or MySQL is unreachable (D1: an empty
    table under fallback-to-self default is a valid, if maximally-fragmented,
    report -- never an error state).
    """
    if not MYSQL_OPS_ENABLED:
        return []
    try:
        from sqlalchemy import text

        with get_mysql_connection() as conn:
            result = conn.execute(
                text(
                    "SELECT raw_package_lf, merged_group, updated_at, updated_by "
                    "FROM production_achievement_package_lf_map "
                    "ORDER BY raw_package_lf ASC"
                )
            )
            rows = result.fetchall()
            return [
                {
                    "raw_package_lf": r._mapping["raw_package_lf"],
                    "merged_group": r._mapping["merged_group"],
                    "updated_at": r._mapping["updated_at"],
                    "updated_by": r._mapping["updated_by"],
                }
                for r in rows
            ]
    except Exception as exc:
        logger.warning(
            "production_achievement_package_lf_service: read failed, degrading to []: %s",
            exc,
        )
        return []


def _query_oracle_package_lf_map() -> Dict[str, str]:
    sql = SQLLoader.load("production_achievement_package_lf_oracle")
    df = read_sql_df(sql, caller="production_achievement_package_lf_service")
    return {
        row["RAW_PACKAGE_LF"]: row["ORACLE_MERGED_GROUP"]
        for _, row in df.iterrows()
    }


def get_oracle_package_lf_map(force_refresh: bool = False) -> Dict[str, str]:
    """Return {raw_package_lf: oracle_merged_group} straight from
    ``DWH.MES_WIP_OUTPUTPLAN_DETAIL`` (the D1 default layer, PA-09).

    Cached globally (this is a static ~46-row reference table, not date-
    partitioned like PA-11's plan rows) with TTL
    ``CACHE_TTL_PRODUCTION_ACHIEVEMENT_PACKAGE_LF_ORACLE``. Degrades to {}
    on Oracle failure (or to the last-known-good cached value if one exists)
    -- never raises, matching every other Oracle-sourced cache in this
    feature.
    """
    with _ORACLE_CACHE_LOCK:
        if (
            not force_refresh
            and _ORACLE_CACHE.get("map") is not None
            and time.time() - _ORACLE_CACHE["loaded_at"] < _ORACLE_CACHE_TTL_SECONDS
        ):
            return _ORACLE_CACHE["map"]

    try:
        oracle_map = _query_oracle_package_lf_map()
    except Exception as exc:
        logger.warning(
            "production_achievement_package_lf_service: Oracle read failed, "
            "degrading to {} (or last-known-good): %s",
            exc,
        )
        with _ORACLE_CACHE_LOCK:
            if _ORACLE_CACHE.get("map") is not None:
                return _ORACLE_CACHE["map"]
        return {}

    with _ORACLE_CACHE_LOCK:
        _ORACLE_CACHE["map"] = oracle_map
        _ORACLE_CACHE["loaded_at"] = time.time()
    return oracle_map


def get_package_lf_map(force_refresh: bool = False) -> Dict[str, str]:
    """Return {raw_package_lf: merged_group} (data-shape §3.30), merging the
    Oracle default layer with D1's manual override rows on top.

    Sourced for the inline ``package_lf_map`` array injected in the
    ``GET /report`` 200 spool-hit envelope (data-shape-contract.md §3.33).
    Merge order: start from ``get_oracle_package_lf_map()`` (the default),
    then overwrite with every manual ``production_achievement_package_lf_map``
    row for the same raw code -- a manual row always wins over Oracle's
    value, which is exactly what makes D1 an exceptions-only OVERRIDE layer
    rather than a duplicate of Oracle's own mapping. Degrades gracefully when
    either source is unavailable -- a raw value present in neither still
    falls back to itself client-side (COALESCE, unchanged).
    """
    merged = dict(get_oracle_package_lf_map(force_refresh=force_refresh))
    merged.update(
        {row["raw_package_lf"]: row["merged_group"] for row in get_package_lf_entries()}
    )
    return merged


def upsert_package_lf(*, raw_package_lf: str, merged_group: str, updated_by: str) -> None:
    """Upsert (INSERT ... ON DUPLICATE KEY UPDATE) a package_lf_map row,
    keyed on ``raw_package_lf`` (data-shape §3.30 unique constraint).

    Raises MySQLUnavailableError when MYSQL_OPS_ENABLED=false or MySQL is
    unreachable -- writes cannot degrade gracefully.
    """
    if not MYSQL_OPS_ENABLED:
        raise MySQLUnavailableError("MySQL OPS is disabled (MYSQL_OPS_ENABLED=false)")

    from sqlalchemy import text

    sql = text(
        """
        INSERT INTO production_achievement_package_lf_map
            (raw_package_lf, merged_group, updated_at, updated_by)
        VALUES
            (:raw_package_lf, :merged_group, NOW(), :updated_by)
        ON DUPLICATE KEY UPDATE
            merged_group = VALUES(merged_group),
            updated_at = NOW(),
            updated_by = VALUES(updated_by)
        """
    )
    try:
        with get_mysql_connection() as conn:
            conn.execute(
                sql,
                {
                    "raw_package_lf": raw_package_lf,
                    "merged_group": merged_group,
                    "updated_by": updated_by,
                },
            )
    except Exception as exc:
        logger.warning(
            "production_achievement_package_lf_service: write failed: %s", exc
        )
        raise MySQLUnavailableError(str(exc)) from exc


def delete_package_lf(*, raw_package_lf: str) -> bool:
    """Delete a package_lf_map row by ``raw_package_lf``.

    Returns True if a row was deleted, False if no matching row existed (the
    route surfaces this as 404). Raises MySQLUnavailableError when
    MYSQL_OPS_ENABLED=false or MySQL is unreachable.
    """
    if not MYSQL_OPS_ENABLED:
        raise MySQLUnavailableError("MySQL OPS is disabled (MYSQL_OPS_ENABLED=false)")

    from sqlalchemy import text

    sql = text(
        "DELETE FROM production_achievement_package_lf_map WHERE raw_package_lf = :raw_package_lf"
    )
    try:
        with get_mysql_connection() as conn:
            result = conn.execute(sql, {"raw_package_lf": raw_package_lf})
            return bool(result.rowcount)
    except Exception as exc:
        logger.warning(
            "production_achievement_package_lf_service: delete failed: %s", exc
        )
        raise MySQLUnavailableError(str(exc)) from exc
