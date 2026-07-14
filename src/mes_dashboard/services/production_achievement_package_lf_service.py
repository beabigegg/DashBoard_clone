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
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from mes_dashboard.core.mysql_client import MYSQL_OPS_ENABLED, get_mysql_connection

logger = logging.getLogger("mes_dashboard.production_achievement_package_lf_service")

_UNCLASSIFIED_SENTINEL = "(未分類)"


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


def get_package_lf_map() -> Dict[str, str]:
    """Return {raw_package_lf: merged_group} for all rows (data-shape §3.30).

    Sourced for the inline ``package_lf_map`` array injected in the
    ``GET /report`` 200 spool-hit envelope (data-shape-contract.md §3.33).
    Degrades to {} when unavailable -- D1's own fallback-to-self default
    (every raw value groups under itself), not an error state.
    """
    return {row["raw_package_lf"]: row["merged_group"] for row in get_package_lf_entries()}


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
