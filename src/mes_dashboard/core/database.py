# -*- coding: utf-8 -*-
"""Database connection and query utilities for MES Dashboard."""

from __future__ import annotations

import logging
import re
import threading
import time
from typing import Optional, Dict, Any

import oracledb
import pandas as pd
from flask import g, current_app
from sqlalchemy import create_engine, event, text
from sqlalchemy.pool import QueuePool

from mes_dashboard.config.database import DB_CONFIG, CONNECTION_STRING
from mes_dashboard.config.settings import DevelopmentConfig

# Configure module logger
logger = logging.getLogger('mes_dashboard.database')

# ============================================================
# SQLAlchemy Engine (QueuePool - connection pooling)
# ============================================================
# Using QueuePool for better performance and connection reuse.
# pool_pre_ping ensures connections are valid before use.
# pool_recycle prevents stale connections from firewalls/NAT.

_ENGINE = None


def get_engine():
    """Get SQLAlchemy engine with connection pooling.

    Uses QueuePool for connection reuse and better performance.
    - pool_size: Base number of persistent connections
    - max_overflow: Additional connections during peak load
    - pool_timeout: Max wait time for available connection
    - pool_recycle: Recycle connections after 30 minutes
    - pool_pre_ping: Validate connection before checkout
    """
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = create_engine(
            CONNECTION_STRING,
            poolclass=QueuePool,
            pool_size=5,              # Base connections
            max_overflow=10,          # Peak extra connections (total max: 15)
            pool_timeout=30,          # Wait up to 30s for connection
            pool_recycle=1800,        # Recycle connections every 30 minutes
            pool_pre_ping=True,       # Validate connection before use
            connect_args={
                "tcp_connect_timeout": 10,   # TCP connect timeout 10s (reduced)
                "retry_count": 1,            # Retry once on connection failure
                "retry_delay": 1,            # 1s delay between retries
            }
        )
        # Register pool event listeners for monitoring
        _register_pool_events(_ENGINE)
        logger.info(
            "Database engine created with QueuePool "
            f"(pool_size=5, max_overflow=10, pool_recycle=1800)"
        )
    return _ENGINE


def _register_pool_events(engine):
    """Register event listeners for connection pool monitoring."""

    @event.listens_for(engine, "checkout")
    def on_checkout(dbapi_conn, connection_record, connection_proxy):
        # Set call_timeout to prevent queries from blocking workers indefinitely
        # 55 seconds (must be less than Gunicorn's 60s worker timeout)
        dbapi_conn.call_timeout = 55000  # milliseconds
        logger.debug("Connection checked out from pool (call_timeout=55s)")

    @event.listens_for(engine, "checkin")
    def on_checkin(dbapi_conn, connection_record):
        logger.debug("Connection returned to pool")

    @event.listens_for(engine, "invalidate")
    def on_invalidate(dbapi_conn, connection_record, exception):
        if exception:
            logger.warning(f"Connection invalidated due to: {exception}")
        else:
            logger.debug("Connection invalidated (soft)")

    @event.listens_for(engine, "connect")
    def on_connect(dbapi_conn, connection_record):
        logger.info("New database connection established")


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
# Keep-Alive for Connection Pool
# ============================================================
# Periodic keep-alive prevents idle connections from being dropped
# by firewalls/NAT. Runs every 5 minutes in a background thread.

_KEEPALIVE_THREAD = None
_KEEPALIVE_STOP = threading.Event()
KEEPALIVE_INTERVAL = 300  # 5 minutes


def _keepalive_worker():
    """Background worker that pings the database periodically."""
    while not _KEEPALIVE_STOP.wait(KEEPALIVE_INTERVAL):
        try:
            engine = get_engine()
            with engine.connect() as conn:
                conn.execute(text("SELECT 1 FROM DUAL"))
            logger.debug("Keep-alive ping successful")
        except Exception as exc:
            logger.warning(f"Keep-alive ping failed: {exc}")


def start_keepalive():
    """Start background keep-alive thread for connection pool."""
    global _KEEPALIVE_THREAD
    if _KEEPALIVE_THREAD is None or not _KEEPALIVE_THREAD.is_alive():
        _KEEPALIVE_STOP.clear()
        _KEEPALIVE_THREAD = threading.Thread(
            target=_keepalive_worker,
            daemon=True,
            name="db-keepalive"
        )
        _KEEPALIVE_THREAD.start()
        logger.info(f"Keep-alive thread started (interval: {KEEPALIVE_INTERVAL}s)")


def stop_keepalive():
    """Stop the keep-alive background thread."""
    global _KEEPALIVE_THREAD
    if _KEEPALIVE_THREAD and _KEEPALIVE_THREAD.is_alive():
        _KEEPALIVE_STOP.set()
        _KEEPALIVE_THREAD.join(timeout=5)
        logger.info("Keep-alive thread stopped")


def dispose_engine():
    """Dispose the database engine and all pooled connections.

    Call this during application shutdown to cleanly release resources.
    """
    global _ENGINE
    stop_keepalive()
    if _ENGINE is not None:
        _ENGINE.dispose()
        logger.info("Database engine disposed, all connections closed")
        _ENGINE = None


# ============================================================
# Direct Connection Helpers
# ============================================================


def get_db_connection():
    """Create a direct oracledb connection.

    Used for operations that need direct cursor access.
    Includes call_timeout to prevent long-running queries from blocking workers.
    """
    try:
        conn = oracledb.connect(
            **DB_CONFIG,
            tcp_connect_timeout=10,  # TCP connect timeout 10s
            retry_count=1,           # Retry once on connection failure
            retry_delay=1,           # 1s delay between retries
        )
        # Set call timeout to 55 seconds (must be less than Gunicorn's 60s worker timeout)
        # This prevents queries from blocking workers indefinitely
        conn.call_timeout = 55000  # milliseconds
        logger.debug("Direct oracledb connection established (call_timeout=55s)")
        return conn
    except Exception as exc:
        ora_code = _extract_ora_code(exc)
        logger.error(f"Database connection failed - ORA-{ora_code}: {exc}")
        return None


def _extract_ora_code(exc: Exception) -> str:
    """Extract ORA error code from exception message."""
    match = re.search(r'ORA-(\d+)', str(exc))
    return match.group(1) if match else 'UNKNOWN'


def read_sql_df(sql: str, params: Optional[Dict[str, Any]] = None) -> pd.DataFrame:
    """Execute SQL query and return results as a DataFrame.

    Includes query timing and error logging with ORA codes.
    """
    start_time = time.time()
    engine = get_engine()

    try:
        with engine.connect() as conn:
            df = pd.read_sql(text(sql), conn, params=params)
            df.columns = [str(c).upper() for c in df.columns]

            elapsed = time.time() - start_time
            # Log slow queries (>1 second) as warnings
            if elapsed > 1.0:
                # Truncate SQL for logging (first 100 chars)
                sql_preview = sql.strip().replace('\n', ' ')[:100]
                logger.warning(f"Slow query ({elapsed:.2f}s): {sql_preview}...")
            else:
                logger.debug(f"Query completed in {elapsed:.3f}s, rows={len(df)}")

            return df

    except Exception as exc:
        elapsed = time.time() - start_time
        ora_code = _extract_ora_code(exc)
        sql_preview = sql.strip().replace('\n', ' ')[:100]
        logger.error(
            f"Query failed after {elapsed:.2f}s - ORA-{ora_code}: {exc} | SQL: {sql_preview}..."
        )
        raise


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
        ora_code = _extract_ora_code(exc)
        logger.error(f"get_table_data failed - ORA-{ora_code}: {exc}")
        if connection:
            connection.close()
        return {'error': f'查詢失敗: {str(exc)}'}
