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
import os
import re
import threading
import time
from typing import Optional, Dict, Any

import oracledb
import pandas as pd
from flask import g, current_app
from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError
from sqlalchemy.pool import QueuePool

from mes_dashboard.config.database import DB_CONFIG, CONNECTION_STRING
from mes_dashboard.config.settings import get_config

# Configure module logger
logger = logging.getLogger('mes_dashboard.database')

_REDACTION_INSTALLED = False
_ORACLE_URL_RE = re.compile(r"(oracle\+oracledb://[^:\s/]+:)([^@/\s]+)(@)")
_ENV_SECRET_RE = re.compile(r"(DB_PASSWORD=)([^\s]+)")


def redact_connection_secrets(message: str) -> str:
    """Redact DB credentials from log message text."""
    if not message:
        return message
    sanitized = _ORACLE_URL_RE.sub(r"\1***\3", message)
    sanitized = _ENV_SECRET_RE.sub(r"\1***", sanitized)
    return sanitized


class SecretRedactionFilter(logging.Filter):
    """Filter that masks DB connection secrets in log messages."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:
            return True
        sanitized = redact_connection_secrets(message)
        if sanitized != message:
            record.msg = sanitized
            record.args = ()
        return True


def install_log_redaction_filter(target_logger: logging.Logger | None = None) -> None:
    """Attach secret-redaction filter to mes_dashboard logging handlers once."""
    global _REDACTION_INSTALLED
    if target_logger is None and _REDACTION_INSTALLED:
        return

    logger_obj = target_logger or logging.getLogger("mes_dashboard")
    redaction_filter = SecretRedactionFilter()

    attached = False
    for handler in logger_obj.handlers:
        if any(isinstance(f, SecretRedactionFilter) for f in handler.filters):
            attached = True
            continue
        handler.addFilter(redaction_filter)
        attached = True

    if not attached and not any(isinstance(f, SecretRedactionFilter) for f in logger_obj.filters):
        logger_obj.addFilter(redaction_filter)
        attached = True

    if attached and target_logger is None:
        _REDACTION_INSTALLED = True

# ============================================================
# SQLAlchemy Engine (QueuePool - connection pooling)
# ============================================================
# Using QueuePool for better performance and connection reuse.
# pool_pre_ping ensures connections are valid before use.
# pool_recycle prevents stale connections from firewalls/NAT.

_ENGINE = None
_HEALTH_ENGINE = None
_DB_RUNTIME_CONFIG: Optional[Dict[str, Any]] = None


class DatabaseDegradedError(RuntimeError):
    """Base class for degraded database conditions."""

    def __init__(self, message: str, retry_after_seconds: int = 5):
        super().__init__(message)
        self.retry_after_seconds = max(int(retry_after_seconds), 1)


class DatabasePoolExhaustedError(DatabaseDegradedError):
    """Raised when DB connection pool is exhausted."""


class DatabaseCircuitOpenError(DatabaseDegradedError):
    """Raised when circuit breaker blocks DB access."""


def _from_app_or_env_int(name: str, fallback: int) -> int:
    try:
        app_value = current_app.config.get(name)
        if app_value is not None:
            return int(app_value)
    except RuntimeError:
        pass

    env_value = os.getenv(name)
    if env_value is not None:
        try:
            return int(env_value)
        except (TypeError, ValueError):
            pass
    return int(fallback)


def _from_app_or_env_float(name: str, fallback: float) -> float:
    try:
        app_value = current_app.config.get(name)
        if app_value is not None:
            return float(app_value)
    except RuntimeError:
        pass

    env_value = os.getenv(name)
    if env_value is not None:
        try:
            return float(env_value)
        except (TypeError, ValueError):
            pass
    return float(fallback)


def get_db_runtime_config(refresh: bool = False) -> Dict[str, Any]:
    """Get effective DB runtime configuration used by pool and direct connections."""
    global _DB_RUNTIME_CONFIG
    if _DB_RUNTIME_CONFIG is not None and not refresh:
        return _DB_RUNTIME_CONFIG.copy()

    config_class = get_config(os.getenv("FLASK_ENV"))

    _DB_RUNTIME_CONFIG = {
        "pool_size": _from_app_or_env_int("DB_POOL_SIZE", config_class.DB_POOL_SIZE),
        "max_overflow": _from_app_or_env_int("DB_MAX_OVERFLOW", config_class.DB_MAX_OVERFLOW),
        "pool_timeout": _from_app_or_env_int("DB_POOL_TIMEOUT", config_class.DB_POOL_TIMEOUT),
        "pool_recycle": _from_app_or_env_int("DB_POOL_RECYCLE", config_class.DB_POOL_RECYCLE),
        "tcp_connect_timeout": _from_app_or_env_int(
            "DB_TCP_CONNECT_TIMEOUT",
            config_class.DB_TCP_CONNECT_TIMEOUT,
        ),
        "retry_count": _from_app_or_env_int("DB_CONNECT_RETRY_COUNT", config_class.DB_CONNECT_RETRY_COUNT),
        "retry_delay": _from_app_or_env_float("DB_CONNECT_RETRY_DELAY", config_class.DB_CONNECT_RETRY_DELAY),
        "call_timeout_ms": _from_app_or_env_int("DB_CALL_TIMEOUT_MS", config_class.DB_CALL_TIMEOUT_MS),
        "health_pool_size": _from_app_or_env_int("DB_HEALTH_POOL_SIZE", 1),
        "health_max_overflow": _from_app_or_env_int("DB_HEALTH_MAX_OVERFLOW", 0),
        "health_pool_timeout": _from_app_or_env_int("DB_HEALTH_POOL_TIMEOUT", 2),
        "pool_exhausted_retry_after_seconds": _from_app_or_env_int(
            "DB_POOL_EXHAUSTED_RETRY_AFTER_SECONDS",
            5,
        ),
    }
    return _DB_RUNTIME_CONFIG.copy()


def get_pool_runtime_config() -> Dict[str, Any]:
    """Expose effective DB pool configuration for health diagnostics."""
    return get_db_runtime_config().copy()


def get_pool_status() -> Dict[str, Any]:
    """Expose current DB pool state for health diagnostics."""
    runtime = get_db_runtime_config()
    engine = get_engine()
    pool = engine.pool
    pool_size = int(runtime["pool_size"])
    max_overflow = int(runtime["max_overflow"])
    max_capacity = max(pool_size + max_overflow, 1)
    checked_out = int(pool.checkedout())
    overflow = int(pool.overflow())
    saturation = round(min(max(checked_out / max_capacity, 0.0), 1.0), 4)
    return {
        "size": int(pool.size()),
        "checked_out": checked_out,
        "overflow": overflow,
        "checked_in": int(pool.checkedin()),
        "max_capacity": max_capacity,
        "saturation": saturation,
    }


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
        runtime = get_db_runtime_config()
        _ENGINE = create_engine(
            CONNECTION_STRING,
            poolclass=QueuePool,
            pool_size=runtime["pool_size"],
            max_overflow=runtime["max_overflow"],
            pool_timeout=runtime["pool_timeout"],
            pool_recycle=runtime["pool_recycle"],
            pool_pre_ping=True,       # Validate connection before use
            connect_args={
                "tcp_connect_timeout": runtime["tcp_connect_timeout"],
                "retry_count": runtime["retry_count"],
                "retry_delay": runtime["retry_delay"],
            }
        )
        # Register pool event listeners for monitoring
        _register_pool_events(_ENGINE, runtime["call_timeout_ms"])
        logger.info(
            "Database engine created with QueuePool "
            f"(pool_size={runtime['pool_size']}, "
            f"max_overflow={runtime['max_overflow']}, "
            f"pool_timeout={runtime['pool_timeout']}, "
            f"pool_recycle={runtime['pool_recycle']}, "
            f"call_timeout_ms={runtime['call_timeout_ms']})"
        )
    return _ENGINE


def get_health_engine():
    """Get dedicated SQLAlchemy engine for health probes.

    Health checks use a tiny isolated pool so status probes remain available
    when the request pool is saturated.
    """
    global _HEALTH_ENGINE
    if _HEALTH_ENGINE is None:
        runtime = get_db_runtime_config()
        _HEALTH_ENGINE = create_engine(
            CONNECTION_STRING,
            poolclass=QueuePool,
            pool_size=max(int(runtime["health_pool_size"]), 1),
            max_overflow=max(int(runtime["health_max_overflow"]), 0),
            pool_timeout=max(int(runtime["health_pool_timeout"]), 1),
            pool_recycle=runtime["pool_recycle"],
            pool_pre_ping=True,
            connect_args={
                "tcp_connect_timeout": runtime["tcp_connect_timeout"],
                "retry_count": runtime["retry_count"],
                "retry_delay": runtime["retry_delay"],
            },
        )
        _register_pool_events(
            _HEALTH_ENGINE,
            min(int(runtime["call_timeout_ms"]), 10_000),
        )
        logger.info(
            "Health engine created (pool_size=%s, max_overflow=%s, pool_timeout=%s)",
            runtime["health_pool_size"],
            runtime["health_max_overflow"],
            runtime["health_pool_timeout"],
        )
    return _HEALTH_ENGINE


def _register_pool_events(engine, call_timeout_ms: int):
    """Register event listeners for connection pool monitoring."""

    @event.listens_for(engine, "checkout")
    def on_checkout(dbapi_conn, connection_record, connection_proxy):
        # Keep DB call timeout below worker timeout to avoid wedged workers.
        dbapi_conn.call_timeout = call_timeout_ms
        logger.debug("Connection checked out from pool (call_timeout_ms=%s)", call_timeout_ms)

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
    global _ENGINE, _HEALTH_ENGINE, _DB_RUNTIME_CONFIG
    stop_keepalive()
    if _HEALTH_ENGINE is not None:
        _HEALTH_ENGINE.dispose()
        logger.info("Health engine disposed")
        _HEALTH_ENGINE = None
    if _ENGINE is not None:
        _ENGINE.dispose()
        logger.info("Database engine disposed, all connections closed")
        _ENGINE = None
    _DB_RUNTIME_CONFIG = None


# ============================================================
# Direct Connection Helpers
# ============================================================


def get_db_connection():
    """Create a direct oracledb connection.

    Used for operations that need direct cursor access.
    Includes call_timeout to prevent long-running queries from blocking workers.
    """
    runtime = get_db_runtime_config()
    try:
        conn = oracledb.connect(
            **DB_CONFIG,
            tcp_connect_timeout=runtime["tcp_connect_timeout"],
            retry_count=runtime["retry_count"],
            retry_delay=runtime["retry_delay"],
        )
        conn.call_timeout = runtime["call_timeout_ms"]
        logger.debug(
            "Direct oracledb connection established (call_timeout_ms=%s)",
            runtime["call_timeout_ms"],
        )
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
        retry_after = max(int(getattr(circuit_breaker, "recovery_timeout", 30)), 1)
        raise DatabaseCircuitOpenError(
            "Database service is temporarily unavailable (circuit breaker open)",
            retry_after_seconds=retry_after,
        )

    start_time = time.time()
    engine = get_engine()

    try:
        with engine.connect() as conn:
            df = pd.read_sql(text(sql), conn, params=params)
            df.columns = [str(c).upper() for c in df.columns]

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

    except SQLAlchemyTimeoutError as exc:
        elapsed = time.time() - start_time

        # Record metrics even for failed queries
        record_query_latency(elapsed)

        if CIRCUIT_BREAKER_ENABLED:
            circuit_breaker.record_failure()

        logger.error(
            "Connection pool exhausted after %.2fs - %s",
            elapsed,
            exc,
        )
        retry_after = max(
            int(get_db_runtime_config().get("pool_exhausted_retry_after_seconds", 5)),
            1,
        )
        raise DatabasePoolExhaustedError(
            "Database connection pool exhausted",
            retry_after_seconds=retry_after,
        ) from exc
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
    timeout_seconds: int = 120,
) -> pd.DataFrame:
    """Execute a slow SQL query with a custom timeout via direct oracledb connection.

    Unlike read_sql_df which uses the pooled engine (55s timeout),
    this creates a dedicated connection with a longer call_timeout
    for known-slow queries (e.g. full table scans on large tables).

    Args:
        sql: SQL query string with Oracle bind variables.
        params: Optional dict of parameter values.
        timeout_seconds: Call timeout in seconds (default: 120).

    Returns:
        DataFrame with query results, or None on connection failure.
    """
    start_time = time.time()
    timeout_ms = timeout_seconds * 1000

    conn = None
    try:
        runtime = get_db_runtime_config()
        conn = oracledb.connect(
            **DB_CONFIG,
            tcp_connect_timeout=runtime["tcp_connect_timeout"],
            retry_count=runtime["retry_count"],
            retry_delay=runtime["retry_delay"],
        )
        conn.call_timeout = timeout_ms
        logger.debug(
            "Slow-query connection established (call_timeout_ms=%s)", timeout_ms
        )

        cursor = conn.cursor()
        cursor.execute(sql, params or {})
        columns = [desc[0].upper() for desc in cursor.description]
        rows = cursor.fetchall()
        cursor.close()

        df = pd.DataFrame(rows, columns=columns)

        elapsed = time.time() - start_time
        if elapsed > 1.0:
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
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


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
        return {'error': '查詢服務暫時無法使用'}


def get_table_column_metadata(table_name: str) -> Dict[str, Any]:
    """Get column metadata from Oracle ALL_TAB_COLUMNS.

    Args:
        table_name: Table name in format 'SCHEMA.TABLE' or 'TABLE'

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
