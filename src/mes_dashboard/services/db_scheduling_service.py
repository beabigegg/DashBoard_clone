# -*- coding: utf-8 -*-
"""DB Scheduling queue service.

Implements GET /api/db-scheduling/queue logic:
1. Load data from the 5-min WIP cache (ADR 0013) via get_cached_wip_data().
   On cache miss → Oracle direct fallback via read_sql_df.
2. Extract D/B-START start-lots (DB-01) and running-equipment pool (DB-02).
3. Primary WORKFLOWNAME match → matchSource='workflow'.
4. BOP first-char fallback for unmatched lots → matchSource='bop-fallback'.
5. Lots with no match → zero rows (matchSource='none' never emitted).
6. Sort: PACKAGE_LEF → PJ_TYPE → WAFERLOT → UTS ASC, NULLS LAST (DB-04).
7. Return list of dicts with 11 fields per §3.22.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import pandas as pd

from mes_dashboard.core.cache import get_cached_wip_data
from mes_dashboard.core.database import read_sql_df

logger = logging.getLogger('mes_dashboard.db_scheduling_service')

# ---------------------------------------------------------------------------
# DB-00: Authoritative 12-SPEC list (pin with membership test)
# ---------------------------------------------------------------------------

DB_PROCESS_SPECS: frozenset = frozenset([
    '1DB', '1DB1WB', '1DB2WB', '2DB', '2DB1WB', '2DB2WB',
    'DBCB', 'Epoxy D/B', 'Eutectic D/B', 'Eutectic D/B-雙晶',
    'Solder Paste D/B+E-Clip', '錫膏網印',
])

# DB-05: PJ_PRODUCEREGION → allowed equipment LOCATIONNAME set
REGION_LOCATION_MAP: Dict[str, frozenset] = {
    'A棟': frozenset(['焊接A區', '焊接B區', '焊接C區']),
    'D區': frozenset(['焊接D區']),
    'E區': frozenset(['焊接E區']),
}

# DB-03: BOP first-char → allowed SPEC set for fallback
BOP_FALLBACK_GROUPS: Dict[str, frozenset] = {
    'U': frozenset([
        '1DB', '1DB1WB', '1DB2WB', '2DB', '2DB1WB', '2DB2WB',
        'Eutectic D/B', 'Eutectic D/B-雙晶',
    ]),
    'E': frozenset(['Epoxy D/B']),
    'P': frozenset(['DBCB', 'Solder Paste D/B+E-Clip', '錫膏網印']),
}

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
) -> Dict[str, Any]:
    """Build one output dict per §3.22.

    start_row: the waiting lot (D/B-START) being dispatched.
    eqp_row:   the running lot currently on the candidate equipment — its
               packageLef/pjType/waferLot/uts determine priority-column grouping.
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
        # Running lot attributes on the candidate equipment (priority key for column grouping)
        'eqpPackageLef': _safe_value(eqp_row.get('PACKAGE_LEF')),
        'eqpPjType': _safe_value(eqp_row.get('PJ_TYPE')),
        'eqpWaferLot': _safe_value(eqp_row.get('WAFERLOT')),
        'eqpUts': _safe_value(eqp_row.get('UTS')),
        'targetSpec': target_spec,
        'equipment': equipment,
        'matchSource': match_source,
    }


# ---------------------------------------------------------------------------
# Main public function
# ---------------------------------------------------------------------------

def get_db_scheduling_queue() -> List[Dict[str, Any]]:
    """Return the DB scheduling queue: one row per recommended equipment per start-lot.

    Returns:
        List of dicts with 11 fields per §3.22. Empty list on cache/Oracle miss
        or when no lots qualify. Never raises.
    """
    try:
        df = _load_wip_df()
        if df is None or df.empty:
            return []

        # Ensure required columns exist (graceful degradation if WIP view changes)
        for col in _REQUIRED_COLS:
            if col not in df.columns:
                df[col] = None

        # --- DB-01: Start lots (SPECNAME == 'D/B-START') ----------------------
        start_mask = df['SPECNAME'].astype(str) == 'D/B-START'
        start_lots = df[start_mask].copy()

        if start_lots.empty:
            return []

        # --- DB-02: Running equipment pool ------------------------------------
        # STATUS == 'ACTIVE' (case-insensitive; Oracle may store 'Active')
        status_active = df['STATUS'].astype(str).str.upper() == 'ACTIVE'
        spec_in_db00 = df['SPECNAME'].isin(DB_PROCESS_SPECS)
        equip_not_null = df['EQUIPMENTS'].notna() & (df['EQUIPMENTS'].astype(str).str.strip() != '')
        running_eqp = df[status_active & spec_in_db00 & equip_not_null].copy()

        # --- DB-05: Build RESOURCEID → LOCATIONNAME lookup from resource cache ---
        # Used to filter the candidate pool by each start lot's PJ_PRODUCEREGION.
        # Fail-open: if the cache is unavailable the map is empty and no zone
        # filtering is applied (all machines stay in the pool).
        try:
            from mes_dashboard.services.resource_cache import get_all_resources
            # Key by RESOURCENAME (matches WIP EQUIPMENTS column), not RESOURCEID (internal numeric ID)
            _eqp_location: Dict[str, str | None] = {
                str(r.get('RESOURCENAME', '')).upper(): r.get('LOCATIONNAME')
                for r in get_all_resources()
                if r.get('RESOURCENAME')
            }
        except Exception:
            logger.warning('db_scheduling_service: resource cache unavailable — skipping zone filter')
            _eqp_location = {}

        # Build output rows
        output_rows: List[Dict[str, Any]] = []
        output_sort_keys: list = []

        for _, start_row in start_lots.iterrows():
            # --- DB-05: Region-based candidate pool restriction ---
            region = _safe_value(start_row.get('PJ_PRODUCEREGION'))
            allowed_locations = REGION_LOCATION_MAP.get(region) if region else None
            if allowed_locations and _eqp_location:
                region_pool = running_eqp[
                    running_eqp['EQUIPMENTS'].astype(str).str.upper().map(
                        lambda e: _eqp_location.get(e) in allowed_locations
                    )
                ]
            else:
                # Unknown region or cache unavailable → no zone restriction (fail-open)
                region_pool = running_eqp

            lot_workflow = _safe_value(start_row.get('WORKFLOWNAME'))

            # Primary match: same WORKFLOWNAME in region-filtered pool
            if lot_workflow:
                wf_matches = region_pool[
                    region_pool['WORKFLOWNAME'].astype(str) == str(lot_workflow)
                ]
            else:
                wf_matches = pd.DataFrame()

            if not wf_matches.empty:
                # Fan-out: one row per equipment
                for _, eqp_row in wf_matches.iterrows():
                    equipment = _safe_value(eqp_row.get('EQUIPMENTS'))
                    target_spec = _safe_value(eqp_row.get('SPECNAME'))
                    if equipment and target_spec:
                        output_rows.append(
                            _make_row(start_row, eqp_row, target_spec, equipment, 'workflow')
                        )
                        output_sort_keys.append((
                            _safe_value(start_row.get('PACKAGE_LEF')),
                            _safe_value(start_row.get('PJ_TYPE')),
                            _safe_value(start_row.get('WAFERLOT')),
                            _safe_value(start_row.get('UTS')),
                        ))
                continue  # workflow match found — skip BOP fallback

            # BOP fallback (DB-03)
            bop = _safe_value(start_row.get('BOP'))
            if bop is None:
                continue  # matchSource='none' → zero rows

            bop_first = str(bop)[0] if bop else None
            allowed_specs = BOP_FALLBACK_GROUPS.get(bop_first)
            if not allowed_specs:
                continue  # matchSource='none' → zero rows

            fallback_matches = region_pool[region_pool['SPECNAME'].isin(allowed_specs)]
            for _, eqp_row in fallback_matches.iterrows():
                equipment = _safe_value(eqp_row.get('EQUIPMENTS'))
                target_spec = _safe_value(eqp_row.get('SPECNAME'))
                if equipment and target_spec:
                    output_rows.append(
                        _make_row(start_row, eqp_row, target_spec, equipment, 'bop-fallback')
                    )
                    output_sort_keys.append((
                        _safe_value(start_row.get('PACKAGE_LEF')),
                        _safe_value(start_row.get('PJ_TYPE')),
                        _safe_value(start_row.get('WAFERLOT')),
                        _safe_value(start_row.get('UTS')),
                    ))

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
