# -*- coding: utf-8 -*-
"""Database connection and query utilities for MES Dashboard."""

from __future__ import annotations

from typing import Optional, Dict, Any

import oracledb
import pandas as pd
from flask import g, current_app
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

from mes_dashboard.config.database import DB_CONFIG, CONNECTION_STRING
from mes_dashboard.config.settings import DevelopmentConfig

# ============================================================
# SQLAlchemy Engine (NullPool - no connection pooling)
# ============================================================
# Using NullPool for dashboard applications that need long-term stability.
# Each query creates a new connection and closes it immediately after use.
# This avoids issues with idle connections being dropped by firewalls/NAT.

_ENGINE = None


def get_engine():
    """Get SQLAlchemy engine without connection pooling.

    Uses NullPool to create fresh connections for each request.
    This is more reliable for long-running dashboard applications
    where idle connections may be dropped by network infrastructure.
    """
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = create_engine(
            CONNECTION_STRING,
            poolclass=NullPool,  # No connection pooling - fresh connection each time
            connect_args={
                "tcp_connect_timeout": 15,   # TCP connect timeout 15s
                "retry_count": 2,            # Retry twice on connection failure
                "retry_delay": 1,            # 1s delay between retries
            }
        )
    return _ENGINE


# ============================================================
# Request-scoped Connection
# ============================================================


def get_db():
    """Get request-scoped database connection via Flask g."""
    if "db" not in g:
        g.db = get_engine().connect()
    return g.db


def close_db(_exc: Optional[BaseException] = None) -> None:
    """Close request-scoped connection."""
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db(app) -> None:
    """Register database teardown handlers on the Flask app."""
    app.teardown_appcontext(close_db)


# ============================================================
# Keep-Alive (No-op with NullPool)
# ============================================================
# Keep-alive is not needed with NullPool since each query creates
# a fresh connection. These functions are kept for API compatibility.

def start_keepalive():
    """No-op: Keep-alive not needed with NullPool."""
    print("[DB] Using NullPool - no keep-alive needed")


def stop_keepalive():
    """No-op: Keep-alive not needed with NullPool."""
    pass


# ============================================================
# Direct Connection Helpers
# ============================================================


def get_db_connection():
    """Create a direct oracledb connection.

    Used for operations that need direct cursor access.
    """
    try:
        return oracledb.connect(
            **DB_CONFIG,
            tcp_connect_timeout=10,  # TCP connect timeout 10s
            retry_count=1,           # Retry once on connection failure
            retry_delay=1,           # 1s delay between retries
        )
    except Exception as exc:
        print(f"Database connection failed: {exc}")
        return None


def read_sql_df(sql: str, params: Optional[Dict[str, Any]] = None) -> pd.DataFrame:
    """Execute SQL query and return results as a DataFrame."""
    engine = get_engine()
    with engine.connect() as conn:
        df = pd.read_sql(text(sql), conn, params=params)
        df.columns = [str(c).upper() for c in df.columns]
        return df


# ============================================================
# Table Utilities
# ============================================================


def get_table_columns(table_name: str) -> list:
    """Get column names for a table."""
    connection = get_db_connection()
    if not connection:
        return []

    try:
        cursor = connection.cursor()
        cursor.execute(f"SELECT * FROM {table_name} WHERE ROWNUM <= 1")
        columns = [desc[0] for desc in cursor.description]
        cursor.close()
        connection.close()
        return columns
    except Exception:
        if connection:
            connection.close()
        return []


def get_table_data(
    table_name: str,
    limit: int = 1000,
    time_field: Optional[str] = None,
    filters: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Fetch rows from a table with optional filtering and sorting."""
    from datetime import datetime

    connection = get_db_connection()
    if not connection:
        return {'error': 'Database connection failed'}

    try:
        cursor = connection.cursor()

        where_conditions = []
        bind_params = {}

        if filters:
            for col, val in filters.items():
                if val and val.strip():
                    safe_col = ''.join(c for c in col if c.isalnum() or c == '_')
                    param_name = f"p_{safe_col}"
                    where_conditions.append(
                        f"UPPER(TO_CHAR({safe_col})) LIKE UPPER(:{param_name})"
                    )
                    bind_params[param_name] = f"%{val.strip()}%"

        if time_field:
            time_condition = f"{time_field} IS NOT NULL"
            if where_conditions:
                all_conditions = " AND ".join([time_condition] + where_conditions)
            else:
                all_conditions = time_condition

            sql = f"""
                SELECT * FROM (
                    SELECT * FROM {table_name}
                    WHERE {all_conditions}
                    ORDER BY {time_field} DESC
                ) WHERE ROWNUM <= :row_limit
            """
        else:
            if where_conditions:
                all_conditions = " AND ".join(where_conditions)
                sql = f"""
                    SELECT * FROM (
                        SELECT * FROM {table_name}
                        WHERE {all_conditions}
                    ) WHERE ROWNUM <= :row_limit
                """
            else:
                sql = f"""
                    SELECT * FROM {table_name}
                    WHERE ROWNUM <= :row_limit
                """

        bind_params['row_limit'] = limit
        cursor.execute(sql, bind_params)
        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()

        data = []
        for row in rows:
            row_dict = {}
            for i, col in enumerate(columns):
                value = row[i]
                if isinstance(value, datetime):
                    row_dict[col] = value.strftime('%Y-%m-%d %H:%M:%S')
                else:
                    row_dict[col] = value
            data.append(row_dict)

        cursor.close()
        connection.close()

        return {
            'columns': columns,
            'data': data,
            'row_count': len(data)
        }
    except Exception as exc:
        if connection:
            connection.close()
        return {'error': f'查詢失敗: {str(exc)}'}
