# -*- coding: utf-8 -*-
"""DB Scheduling queue service.

Implements GET /api/db-scheduling/queue logic (rewritten 2026-07 — see the
business-rule change that replaced the D/B-START/WORKFLOWNAME matching model
with a 晶片切割-END/BOP+PACKAGE+zone model):

1. Load data from the 5-min WIP cache (ADR 0013) via get_cached_wip_data().
   On cache miss → Oracle direct fallback via read_sql_df.
2. Extract 晶片切割-END start-lots (DB-01, replaces the retired D/B-START
   origin) and the currently-ACTIVE running-equipment pool (DB-02).
3. Single-tier match (replaces the old WORKFLOWNAME primary / BOP-fallback
   two-tier model): a candidate equipment qualifies iff ALL of —
     (a) its current/most-recent lot's SPECNAME is in
         BOP_FALLBACK_GROUPS[start lot's BOP first-char],
     (b) its current/most-recent lot's PACKAGE equals the start lot's
         PACKAGE_LEF, and
     (c) its LOCATIONNAME is in the BOP-first-char-derived allowed zone set
         (see _allowed_zones_for / BOP_U_REGION_ZONE_MAP / BOP_FIXED_ZONE_MAP).
   matchSource='bop-package-zone' for every emitted row (the old 'workflow'
   and 'bop-fallback' values are retired).
4. Candidates include BOTH currently-ACTIVE 焊接_DB equipment (attributes
   read live from the WIP cache, equipmentSource='live') AND currently-IDLE
   焊接_DB equipment, whose most-recent SPECNAME/PACKAGE are resolved via a
   synchronous DWH.DW_MES_LOTWIPHISTORY fallback query (equipmentSource=
   'history'; see sql/db_scheduling/idle_equipment_history.sql and
   _load_idle_equipment_history()).
5. Lots with no match → zero rows (matchSource='none' never emitted).
6. Sort: PACKAGE_LEF → PJ_TYPE → WAFERLOT → UTS ASC, NULLS LAST (DB-04, unchanged).
7. Return list of dicts. API response shape change vs the pre-2026-07
   contract (§3.22): added 'equipmentSource': 'live' | 'history'; matchSource
   is now a single-value enum {'bop-package-zone'} instead of
   {'workflow', 'bop-fallback', 'none'} (all other fields unchanged, 16 total).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import pandas as pd

from mes_dashboard.config.workcenter_groups import get_workcenter_group
from mes_dashboard.core.cache import get_cached_wip_data
from mes_dashboard.core.database import read_sql_df
from mes_dashboard.sql import QueryBuilder, SQLLoader

logger = logging.getLogger('mes_dashboard.db_scheduling_service')

# ---------------------------------------------------------------------------
# DB-00: Authoritative 12-SPEC list (pin with membership test)
# ---------------------------------------------------------------------------

DB_PROCESS_SPECS: frozenset = frozenset([
    '1DB', '1DB1WB', '1DB2WB', '2DB', '2DB1WB', '2DB2WB',
    'DBCB', 'Epoxy D/B', 'Eutectic D/B', 'Eutectic D/B-雙晶',
    'Solder Paste D/B+E-Clip', '錫膏網印',
])

# DB-01 (rewritten 2026-07): start-lot origin SPEC. Replaces 'D/B-START' —
# that constant/logic is intentionally NOT deleted (see below) but is no
# longer read as the queue's entry point.
_LEGACY_START_LOT_SPEC = 'D/B-START'  # retired origin; kept for reference only
_START_LOT_SPEC = '晶片切割-END'

# DB-03: BOP first-char → allowed SPEC set. Reused as-is (values unchanged)
# from the pre-2026-07 "fallback" tier — under the new single-tier rule this
# is condition (a) of the ONLY match path, not a fallback.
BOP_FALLBACK_GROUPS: Dict[str, frozenset] = {
    'U': frozenset([
        '1DB', '1DB1WB', '1DB2WB', '2DB', '2DB1WB', '2DB2WB',
        'Eutectic D/B', 'Eutectic D/B-雙晶',
    ]),
    'E': frozenset(['Epoxy D/B']),
    'P': frozenset(['DBCB', 'Solder Paste D/B+E-Clip', '錫膏網印']),
}

# DB-05 (rewritten 2026-07): BOP first-char → allowed equipment zone
# (LOCATIONNAME) set — condition (c) of the match rule. Replaces the retired
# REGION_LOCATION_MAP (which keyed purely off the waiting lot's own
# PJ_PRODUCEREGION for every BOP). 'U' is the only BOP that still depends on
# the waiting lot's own PJ_PRODUCEREGION; 'E'/'P' are FIXED regardless of the
# waiting lot's region. Any BOP='U' region not listed here — including
# 'E區', None, or any other/unknown value — yields zero candidates by design.
BOP_U_REGION_ZONE_MAP: Dict[str, frozenset] = {
    'A棟': frozenset(['焊接A區', '焊接B區', '焊接C區']),
    'D區': frozenset(['焊接D區']),
}
BOP_FIXED_ZONE_MAP: Dict[str, frozenset] = {
    'E': frozenset(['焊接D區']),
    'P': frozenset(['焊接E區']),
}

# Workcenter group (see config/workcenter_groups.py) covering DB-process
# equipment — used to build the full idle-equipment universe (point 4 of the
# 2026-07 rule change: idle machines must be considered too, not only ones
# with a live WIP row).
_DB_WELDING_GROUP = '焊接_DB'

# DB-idle-fallback: lookback window for the idle-equipment history query.
# 30 days is long enough to cover a typical PM/changeover idle span without
# surfacing equipment that has been relocated or decommissioned long ago.
_IDLE_HISTORY_LOOKBACK_DAYS = 30
_IDLE_HISTORY_SQL_NAME = 'db_scheduling/idle_equipment_history'

# matchSource value emitted by the new single-tier rule (replaces the old
# 'workflow' / 'bop-fallback' pair; 'none' is still never emitted).
_MATCH_SOURCE = 'bop-package-zone'

# Oracle view
_WIP_VIEW = "DWH.DW_MES_LOT_V"

# Sort keys for output (DB-04)
_SORT_COLS = ['PACKAGE_LEF', 'PJ_TYPE', 'WAFERLOT', 'UTS']

# Columns required from the WIP view for this service
_REQUIRED_COLS = {
    'LOTID', 'WORKFLOWNAME', 'PACKAGE_LEF', 'PJ_TYPE', 'WAFERLOT',
    'UTS', 'QTY', 'BOP', 'SPECNAME', 'STATUS', 'EQUIPMENTS',
    'PJ_PRODUCEREGION',
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_value(value: Any) -> Any:
    """Normalize pandas NaN/NaT to None; unwrap numpy scalars."""
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    if hasattr(value, 'item'):
        try:
            return value.item()
        except Exception:
            return value
    return value


def _safe_int(value: Any) -> int:
    v = _safe_value(value)
    if v is None:
        return 0
    try:
        return int(v)
    except (ValueError, TypeError):
        return 0


def _load_wip_df() -> Optional[pd.DataFrame]:
    """Load WIP data: cache first, Oracle fallback on miss.

    Returns None only if both cache and Oracle are unavailable.
    """
    df = get_cached_wip_data()
    if df is not None:
        return df

    logger.info(
        'db_scheduling_service: WIP cache miss — falling back to Oracle'
    )
    try:
        sql = f"SELECT * FROM {_WIP_VIEW} WHERE WORKORDER IS NOT NULL"
        df = read_sql_df(sql, caller='db_scheduling_service:_load_wip_df')
        return df
    except Exception as exc:
        logger.error('db_scheduling_service: Oracle fallback failed: %s', exc)
        return None


def _make_row(
    start_row: Any,
    eqp_row: Any,
    target_spec: str,
    equipment: str,
    match_source: str,
    equipment_source: str,
) -> Dict[str, Any]:
    """Build one output dict per §3.22 (field 16 'equipmentSource' added 2026-07).

    start_row: the waiting lot (晶片切割-END) being dispatched.
    eqp_row:   the candidate equipment's current/most-recent lot attributes —
               a WIP-cache row (Series) for equipmentSource='live', or a
               plain dict (PACKAGE_LEF only; PJ_TYPE/WAFERLOT/UTS unavailable
               from history) for equipmentSource='history'.
    equipment_source: 'live' (currently-ACTIVE, read from the WIP cache) or
               'history' (currently-idle, resolved via the LOTWIPHISTORY
               fallback — see _load_idle_equipment_history()).
    """
    return {
        # Waiting lot attributes (displayed in the fixed lot columns)
        'lotId': _safe_value(start_row.get('LOTID')),
        'workflowName': _safe_value(start_row.get('WORKFLOWNAME')),
        'packageLef': _safe_value(start_row.get('PACKAGE_LEF')),
        'pjType': _safe_value(start_row.get('PJ_TYPE')),
        'waferLot': _safe_value(start_row.get('WAFERLOT')),
        'uts': _safe_value(start_row.get('UTS')),
        'qty': _safe_int(start_row.get('QTY')),
        'bop': _safe_value(start_row.get('BOP')),
        'produceRegion': _safe_value(start_row.get('PJ_PRODUCEREGION')),
        # Candidate equipment's current/most-recent lot attributes
        'eqpPackageLef': _safe_value(eqp_row.get('PACKAGE_LEF')),
        'eqpPjType': _safe_value(eqp_row.get('PJ_TYPE')),
        'eqpWaferLot': _safe_value(eqp_row.get('WAFERLOT')),
        'eqpUts': _safe_value(eqp_row.get('UTS')),
        'targetSpec': target_spec,
        'equipment': equipment,
        'matchSource': match_source,
        'equipmentSource': equipment_source,
    }


def _allowed_zones_for(
    bop_first: Optional[str], produce_region: Optional[str]
) -> Optional[frozenset]:
    """DB-05 (rewritten 2026-07): resolve condition (c)'s allowed equipment
    LOCATIONNAME set for a given waiting lot.

    BOP='U' depends on the waiting lot's own PJ_PRODUCEREGION — only 'A棟'
    and 'D區' are recognized; any other region (including 'E區', None, or an
    unknown value) returns None (zero candidates by design). BOP='E'/'P' are
    fixed regardless of the waiting lot's region. Any other bop_first returns
    None, consistent with BOP_FALLBACK_GROUPS.get() returning None for the
    same case.
    """
    if bop_first == 'U':
        return BOP_U_REGION_ZONE_MAP.get(produce_region)
    return BOP_FIXED_ZONE_MAP.get(bop_first)


def _load_idle_equipment_history(
    idle_equipment_names_upper: set,
) -> Dict[str, Dict[str, Any]]:
    """DB-idle-fallback: resolve each idle equipment's most-recent SPECNAME +
    PACKAGE_LF from DWH.DW_MES_LOTWIPHISTORY.

    See sql/db_scheduling/idle_equipment_history.sql for the query and the
    rationale for this deliberate, narrow exception to ADR 0013 — it only
    ever runs against the small set of currently-idle 焊接_DB equipment that
    has no row in the WIP cache to read attributes from.

    Args:
        idle_equipment_names_upper: RESOURCENAME values (already upper-cased)
            for 焊接_DB equipment NOT already present in the live DB-02 pool.

    Returns:
        Dict keyed by EQUIPMENTNAME (upper-cased) → {'SPECNAME', 'PACKAGE_LF'}
        for its most-recent DB-00-spec trackout within the lookback window.
        Fail-open: returns {} (no idle candidates) on any error or when the
        input set is empty — never raises.
    """
    if not idle_equipment_names_upper:
        return {}
    try:
        builder = QueryBuilder()
        builder.add_in_condition(
            'UPPER(h.EQUIPMENTNAME)', sorted(idle_equipment_names_upper)
        )
        equipment_filter = builder.conditions[0] if builder.conditions else '1=0'
        builder.add_in_condition('h.SPECNAME', sorted(DB_PROCESS_SPECS))
        spec_filter = builder.conditions[-1] if len(builder.conditions) > 1 else '1=0'

        sql = SQLLoader.load_with_params(
            _IDLE_HISTORY_SQL_NAME,
            EQUIPMENT_FILTER=equipment_filter,
            SPEC_FILTER=spec_filter,
        )
        cutoff_date = (
            datetime.now() - timedelta(days=_IDLE_HISTORY_LOOKBACK_DAYS)
        ).strftime('%Y-%m-%d')
        params: Dict[str, Any] = {'cutoff_date': cutoff_date}
        params.update(builder.params)

        df = read_sql_df(
            sql, params, caller='db_scheduling_service:_load_idle_equipment_history'
        )
        if df is None or df.empty:
            return {}

        lookup: Dict[str, Dict[str, Any]] = {}
        for _, row in df.iterrows():
            name = _safe_value(row.get('EQUIPMENTNAME'))
            if not name:
                continue
            lookup[str(name).strip().upper()] = {
                'SPECNAME': _safe_value(row.get('SPECNAME')),
                'PACKAGE_LF': _safe_value(row.get('PACKAGE_LF')),
            }
        return lookup
    except Exception:
        logger.warning(
            'db_scheduling_service: idle-equipment history fallback failed',
            exc_info=True,
        )
        return {}


# ---------------------------------------------------------------------------
# Main public function
# ---------------------------------------------------------------------------

def get_db_scheduling_queue() -> List[Dict[str, Any]]:
    """Return the DB scheduling queue: one row per recommended equipment per start-lot.

    Returns:
        List of dicts with 16 fields per §3.22 (see module docstring for the
        2026-07 field-shape delta). Empty list on cache/Oracle miss or when
        no lots qualify. Never raises.
    """
    try:
        df = _load_wip_df()
        if df is None or df.empty:
            return []

        # Ensure required columns exist (graceful degradation if WIP view changes)
        for col in _REQUIRED_COLS:
            if col not in df.columns:
                df[col] = None

        # --- DB-01: Start lots (SPECNAME == '晶片切割-END') --------------------
        start_mask = df['SPECNAME'].astype(str) == _START_LOT_SPEC
        start_lots = df[start_mask].copy()

        if start_lots.empty:
            return []

        # --- DB-02: Live running-equipment pool ---------------------------------
        # STATUS == 'ACTIVE' (case-insensitive; Oracle may store 'Active')
        status_active = df['STATUS'].astype(str).str.upper() == 'ACTIVE'
        spec_in_db00 = df['SPECNAME'].isin(DB_PROCESS_SPECS)
        equip_not_null = df['EQUIPMENTS'].notna() & (df['EQUIPMENTS'].astype(str).str.strip() != '')
        running_eqp = df[status_active & spec_in_db00 & equip_not_null].copy()

        # --- Build RESOURCENAME → LOCATIONNAME lookup + the full 焊接_DB
        # equipment universe (live + idle) from the resource cache. Zone
        # matching is now a required AND-condition (c) of the single-tier
        # match rule, so an unavailable resource cache fails CLOSED (an empty
        # _eqp_location map makes every zone lookup resolve to None, which is
        # never a member of any allowed-zone set) rather than the old
        # fail-open "skip the filter" behavior.
        _eqp_location: Dict[str, Optional[str]] = {}
        _db_welding_universe: Dict[str, str] = {}  # RESOURCENAME upper → original case
        try:
            from mes_dashboard.services.resource_cache import get_all_resources
            for r in get_all_resources():
                name = r.get('RESOURCENAME')
                if not name:
                    continue
                name_upper = str(name).strip().upper()
                _eqp_location[name_upper] = r.get('LOCATIONNAME')
                group_name, _order = get_workcenter_group(r.get('WORKCENTERNAME'))
                if group_name == _DB_WELDING_GROUP:
                    _db_welding_universe[name_upper] = str(name).strip()
        except Exception:
            logger.warning(
                'db_scheduling_service: resource cache unavailable — zone '
                'matching cannot proceed (fail-closed: zero candidates)'
            )
            _eqp_location = {}
            _db_welding_universe = {}

        # --- Idle-equipment universe (point 4 of the 2026-07 rule change) ---
        # "Idle" = 焊接_DB equipment NOT already present in the live DB-02 pool.
        active_equipment_upper = set(
            running_eqp['EQUIPMENTS'].dropna().astype(str).str.strip().str.upper()
        )
        idle_equipment_map = {
            upper: orig
            for upper, orig in _db_welding_universe.items()
            if upper not in active_equipment_upper
        }
        idle_history_lookup = _load_idle_equipment_history(
            set(idle_equipment_map.keys())
        )

        # Build output rows
        output_rows: List[Dict[str, Any]] = []

        for _, start_row in start_lots.iterrows():
            bop = _safe_value(start_row.get('BOP'))
            if not bop:
                continue  # no BOP → no candidates (matchSource='none' never emitted)
            bop_first = str(bop)[0]

            # Condition (a): BOP-derived allowed running-SPEC set
            allowed_specs = BOP_FALLBACK_GROUPS.get(bop_first)
            if not allowed_specs:
                continue

            # Condition (c): BOP-derived allowed equipment zone set
            region = _safe_value(start_row.get('PJ_PRODUCEREGION'))
            allowed_zones = _allowed_zones_for(bop_first, region)
            if not allowed_zones:
                continue

            # Condition (b): PACKAGE must match — nothing can match an unknown package
            package = _safe_value(start_row.get('PACKAGE_LEF'))
            if package is None:
                continue
            package_str = str(package).strip()

            # --- Live candidates: currently-ACTIVE DB-process equipment (DB-02) ---
            spec_match = running_eqp['SPECNAME'].isin(allowed_specs)
            pkg_match = running_eqp['PACKAGE_LEF'].notna() & (
                running_eqp['PACKAGE_LEF'].astype(str).str.strip() == package_str
            )
            zone_match = running_eqp['EQUIPMENTS'].astype(str).str.strip().str.upper().map(
                lambda e: _eqp_location.get(e) in allowed_zones
            )
            live_candidates = running_eqp[spec_match & pkg_match & zone_match]

            for _, eqp_row in live_candidates.iterrows():
                equipment = _safe_value(eqp_row.get('EQUIPMENTS'))
                target_spec = _safe_value(eqp_row.get('SPECNAME'))
                if equipment and target_spec:
                    output_rows.append(
                        _make_row(start_row, eqp_row, target_spec, equipment, _MATCH_SOURCE, 'live')
                    )

            # --- Idle candidates: 焊接_DB equipment with no live WIP row,
            # resolved via the LOTWIPHISTORY fallback ---
            for eqp_upper, hist in idle_history_lookup.items():
                hist_spec = hist.get('SPECNAME')
                if hist_spec not in allowed_specs:
                    continue
                hist_pkg = hist.get('PACKAGE_LF')
                if hist_pkg is None or str(hist_pkg).strip() != package_str:
                    continue
                if _eqp_location.get(eqp_upper) not in allowed_zones:
                    continue
                equipment = idle_equipment_map.get(eqp_upper, eqp_upper)
                eqp_attrs = {
                    'PACKAGE_LEF': hist_pkg,
                    'PJ_TYPE': None,
                    'WAFERLOT': None,
                    'UTS': None,
                }
                output_rows.append(
                    _make_row(start_row, eqp_attrs, hist_spec, equipment, _MATCH_SOURCE, 'history')
                )

        if not output_rows:
            return []

        # --- DB-04: Sort PACKAGE_LEF → PJ_TYPE → WAFERLOT → UTS ASC NULLS LAST ---
        # Use pandas for correct NULLS LAST across mixed str/None columns.
        result_df = pd.DataFrame(output_rows)
        # Map output keys back to the sort column names for sort_values
        result_df['_pkg'] = result_df['packageLef']
        result_df['_pj'] = result_df['pjType']
        result_df['_wl'] = result_df['waferLot']
        result_df['_uts'] = result_df['uts']

        result_df = result_df.sort_values(
            ['_pkg', '_pj', '_wl', '_uts'],
            ascending=True,
            na_position='last',
        ).drop(columns=['_pkg', '_pj', '_wl', '_uts'])

        return result_df.to_dict(orient='records')

    except Exception:
        logger.exception('db_scheduling_service: unexpected error in get_db_scheduling_queue')
        return []


# ---------------------------------------------------------------------------
# Equipment detail (for pill click popup)
# ---------------------------------------------------------------------------

def _safe_float(value: Any) -> Optional[float]:
    v = _safe_value(value)
    if v is None:
        return None
    try:
        return round(float(v), 2)
    except (ValueError, TypeError):
        return None


def get_equipment_detail(equipment: str) -> Dict[str, Any]:
    """Return machine status + running-lot info for one equipment ID.

    Machine status comes from the realtime-equipment-cache (Redis + process cache).
    Lot info is read from the same WIP cache used by get_db_scheduling_queue().
    """
    from mes_dashboard.services.realtime_equipment_cache import get_equipment_status_lookup

    # ── Machine status ──────────────────────────────────────────────────────
    lookup = get_equipment_status_lookup()
    eqp_rec = (
        lookup.get(equipment)
        or lookup.get(equipment.upper())
        or next(
            (v for v in lookup.values() if
             str(v.get('EQUIPMENTID', '')).upper() == equipment.upper()),
            {}
        )
    )

    machine_status: Dict[str, Any] = {
        'e10Status':  _safe_value(eqp_rec.get('EQUIPMENTASSETSSTATUS')),
        'e10Reason':  _safe_value(eqp_rec.get('EQUIPMENTASSETSSTATUSREASON')),
        'jobOrder':   _safe_value(eqp_rec.get('JOBORDER')),
        'jobModel':   _safe_value(eqp_rec.get('JOBMODEL')),
        'jobStage':   _safe_value(eqp_rec.get('JOBSTAGE')),
        'jobId':      _safe_value(eqp_rec.get('JOBID')),
        'jobStatus':  _safe_value(eqp_rec.get('JOBSTATUS')),
    }

    # ── Running lot (WIP cache) ─────────────────────────────────────────────
    lot_info: Optional[Dict[str, Any]] = None
    df = _load_wip_df()
    if df is not None and 'EQUIPMENTS' in df.columns:
        mask = df['EQUIPMENTS'].astype(str).str.upper() == equipment.upper()
        hit = df[mask]
        if not hit.empty:
            row = hit.iloc[0].to_dict()
            lot_info = {
                'lotId':           _safe_value(row.get('LOTID')),
                'workorder':       _safe_value(row.get('WORKORDER')),
                'wipStatus':       _safe_value(row.get('STATUS')),
                'runcardStatus':   _safe_value(row.get('RUNCARDSTATUS')),
                'qty':             _safe_int(row.get('QTY')),
                'waferLotQty':     _safe_int(row.get('WAFERLOTQTY') or row.get('WAFER_QTY')),
                'ageByDays':       _safe_float(row.get('AGEBYDAYS')),
                'priorityCodeName':_safe_value(row.get('PRIORITYCODENAME')),
                'productName':     _safe_value(row.get('PRODUCT')),
                'package':         _safe_value(row.get('PRODUCTLINENAME')),
                'packageLef':      _safe_value(row.get('PACKAGE_LEF')),
                'pjType':          _safe_value(row.get('PJ_TYPE')),
                'pjFunction':      _safe_value(row.get('PJ_FUNCTION')),
                'bop':             _safe_value(row.get('BOP')),
                'dateCodeReq':     _safe_value(row.get('DATECODE')),
                'produceRegion':   _safe_value(row.get('PJ_PRODUCEREGION')),
                'specName':        _safe_value(row.get('SPECNAME')),
                'workflowName':    _safe_value(row.get('WORKFLOWNAME')),
            }

    return {
        'equipment':    equipment,
        'machineStatus': machine_status,
        'lotInfo':      lot_info,
    }
