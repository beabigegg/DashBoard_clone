# -*- coding: utf-8 -*-
"""Persistent DuckDB cache for downtime-analysis raw data.

Loads the last DOWNTIME_ANALYSIS_PREWARM_MONTHS months of base_events and
job_data from Oracle at startup.  User queries with end_date in
[today-MONTHS*31d, yesterday] are served from DuckDB instead of Oracle.

Tables stored in DuckDB file:
  base_events — HISTORYID, OLDSTATUSNAME, OLDREASONNAME,
                OLDLASTSTATUSCHANGEDATE, LASTSTATUSCHANGEDATE, HOURS, JOBID
  job_data    — JOBID, RESOURCEID, CREATEDATE, COMPLETEDATE, SYMPTOMCODENAME,
                CAUSECODENAME, REPAIRCODENAME, COMPLETE_FULLNAME,
                FIRSTCLOCKONDATE, LASTCLOCKOFFDATE, JOBORDERNAME, JOBMODELNAME
  prewarm_meta — loaded_at, start_date, end_date
"""

from __future__ import annotations

import fcntl
import logging
import os
import threading
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger("mes_dashboard.downtime_analysis_duckdb_cache")

_PREWARM_MONTHS: int = int(os.getenv("DOWNTIME_ANALYSIS_PREWARM_MONTHS", "3"))

# DuckDB file path — resolved to absolute; same pattern as RESOURCE_HISTORY_DUCKDB_PATH.
_DUCKDB_RAW_PATH = os.getenv("DOWNTIME_ANALYSIS_DUCKDB_PATH", "tmp/downtime_analysis.duckdb")
_DUCKDB_PATH = (
    Path(_DUCKDB_RAW_PATH)
    if Path(_DUCKDB_RAW_PATH).is_absolute()
    else Path.cwd() / _DUCKDB_RAW_PATH
)

_state_lock = threading.Lock()
_duckdb_ready: bool = False

# File-based exclusive lock so multiple gunicorn workers don't all hit Oracle simultaneously.
_LOCK_PATH = _DUCKDB_PATH.with_suffix(".duckdb.loading")
_LOCK_FD: list = [None]


def _try_lock() -> bool:
    try:
        _DUCKDB_PATH.parent.mkdir(parents=True, exist_ok=True)
        fd = open(str(_LOCK_PATH), "w")
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _LOCK_FD[0] = fd
        return True
    except BlockingIOError:
        return False
    except OSError:
        return True


def _release_lock() -> None:
    fd = _LOCK_FD[0]
    if fd is not None:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
            fd.close()
        except Exception:
            pass
        _LOCK_FD[0] = None
    try:
        _LOCK_PATH.unlink(missing_ok=True)
    except Exception:
        pass


def _prewarm_dates() -> tuple[date, date]:
    """Return (start, end) for the current prewarm window. end = yesterday."""
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=_PREWARM_MONTHS * 31)
    return start, end


def is_duckdb_warm() -> bool:
    """True if DuckDB cache is loaded and ready."""
    return _duckdb_ready


def should_use_duckdb(end_date: str, start_date: Optional[str] = None) -> bool:
    """True when the requested range falls entirely inside the DuckDB cache window.

    Window: [today - PREWARM_MONTHS*31d, yesterday].
    Queries ending today or in the future use Oracle (data still changing).
    Queries older than the window fall back to Oracle.
    """
    if not _duckdb_ready:
        # Lazy worker init: threads don't survive gunicorn preload_app fork, so
        # _duckdb_ready is always False in forked workers.  Once the master's
        # prewarm thread writes the file, the first request to each worker
        # discovers it here and marks this worker ready.
        if _DUCKDB_PATH.exists():
            _try_reuse_existing()
        if not _duckdb_ready:
            return False
    try:
        ed = date.fromisoformat(end_date)
        cache_start, cache_end = _prewarm_dates()
        if not (cache_start <= ed <= cache_end):
            return False
        if start_date is not None:
            sd = date.fromisoformat(start_date)
            if sd < cache_start:
                return False
        return True
    except (ValueError, TypeError):
        return False


def query_base_from_duckdb(start_date: str, end_date: str) -> pd.DataFrame:
    """Return base_events rows for the given date range from DuckDB.

    Mirrors the base_events.sql WHERE clause:
      OLDLASTSTATUSCHANGEDATE >= start_date  AND  < end_date + 1 day
    Returns same columns as base_events.sql Oracle output.
    """
    if not _duckdb_ready:
        return pd.DataFrame()
    import duckdb
    try:
        conn = duckdb.connect(str(_DUCKDB_PATH), read_only=True)
        df = conn.execute(f"""
            SELECT HISTORYID, OLDSTATUSNAME, OLDREASONNAME,
                   OLDLASTSTATUSCHANGEDATE, LASTSTATUSCHANGEDATE,
                   HOURS, JOBID
            FROM base_events
            WHERE OLDLASTSTATUSCHANGEDATE >= '{start_date}'::DATE
              AND OLDLASTSTATUSCHANGEDATE <  '{end_date}'::DATE + INTERVAL '1 day'
            ORDER BY OLDLASTSTATUSCHANGEDATE DESC, HISTORYID ASC
        """).fetchdf()
        conn.close()
        if not df.empty:
            for col in ("OLDLASTSTATUSCHANGEDATE", "LASTSTATUSCHANGEDATE"):
                if col in df.columns:
                    df[col] = pd.to_datetime(df[col])
        return df
    except Exception as exc:
        logger.warning("DuckDB base_events query failed: %s", exc)
        return pd.DataFrame()


def query_job_from_duckdb(start_date: str, end_date: str) -> pd.DataFrame:
    """Return job_data rows for the given date range from DuckDB.

    Mirrors the job_bridge.sql WHERE clause (without RESOURCE_FILTER):
      (COMPLETEDATE >= start_date - 7 OR COMPLETEDATE IS NULL)
      AND CREATEDATE <= end_date + 7
    Returns same columns as job_bridge.sql Oracle output.
    """
    if not _duckdb_ready:
        return pd.DataFrame()
    import duckdb
    try:
        conn = duckdb.connect(str(_DUCKDB_PATH), read_only=True)
        df = conn.execute(f"""
            SELECT JOBID, RESOURCEID, CREATEDATE, COMPLETEDATE,
                   SYMPTOMCODENAME, CAUSECODENAME, REPAIRCODENAME, COMPLETE_FULLNAME,
                   FIRSTCLOCKONDATE, LASTCLOCKOFFDATE, JOBORDERNAME, JOBMODELNAME
            FROM job_data
            WHERE (COMPLETEDATE IS NULL
                   OR COMPLETEDATE >= '{start_date}'::DATE - INTERVAL '7 days')
              AND CREATEDATE <= '{end_date}'::DATE + INTERVAL '7 days'
        """).fetchdf()
        conn.close()
        if not df.empty:
            for col in ("CREATEDATE", "COMPLETEDATE", "FIRSTCLOCKONDATE", "LASTCLOCKOFFDATE"):
                if col in df.columns:
                    df[col] = pd.to_datetime(df[col])
        return df
    except Exception as exc:
        logger.warning("DuckDB job_data query failed: %s", exc)
        return pd.DataFrame()


def _try_reuse_existing() -> bool:
    """Return True and mark ready if an up-to-date DuckDB file already exists."""
    global _duckdb_ready
    if not _DUCKDB_PATH.exists():
        return False
    import duckdb
    try:
        conn = duckdb.connect(str(_DUCKDB_PATH), read_only=True)
        row = conn.execute("SELECT loaded_at FROM prewarm_meta LIMIT 1").fetchone()
        conn.close()
        if row and row[0] == date.today().isoformat():
            with _state_lock:
                _duckdb_ready = True
            logger.info(
                "downtime_analysis DuckDB prewarm: reusing today's cache (%.1f MB)",
                _DUCKDB_PATH.stat().st_size / 1e6,
            )
            return True
    except Exception as exc:
        logger.debug("downtime_analysis DuckDB existing cache unusable: %s", exc)
    return False


def _load_and_save() -> None:
    """Load base_events + job_data from Oracle and write to DuckDB (atomic)."""
    global _duckdb_ready
    import duckdb
    from mes_dashboard.core.database import read_sql_df_slow as read_sql_df
    from pathlib import Path as P

    start, end = _prewarm_dates()
    logger.info(
        "downtime_analysis DuckDB prewarm: loading %s → %s from Oracle",
        start.isoformat(), end.isoformat(),
    )

    # --- base_events: reuse existing SQL file ---
    t0 = time.time()
    base_sql_path = P(__file__).resolve().parent.parent / "sql" / "downtime_analysis" / "base_events.sql"
    base_sql = base_sql_path.read_text(encoding="utf-8")
    base_df = read_sql_df(
        base_sql,
        {"start_date": start.isoformat(), "end_date": end.isoformat()},
        caller="downtime_analysis_duckdb_cache:prewarm_base",
    )
    if base_df is None or base_df.empty:
        logger.warning("downtime_analysis DuckDB prewarm: base_events empty — aborting")
        return
    t_base = time.time() - t0
    logger.info("DuckDB prewarm: base_events %d rows in %.1fs", len(base_df), t_base)

    # --- job_data: job_bridge.sql without RESOURCE_FILTER (load all jobs for the period) ---
    t0 = time.time()
    job_sql_path = P(__file__).resolve().parent.parent / "sql" / "downtime_analysis" / "job_bridge.sql"
    job_sql = job_sql_path.read_text(encoding="utf-8").replace("{{ RESOURCE_FILTER }}", "1=1")
    job_df = read_sql_df(
        job_sql,
        {"start_date": start.isoformat(), "end_date": end.isoformat()},
        caller="downtime_analysis_duckdb_cache:prewarm_jobs",
    )
    if job_df is None:
        job_df = pd.DataFrame()
    t_job = time.time() - t0
    logger.info("DuckDB prewarm: job_data %d rows in %.1fs", len(job_df), t_job)

    # --- Write to DuckDB (atomic: write to .tmp, then rename) ---
    _DUCKDB_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = _DUCKDB_PATH.with_suffix(".duckdb.tmp")
    if tmp_path.exists():
        tmp_path.unlink()

    conn = duckdb.connect(str(tmp_path))
    conn.execute("""
        CREATE TABLE base_events AS
        SELECT
            CAST(HISTORYID AS VARCHAR)           AS HISTORYID,
            CAST(OLDSTATUSNAME AS VARCHAR)        AS OLDSTATUSNAME,
            CAST(OLDREASONNAME AS VARCHAR)        AS OLDREASONNAME,
            OLDLASTSTATUSCHANGEDATE::TIMESTAMP    AS OLDLASTSTATUSCHANGEDATE,
            LASTSTATUSCHANGEDATE::TIMESTAMP       AS LASTSTATUSCHANGEDATE,
            CAST(HOURS AS DOUBLE)                 AS HOURS,
            CAST(JOBID AS VARCHAR)                AS JOBID
        FROM base_df
    """)
    conn.execute("CREATE INDEX idx_base_date ON base_events(OLDLASTSTATUSCHANGEDATE)")
    conn.execute("CREATE INDEX idx_base_hist ON base_events(HISTORYID)")

    if not job_df.empty:
        conn.execute("""
            CREATE TABLE job_data AS
            SELECT
                CAST(JOBID AS VARCHAR)              AS JOBID,
                CAST(RESOURCEID AS VARCHAR)         AS RESOURCEID,
                CREATEDATE::TIMESTAMP               AS CREATEDATE,
                COMPLETEDATE::TIMESTAMP             AS COMPLETEDATE,
                CAST(SYMPTOMCODENAME AS VARCHAR)    AS SYMPTOMCODENAME,
                CAST(CAUSECODENAME AS VARCHAR)      AS CAUSECODENAME,
                CAST(REPAIRCODENAME AS VARCHAR)     AS REPAIRCODENAME,
                CAST(COMPLETE_FULLNAME AS VARCHAR)  AS COMPLETE_FULLNAME,
                FIRSTCLOCKONDATE::TIMESTAMP         AS FIRSTCLOCKONDATE,
                LASTCLOCKOFFDATE::TIMESTAMP         AS LASTCLOCKOFFDATE,
                CAST(JOBORDERNAME AS VARCHAR)       AS JOBORDERNAME,
                CAST(JOBMODELNAME AS VARCHAR)       AS JOBMODELNAME
            FROM job_df
        """)
        conn.execute("CREATE INDEX idx_job_resourceid   ON job_data(RESOURCEID)")
        conn.execute("CREATE INDEX idx_job_completedate ON job_data(COMPLETEDATE)")
    else:
        conn.execute("""
            CREATE TABLE job_data (
                JOBID VARCHAR, RESOURCEID VARCHAR,
                CREATEDATE TIMESTAMP, COMPLETEDATE TIMESTAMP,
                SYMPTOMCODENAME VARCHAR, CAUSECODENAME VARCHAR,
                REPAIRCODENAME VARCHAR, COMPLETE_FULLNAME VARCHAR,
                FIRSTCLOCKONDATE TIMESTAMP, LASTCLOCKOFFDATE TIMESTAMP,
                JOBORDERNAME VARCHAR, JOBMODELNAME VARCHAR
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

    logger.info(
        "downtime_analysis DuckDB prewarm complete: %d base rows, %d job rows, file %.1f MB",
        len(base_df), len(job_df), _DUCKDB_PATH.stat().st_size / 1e6,
    )


def start_duckdb_prewarm() -> None:
    """Start downtime-analysis DuckDB pre-warm as a daemon background thread (10s startup delay).

    Safe to call from every gunicorn worker; reuses today's existing cache file if present.
    Disabled when DOWNTIME_ANALYSIS_PREWARM_MONTHS=0.
    """
    if _PREWARM_MONTHS <= 0:
        logger.info("downtime_analysis DuckDB prewarm disabled (DOWNTIME_ANALYSIS_PREWARM_MONTHS=0)")
        return

    try:
        from mes_dashboard.core.redis_client import REDIS_ENABLED
        if not REDIS_ENABLED:
            logger.info("downtime_analysis DuckDB prewarm skipped (Redis disabled)")
            return
    except Exception:
        return

    def _run() -> None:
        time.sleep(10)
        if _try_reuse_existing():
            return
        if not _try_lock():
            logger.info("downtime_analysis DuckDB prewarm: peer worker loading, waiting…")
            for _ in range(18):
                time.sleep(5)
                if _try_reuse_existing():
                    return
            logger.warning("downtime_analysis DuckDB prewarm: timed out waiting for peer worker")
            return
        try:
            _load_and_save()
        except Exception as exc:
            logger.warning("downtime_analysis DuckDB prewarm failed: %s", exc)
        finally:
            _release_lock()

    threading.Thread(target=_run, daemon=True, name="downtime-analysis-duckdb-prewarm").start()
    logger.info("downtime_analysis DuckDB prewarm background thread started")
