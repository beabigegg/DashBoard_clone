# -*- coding: utf-8 -*-
"""Direct-MySQL persistence for the production-achievement daily-plan table
(`production_achievement_daily_plans`, data-shape §3.32).

Read/written directly via ``core/mysql_client.get_mysql_connection()`` --
NEVER via ``core/sync_worker.py`` (mirrors
``production_achievement_target_service.py``'s ``text()`` +
``get_mysql_connection()`` idiom exactly).

Keyed on ``(workcenter_group, package_lf_group)`` -- both already-MERGED/
resolved values (post D1/D2 mapping) -- with NO shift dimension, unlike
``production_achievement_targets`` (§3.26, keyed on
``(shift_code, workcenter_group)``). The two tables are fully independent
and coexist: this table is an ADDITIVE new denominator concept for the
DailyView/CumulativeView report modes (business-rules.md PA-11/PA-12/PA-13);
writing one table never mutates or reads the other.
"""

from __future__ import annotations

import logging
from numbers import Number
from typing import Any, Dict, List, Optional, Tuple

from mes_dashboard.core.mysql_client import MYSQL_OPS_ENABLED, get_mysql_connection

logger = logging.getLogger("mes_dashboard.production_achievement_daily_plan_service")


class DailyPlanValidationError(ValueError):
    """Raised when ``daily_plan_qty`` fails non-negative-integer validation."""


class MySQLUnavailableError(RuntimeError):
    """Raised by write operations when MySQL OPS is disabled or unreachable."""


def validate_daily_plan_qty(daily_plan_qty: Any) -> int:
    """Validate ``daily_plan_qty`` is a non-negative integer (data-shape
    §3.32; mirrors ``production_achievement_target_service.validate_target_qty``
    exactly).

    Accepts int, or float with an integral value. Rejects bool, negative
    values, and non-numeric input. Raises DailyPlanValidationError otherwise.
    Never touches MySQL -- callers (routes) validate at the API boundary
    BEFORE any MySQL round-trip and return 400 VALIDATION_ERROR.
    """
    if isinstance(daily_plan_qty, bool):
        raise DailyPlanValidationError("daily_plan_qty must be a non-negative integer")
    if not isinstance(daily_plan_qty, Number):
        raise DailyPlanValidationError("daily_plan_qty must be a non-negative integer")
    if isinstance(daily_plan_qty, float) and not daily_plan_qty.is_integer():
        raise DailyPlanValidationError("daily_plan_qty must be a non-negative integer")
    value = int(daily_plan_qty)
    if value < 0:
        raise DailyPlanValidationError("daily_plan_qty must be a non-negative integer")
    return value


def get_daily_plans(
    *, workcenter_group: Optional[str] = None, package_lf_group: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Return daily_plans rows, optionally filtered by
    workcenter_group/package_lf_group.

    Used by ``GET /api/production-achievement/daily-plans``. Degrades to []
    when MYSQL_OPS_ENABLED=false or MySQL is unreachable -- callers treat a
    missing key as a null daily_plan_qty (PA-12), never a 500.
    """
    if not MYSQL_OPS_ENABLED:
        return []
    try:
        from sqlalchemy import text

        clauses = []
        params: Dict[str, Any] = {}
        if workcenter_group:
            clauses.append("workcenter_group = :workcenter_group")
            params["workcenter_group"] = workcenter_group
        if package_lf_group:
            clauses.append("package_lf_group = :package_lf_group")
            params["package_lf_group"] = package_lf_group
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

        with get_mysql_connection() as conn:
            result = conn.execute(
                text(
                    "SELECT workcenter_group, package_lf_group, daily_plan_qty, updated_at, updated_by "
                    f"FROM production_achievement_daily_plans {where}"
                ),
                params,
            )
            rows = result.fetchall()
            return [
                {
                    "workcenter_group": r._mapping["workcenter_group"],
                    "package_lf_group": r._mapping["package_lf_group"],
                    "daily_plan_qty": r._mapping["daily_plan_qty"],
                    "updated_at": r._mapping["updated_at"],
                    "updated_by": r._mapping["updated_by"],
                }
                for r in rows
            ]
    except Exception as exc:
        logger.warning(
            "production_achievement_daily_plan_service: read failed, degrading to []: %s",
            exc,
        )
        return []


def get_daily_plans_map() -> Dict[Tuple[str, str], Optional[int]]:
    """Return {(workcenter_group, package_lf_group): daily_plan_qty} for all
    rows (data-shape §3.32).

    Sourced for the inline ``daily_plan_map`` array injected in the
    ``GET /report`` 200 spool-hit envelope (data-shape-contract.md §3.34).
    Degrades to {} when unavailable -- every client-computed
    daily/cumulative achievement_rate becomes null (PA-12/PA-13), never a 500.
    """
    return {
        (row["workcenter_group"], row["package_lf_group"]): row["daily_plan_qty"]
        for row in get_daily_plans()
    }


def upsert_daily_plan(
    *, workcenter_group: str, package_lf_group: str, daily_plan_qty: int, updated_by: str
) -> None:
    """Upsert (INSERT ... ON DUPLICATE KEY UPDATE) a daily_plans row, keyed
    on ``(workcenter_group, package_lf_group)`` (data-shape §3.32 unique
    constraint).

    Caller must call ``validate_daily_plan_qty()`` before invoking this
    (routes validate at the API boundary and return 400 VALIDATION_ERROR).
    Never writes to ``production_achievement_targets`` -- the two tables are
    fully independent (PA-11).

    Raises MySQLUnavailableError when MYSQL_OPS_ENABLED=false or MySQL is
    unreachable -- writes cannot degrade gracefully.
    """
    if not MYSQL_OPS_ENABLED:
        raise MySQLUnavailableError("MySQL OPS is disabled (MYSQL_OPS_ENABLED=false)")

    from sqlalchemy import text

    sql = text(
        """
        INSERT INTO production_achievement_daily_plans
            (workcenter_group, package_lf_group, daily_plan_qty, updated_at, updated_by)
        VALUES
            (:workcenter_group, :package_lf_group, :daily_plan_qty, NOW(), :updated_by)
        ON DUPLICATE KEY UPDATE
            daily_plan_qty = VALUES(daily_plan_qty),
            updated_at = NOW(),
            updated_by = VALUES(updated_by)
        """
    )
    try:
        with get_mysql_connection() as conn:
            conn.execute(
                sql,
                {
                    "workcenter_group": workcenter_group,
                    "package_lf_group": package_lf_group,
                    "daily_plan_qty": daily_plan_qty,
                    "updated_by": updated_by,
                },
            )
    except Exception as exc:
        logger.warning(
            "production_achievement_daily_plan_service: write failed: %s", exc
        )
        raise MySQLUnavailableError(str(exc)) from exc


def bulk_upsert_daily_plans(
    rows: List[Dict[str, Any]], *, updated_by: str
) -> int:
    """Upsert multiple daily_plans rows in a SINGLE transaction (Excel-import
    confirm step, business-rules.md PA-16) -- unlike ``upsert_daily_plan``
    (one connection/commit per call), all rows share one
    ``get_mysql_connection()`` context so a mid-batch failure rolls back the
    ENTIRE batch (no partial import).

    Each row dict must have ``workcenter_group``, ``package_lf_group``,
    ``daily_plan_qty`` (already validated by the caller via
    ``validate_daily_plan_qty`` -- this function does not re-validate).
    Returns the number of rows upserted. Raises MySQLUnavailableError when
    MYSQL_OPS_ENABLED=false or MySQL is unreachable.
    """
    if not MYSQL_OPS_ENABLED:
        raise MySQLUnavailableError("MySQL OPS is disabled (MYSQL_OPS_ENABLED=false)")
    if not rows:
        return 0

    from sqlalchemy import text

    sql = text(
        """
        INSERT INTO production_achievement_daily_plans
            (workcenter_group, package_lf_group, daily_plan_qty, updated_at, updated_by)
        VALUES
            (:workcenter_group, :package_lf_group, :daily_plan_qty, NOW(), :updated_by)
        ON DUPLICATE KEY UPDATE
            daily_plan_qty = VALUES(daily_plan_qty),
            updated_at = NOW(),
            updated_by = VALUES(updated_by)
        """
    )
    try:
        with get_mysql_connection() as conn:
            for row in rows:
                conn.execute(
                    sql,
                    {
                        "workcenter_group": row["workcenter_group"],
                        "package_lf_group": row["package_lf_group"],
                        "daily_plan_qty": row["daily_plan_qty"],
                        "updated_by": updated_by,
                    },
                )
    except Exception as exc:
        logger.warning(
            "production_achievement_daily_plan_service: bulk write failed, rolled back: %s",
            exc,
        )
        raise MySQLUnavailableError(str(exc)) from exc

    return len(rows)
