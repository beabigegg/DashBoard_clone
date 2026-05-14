# -*- coding: utf-8 -*-
"""Persistent DuckDB cache for resource-history data.

Loads the last RESOURCE_HISTORY_PREWARM_MONTHS months of base_facts and
oee_facts from Oracle at startup. User queries with end_date in
[today-90d, yesterday] are served from DuckDB instead of Oracle.

Tables stored in DuckDB file:
  base_facts  — HISTORYID, DATA_DATE, PRD_HOURS, SBY_HOURS, UDT_HOURS,
                SDT_HOURS, EGT_HOURS, NST_HOURS, TOTAL_HOURS
  oee_facts   — EQUIPMENTID, SHIFT_DATE, TRACKOUT_QTY, NG_QTY
  prewarm_meta — loaded_at, start_date, end_date
"""

from __future__ import annotations

import logging
import os
import threading
import time
from datetime import date, timedelta
from pathlib import Path
from typing import List, Optional

import pandas as pd

logger = logging.getLogger("mes_dashboard.resource_history_duckdb_cache")

_PREWARM_MONTHS: int = int(os.getenv("RESOURCE_HISTORY_PREWARM_MONTHS", "3"))

# DuckDB file path — resolved to absolute; follows the same pattern as QUERY_SPOOL_DIR.
_DUCKDB_RAW_PATH = os.getenv("RESOURCE_HISTORY_DUCKDB_PATH", "tmp/resource_history.duckdb")
_DUCKDB_PATH = (
    Path(_DUCKDB_RAW_PATH)
    if Path(_DUCKDB_RAW_PATH).is_absolute()
    else Path.cwd() / _DUCKDB_RAW_PATH
)

_state_lock = threading.Lock()
_duckdb_ready: bool = False
_prewarm_cache_end: Optional[date] = None  # inclusive end date loaded into DuckDB

# File-based lock so multiple gunicorn workers don't all hit Oracle simultaneously.
_LOCK_PATH = _DUCKDB_PATH.with_suffix(".duckdb.loading")


def _try_lock() -> bool:
    """Create lock file exclusively; returns True if this process got the lock."""
    try:
        _DUCKDB_PATH.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(_LOCK_PATH), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(fd)
        return True
    except FileExistsError:
        return False
    except OSError:
        return True  # Can't create lock — proceed anyway to avoid silent skip


def _release_lock() -> None:
    try:
        _LOCK_PATH.unlink(missing_ok=True)
    except Exception:
        pass


def _prewarm_dates() -> tuple[date, date, date, date]:
    """Return (start, end, oee_reject_start, oee_reject_end) for current prewarm window."""
    end = date.today() - timedelta(days=1)          # up to yesterday — stable data
    start = end - timedelta(days=_PREWARM_MONTHS * 31)
    return start, end, start - timedelta(days=30), end + timedelta(days=30)


def is_duckdb_warm() -> bool:
    """True if DuckDB cache is loaded and ready."""
    return _duckdb_ready


def should_use_duckdb(end_date: str, start_date: Optional[str] = None) -> bool:
    """True when the requested range falls entirely inside the DuckDB cache window.

    Window: [today - PREWARM_MONTHS*31d, yesterday].
    Queries ending today use Oracle (data still changing).
    Queries older than the window use Oracle + 24h TTL.
    If start_date is provided, both bounds are checked — a start_date before
    the cache window means DuckDB can only return partial data, so Oracle is used.
    """
    if not _duckdb_ready:
        return False
    try:
        ed = date.fromisoformat(end_date)
        cache_start, cache_end, _, _ = _prewarm_dates()
        if not (cache_start <= ed <= cache_end):
            return False
        if start_date is not None:
            sd = date.fromisoformat(start_date)
            if sd < cache_start:
                return False
        return True
    except (ValueError, TypeError):
        return False


def query_base_from_duckdb(hist_ids: List[str], start_date: str, end_date: str) -> pd.DataFrame:
    """Return base_facts rows for given HISTORYIDs and date range from DuckDB."""
    if not hist_ids or not _duckdb_ready:
        return pd.DataFrame()
    import duckdb
    try:
        escaped = [h.replace("'", "''") for h in hist_ids]
        id_list = "'" + "', '".join(escaped) + "'"
        conn = duckdb.connect(str(_DUCKDB_PATH), read_only=True)
        df = conn.execute(f"""
            SELECT HISTORYID, DATA_DATE, PRD_HOURS, SBY_HOURS, UDT_HOURS,
                   SDT_HOURS, EGT_HOURS, NST_HOURS, TOTAL_HOURS
            FROM base_facts
            WHERE HISTORYID IN ({id_list})
              AND DATA_DATE >= '{start_date}'::DATE
              AND DATA_DATE <= '{end_date}'::DATE
            ORDER BY HISTORYID, DATA_DATE
        """).fetchdf()
        conn.close()
        # Ensure DATA_DATE is datetime64 to match Oracle path
        if not df.empty:
            df["DATA_DATE"] = pd.to_datetime(df["DATA_DATE"])
        return df
    except Exception as exc:
        logger.warning("DuckDB base_facts query failed: %s", exc)
        return pd.DataFrame()


def query_oee_from_duckdb(start_date: str, end_date: str) -> pd.DataFrame:
    """Return oee_facts rows for given date range from DuckDB."""
    if not _duckdb_ready:
        return pd.DataFrame()
    import duckdb
    try:
        conn = duckdb.connect(str(_DUCKDB_PATH), read_only=True)
        df = conn.execute(f"""
            SELECT EQUIPMENTID, SHIFT_DATE, TRACKOUT_QTY, NG_QTY
            FROM oee_facts
            WHERE SHIFT_DATE >= '{start_date}'::DATE
              AND SHIFT_DATE <= '{end_date}'::DATE
            ORDER BY EQUIPMENTID, SHIFT_DATE
        """).fetchdf()
        conn.close()
        if not df.empty:
            df["SHIFT_DATE"] = pd.to_datetime(df["SHIFT_DATE"])
        return df
    except Exception as exc:
        logger.warning("DuckDB oee_facts query failed: %s", exc)
        return pd.DataFrame()


def _try_reuse_existing() -> bool:
    """Return True and mark ready if an up-to-date DuckDB file already exists."""
    global _duckdb_ready, _prewarm_cache_end
    if not _DUCKDB_PATH.exists():
        return False
    import duckdb
    try:
        conn = duckdb.connect(str(_DUCKDB_PATH), read_only=True)
        row = conn.execute("SELECT loaded_at FROM prewarm_meta LIMIT 1").fetchone()
        conn.close()
        if row and row[0] == date.today().isoformat():
            _, end, _, _ = _prewarm_dates()
            with _state_lock:
                _duckdb_ready = True
                _prewarm_cache_end = end
            logger.info(
                "resource_history DuckDB prewarm: reusing today's cache (%.1f MB)",
                _DUCKDB_PATH.stat().st_size / 1e6,
            )
            return True
    except Exception as exc:
        logger.debug("DuckDB existing cache unusable: %s", exc)
    return False


def _load_and_save() -> None:
    """Load base_facts + oee_facts from Oracle and write to DuckDB file (atomic)."""
    global _duckdb_ready, _prewarm_cache_end
    import duckdb
    from mes_dashboard.core.database import read_sql_df_slow as read_sql_df
    from pathlib import Path as P

    start, end, oee_reject_start, oee_reject_end = _prewarm_dates()
    logger.info(
        "resource_history DuckDB prewarm: loading %s → %s from Oracle",
        start.isoformat(), end.isoformat(),
    )

    # --- base_facts: all resources, no HISTORYID filter ---
    t0 = time.time()
    base_sql = """
        SELECT HISTORYID, TRUNC(TXNDATE) AS DATA_DATE,
               SUM(CASE WHEN OLDSTATUSNAME = 'PRD' THEN HOURS ELSE 0 END) AS PRD_HOURS,
               SUM(CASE WHEN OLDSTATUSNAME = 'SBY' THEN HOURS ELSE 0 END) AS SBY_HOURS,
               SUM(CASE WHEN OLDSTATUSNAME = 'UDT' THEN HOURS ELSE 0 END) AS UDT_HOURS,
               SUM(CASE WHEN OLDSTATUSNAME = 'SDT' THEN HOURS ELSE 0 END) AS SDT_HOURS,
               SUM(CASE WHEN OLDSTATUSNAME = 'EGT' THEN HOURS ELSE 0 END) AS EGT_HOURS,
               SUM(CASE WHEN OLDSTATUSNAME = 'NST' THEN HOURS ELSE 0 END) AS NST_HOURS,
               SUM(HOURS) AS TOTAL_HOURS
        FROM DWH.DW_MES_RESOURCESTATUS_SHIFT
        WHERE TXNDATE >= TO_DATE(:start_date, 'YYYY-MM-DD')
          AND TXNDATE < TO_DATE(:end_date, 'YYYY-MM-DD') + 1
        GROUP BY HISTORYID, TRUNC(TXNDATE)
        ORDER BY HISTORYID, TRUNC(TXNDATE)
    """
    base_df = read_sql_df(
        base_sql,
        {"start_date": start.isoformat(), "end_date": end.isoformat()},
        caller="resource_history_duckdb_cache:prewarm_base",
    )
    if base_df is None or base_df.empty:
        logger.warning("resource_history DuckDB prewarm: base_facts empty — aborting")
        return
    t_base = time.time() - t0
    logger.info("DuckDB prewarm: base_facts %d rows in %.1fs", len(base_df), t_base)

    # --- oee_facts: reuse existing SQL file ---
    t0 = time.time()
    oee_sql_path = P(__file__).resolve().parent.parent / "sql" / "resource_history" / "oee_facts.sql"
    oee_sql = oee_sql_path.read_text(encoding="utf-8")
    oee_df = read_sql_df(
        oee_sql,
        {
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "reject_start": oee_reject_start.isoformat(),
            "reject_end": oee_reject_end.isoformat(),
        },
        caller="resource_history_duckdb_cache:prewarm_oee",
    )
    if oee_df is None:
        oee_df = pd.DataFrame()
    t_oee = time.time() - t0
    logger.info("DuckDB prewarm: oee_facts %d rows in %.1fs", len(oee_df), t_oee)

    # --- Write to DuckDB (atomic: write to .tmp, then rename) ---
    _DUCKDB_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = _DUCKDB_PATH.with_suffix(".duckdb.tmp")
    if tmp_path.exists():
        tmp_path.unlink()

    conn = duckdb.connect(str(tmp_path))
    conn.execute("""
        CREATE TABLE base_facts AS
        SELECT
            HISTORYID,
            DATA_DATE::DATE  AS DATA_DATE,
            PRD_HOURS, SBY_HOURS, UDT_HOURS, SDT_HOURS, EGT_HOURS, NST_HOURS, TOTAL_HOURS
        FROM base_df
    """)
    conn.execute("CREATE INDEX idx_base_historyid ON base_facts(HISTORYID)")
    conn.execute("CREATE INDEX idx_base_date      ON base_facts(DATA_DATE)")
    if not oee_df.empty:
        conn.execute("""
            CREATE TABLE oee_facts AS
            SELECT EQUIPMENTID, SHIFT_DATE::DATE AS SHIFT_DATE, TRACKOUT_QTY, NG_QTY
            FROM oee_df
        """)
        conn.execute("CREATE INDEX idx_oee_date ON oee_facts(SHIFT_DATE)")
    else:
        conn.execute("""
            CREATE TABLE oee_facts (
                EQUIPMENTID VARCHAR, SHIFT_DATE DATE,
                TRACKOUT_QTY DOUBLE, NG_QTY DOUBLE
            )
        """)
    conn.execute("CREATE TABLE prewarm_meta (loaded_at VARCHAR, start_date VARCHAR, end_date VARCHAR)")
    conn.execute(
        "INSERT INTO prewarm_meta VALUES (?, ?, ?)",
        [date.today().isoformat(), start.isoformat(), end.isoformat()],
    )
    conn.close()

    # Atomic rename
    if _DUCKDB_PATH.exists():
        _DUCKDB_PATH.unlink()
    tmp_path.rename(_DUCKDB_PATH)

    with _state_lock:
        _duckdb_ready = True
        _prewarm_cache_end = end

    logger.info(
        "resource_history DuckDB prewarm complete: %d base rows, %d oee rows, file %.1f MB",
        len(base_df), len(oee_df), _DUCKDB_PATH.stat().st_size / 1e6,
    )


def start_duckdb_prewarm() -> None:
    """Start DuckDB pre-warm as a daemon background thread (10s startup delay).

    Safe to call from every gunicorn worker; reuses today's existing cache
    file if present (idempotent). Disabled when RESOURCE_HISTORY_PREWARM_MONTHS=0.
    """
    if _PREWARM_MONTHS <= 0:
        logger.info("resource_history DuckDB prewarm disabled (RESOURCE_HISTORY_PREWARM_MONTHS=0)")
        return

    try:
        from mes_dashboard.core.redis_client import REDIS_ENABLED
        if not REDIS_ENABLED:
            logger.info("resource_history DuckDB prewarm skipped (Redis disabled)")
            return
    except Exception:
        return

    def _run() -> None:
        time.sleep(10)
        if _try_reuse_existing():
            return
        if not _try_lock():
            # Another worker is already loading — wait up to 90s for it to finish.
            logger.info("resource_history DuckDB prewarm: peer worker loading, waiting…")
            for _ in range(18):
                time.sleep(5)
                if _try_reuse_existing():
                    return
            logger.warning("resource_history DuckDB prewarm: timed out waiting for peer worker")
            return
        try:
            _load_and_save()
        except Exception as exc:
            logger.warning("resource_history DuckDB prewarm failed: %s", exc)
        finally:
            _release_lock()

    threading.Thread(target=_run, daemon=True, name="resource-history-duckdb-prewarm").start()
    logger.info("resource_history DuckDB prewarm background thread started")
