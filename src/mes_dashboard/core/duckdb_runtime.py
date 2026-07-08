# -*- coding: utf-8 -*-
"""Shared DuckDB runtime factory and policy for heavy-query modules.

All heavy-query DuckDB runtimes must obtain connections through this module
so that memory limits, thread limits, and error semantics are consistent
across domains (reject, production-history, material-trace, query-tool,
anomaly detection, etc.).

Environment variables:
  DUCKDB_MEMORY_LIMIT  – Memory budget per connection (default: "512MB").
  DUCKDB_THREADS       – Thread count per connection (default: 2).

Usage::

    from mes_dashboard.core.duckdb_runtime import (
        create_heavy_query_connection,
        SpoolMissError,
    )

    try:
        conn = create_heavy_query_connection()
        result = conn.execute("SELECT … FROM read_parquet(?)", [spool_path]).fetchall()
    except SpoolMissError:
        return http_expired_response()
    finally:
        conn.close()
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import duckdb

logger = logging.getLogger("mes_dashboard.duckdb_runtime")


# ============================================================
# Policy constants (env-configurable)
# ============================================================

def _str_env(name: str, default: str) -> str:
    return os.getenv(name, default).strip() or default


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return max(int(raw), 1)
    except (TypeError, ValueError):
        return default


DUCKDB_MEMORY_LIMIT: str = _str_env("DUCKDB_MEMORY_LIMIT", "512MB")
DUCKDB_THREADS: int = _int_env("DUCKDB_THREADS", 2)

# Temp-dir for spill; falls back to OS default when empty.
DUCKDB_TEMP_DIR: str = _str_env("DUCKDB_TEMP_DIR", "")


# ============================================================
# Exception types
# ============================================================

class SpoolMissError(RuntimeError):
    """Raised when a required Parquet spool result is missing or expired.

    Callers should translate this into an explicit result-lifecycle
    response (HTTP 404 / 410 or equivalent) rather than silently
    falling back to a second canonical result-storage path.
    """


class DuckDBRuntimeError(RuntimeError):
    """Raised when the DuckDB runtime cannot execute a query."""


# ============================================================
# Connection factory
# ============================================================

def create_heavy_query_connection() -> "duckdb.DuckDBPyConnection":
    """Return a DuckDB in-memory connection with the shared runtime policy.

    Applies DUCKDB_MEMORY_LIMIT and DUCKDB_THREADS so that all heavy-query
    runtimes operate within predictable resource bounds.

    The caller is responsible for closing the connection when done.

    Returns:
        DuckDB connection with memory and thread limits applied.

    Raises:
        ImportError: If duckdb is not installed.
        DuckDBRuntimeError: If connection creation or policy application fails.
    """
    try:
        import duckdb  # type: ignore
    except ImportError:
        raise ImportError("duckdb package is required for heavy-query runtime")

    try:
        conn = duckdb.connect(database=":memory:")
    except Exception as exc:
        raise DuckDBRuntimeError(f"Failed to create DuckDB connection: {exc}") from exc

    try:
        conn.execute(f"SET memory_limit='{DUCKDB_MEMORY_LIMIT}'")
        conn.execute(f"SET threads={DUCKDB_THREADS}")
        if DUCKDB_TEMP_DIR:
            conn.execute(f"SET temp_directory='{DUCKDB_TEMP_DIR}'")
    except Exception as exc:
        try:
            conn.close()
        except Exception:
            pass
        raise DuckDBRuntimeError(f"Failed to apply DuckDB runtime policy: {exc}") from exc

    return conn


def _resolve_temp_dir() -> str | None:
    """Return the absolute temp-spill directory DuckDB actually uses.

    ``DUCKDB_TEMP_DIR`` is empty by default, so an env-only lookup reports
    nothing. But an in-memory connection still spills to a default directory
    (``.tmp`` relative to CWD in current DuckDB). Probe the live connection's
    ``temp_directory`` setting so telemetry reflects the real spill location;
    fall back to the configured env path if the probe fails.
    """
    try:
        conn = create_heavy_query_connection()
        try:
            row = conn.execute("SELECT current_setting('temp_directory')").fetchone()
        finally:
            conn.close()
        probed = (row[0] if row else "") or ""
        if probed:
            return os.path.abspath(probed)
    except Exception:
        pass
    return os.path.abspath(DUCKDB_TEMP_DIR) if DUCKDB_TEMP_DIR else None


def _dir_size_bytes(path: str) -> int:
    """Recursively sum file sizes under *path*; 0 if the dir is absent/unreadable.

    DuckDB may nest spill files in sub-directories, so this walks the tree
    rather than a single ``scandir`` level.
    """
    total = 0
    try:
        for root, _dirs, files in os.walk(path):
            for name in files:
                try:
                    total += os.stat(os.path.join(root, name)).st_size
                except OSError:
                    continue
    except OSError:
        return 0
    return total


def get_duckdb_telemetry() -> dict:
    """Return DuckDB runtime telemetry for admin performance-detail endpoint.

    Includes temp-dir disk usage and memory-limit configuration state.
    Never raises — returns null fields on any failure.

    Returns:
        Dict with keys:
          - ``temp_dir_bytes``: total bytes spilled under the active temp
            directory. ``0`` when the directory exists-but-empty or has not
            been created yet (no spill); ``None`` only when the temp directory
            cannot be resolved at all.
          - ``memory_limit_state``: configured per-connection memory limit.
    """
    temp_dir = _resolve_temp_dir()
    temp_dir_bytes = _dir_size_bytes(temp_dir) if temp_dir else None

    return {
        "temp_dir_bytes": temp_dir_bytes,
        "memory_limit_state": DUCKDB_MEMORY_LIMIT or None,
    }


def assert_spool_path(spool_path: str | None, query_id: str = "") -> str:
    """Assert that *spool_path* is non-empty and return it.

    Raises SpoolMissError with a descriptive message if the path is None
    or empty, ensuring callers never proceed silently on a spool miss.

    Args:
        spool_path: Resolved spool file path (or None on miss).
        query_id:   Optional query identity for the error message.

    Returns:
        *spool_path* unchanged.

    Raises:
        SpoolMissError: If *spool_path* is None or empty.
    """
    if not spool_path:
        label = f" (query_id={query_id})" if query_id else ""
        raise SpoolMissError(f"Spool result not found or expired{label}")
    return spool_path
