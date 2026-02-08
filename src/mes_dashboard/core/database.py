# -*- coding: utf-8 -*-
"""Database connection and query utilities for MES Dashboard.

Connection Management:
    - Uses SQLAlchemy with QueuePool for connection pooling
    - Background keep-alive thread prevents idle connection drops
    - Request-scoped connections via Flask g object

Query Execution (Recommended Pattern):
    Use SQLLoader + QueryBuilder for safe, parameterized queries:

    >>> from mes_dashboard.sql import SQLLoader, QueryBuilder
    >>> from mes_dashboard.core.database import read_sql_df
    >>>
    >>> # Load SQL template from file
    >>> sql = SQLLoader.load("resource/by_status")
    >>>
    >>> # Build conditions with parameters (SQL injection safe)
    >>> builder = QueryBuilder()
    >>> builder.add_in_condition("STATUS", ["PRD", "SBY"])
    >>> builder.add_param_condition("LOCATION", "FAB1")
    >>> where_clause, params = builder.build_where_only()
    >>>
    >>> # Replace placeholders and execute
    >>> sql = sql.replace("{{ WHERE_CLAUSE }}", where_clause)
    >>> df = read_sql_df(sql, params)

    SQL files are stored in src/mes_dashboard/sql/<module>/<query>.sql
    with LRU caching (max 100 files).
"""

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


def get_engine(app_config=None):
    """Get SQLAlchemy engine with connection pooling.

    Uses QueuePool for connection reuse and better performance.

    Args:
        app_config: Optional Flask app.config dict. If provided,
                   reads DB_POOL_SIZE and DB_MAX_OVERFLOW from config.
    """
    global _ENGINE
    if _ENGINE is None:
        pool_size = app_config.get('DB_POOL_SIZE', 5) if app_config else 5
        max_overflow = app_config.get('DB_MAX_OVERFLOW', 10) if app_config else 10
        _ENGINE = create_engine(
            CONNECTION_STRING,
            poolclass=QueuePool,
            pool_size=pool_size,
            max_overflow=max_overflow,
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
            f"(pool_size={pool_size}, max_overflow={max_overflow}, pool_recycle=1800)"
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


def get_db_connection(call_timeout_ms: int = 55000):
    """Create a direct oracledb connection.

    Used for operations that need direct cursor access.
    Includes call_timeout to prevent long-running queries from blocking workers.

    Args:
        call_timeout_ms: Query timeout in milliseconds (default 55000 = 55s)
    """
    try:
        conn = oracledb.connect(
            **DB_CONFIG,
            tcp_connect_timeout=10,  # TCP connect timeout 10s
            retry_count=1,           # Retry once on connection failure
            retry_delay=1,           # 1s delay between retries
        )
        # Set call timeout (must be less than Gunicorn's 60s worker timeout)
        # This prevents queries from blocking workers indefinitely
        conn.call_timeout = call_timeout_ms
        logger.debug(f"Direct oracledb connection established (call_timeout={call_timeout_ms}ms)")
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

    Args:
        sql: SQL query string. Can include Oracle bind variables (:param_name)
            for parameterized queries. Use SQLLoader to load SQL from files.
        params: Optional dict of parameter values to bind to the query.
            Use QueryBuilder to construct safe parameterized conditions.

    Returns:
        DataFrame with query results. Column names are uppercased.

    Raises:
        Exception: If query execution fails. ORA code is logged.
        RuntimeError: If circuit breaker is open (service degraded).

    Example:
        >>> sql = "SELECT * FROM users WHERE status = :status"
        >>> df = read_sql_df(sql, {"status": "active"})

    Note:
        - Slow queries (>1s) are logged as warnings
        - All queries use connection pooling via SQLAlchemy
        - Call timeout is set to 55s to prevent worker blocking
        - Circuit breaker protects against cascading failures
        - Query latency is recorded for metrics
    """
    from mes_dashboard.core.circuit_breaker import (
        get_database_circuit_breaker,
        CIRCUIT_BREAKER_ENABLED
    )
    from mes_dashboard.core.metrics import record_query_latency

    # Check circuit breaker before executing
    circuit_breaker = get_database_circuit_breaker()
    if not circuit_breaker.allow_request():
        logger.warning("Circuit breaker OPEN - rejecting database query")
        raise RuntimeError("Database service is temporarily unavailable (circuit breaker open)")

    start_time = time.time()
    engine = get_engine()

    try:
        with engine.connect() as conn:
            # SQLAlchemy 2.0: execute text() with params dict, then convert to DataFrame
            stmt = text(sql)
            result = conn.execute(stmt, params or {})
            rows = result.fetchall()
            columns = [str(c).upper() for c in result.keys()]
            df = pd.DataFrame(rows, columns=columns)

            elapsed = time.time() - start_time

            # Record metrics
            record_query_latency(elapsed)

            # Record success to circuit breaker
            if CIRCUIT_BREAKER_ENABLED:
                circuit_breaker.record_success()

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

        # Record metrics even for failed queries
        record_query_latency(elapsed)

        # Record failure to circuit breaker
        if CIRCUIT_BREAKER_ENABLED:
            circuit_breaker.record_failure()

        ora_code = _extract_ora_code(exc)
        sql_preview = sql.strip().replace('\n', ' ')[:100]
        logger.error(
            f"Query failed after {elapsed:.2f}s - ORA-{ora_code}: {exc} | SQL: {sql_preview}..."
        )
        raise


def read_sql_df_slow(
    sql: str,
    params: Optional[Dict[str, Any]] = None,
    timeout_seconds: int = 90
) -> pd.DataFrame:
    """Execute slow SQL query with dedicated connection and timeout.

    This function is designed for known slow queries that should not:
    - Block the connection pool (uses direct connection)
    - Affect circuit breaker state (timeouts are expected)

    Args:
        sql: SQL query string with Oracle bind variables (:param_name)
        params: Optional dict of parameter values to bind
        timeout_seconds: Query timeout in seconds (default 90s)

    Returns:
        DataFrame with query results. Column names are uppercased.

    Raises:
        TimeoutError: If query exceeds timeout (ORA-01013)
        RuntimeError: If connection fails
        Exception: Other database errors

    Example:
        >>> sql = "SELECT * FROM large_table WHERE id = :id"
        >>> df = read_sql_df_slow(sql, {"id": "123"}, timeout_seconds=60)
    """
    from mes_dashboard.core.metrics import record_query_latency

    start_time = time.time()

    # Use dedicated connection with custom timeout (not from pool)
    conn = get_db_connection(call_timeout_ms=timeout_seconds * 1000)
    if conn is None:
        raise RuntimeError("Failed to establish database connection for slow query")

    try:
        cursor = conn.cursor()

        # Execute with bind parameters
        if params:
            cursor.execute(sql, params)
        else:
            cursor.execute(sql)

        # Fetch results
        columns = [desc[0].upper() for desc in cursor.description]
        rows = cursor.fetchall()

        # Convert to DataFrame
        df = pd.DataFrame(rows, columns=columns)

        elapsed = time.time() - start_time

        # Record metrics (but not to circuit breaker - slow queries are expected)
        record_query_latency(elapsed)

        logger.info(f"Slow query completed in {elapsed:.2f}s, rows={len(df)}")
        return df

    except oracledb.DatabaseError as exc:
        elapsed = time.time() - start_time
        record_query_latency(elapsed)

        error_obj = exc.args[0] if exc.args else None
        ora_code = getattr(error_obj, 'code', None) or _extract_ora_code(exc)

        sql_preview = sql.strip().replace('\n', ' ')[:100]

        # ORA-01013: user requested cancel of current operation (timeout)
        if ora_code == 1013 or str(ora_code) == '1013':
            logger.warning(
                f"Slow query timed out after {elapsed:.2f}s "
                f"(limit: {timeout_seconds}s) | SQL: {sql_preview}..."
            )
            raise TimeoutError(
                f"Query timed out after {timeout_seconds} seconds"
            ) from exc
        else:
            logger.error(
                f"Slow query failed after {elapsed:.2f}s - ORA-{ora_code}: {exc} | "
                f"SQL: {sql_preview}..."
            )
            raise

    except Exception as exc:
        elapsed = time.time() - start_time
        record_query_latency(elapsed)

        sql_preview = sql.strip().replace('\n', ' ')[:100]
        logger.error(
            f"Slow query failed after {elapsed:.2f}s: {exc} | SQL: {sql_preview}..."
        )
        raise

    finally:
        try:
            conn.close()
            logger.debug("Slow query connection closed")
        except Exception:
            pass


# ============================================================
# Table Utilities
# ============================================================

# Whitelist cache: maps uppercase table name → TABLES_CONFIG entry
_ALLOWED_TABLES: Dict[str, dict] = {}


def _get_table_config(table_name: str) -> Optional[dict]:
    """Look up table in TABLES_CONFIG whitelist.

    Returns the config dict if found, None otherwise.
    """
    global _ALLOWED_TABLES
    if not _ALLOWED_TABLES:
        from mes_dashboard.config.tables import TABLES_CONFIG
        for tables in TABLES_CONFIG.values():
            for t in tables:
                _ALLOWED_TABLES[t['name'].upper()] = t
    return _ALLOWED_TABLES.get(table_name.upper())


def _validate_column_name(col_name: str) -> bool:
    """Validate column name format (alphanumeric + underscore only)."""
    return bool(re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', col_name))


def get_table_columns(table_name: str) -> list:
    """Get column names for a whitelisted table.

    Uses read_sql_df() for connection pooling and circuit breaker.
    """
    if not _get_table_config(table_name):
        logger.warning(f"Table not in whitelist: {table_name}")
        return []

    try:
        # table_name validated against whitelist — safe to embed
        df = read_sql_df(f"SELECT * FROM {table_name} WHERE ROWNUM <= 1")
        return list(df.columns)
    except Exception:
        return []


def get_table_data(
    table_name: str,
    limit: int = 1000,
    time_field: Optional[str] = None,
    filters: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Fetch rows from a whitelisted table with optional filtering and sorting.

    Uses TABLES_CONFIG whitelist + QueryBuilder for safe parameterized queries.
    Executes via read_sql_df() (connection pool + circuit breaker + metrics).
    """
    from mes_dashboard.sql.builder import QueryBuilder

    # 1. Whitelist validation
    table_cfg = _get_table_config(table_name)
    if not table_cfg:
        return {'error': f'不允許查詢的表: {table_name}'}

    # 2. time_field validation: only allow the value defined in TABLES_CONFIG
    if time_field:
        allowed_tf = table_cfg.get('time_field')
        if not allowed_tf or time_field.upper() != allowed_tf.upper():
            return {'error': f'不允許的時間欄位: {time_field}'}

    # 3. Build WHERE clause with QueryBuilder (parameterized)
    builder = QueryBuilder()
    if time_field:
        builder.add_is_not_null(time_field)
    if filters:
        for col, val in filters.items():
            if val and val.strip() and _validate_column_name(col):
                builder.add_like_condition(
                    f"UPPER(TO_CHAR({col}))", val.strip(), position="both"
                )
    where_clause, params = builder.build_where_only()

    # 4. Build SQL (table_name and time_field are whitelist-validated)
    order_by = f"ORDER BY {time_field} DESC" if time_field else ""
    if where_clause or order_by:
        sql = (
            f"SELECT * FROM ("
            f"SELECT * FROM {table_name} {where_clause} {order_by}"
            f") WHERE ROWNUM <= :row_limit"
        )
    else:
        sql = f"SELECT * FROM {table_name} WHERE ROWNUM <= :row_limit"
    params['row_limit'] = limit

    # 5. Execute via read_sql_df (connection pool + circuit breaker + metrics)
    try:
        df = read_sql_df(sql, params)
        # Convert datetime columns to string for JSON serialization
        for col in df.select_dtypes(include=['datetime64']).columns:
            df[col] = df[col].dt.strftime('%Y-%m-%d %H:%M:%S')
        return {
            'columns': list(df.columns),
            'data': df.to_dict('records'),
            'row_count': len(df),
        }
    except Exception as exc:
        logger.error(f"get_table_data failed: {exc}")
        return {'error': f'查詢失敗: {str(exc)}'}


def get_table_column_metadata(table_name: str) -> Dict[str, Any]:
    """Get column metadata from Oracle ALL_TAB_COLUMNS.

    Args:
        table_name: Table name in format 'SCHEMA.TABLE' or 'TABLE'
                   Must be in TABLES_CONFIG whitelist.

    Returns:
        Dict with 'columns' list containing column info:
        - name: Column name
        - data_type: Oracle data type (VARCHAR2, NUMBER, DATE, etc.)
        - data_length: Max length for character types
        - data_precision: Precision for numeric types
        - data_scale: Scale for numeric types
        - is_date: True if column is DATE or TIMESTAMP type
        - is_number: True if column is NUMBER type
    """
    if not _get_table_config(table_name):
        logger.warning(f"Table not in whitelist: {table_name}")
        return {'error': f'不允許查詢的表: {table_name}', 'columns': []}

    connection = get_db_connection()
    if not connection:
        return {'error': 'Database connection failed', 'columns': []}

    try:
        cursor = connection.cursor()

        # Parse schema and table name
        parts = table_name.split('.')
        if len(parts) == 2:
            owner, tbl_name = parts[0].upper(), parts[1].upper()
        else:
            owner = None
            tbl_name = parts[0].upper()

        # Query ALL_TAB_COLUMNS for metadata
        if owner:
            sql = """
                SELECT COLUMN_NAME, DATA_TYPE, DATA_LENGTH,
                       DATA_PRECISION, DATA_SCALE, COLUMN_ID
                FROM ALL_TAB_COLUMNS
                WHERE OWNER = :owner AND TABLE_NAME = :table_name
                ORDER BY COLUMN_ID
            """
            cursor.execute(sql, {'owner': owner, 'table_name': tbl_name})
        else:
            sql = """
                SELECT COLUMN_NAME, DATA_TYPE, DATA_LENGTH,
                       DATA_PRECISION, DATA_SCALE, COLUMN_ID
                FROM ALL_TAB_COLUMNS
                WHERE TABLE_NAME = :table_name
                ORDER BY COLUMN_ID
            """
            cursor.execute(sql, {'table_name': tbl_name})

        rows = cursor.fetchall()
        cursor.close()
        connection.close()

        if not rows:
            # Fallback to basic column detection if no metadata found
            logger.warning(
                f"No metadata found for {table_name}, falling back to basic detection"
            )
            basic_columns = get_table_columns(table_name)
            return {
                'columns': [
                    {
                        'name': col,
                        'data_type': 'UNKNOWN',
                        'data_length': None,
                        'data_precision': None,
                        'data_scale': None,
                        'is_date': False,
                        'is_number': False
                    }
                    for col in basic_columns
                ]
            }

        # Process results
        columns = []
        date_types = {'DATE', 'TIMESTAMP', 'TIMESTAMP WITH TIME ZONE',
                      'TIMESTAMP WITH LOCAL TIME ZONE'}
        number_types = {'NUMBER', 'FLOAT', 'BINARY_FLOAT', 'BINARY_DOUBLE',
                        'INTEGER', 'SMALLINT'}

        for row in rows:
            col_name, data_type, data_length, data_precision, data_scale, _ = row
            columns.append({
                'name': col_name,
                'data_type': data_type,
                'data_length': data_length,
                'data_precision': data_precision,
                'data_scale': data_scale,
                'is_date': data_type in date_types,
                'is_number': data_type in number_types
            })

        logger.debug(f"Retrieved metadata for {table_name}: {len(columns)} columns")
        return {'columns': columns}

    except Exception as exc:
        ora_code = _extract_ora_code(exc)
        logger.warning(
            f"get_table_column_metadata failed - ORA-{ora_code}: {exc}, "
            f"falling back to basic detection"
        )
        if connection:
            connection.close()

        # Fallback to basic column detection
        basic_columns = get_table_columns(table_name)
        return {
            'columns': [
                {
                    'name': col,
                    'data_type': 'UNKNOWN',
                    'data_length': None,
                    'data_precision': None,
                    'data_scale': None,
                    'is_date': False,
                    'is_number': False
                }
                for col in basic_columns
            ]
        }
