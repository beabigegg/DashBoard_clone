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

import hashlib
import json
import logging
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from mes_dashboard.services.filter_cache import get_spec_workcenter_mapping
from mes_dashboard.services.production_achievement_workcenter_merge_service import (
    get_workcenter_merge_map,
)

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
    "OR (WC.SPECNAME IN ('2DBCBRO','1DBCBRO','CBRO') AND weh.processtypename IN ('CBA_RO')) "
    "OR (WC.SPECID IN ('48812c8000025fd2','48812c8000025fd4','48812c8000000025','48812c8000000026',"
    "'48812c8000000027','48812c8000039e15') AND weh.Trackoutqty<>0)"
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


# ============================================================
# Canonical async spool key (production-achievement-async-spool, ADR-0016)
# ============================================================
#
# NOTE: get_achievement_report() (the synchronous Oracle-backed request-path
# reader) has been REMOVED by production-achievement-async-spool. The route
# no longer performs the Oracle read + PA-06/PA-07 rollup on the request
# path -- see workers/production_achievement_worker.py (ProductionAchievementJob)
# for the async equivalent. build_achievement_rows()/_compute_achievement_rate()
# above are retained as the test-only golden reference for the dual-tier
# parity gate (business-rules.md PA-06/PA-07) -- the frontend now performs
# this rollup client-side in DuckDB-WASM from the SPECNAME-grain spool.

_PA_SPOOL_SCHEMA_VERSION = 2
"""Schema version for the SPECNAME+PACKAGE_LF-grain async spool
(data-shape-contract.md §3.28.1). Participates in the canonical spool key so
a schema-breaking bump orphans stale parquets by key (cache-spool-patterns.md).
Bumped 1->2 by production-achievement-overhaul (+PACKAGE_LF nullable column,
business-rules.md PA-09)."""

PRODUCTION_ACHIEVEMENT_SPOOL_NAMESPACE = "production_achievement"
"""Shared spool namespace constant -- single source of truth for the
worker's ``ProductionAchievementJob.namespace``, the route's spool-hit/miss
lookup, and the warm-cache module's ``get_spool_file_path()`` calls, so the
three call sites can never drift apart (production-achievement-overhaul,
IP-1/IP-5)."""


def make_canonical_pa_spool_id(start_date: str, end_date: str) -> str:
    """Return the canonical spool key for the production-achievement async spool.

    Date-range only (data-shape-contract.md §3.28 canonical-key rule):
    ``shift_code``/``workcenter_group`` request params do NOT participate in
    the spool key and do NOT filter the spooled dataset server-side -- the
    full PA-05-qualifying dataset for the date range is always spooled, and
    any shift_code/workcenter_group narrowing happens client-side after
    download. Shared by the route (spool-hit check) and the worker
    (pre_query spool-path resolution) so both resolve the identical key.
    """
    canonical = json.dumps(
        {
            "schema_version": _PA_SPOOL_SCHEMA_VERSION,
            "start_date": start_date,
            "end_date": end_date,
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


_SHIFT_CODE_ENUM = ["N", "D", "A", "B", "C"]


def get_filter_options() -> Dict[str, Any]:
    """Return available shift_code enum + workcenter_group values for the
    FilterBar (api-contract.md).

    ``workcenter_groups`` redefined in place by production-achievement-overhaul
    (Phase 1/3) to the MERGED (D2) list: the deduplicated set of
    ``merged_workcenter_group`` values from
    ``production_achievement_workcenter_merge_service.get_workcenter_merge_map()``
    -- NOT the raw ``WORK_CENTER_GROUP`` set previously sourced directly from
    ``filter_cache.get_spec_workcenter_mapping()``. A raw workcenter_group
    absent from ``production_achievement_workcenter_merge_map`` is excluded
    here too (D2 exclude-by-absence, business-rules.md PA-10) -- the merge
    service's own map already reflects that default, this function just
    de-duplicates its values.
    """
    merged_groups = sorted(set(get_workcenter_merge_map().values()))
    return {
        "shift_codes": _SHIFT_CODE_ENUM,
        "workcenter_groups": merged_groups,
    }


def get_known_workcenter_groups() -> List[str]:
    """Return the FULL raw WORK_CENTER_GROUP universe (including currently
    D2-excluded groups), sourced directly from
    filter_cache.get_spec_workcenter_mapping() -- NOT the merged/filtered
    list from get_filter_options().

    Backs ``GET /api/production-achievement/known-workcenter-groups``
    (interaction-design.md OD-8), added so ``WorkcenterMergeMappingPanel``
    can enumerate every raw group an admin might want to include/exclude/
    merge, mirroring ``filter_cache.get_known_package_lf_values()``'s role
    for D1.
    """
    mapping = get_spec_workcenter_mapping()
    return sorted({info.get("group") for info in mapping.values() if info.get("group")})
