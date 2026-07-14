# -*- coding: utf-8 -*-
"""Direct-MySQL persistence for the production-achievement workcenter
merge-mapping table (`production_achievement_workcenter_merge_map`,
data-shape §3.31, D2 -- explicit-inclusion, exclude-by-absence).

Read/written directly via ``core/mysql_client.get_mysql_connection()`` --
NEVER via ``core/sync_worker.py`` (mirrors
``production_achievement_target_service.py``'s ``text()`` +
``get_mysql_connection()`` idiom exactly).

D1 vs D2 (business-rules.md PA-09/PA-10): this table's default-on-absence is
exclude-by-absence (a raw workcenter_group with no row here is EXCLUDED from
the report entirely) -- the OPPOSITE default from
``production_achievement_package_lf_service`` (D1, fallback-to-self). Do NOT
normalize the two to the same join kind -- that is the easiest copy-paste
inversion an implementer can make.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from mes_dashboard.core.mysql_client import MYSQL_OPS_ENABLED, get_mysql_connection

logger = logging.getLogger("mes_dashboard.production_achievement_workcenter_merge_service")


class MySQLUnavailableError(RuntimeError):
    """Raised by write operations when MySQL OPS is disabled or unreachable."""


def resolve_workcenter_merge_group(
    raw_workcenter_group: str, mapping: Dict[str, str]
) -> Optional[str]:
    """Python mirror of the client-side D2 INNER JOIN resolution
    (business-rules.md PA-10) -- unit-test / parity-verification helper
    ONLY. The real resolution runs client-side in DuckDB-WASM
    (``useProductionAchievementDuckDB.ts``); this service never performs the
    join on the request path (ADR-0016 extended -- rollup stays client-side).

    INNER JOIN semantics (never LEFT JOIN -- that is PA-09's opposite
    default): a raw value absent from ``mapping`` is EXCLUDED (returns
    None), unlike D1's fallback-to-self.
    """
    return mapping.get(raw_workcenter_group)


def get_workcenter_merge_entries() -> List[Dict[str, Any]]:
    """Return all workcenter_merge_map rows (full shape incl.
    updated_at/updated_by).

    Used by ``GET /api/production-achievement/workcenter-merge-map``.
    Degrades to [] when MYSQL_OPS_ENABLED=false or MySQL is unreachable --
    D2's downstream effect differs from D1's: an empty table here means the
    INNER JOIN matches zero rows, so the ENTIRE report renders empty (not
    "every raw value shows as its own group").
    """
    if not MYSQL_OPS_ENABLED:
        return []
    try:
        from sqlalchemy import text

        with get_mysql_connection() as conn:
            result = conn.execute(
                text(
                    "SELECT raw_workcenter_group, merged_workcenter_group, updated_at, updated_by "
                    "FROM production_achievement_workcenter_merge_map "
                    "ORDER BY raw_workcenter_group ASC"
                )
            )
            rows = result.fetchall()
            return [
                {
                    "raw_workcenter_group": r._mapping["raw_workcenter_group"],
                    "merged_workcenter_group": r._mapping["merged_workcenter_group"],
                    "updated_at": r._mapping["updated_at"],
                    "updated_by": r._mapping["updated_by"],
                }
                for r in rows
            ]
    except Exception as exc:
        logger.warning(
            "production_achievement_workcenter_merge_service: read failed, degrading to []: %s",
            exc,
        )
        return []


def get_workcenter_merge_map() -> Dict[str, str]:
    """Return {raw_workcenter_group: merged_workcenter_group} for all rows
    (data-shape §3.31).

    Sourced for the inline ``workcenter_merge_map`` array injected in the
    ``GET /report`` 200 spool-hit envelope (data-shape-contract.md §3.33) and
    for ``get_filter_options().workcenter_groups`` (redefined to the merged
    D2 list, production-achievement-overhaul). Degrades to {} when
    unavailable.
    """
    return {
        row["raw_workcenter_group"]: row["merged_workcenter_group"]
        for row in get_workcenter_merge_entries()
    }


def upsert_workcenter_merge(
    *, raw_workcenter_group: str, merged_workcenter_group: str, updated_by: str
) -> None:
    """Upsert (INSERT ... ON DUPLICATE KEY UPDATE) a workcenter_merge_map
    row, keyed on ``raw_workcenter_group`` (data-shape §3.31 unique
    constraint).

    Raises MySQLUnavailableError when MYSQL_OPS_ENABLED=false or MySQL is
    unreachable -- writes cannot degrade gracefully.
    """
    if not MYSQL_OPS_ENABLED:
        raise MySQLUnavailableError("MySQL OPS is disabled (MYSQL_OPS_ENABLED=false)")

    from sqlalchemy import text

    sql = text(
        """
        INSERT INTO production_achievement_workcenter_merge_map
            (raw_workcenter_group, merged_workcenter_group, updated_at, updated_by)
        VALUES
            (:raw_workcenter_group, :merged_workcenter_group, NOW(), :updated_by)
        ON DUPLICATE KEY UPDATE
            merged_workcenter_group = VALUES(merged_workcenter_group),
            updated_at = NOW(),
            updated_by = VALUES(updated_by)
        """
    )
    try:
        with get_mysql_connection() as conn:
            conn.execute(
                sql,
                {
                    "raw_workcenter_group": raw_workcenter_group,
                    "merged_workcenter_group": merged_workcenter_group,
                    "updated_by": updated_by,
                },
            )
    except Exception as exc:
        logger.warning(
            "production_achievement_workcenter_merge_service: write failed: %s", exc
        )
        raise MySQLUnavailableError(str(exc)) from exc


def delete_workcenter_merge(*, raw_workcenter_group: str) -> bool:
    """Delete a workcenter_merge_map row by ``raw_workcenter_group``.

    Returns True if a row was deleted, False if no matching row existed (the
    route surfaces this as 404). Raises MySQLUnavailableError when
    MYSQL_OPS_ENABLED=false or MySQL is unreachable.
    """
    if not MYSQL_OPS_ENABLED:
        raise MySQLUnavailableError("MySQL OPS is disabled (MYSQL_OPS_ENABLED=false)")

    from sqlalchemy import text

    sql = text(
        "DELETE FROM production_achievement_workcenter_merge_map "
        "WHERE raw_workcenter_group = :raw_workcenter_group"
    )
    try:
        with get_mysql_connection() as conn:
            result = conn.execute(sql, {"raw_workcenter_group": raw_workcenter_group})
            return bool(result.rowcount)
    except Exception as exc:
        logger.warning(
            "production_achievement_workcenter_merge_service: delete failed: %s", exc
        )
        raise MySQLUnavailableError(str(exc)) from exc
