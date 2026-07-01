# -*- coding: utf-8 -*-
"""User Usage KPI service — aggregates login session data for the KPI dashboard.

Queries MySQL (dashboard_login_sessions) when available, falls back to SQLite.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import text

logger = logging.getLogger("mes_dashboard.user_usage_kpi_service")


def _get_sqlite_active_session_ids() -> set:
    """Return session_ids of currently active sessions from SQLite (authoritative source)."""
    try:
        from mes_dashboard.core.login_session_store import get_login_session_store
        store = get_login_session_store()
        if not store._initialized:
            store.initialize()
        cutoff = (datetime.now() - timedelta(minutes=30)).isoformat()
        with store._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT session_id FROM login_sessions "
                "WHERE logout_time IS NULL AND last_active >= ?",
                (cutoff,),
            )
            return {row[0] for row in cursor.fetchall()}
    except Exception:
        return set()


# Duration bucket boundaries in seconds
_DURATION_BUCKETS = [
    ("<5min", 0, 300),
    ("5-30min", 300, 1800),
    ("30min-1h", 1800, 3600),
    ("1-2h", 3600, 7200),
    ("2-4h", 7200, 14400),
    ("4h+", 14400, None),
]


def get_user_usage_kpi(
    start_date: str,
    end_date: str,
    department: Optional[str] = None,
) -> Dict[str, Any]:
    """Return all KPI data for the user usage dashboard.

    Args:
        start_date: ISO date string (e.g. "2026-02-18")
        end_date: ISO date string (e.g. "2026-03-20")
        department: Optional department filter

    Returns:
        Dict with overview, dau_trend, hourly_logins, duration_distribution,
        top_users, dept_breakdown, recent_sessions, departments_available, source.
    """
    from mes_dashboard.core.mysql_client import MYSQL_OPS_ENABLED

    # end_date is inclusive — queries use < end_date + 1 day
    try:
        end_dt = datetime.fromisoformat(end_date) + timedelta(days=1)
        end_date_exclusive = end_dt.strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        end_date_exclusive = end_date

    if MYSQL_OPS_ENABLED:
        try:
            return _query_mysql(start_date, end_date_exclusive, department)
        except Exception as e:
            logger.warning("MySQL query failed, falling back to SQLite: %s", e)

    return _query_sqlite(start_date, end_date_exclusive, department)


# ============================================================
# MySQL queries
# ============================================================

def _query_mysql(
    start_date: str,
    end_date_exclusive: str,
    department: Optional[str],
) -> Dict[str, Any]:
    from mes_dashboard.core.mysql_client import get_mysql_connection

    dept_filter = "AND department = :department" if department else ""
    params: Dict[str, Any] = {"start_date": start_date, "end_date": end_date_exclusive}
    if department:
        params["department"] = department

    with get_mysql_connection() as conn:
        # Overview — period
        row = conn.execute(text(f"""
            SELECT COUNT(DISTINCT emp_id) AS unique_users,
                   COUNT(*) AS total_sessions,
                   AVG(duration_sec) AS avg_duration_sec
            FROM dashboard_login_sessions
            WHERE login_time >= :start_date AND login_time < :end_date
            {dept_filter}
        """), params).mappings().first()
        overview = {
            "unique_users": row["unique_users"] if row else 0,
            "total_sessions": row["total_sessions"] if row else 0,
            "avg_duration_sec": _safe_int(row["avg_duration_sec"]) if row else 0,
        }

        # Active sessions — always use SQLite (authoritative real-time source).
        # online_sessions = presence (short window); active_sessions = 30-min engagement.
        from mes_dashboard.core.login_session_store import get_login_session_store
        _store = get_login_session_store()
        overview["online_sessions"] = _store.get_online_count()
        overview["active_sessions"] = _store.get_active_count()

        # DAU trend
        dau_rows = conn.execute(text(f"""
            SELECT DATE(login_time) AS date,
                   COUNT(DISTINCT emp_id) AS unique_users,
                   COUNT(*) AS sessions
            FROM dashboard_login_sessions
            WHERE login_time >= :start_date AND login_time < :end_date
            {dept_filter}
            GROUP BY DATE(login_time)
            ORDER BY date ASC
        """), params).mappings().all()
        dau_trend = [{"date": str(r["date"]), "unique_users": r["unique_users"], "sessions": r["sessions"]} for r in dau_rows]

        # Hourly logins
        hourly_rows = conn.execute(text(f"""
            SELECT HOUR(login_time) AS hour, COUNT(*) AS count
            FROM dashboard_login_sessions
            WHERE login_time >= :start_date AND login_time < :end_date
            {dept_filter}
            GROUP BY HOUR(login_time)
            ORDER BY hour ASC
        """), params).mappings().all()
        hourly_map = {r["hour"]: r["count"] for r in hourly_rows}
        hourly_logins = [{"hour": h, "count": hourly_map.get(h, 0)} for h in range(24)]

        # Duration distribution
        duration_rows = conn.execute(text(f"""
            SELECT duration_sec FROM dashboard_login_sessions
            WHERE duration_sec IS NOT NULL
              AND login_time >= :start_date AND login_time < :end_date
            {dept_filter}
        """), params).mappings().all()
        duration_distribution = _compute_duration_buckets([r["duration_sec"] for r in duration_rows])

        # Top users
        top_rows = conn.execute(text(f"""
            SELECT emp_id AS username, display_name, department,
                   COUNT(*) AS login_count,
                   AVG(duration_sec) AS avg_duration_sec
            FROM dashboard_login_sessions
            WHERE login_time >= :start_date AND login_time < :end_date
            {dept_filter}
            GROUP BY emp_id, display_name, department
            ORDER BY login_count DESC
            LIMIT 10
        """), params).mappings().all()
        top_users = [
            {
                "username": r["username"],
                "display_name": r["display_name"],
                "department": r["department"],
                "login_count": r["login_count"],
                "avg_duration_sec": _safe_int(r["avg_duration_sec"]),
            }
            for r in top_rows
        ]

        # Department breakdown
        dept_rows = conn.execute(text(f"""
            SELECT department,
                   COUNT(DISTINCT emp_id) AS unique_users,
                   COUNT(*) AS total_sessions,
                   AVG(duration_sec) AS avg_duration_sec
            FROM dashboard_login_sessions
            WHERE login_time >= :start_date AND login_time < :end_date
              AND department IS NOT NULL AND department != ''
            {dept_filter}
            GROUP BY department
            ORDER BY total_sessions DESC
        """), params).mappings().all()
        dept_breakdown = [
            {
                "department": r["department"],
                "unique_users": r["unique_users"],
                "total_sessions": r["total_sessions"],
                "avg_duration_sec": _safe_int(r["avg_duration_sec"]),
            }
            for r in dept_rows
        ]

        # Recent sessions (status from MySQL may lag behind SQLite;
        # cross-reference with authoritative SQLite active sessions by session_id)
        recent_rows = conn.execute(text("""
            SELECT session_id, emp_id AS username, display_name, department,
                   login_time, duration_sec,
                   CASE WHEN logout_time IS NULL AND last_active >= DATE_SUB(NOW(), INTERVAL 30 MINUTE)
                        THEN 'active' ELSE 'ended' END AS status
            FROM dashboard_login_sessions
            ORDER BY login_time DESC
            LIMIT 20
        """)).mappings().all()
        active_sids = _get_sqlite_active_session_ids()
        recent_sessions = [
            {
                "username": r["username"],
                "display_name": r["display_name"],
                "department": r["department"],
                "login_time": str(r["login_time"]) if r["login_time"] else None,
                "duration_sec": r["duration_sec"],
                "status": "active" if r["session_id"] in active_sids else r["status"],
            }
            for r in recent_rows
        ]

        # Available departments
        dept_list_rows = conn.execute(text("""
            SELECT DISTINCT department FROM dashboard_login_sessions
            WHERE department IS NOT NULL AND department != ''
            ORDER BY department
        """)).mappings().all()
        departments_available = [r["department"] for r in dept_list_rows]

    return {
        "overview": overview,
        "dau_trend": dau_trend,
        "hourly_logins": hourly_logins,
        "duration_distribution": duration_distribution,
        "top_users": top_users,
        "dept_breakdown": dept_breakdown,
        "recent_sessions": recent_sessions,
        "departments_available": departments_available,
        "source": "mysql",
    }


# ============================================================
# SQLite queries
# ============================================================

def _query_sqlite(
    start_date: str,
    end_date_exclusive: str,
    department: Optional[str],
) -> Dict[str, Any]:
    from mes_dashboard.core.login_session_store import get_login_session_store

    store = get_login_session_store()
    dept_filter = "AND department = ?" if department else ""
    base_params: list = [start_date, end_date_exclusive]
    if department:
        base_params.append(department)

    with store._get_connection() as conn:
        cursor = conn.cursor()

        # Overview — period
        cursor.execute(f"""
            SELECT COUNT(DISTINCT emp_id) AS unique_users,
                   COUNT(*) AS total_sessions,
                   AVG(duration_sec) AS avg_duration_sec
            FROM login_sessions
            WHERE login_time >= ? AND login_time < ?
            {dept_filter}
        """, base_params)
        row = cursor.fetchone()
        overview = {
            "unique_users": row[0] if row else 0,
            "total_sessions": row[1] if row else 0,
            "avg_duration_sec": _safe_int(row[2]) if row else 0,
        }

        # Active sessions — use LoginSessionStore (consistent with MySQL path).
        # online_sessions = presence (short window); active_sessions = 30-min engagement.
        from mes_dashboard.core.login_session_store import get_login_session_store
        _store = get_login_session_store()
        overview["online_sessions"] = _store.get_online_count()
        overview["active_sessions"] = _store.get_active_count()

        # DAU trend
        cursor.execute(f"""
            SELECT DATE(login_time) AS date,
                   COUNT(DISTINCT emp_id) AS unique_users,
                   COUNT(*) AS sessions
            FROM login_sessions
            WHERE login_time >= ? AND login_time < ?
            {dept_filter}
            GROUP BY DATE(login_time)
            ORDER BY date ASC
        """, base_params)
        dau_trend = [{"date": r[0], "unique_users": r[1], "sessions": r[2]} for r in cursor.fetchall()]

        # Hourly logins
        cursor.execute(f"""
            SELECT CAST(strftime('%H', login_time) AS INTEGER) AS hour,
                   COUNT(*) AS count
            FROM login_sessions
            WHERE login_time >= ? AND login_time < ?
            {dept_filter}
            GROUP BY hour
            ORDER BY hour ASC
        """, base_params)
        hourly_map = {r[0]: r[1] for r in cursor.fetchall()}
        hourly_logins = [{"hour": h, "count": hourly_map.get(h, 0)} for h in range(24)]

        # Duration distribution
        cursor.execute(f"""
            SELECT duration_sec FROM login_sessions
            WHERE duration_sec IS NOT NULL
              AND login_time >= ? AND login_time < ?
            {dept_filter}
        """, base_params)
        durations = [r[0] for r in cursor.fetchall()]
        duration_distribution = _compute_duration_buckets(durations)

        # Top users
        cursor.execute(f"""
            SELECT emp_id, display_name, department,
                   COUNT(*) AS login_count,
                   AVG(duration_sec) AS avg_duration_sec
            FROM login_sessions
            WHERE login_time >= ? AND login_time < ?
            {dept_filter}
            GROUP BY emp_id, display_name, department
            ORDER BY login_count DESC
            LIMIT 10
        """, base_params)
        top_users = [
            {
                "username": r[0],
                "display_name": r[1],
                "department": r[2],
                "login_count": r[3],
                "avg_duration_sec": _safe_int(r[4]),
            }
            for r in cursor.fetchall()
        ]

        # Department breakdown
        cursor.execute(f"""
            SELECT department,
                   COUNT(DISTINCT emp_id) AS unique_users,
                   COUNT(*) AS total_sessions,
                   AVG(duration_sec) AS avg_duration_sec
            FROM login_sessions
            WHERE login_time >= ? AND login_time < ?
              AND department IS NOT NULL AND department != ''
            {dept_filter}
            GROUP BY department
            ORDER BY total_sessions DESC
        """, base_params)
        dept_breakdown = [
            {
                "department": r[0],
                "unique_users": r[1],
                "total_sessions": r[2],
                "avg_duration_sec": _safe_int(r[3]),
            }
            for r in cursor.fetchall()
        ]

        # Recent sessions
        cursor.execute("""
            SELECT emp_id, display_name, department, login_time, duration_sec,
                   CASE WHEN logout_time IS NULL AND last_active >= datetime('now', '-30 minutes')
                        THEN 'active' ELSE 'ended' END AS status
            FROM login_sessions
            ORDER BY login_time DESC
            LIMIT 20
        """)
        recent_sessions = [
            {
                "username": r[0],
                "display_name": r[1],
                "department": r[2],
                "login_time": r[3],
                "duration_sec": r[4],
                "status": r[5],
            }
            for r in cursor.fetchall()
        ]

        # Available departments
        cursor.execute("""
            SELECT DISTINCT department FROM login_sessions
            WHERE department IS NOT NULL AND department != ''
            ORDER BY department
        """)
        departments_available = [r[0] for r in cursor.fetchall()]

    return {
        "overview": overview,
        "dau_trend": dau_trend,
        "hourly_logins": hourly_logins,
        "duration_distribution": duration_distribution,
        "top_users": top_users,
        "dept_breakdown": dept_breakdown,
        "recent_sessions": recent_sessions,
        "departments_available": departments_available,
        "source": "sqlite",
    }


# ============================================================
# Helpers
# ============================================================

def _safe_int(value: Any) -> int:
    """Convert a value to int, defaulting to 0."""
    if value is None:
        return 0
    try:
        return int(round(float(value)))
    except (ValueError, TypeError):
        return 0


def _compute_duration_buckets(durations: List[int]) -> List[Dict[str, Any]]:
    """Bucket a list of duration_sec values into predefined ranges."""
    counts = {label: 0 for label, _, _ in _DURATION_BUCKETS}
    for d in durations:
        for label, lo, hi in _DURATION_BUCKETS:
            if hi is None:
                if d >= lo:
                    counts[label] += 1
                    break
            elif lo <= d < hi:
                counts[label] += 1
                break
    return [{"bucket": label, "count": counts[label]} for label, _, _ in _DURATION_BUCKETS]
