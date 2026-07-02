# -*- coding: utf-8 -*-
"""Direct-MySQL persistence for the production-achievement edit-permission
whitelist table (`production_achievement_edit_permissions`, data-shape §3.27).

Read/written directly via ``core/mysql_client.get_mysql_connection()`` --
NEVER via ``core/sync_worker.py`` (design.md: immediate read-your-writes
consistency required for an auth gate; the sync_worker path is a one-way,
~10-min-lag, no-read-back log/metrics sync).

This module owns MySQL I/O only. The authorization decision (fail-closed
interpretation) is made by ``core.permissions.can_edit_targets()``, which
calls ``is_user_whitelisted()`` here and treats any exception as deny.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from mes_dashboard.core.mysql_client import MYSQL_OPS_ENABLED, get_mysql_connection

logger = logging.getLogger("mes_dashboard.production_achievement_permission_service")


class MySQLUnavailableError(RuntimeError):
    """Raised by write operations when MySQL OPS is disabled or unreachable."""


def is_user_whitelisted(user_identifier: str) -> bool:
    """Return True only if a whitelist row exists for ``user_identifier`` with
    ``can_edit_targets = true``.

    Fails closed (returns False) when MYSQL_OPS_ENABLED=false or any MySQL
    exception occurs -- never raises, so callers (core.permissions) can treat
    this as the sole source of truth for the allow/deny decision.
    """
    if not user_identifier:
        return False
    if not MYSQL_OPS_ENABLED:
        return False
    try:
        from sqlalchemy import text

        with get_mysql_connection() as conn:
            result = conn.execute(
                text(
                    "SELECT can_edit_targets FROM production_achievement_edit_permissions "
                    "WHERE user_identifier = :user_identifier LIMIT 1"
                ),
                {"user_identifier": user_identifier},
            )
            row = result.fetchone()
            if row is None:
                return False
            value = row[0]
            return bool(value)
    except Exception as exc:
        logger.warning(
            "production_achievement_permission_service: whitelist lookup failed "
            "for %s, failing closed (deny): %s",
            user_identifier, exc,
        )
        return False


def get_permissions() -> List[Dict[str, Any]]:
    """Return all whitelist rows. Degrades to [] when OPS disabled/unreachable."""
    if not MYSQL_OPS_ENABLED:
        return []
    try:
        from sqlalchemy import text

        with get_mysql_connection() as conn:
            result = conn.execute(
                text(
                    "SELECT user_identifier, can_edit_targets, granted_at, granted_by "
                    "FROM production_achievement_edit_permissions "
                    "ORDER BY user_identifier ASC"
                )
            )
            rows = result.fetchall()
            return [
                {
                    "user_identifier": r._mapping["user_identifier"],
                    "can_edit_targets": bool(r._mapping["can_edit_targets"]),
                    "granted_at": r._mapping["granted_at"],
                    "granted_by": r._mapping["granted_by"],
                }
                for r in rows
            ]
    except Exception as exc:
        logger.warning(
            "production_achievement_permission_service: read failed, degrading to []: %s",
            exc,
        )
        return []


def upsert_permission(
    *, user_identifier: str, can_edit_targets: bool, granted_by: str
) -> None:
    """Upsert (INSERT ... ON DUPLICATE KEY UPDATE) a whitelist row, keyed on
    ``user_identifier`` (data-shape §3.27 unique constraint).

    Raises MySQLUnavailableError when MYSQL_OPS_ENABLED=false or MySQL is
    unreachable -- writes cannot degrade gracefully (design.md: caller must
    surface 503 SERVICE_UNAVAILABLE).
    """
    if not MYSQL_OPS_ENABLED:
        raise MySQLUnavailableError("MySQL OPS is disabled (MYSQL_OPS_ENABLED=false)")

    from sqlalchemy import text

    sql = text(
        """
        INSERT INTO production_achievement_edit_permissions
            (user_identifier, can_edit_targets, granted_at, granted_by)
        VALUES
            (:user_identifier, :can_edit_targets, NOW(), :granted_by)
        ON DUPLICATE KEY UPDATE
            can_edit_targets = VALUES(can_edit_targets),
            granted_at = NOW(),
            granted_by = VALUES(granted_by)
        """
    )
    try:
        with get_mysql_connection() as conn:
            conn.execute(
                sql,
                {
                    "user_identifier": user_identifier,
                    "can_edit_targets": bool(can_edit_targets),
                    "granted_by": granted_by,
                },
            )
    except Exception as exc:
        logger.warning(
            "production_achievement_permission_service: write failed: %s", exc
        )
        raise MySQLUnavailableError(str(exc)) from exc
