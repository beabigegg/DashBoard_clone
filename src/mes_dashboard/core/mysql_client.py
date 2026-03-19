# -*- coding: utf-8 -*-
"""MySQL connection management for the dual-layer (SQLite + MySQL) sync architecture.

Provides a SQLAlchemy engine singleton for the MySQL OPS database,
separate from the Oracle engine used for business data.
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Generator, Optional

logger = logging.getLogger('mes_dashboard.mysql_client')

# ============================================================
# Configuration
# ============================================================

MYSQL_OPS_ENABLED: bool = os.getenv('MYSQL_OPS_ENABLED', 'false').lower() == 'true'

_MYSQL_HOST = os.getenv('MYSQL_OPS_HOST', 'localhost')
_MYSQL_PORT = int(os.getenv('MYSQL_OPS_PORT', '3306'))
_MYSQL_USER = os.getenv('MYSQL_OPS_USER', '')
_MYSQL_PASSWORD = os.getenv('MYSQL_OPS_PASSWORD', '')
_MYSQL_DATABASE = os.getenv('MYSQL_OPS_DATABASE', '')

# ============================================================
# Engine Singleton
# ============================================================

_mysql_engine = None


def create_mysql_engine():
    """Build a new SQLAlchemy engine for the MySQL OPS database."""
    from sqlalchemy import create_engine as sa_create_engine

    url = (
        f"mysql+pymysql://{_MYSQL_USER}:{_MYSQL_PASSWORD}"
        f"@{_MYSQL_HOST}:{_MYSQL_PORT}/{_MYSQL_DATABASE}"
        f"?charset=utf8mb4"
    )
    return sa_create_engine(
        url,
        pool_size=3,
        max_overflow=2,
        pool_pre_ping=True,
        pool_recycle=1800,
    )


def get_mysql_engine():
    """Return the global MySQL engine singleton, creating it if needed."""
    global _mysql_engine
    if _mysql_engine is None:
        if not MYSQL_OPS_ENABLED:
            raise RuntimeError("MySQL OPS is disabled (MYSQL_OPS_ENABLED=false)")
        _mysql_engine = create_mysql_engine()
        logger.info("MySQL OPS engine created (%s:%d/%s)", _MYSQL_HOST, _MYSQL_PORT, _MYSQL_DATABASE)
    return _mysql_engine


@contextmanager
def get_mysql_connection() -> Generator:
    """Context manager that yields a MySQL connection from the pool."""
    engine = get_mysql_engine()
    conn = engine.connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def check_mysql_health() -> bool:
    """Run a SELECT 1 health check. Returns True if healthy."""
    try:
        with get_mysql_connection() as conn:
            from sqlalchemy import text
            conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        logger.warning("MySQL health check failed: %s", exc)
        return False


def dispose_mysql_engine() -> None:
    """Dispose the global MySQL engine (call during shutdown)."""
    global _mysql_engine
    if _mysql_engine is not None:
        try:
            _mysql_engine.dispose()
            logger.info("MySQL OPS engine disposed")
        except Exception as exc:
            logger.warning("Error disposing MySQL engine: %s", exc)
        _mysql_engine = None
