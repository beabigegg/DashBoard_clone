# -*- coding: utf-8 -*-
"""Direct-MySQL persistence for the production-achievement target-value table
(`production_achievement_targets`, data-shape §3.26).

Read/written directly via ``core/mysql_client.get_mysql_connection()`` --
NEVER via ``core/sync_worker.py`` (design.md: same immediate-consistency
rationale as the permission table). No date dimension: one row per
``(shift_code, workcenter_group)``; the same target value is reused for every
``output_date`` in a report query.
"""

from __future__ import annotations

import logging
from numbers import Number
from typing import Any, Dict, List, Optional

from mes_dashboard.core.mysql_client import MYSQL_OPS_ENABLED, get_mysql_connection

logger = logging.getLogger("mes_dashboard.production_achievement_target_service")


class TargetValidationError(ValueError):
    """Raised when ``target_qty`` fails non-negative-integer validation."""


class MySQLUnavailableError(RuntimeError):
    """Raised by write operations when MySQL OPS is disabled or unreachable."""


def validate_target_qty(target_qty: Any) -> int:
    """Validate ``target_qty`` is a non-negative integer (data-shape §3.26).

    Accepts int, or float with an integral value (e.g. 500.0). Rejects bool
    (subclass of int, but not a legitimate quantity), negative values, and
    non-numeric input. Raises TargetValidationError otherwise.
    """
    if isinstance(target_qty, bool):
        raise TargetValidationError("target_qty must be a non-negative integer")
    if not isinstance(target_qty, Number):
        raise TargetValidationError("target_qty must be a non-negative integer")
    if isinstance(target_qty, float) and not target_qty.is_integer():
        raise TargetValidationError("target_qty must be a non-negative integer")
    value = int(target_qty)
    if value < 0:
        raise TargetValidationError("target_qty must be a non-negative integer")
    return value


def get_targets(
    *, shift_code: Optional[str] = None, workcenter_group: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Return target rows, optionally filtered by shift_code/workcenter_group.

    Degrades to [] when MYSQL_OPS_ENABLED=false or MySQL is unreachable --
    callers (production_achievement_service) treat a missing key as a null
    target (PA-07), never a 500.
    """
    if not MYSQL_OPS_ENABLED:
        return []
    try:
        from sqlalchemy import text

        clauses = []
        params: Dict[str, Any] = {}
        if shift_code:
            clauses.append("shift_code = :shift_code")
            params["shift_code"] = shift_code
        if workcenter_group:
            clauses.append("workcenter_group = :workcenter_group")
            params["workcenter_group"] = workcenter_group
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

        with get_mysql_connection() as conn:
            result = conn.execute(
                text(
                    "SELECT shift_code, workcenter_group, target_qty, updated_at, updated_by "
                    f"FROM production_achievement_targets {where}"
                ),
                params,
            )
            rows = result.fetchall()
            return [
                {
                    "shift_code": r._mapping["shift_code"],
                    "workcenter_group": r._mapping["workcenter_group"],
                    "target_qty": r._mapping["target_qty"],
                    "updated_at": r._mapping["updated_at"],
                    "updated_by": r._mapping["updated_by"],
                }
                for r in rows
            ]
    except Exception as exc:
        logger.warning(
            "production_achievement_target_service: read failed, degrading to []: %s",
            exc,
        )
        return []


def get_targets_map() -> Dict[tuple, Optional[int]]:
    """Return {(shift_code, workcenter_group): target_qty} for all rows.

    Used by production_achievement_service to join target values onto
    actual-output groups (PA-06/PA-07). Degrades to {} when unavailable.
    """
    return {
        (row["shift_code"], row["workcenter_group"]): row["target_qty"]
        for row in get_targets()
    }


def upsert_target(
    *, shift_code: str, workcenter_group: str, target_qty: int, updated_by: str
) -> None:
    """Upsert (INSERT ... ON DUPLICATE KEY UPDATE) a target row, keyed on
    ``(shift_code, workcenter_group)`` (data-shape §3.26 unique constraint).

    Caller must call ``validate_target_qty()`` before invoking this (routes
    validate at the API boundary and return 400 VALIDATION_ERROR).

    Raises MySQLUnavailableError when MYSQL_OPS_ENABLED=false or MySQL is
    unreachable -- writes cannot degrade gracefully.
    """
    if not MYSQL_OPS_ENABLED:
        raise MySQLUnavailableError("MySQL OPS is disabled (MYSQL_OPS_ENABLED=false)")

    from sqlalchemy import text

    sql = text(
        """
        INSERT INTO production_achievement_targets
            (shift_code, workcenter_group, target_qty, updated_at, updated_by)
        VALUES
            (:shift_code, :workcenter_group, :target_qty, NOW(), :updated_by)
        ON DUPLICATE KEY UPDATE
            target_qty = VALUES(target_qty),
            updated_at = NOW(),
            updated_by = VALUES(updated_by)
        """
    )
    try:
        with get_mysql_connection() as conn:
            conn.execute(
                sql,
                {
                    "shift_code": shift_code,
                    "workcenter_group": workcenter_group,
                    "target_qty": target_qty,
                    "updated_by": updated_by,
                },
            )
    except Exception as exc:
        logger.warning(
            "production_achievement_target_service: write failed: %s", exc
        )
        raise MySQLUnavailableError(str(exc)) from exc
