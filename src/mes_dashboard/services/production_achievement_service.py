# -*- coding: utf-8 -*-
"""Oracle read service for the 生產達成率 (Production Achievement Rate) report.

Implements business-rules.md PA-01..PA-07:
  - shift_code (PA-01/PA-02) and output_date (PA-03/PA-04) are computed as SQL
    CASE expressions inside sql/production_achievement.sql so grouping/SUM run
    server-side. compute_shift_code()/compute_output_date() below are a thin
    Python mirror used ONLY for unit-test boundary assertions (not on the
    query hot path) — see design.md Key Decisions.
  - PA-05 effective-output qualifying predicate is preserved verbatim in the
    SQL file; PA05_PREDICATE_SQL here is the same literal text for static
    branch-coverage assertions in tests (not re-executed in Python).
  - PA-06/PA-07: workcenter_group resolved via the EXISTING
    filter_cache.get_spec_workcenter_mapping() cache (no new SPECNAME map);
    achievement_rate = actual_output_qty / target_qty with null/zero guards.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from mes_dashboard.core.database import read_sql_df
from mes_dashboard.services.filter_cache import get_spec_workcenter_mapping
from mes_dashboard.services.production_achievement_target_service import get_targets_map
from mes_dashboard.sql import SQLLoader

logger = logging.getLogger("mes_dashboard.production_achievement_service")

MAX_QUERY_DAYS = 730  # SYS-04

# PA-05 predicate, preserved verbatim (literal copy of business-rules.md PA-05
# for static test assertions; the actual executable predicate lives in
# sql/production_achievement.sql and MUST stay in sync with this text).
PA05_PREDICATE_SQL = (
    "(CASE WHEN (WB.WORKFLOWNAME LIKE '%雙晶%' OR WB.WORKFLOWNAME LIKE '%三晶%') THEN 1 ELSE 0 END = 0 "
    "AND WC.SPECNAME IN ('Epoxy D/B','Eutectic D/B','Solder Paste D/B','Solder D/B+E-Clip+固化',"
    "'Solder D/B+E-Clip+固化-DW','Solder Paste D/B+E-Clip','Solder Paste D/B+E-Clip-DW')) "
    "OR WC.SPECNAME IN ('金線製程','銀線製程','銅線製程','手工跳線','雷射焊接','Eutectic D/B+Ag Wire',"
    "'Eutectic D/B+Au Wire','Eutectic D/B+Cu Wire','E-Clip+固化','包膠-WB') "
    "OR (WC.SPECNAME IN ('2DB2WB','1DB2WB') AND weh.processtypename IN ('DWB_WB2')) "
    "OR (WC.SPECNAME IN ('2DB1WB','1DB1WB') AND weh.processtypename IN ('DWB_WB')) "
    "OR (WB.WORKFLOWNAME LIKE '%雙晶%' AND WC.SPECNAME IN ('Epoxy D/B-2','Eutectic D/B-2','Eutectic D/B-雙晶')) "
    "OR (WB.WORKFLOWNAME LIKE '%三晶%' AND WC.SPECNAME IN ('Epoxy D/B-3','Eutectic D/B-3')) "
    "OR (WC.SPECNAME IN ('2DB') AND weh.processtypename IN ('2DB_DB2')) "
    "OR (WC.SPECNAME IN ('1DB') AND weh.processtypename IN ('2DB_DB')) "
    "OR (WC.SPECNAME IN ('DBCB') AND weh.processtypename IN ('DBCB_CB')) "
    "OR (WC.SPECNAME IN ('2DBCBRO','1DBCBRO','CBRO') AND weh.processtypename IN ('CBA_RO'))"
)

_TWO_SHIFT_HIST_START = "20191231"  # exclusive lower edge of the historical window
_TWO_SHIFT_HIST_END = "20200330"    # exclusive upper edge of the historical window


class ProductionAchievementValidationError(ValueError):
    """Raised for invalid date-range input at the service boundary."""


# ============================================================
# Python mirror of shift_code / output_date (PA-01..PA-04)
# — unit-test boundary assertions only, NOT the query hot path.
# ============================================================


def _is_three_shift_regime(ts: datetime) -> bool:
    """True when ts falls strictly within 2020/01/01-2020/03/29 (PA-02 window)."""
    ymd = ts.strftime("%Y%m%d")
    return _TWO_SHIFT_HIST_START < ymd < _TWO_SHIFT_HIST_END


def compute_shift_code(ts: datetime) -> str:
    """Python mirror of PJ_GET_CLASSCODE_F (PA-01/PA-02)."""
    tod = ts.time()
    if _is_three_shift_regime(ts):
        if datetime.strptime("08:00:00", "%H:%M:%S").time() <= tod <= datetime.strptime("15:59:59", "%H:%M:%S").time():
            return "A"
        if datetime.strptime("16:00:00", "%H:%M:%S").time() <= tod <= datetime.strptime("23:59:59", "%H:%M:%S").time():
            return "B"
        return "C"
    # PA-01: two-shift current regime
    if datetime.strptime("07:30:00", "%H:%M:%S").time() <= tod <= datetime.strptime("19:29:59", "%H:%M:%S").time():
        return "D"
    return "N"


def compute_output_date(ts: datetime) -> date:
    """Python mirror of PJ_GET_OUTPUTDATE_F (PA-03/PA-04)."""
    tod = ts.time()
    if _is_three_shift_regime(ts):
        # PA-04 (UNVERIFIED ASSUMPTION): C-shift tail attributes to previous day.
        logger.info(
            "production_achievement: three-shift regime output_date rule is an "
            "UNVERIFIED ASSUMPTION (business-rules.md PA-04) for ts=%s", ts,
        )
        if tod < datetime.strptime("08:00:00", "%H:%M:%S").time():
            return (ts - timedelta(days=1)).date()
        return ts.date()
    # PA-03: two-shift N-tail attributes to previous day.
    if tod < datetime.strptime("07:30:00", "%H:%M:%S").time():
        return (ts - timedelta(days=1)).date()
    return ts.date()


# ============================================================
# Achievement-rate grouping + math (PA-06/PA-07)
# ============================================================


def build_achievement_rows(
    df: pd.DataFrame, targets: Dict[Tuple[str, str], Optional[int]]
) -> List[Dict[str, Any]]:
    """Re-aggregate Oracle rows grouped by (output_date, shift_code, SPECNAME)
    into (output_date, shift_code, workcenter_group) using
    filter_cache.get_spec_workcenter_mapping() (PA-06), then compute
    achievement_rate per PA-07.

    Args:
        df: DataFrame with columns OUTPUT_DATE, SHIFT_CODE, SPECNAME,
            ACTUAL_OUTPUT_QTY (as returned by read_sql_df on
            sql/production_achievement.sql).
        targets: {(shift_code, workcenter_group): target_qty or None}.

    Returns:
        List of row dicts per data-shape-contract.md §3.25, sorted by
        output_date ASC, shift_code ASC, workcenter_group ASC.
    """
    mapping = get_spec_workcenter_mapping()

    grouped: Dict[Tuple[str, str, str], int] = {}
    for _, record in df.iterrows():
        specname = record.get("SPECNAME")
        if specname is None:
            continue
        info = mapping.get(str(specname).strip().upper())
        if not info:
            # Unmapped SPECNAME -- excluded from grouped output (PA-06,
            # data-boundary condition, not an error).
            continue
        workcenter_group = info.get("group")
        if not workcenter_group:
            continue

        output_date = record.get("OUTPUT_DATE")
        shift_code = record.get("SHIFT_CODE")
        qty = record.get("ACTUAL_OUTPUT_QTY") or 0

        key = (str(output_date), str(shift_code), str(workcenter_group))
        grouped[key] = grouped.get(key, 0) + int(qty)

    rows: List[Dict[str, Any]] = []
    for (output_date, shift_code, workcenter_group), actual_output_qty in grouped.items():
        target_qty = targets.get((shift_code, workcenter_group))
        achievement_rate = _compute_achievement_rate(actual_output_qty, target_qty)
        rows.append(
            {
                "output_date": output_date,
                "shift_code": shift_code,
                "workcenter_group": workcenter_group,
                "actual_output_qty": actual_output_qty,
                "target_qty": target_qty,
                "achievement_rate": achievement_rate,
            }
        )

    rows.sort(key=lambda r: (r["output_date"], r["shift_code"], r["workcenter_group"]))
    return rows


def _compute_achievement_rate(
    actual_output_qty: int, target_qty: Optional[int]
) -> Optional[float]:
    """PA-07: null on missing/zero target; 0.0 on zero-output+nonzero-target."""
    if target_qty is None:
        return None
    if target_qty == 0:
        return None
    return actual_output_qty / target_qty


# ============================================================
# Public API — report / filter-options
# ============================================================


def _validate_date_range(start_date: str, end_date: str) -> None:
    if not start_date or not end_date:
        raise ProductionAchievementValidationError("必須提供 start_date 和 end_date 參數")
    sd = datetime.strptime(start_date, "%Y-%m-%d")
    ed = datetime.strptime(end_date, "%Y-%m-%d")
    if ed < sd:
        raise ProductionAchievementValidationError("end_date 不可早於 start_date")
    if (ed - sd).days > MAX_QUERY_DAYS:
        raise ProductionAchievementValidationError(f"查詢範圍不可超過 {MAX_QUERY_DAYS} 天")


def get_achievement_report(
    *,
    start_date: str,
    end_date: str,
    shift_code: Optional[str] = None,
    workcenter_group: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Query the achievement-rate report for the given date range + optional
    filters. Reuses filter_cache for workcenter_group resolution; joins the
    target-value table (degrades to null target/achievement_rate, never 500,
    when MySQL OPS is off/unreachable — production_achievement_target_service
    already degrades get_targets_map() to {} in that case).
    """
    _validate_date_range(start_date, end_date)

    chunk_end_excl = (datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")

    sql = SQLLoader.load_with_params(
        "production_achievement", CONTAINERNAME_FILTER=""
    )
    params = {"start_date": start_date, "chunk_end_excl": chunk_end_excl}
    df = read_sql_df(sql, params, caller="production_achievement_service")

    targets = get_targets_map()
    rows = build_achievement_rows(df, targets)

    if shift_code:
        rows = [r for r in rows if r["shift_code"] == shift_code]
    if workcenter_group:
        rows = [r for r in rows if r["workcenter_group"] == workcenter_group]

    return rows


_SHIFT_CODE_ENUM = ["N", "D", "A", "B", "C"]


def get_filter_options() -> Dict[str, Any]:
    """Return available shift_code enum + workcenter_group values for the
    FilterBar. Sourced from filter_cache + the shift-code enum, not a new
    cache namespace (api-contract.md)."""
    mapping = get_spec_workcenter_mapping()
    groups = sorted({info.get("group") for info in mapping.values() if info.get("group")})
    return {
        "shift_codes": _SHIFT_CODE_ENUM,
        "workcenter_groups": groups,
    }
