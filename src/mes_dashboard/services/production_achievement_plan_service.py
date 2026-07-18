# -*- coding: utf-8 -*-
"""Oracle-sourced production plan/target cache
(production-achievement-oracle-plan-source, business-rules.md PA-11).

Replaces the Excel-imported ``production_achievement_daily_plans`` MySQL
table. Reads ``DWH.MES_WIP_OUTPUTPLAN``/``MES_WIP_OUTPUTPLAN_DETAIL`` via
``sql/production_achievement_plan.sql`` -- see that file's header for the
full derivation (why the query is per-day rather than pre-aggregated, the
INNER JOIN choice, the DAYSN<=last-day-of-month guard).

Cached per calendar month (``TMONTH`` = ``YYYYMM``), NOT globally like
``filter_cache.py`` -- the source data is itself date-indexed, so a single
cache entry would either be unbounded (cache the whole table) or would need
re-keying on every distinct date range a report requests (cache nothing
reusable). Per-month keying lets every report request that touches the same
calendar month(s) reuse the same Oracle round-trip, mirrors the L1(memory)
+ L2(Redis) + Oracle two-tier pattern every other small-reference-table
cache in this codebase uses (dict + threading.Lock + TTL, filter_cache.py
style), just parameterized by month.

Fail-open by construction: any Oracle error for a given month degrades that
month's rows to [] (never raises) -- callers/downstream client code already
treat a missing plan_map entry as "no target for that package/date" (PA-12
degrade semantics), same as the daily_plans table it replaces.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from datetime import date, datetime
from typing import Any, Dict, List

from mes_dashboard.config.constants import CACHE_TTL_PRODUCTION_ACHIEVEMENT_PLAN
from mes_dashboard.core.cache_plane import snapshot_redis_ttl
from mes_dashboard.core.database import read_sql_df
from mes_dashboard.core.redis_client import get_key, get_redis_client, REDIS_ENABLED
from mes_dashboard.sql import SQLLoader

logger = logging.getLogger("mes_dashboard.production_achievement_plan_service")

_CACHE_TTL_SECONDS = CACHE_TTL_PRODUCTION_ACHIEVEMENT_PLAN
_REDIS_TTL_SECONDS = snapshot_redis_ttl(_CACHE_TTL_SECONDS)

# {tmonth: {"rows": [...], "loaded_at": epoch_seconds}}
_CACHE: Dict[str, Dict[str, Any]] = {}
_CACHE_LOCK = threading.Lock()


def _redis_key(tmonth: str) -> str:
    return get_key(f"production_achievement_plan_cache:{tmonth}")


def _months_between(start_date: str, end_date: str) -> List[str]:
    """Return every ``YYYYMM`` month covered by ``[start_date, end_date]``
    (both ``YYYY-MM-DD``, inclusive), in chronological order."""
    start = datetime.strptime(start_date, "%Y-%m-%d").date()
    end = datetime.strptime(end_date, "%Y-%m-%d").date()
    months = []
    cursor = date(start.year, start.month, 1)
    while cursor <= end:
        months.append(cursor.strftime("%Y%m"))
        if cursor.month == 12:
            cursor = date(cursor.year + 1, 1, 1)
        else:
            cursor = date(cursor.year, cursor.month + 1, 1)
    return months


def _read_from_redis(tmonth: str) -> "List[Dict[str, Any]] | None":
    if not REDIS_ENABLED:
        return None
    try:
        client = get_redis_client()
        if client is None:
            return None
        raw = client.get(_redis_key(tmonth))
        if raw is None:
            return None
        return json.loads(raw)
    except Exception as exc:
        logger.warning(
            "production_achievement_plan_service: Redis read failed for %s: %s",
            tmonth, exc,
        )
        return None


def _write_to_redis(tmonth: str, rows: List[Dict[str, Any]]) -> None:
    if not REDIS_ENABLED:
        return
    try:
        client = get_redis_client()
        if client is None:
            return
        client.setex(_redis_key(tmonth), _REDIS_TTL_SECONDS, json.dumps(rows))
    except Exception as exc:
        logger.warning(
            "production_achievement_plan_service: Redis write failed for %s: %s",
            tmonth, exc,
        )


def _query_oracle(tmonth: str) -> List[Dict[str, Any]]:
    sql = SQLLoader.load("production_achievement_plan")
    df = read_sql_df(
        sql, {"tmonth": tmonth}, caller="production_achievement_plan_service"
    )
    return [
        {
            "output_date": row["OUTPUT_DATE"].strftime("%Y-%m-%d"),
            "plan_package_group": row["PLAN_PACKAGE_GROUP"],
            "planqty_input": int(row["PLANQTY_INPUT"]),
            "planqty_output": int(row["PLANQTY_OUTPUT"]),
        }
        for _, row in df.iterrows()
    ]


def _get_month_rows(tmonth: str, force_refresh: bool = False) -> List[Dict[str, Any]]:
    with _CACHE_LOCK:
        entry = _CACHE.get(tmonth)
        if not force_refresh and entry is not None:
            if time.time() - entry["loaded_at"] < _CACHE_TTL_SECONDS:
                return entry["rows"]

    if not force_refresh:
        redis_rows = _read_from_redis(tmonth)
        if redis_rows is not None:
            with _CACHE_LOCK:
                _CACHE[tmonth] = {"rows": redis_rows, "loaded_at": time.time()}
            return redis_rows

    try:
        rows = _query_oracle(tmonth)
    except Exception as exc:
        logger.warning(
            "production_achievement_plan_service: Oracle read failed for %s, "
            "degrading to []: %s",
            tmonth, exc,
        )
        with _CACHE_LOCK:
            existing = _CACHE.get(tmonth)
            if existing is not None:
                return existing["rows"]
        return []

    with _CACHE_LOCK:
        _CACHE[tmonth] = {"rows": rows, "loaded_at": time.time()}
    _write_to_redis(tmonth, rows)
    return rows


def get_oracle_plan_rows(
    start_date: str, end_date: str, force_refresh: bool = False
) -> List[Dict[str, Any]]:
    """Return raw per-day plan rows for every calendar month touched by
    ``[start_date, end_date]`` (both ``YYYY-MM-DD``, inclusive).

    Returns the FULL month(s), not rows narrowed to the exact date range --
    the cache is keyed per-month so it can be reused across every report
    request touching that month regardless of exact day boundaries; the
    client (DuckDB-WASM) is the one that narrows to the requested range, same
    coarse-superset-then-client-narrow shape as this feature's spool data.

    Sourced for the inline ``plan_map`` array injected in the ``GET /report``
    200 spool-hit envelope (data-shape-contract.md §3.34), replacing the old
    ``daily_plan_map``. Each row: ``{output_date, plan_package_group,
    planqty_input, planqty_output}``. Degrades to [] per-month on Oracle
    failure -- never raises, never 500s the report endpoint.
    """
    rows: List[Dict[str, Any]] = []
    for tmonth in _months_between(start_date, end_date):
        rows.extend(_get_month_rows(tmonth, force_refresh=force_refresh))
    return rows
