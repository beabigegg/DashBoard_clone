# -*- coding: utf-8 -*-
"""Query Tool Service.

Provides functions for batch tracing and equipment period queries:
- LOT resolution (LOT ID / Serial Number / Work Order → CONTAINERID)
- LOT production history and adjacent lots
- LOT associations (materials, rejects, holds, jobs)
- Equipment period queries (status hours, lots, materials, rejects, jobs)
- CSV export functionality

Architecture:
- All historical tables use CONTAINERID as primary key (NOT CONTAINERNAME)
- EQUIPMENTID = RESOURCEID (same ID system)
- Uses SQLLoader for SQL templates
- Uses QueryBuilder for dynamic conditions
"""

import csv
import io
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, Generator

import pandas as pd

from mes_dashboard.core.database import read_sql_df, read_sql_df_slow
from mes_dashboard.sql import SQLLoader

logger = logging.getLogger('mes_dashboard.query_tool')

# Constants
BATCH_SIZE = 1000  # Oracle IN clause limit
MAX_LOT_IDS = 50
MAX_SERIAL_NUMBERS = 50
MAX_WORK_ORDERS = 10
MAX_EQUIPMENTS = 20
MAX_DATE_RANGE_DAYS = 90
DEFAULT_TIME_WINDOW_HOURS = 168  # 1 week for better PJ_TYPE detection
ADJACENT_LOTS_COUNT = 3


# ============================================================
# Validation Functions
# ============================================================

def validate_date_range(start_date: str, end_date: str, max_days: int = MAX_DATE_RANGE_DAYS) -> Optional[str]:
    """Validate date range.

    Args:
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format
        max_days: Maximum allowed days

    Returns:
        Error message if validation fails, None if valid.
    """
    try:
        start = datetime.strptime(start_date, '%Y-%m-%d')
        end = datetime.strptime(end_date, '%Y-%m-%d')

        if end < start:
            return '結束日期不可早於起始日期'

        diff = (end - start).days
        if diff > max_days:
            return f'日期範圍不可超過 {max_days} 天'

        return None
    except ValueError as e:
        return f'日期格式錯誤: {e}'


def validate_lot_input(input_type: str, values: List[str]) -> Optional[str]:
    """Validate LOT input based on type.

    Args:
        input_type: Type of input ('lot_id', 'serial_number', 'work_order')
        values: List of input values

    Returns:
        Error message if validation fails, None if valid.
    """
    if not values:
        return '請輸入至少一個查詢條件'

    limits = {
        'lot_id': MAX_LOT_IDS,
        'serial_number': MAX_SERIAL_NUMBERS,
        'work_order': MAX_WORK_ORDERS,
    }

    limit = limits.get(input_type, MAX_LOT_IDS)
    if len(values) > limit:
        return f'輸入數量超過上限 ({limit} 筆)'

    return None


def validate_equipment_input(equipment_ids: List[str]) -> Optional[str]:
    """Validate equipment input.

    Args:
        equipment_ids: List of equipment IDs

    Returns:
        Error message if validation fails, None if valid.
    """
    if not equipment_ids:
        return '請選擇至少一台設備'

    if len(equipment_ids) > MAX_EQUIPMENTS:
        return f'設備數量不得超過 {MAX_EQUIPMENTS} 台'

    return None


# ============================================================
# Helper Functions
# ============================================================

def _build_in_clause(values: List[str], max_chunk_size: int = BATCH_SIZE) -> List[str]:
    """Build SQL IN clause lists for values.

    Oracle has a limit of ~1000 items per IN clause, so we chunk if needed.

    Args:
        values: List of values.
        max_chunk_size: Maximum items per IN clause.

    Returns:
        List of SQL IN clause strings (e.g., "'val1', 'val2', 'val3'").
    """
    if not values:
        return []

    # Escape single quotes
    escaped = [v.replace("'", "''") for v in values]

    # Chunk into groups
    chunks = []
    for i in range(0, len(escaped), max_chunk_size):
        chunk = escaped[i:i + max_chunk_size]
        chunks.append("'" + "', '".join(chunk) + "'")

    return chunks


def _build_in_filter(values: List[str], column: str) -> str:
    """Build SQL IN filter clause.

    Args:
        values: List of values.
        column: Column name.

    Returns:
        SQL condition string.
    """
    chunks = _build_in_clause(values)
    if not chunks:
        return "1=0"

    if len(chunks) == 1:
        return f"{column} IN ({chunks[0]})"

    conditions = [f"{column} IN ({chunk})" for chunk in chunks]
    return "(" + " OR ".join(conditions) + ")"


def _df_to_records(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """Convert DataFrame to list of records with proper type handling.

    Args:
        df: DataFrame to convert

    Returns:
        List of dictionaries
    """
    if df is None or df.empty:
        return []

    data = []
    for _, row in df.iterrows():
        record = {}
        for col in df.columns:
            value = row[col]
            if pd.isna(value):
                record[col] = None
            elif isinstance(value, datetime):
                record[col] = value.strftime('%Y-%m-%d %H:%M:%S')
            elif isinstance(value, pd.Timestamp):
                record[col] = value.strftime('%Y-%m-%d %H:%M:%S')
            elif isinstance(value, Decimal):
                record[col] = float(value)
            else:
                record[col] = value
        data.append(record)

    return data


# ============================================================
# LOT Resolution Functions
# ============================================================

def resolve_lots(input_type: str, values: List[str]) -> Dict[str, Any]:
    """Resolve input to CONTAINERID list.

    All historical tables (LOTWIPHISTORY, LOTMATERIALSHISTORY, etc.)
    use CONTAINERID as primary key, NOT CONTAINERNAME.
    This function converts user input to CONTAINERID for subsequent queries.

    Args:
        input_type: Type of input ('lot_id', 'serial_number', 'work_order')
        values: List of input values

    Returns:
        Dict with 'data' (list of {container_id, input_value}),
        'total', 'input_count', or 'error'.
    """
    # Validate input
    validation_error = validate_lot_input(input_type, values)
    if validation_error:
        return {'error': validation_error}

    # Clean values
    cleaned = [v.strip() for v in values if v.strip()]
    if not cleaned:
        return {'error': '請輸入有效的查詢條件'}

    try:
        if input_type == 'lot_id':
            return _resolve_by_lot_id(cleaned)
        elif input_type == 'serial_number':
            return _resolve_by_serial_number(cleaned)
        elif input_type == 'work_order':
            return _resolve_by_work_order(cleaned)
        else:
            return {'error': f'不支援的輸入類型: {input_type}'}

    except Exception as exc:
        logger.error(f"LOT resolution failed: {exc}")
        return {'error': f'解析失敗: {str(exc)}'}


def _resolve_by_lot_id(lot_ids: List[str]) -> Dict[str, Any]:
    """Resolve LOT IDs (CONTAINERNAME) to CONTAINERID.

    Args:
        lot_ids: List of LOT IDs (CONTAINERNAME values)

    Returns:
        Resolution result dict.
    """
    in_filter = _build_in_filter(lot_ids, 'CONTAINERNAME')
    sql = SQLLoader.load("query_tool/lot_resolve_id")
    sql = sql.replace("{{ CONTAINER_NAMES }}", in_filter.replace("CONTAINERNAME IN (", "").rstrip(")"))

    # Direct IN clause construction
    sql = f"""
    SELECT
        CONTAINERID,
        CONTAINERNAME,
        MFGORDERNAME,
        SPECNAME,
        QTY
    FROM DWH.DW_MES_CONTAINER
    WHERE {in_filter}
    """

    df = read_sql_df(sql, {})
    data = _df_to_records(df)

    # Map results
    found = {r['CONTAINERNAME']: r for r in data}
    results = []
    not_found = []

    for lot_id in lot_ids:
        if lot_id in found:
            results.append({
                'container_id': found[lot_id]['CONTAINERID'],
                'lot_id': found[lot_id]['CONTAINERNAME'],  # LOT ID for display
                'input_value': lot_id,
                'spec_name': found[lot_id].get('SPECNAME'),
                'qty': found[lot_id].get('QTY'),
            })
        else:
            not_found.append(lot_id)

    logger.info(f"LOT ID resolution: {len(results)} found, {len(not_found)} not found")

    return {
        'data': results,
        'total': len(results),
        'input_count': len(lot_ids),
        'not_found': not_found,
    }


def _resolve_by_serial_number(serial_numbers: List[str]) -> Dict[str, Any]:
    """Resolve serial numbers (FINISHEDNAME) to CONTAINERID.

    Note: One serial number may map to multiple CONTAINERIDs.

    Args:
        serial_numbers: List of serial numbers

    Returns:
        Resolution result dict.
    """
    in_filter = _build_in_filter(serial_numbers, 'p.FINISHEDNAME')

    # JOIN with CONTAINER to get LOT ID (CONTAINERNAME)
    sql = f"""
    SELECT DISTINCT
        p.CONTAINERID,
        p.FINISHEDNAME,
        c.CONTAINERNAME,
        c.SPECNAME
    FROM DWH.DW_MES_PJ_COMBINEDASSYLOTS p
    LEFT JOIN DWH.DW_MES_CONTAINER c ON p.CONTAINERID = c.CONTAINERID
    WHERE {in_filter}
    """

    df = read_sql_df(sql, {})
    data = _df_to_records(df)

    # Group by serial number
    sn_to_containers = {}
    for r in data:
        sn = r['FINISHEDNAME']
        if sn not in sn_to_containers:
            sn_to_containers[sn] = []
        sn_to_containers[sn].append({
            'container_id': r['CONTAINERID'],
            'lot_id': r.get('CONTAINERNAME'),
            'spec_name': r.get('SPECNAME'),
        })

    results = []
    not_found = []

    for sn in serial_numbers:
        if sn in sn_to_containers:
            for item in sn_to_containers[sn]:
                results.append({
                    'container_id': item['container_id'],
                    'lot_id': item['lot_id'],
                    'input_value': sn,
                    'spec_name': item.get('spec_name'),
                })
        else:
            not_found.append(sn)

    logger.info(f"Serial number resolution: {len(results)} containers from {len(serial_numbers)} inputs")

    return {
        'data': results,
        'total': len(results),
        'input_count': len(serial_numbers),
        'not_found': not_found,
    }


def _resolve_by_work_order(work_orders: List[str]) -> Dict[str, Any]:
    """Resolve work orders (PJ_WORKORDER) to CONTAINERID.

    Note: One work order may expand to many CONTAINERIDs (can be 100+).

    Args:
        work_orders: List of work orders

    Returns:
        Resolution result dict.
    """
    in_filter = _build_in_filter(work_orders, 'h.PJ_WORKORDER')

    # JOIN with CONTAINER to get LOT ID (CONTAINERNAME)
    sql = f"""
    SELECT DISTINCT
        h.CONTAINERID,
        h.PJ_WORKORDER,
        c.CONTAINERNAME,
        c.SPECNAME
    FROM DWH.DW_MES_LOTWIPHISTORY h
    LEFT JOIN DWH.DW_MES_CONTAINER c ON h.CONTAINERID = c.CONTAINERID
    WHERE {in_filter}
    """

    df = read_sql_df(sql, {})
    data = _df_to_records(df)

    # Group by work order
    wo_to_containers = {}
    for r in data:
        wo = r['PJ_WORKORDER']
        if wo not in wo_to_containers:
            wo_to_containers[wo] = []
        wo_to_containers[wo].append({
            'container_id': r['CONTAINERID'],
            'lot_id': r.get('CONTAINERNAME'),
            'spec_name': r.get('SPECNAME'),
        })

    results = []
    not_found = []
    expansion_info = {}

    for wo in work_orders:
        if wo in wo_to_containers:
            expansion_info[wo] = len(wo_to_containers[wo])
            for item in wo_to_containers[wo]:
                results.append({
                    'container_id': item['container_id'],
                    'lot_id': item['lot_id'],
                    'input_value': wo,
                    'spec_name': item.get('spec_name'),
                })
        else:
            not_found.append(wo)

    logger.info(f"Work order resolution: {len(results)} containers from {len(work_orders)} orders")

    return {
        'data': results,
        'total': len(results),
        'input_count': len(work_orders),
        'not_found': not_found,
        'expansion_info': expansion_info,
    }


# ============================================================
# LOT History Functions
# ============================================================

def _get_workcenters_for_groups(groups: List[str]) -> List[str]:
    """Get workcenter names for given groups using filter_cache.

    Args:
        groups: List of WORKCENTER_GROUP names

    Returns:
        List of WORKCENTERNAME values
    """
    from mes_dashboard.services.filter_cache import get_workcenters_for_groups
    return get_workcenters_for_groups(groups)


def get_lot_history(
    container_id: str,
    workcenter_groups: Optional[List[str]] = None
) -> Dict[str, Any]:
    """Get production history for a LOT.

    Args:
        container_id: CONTAINERID (16-char hex)
        workcenter_groups: Optional list of WORKCENTER_GROUP names to filter by

    Returns:
        Dict with 'data' (history records) and 'total', or 'error'.
    """
    if not container_id:
        return {'error': '請指定 CONTAINERID'}

    try:
        sql = SQLLoader.load("query_tool/lot_history")
        params = {'container_id': container_id}

        # Add workcenter filter if groups specified
        workcenter_filter = ""
        if workcenter_groups:
            workcenters = _get_workcenters_for_groups(workcenter_groups)
            if workcenters:
                workcenter_filter = f"AND {_build_in_filter(workcenters, 'h.WORKCENTERNAME')}"
                logger.debug(
                    f"Filtering by {len(workcenter_groups)} groups "
                    f"({len(workcenters)} workcenters)"
                )

        # Replace placeholder in SQL
        sql = sql.replace("{{ WORKCENTER_FILTER }}", workcenter_filter)

        df = read_sql_df(sql, params)
        data = _df_to_records(df)

        logger.debug(f"LOT history: {len(data)} records for {container_id}")

        return {
            'data': data,
            'total': len(data),
            'container_id': container_id,
            'filtered_by_groups': workcenter_groups or [],
        }

    except Exception as exc:
        logger.error(f"LOT history query failed for {container_id}: {exc}")
        return {'error': f'查詢失敗: {str(exc)}'}


def get_adjacent_lots(
    equipment_id: str,
    target_trackin_time: str,
    time_window_hours: int = DEFAULT_TIME_WINDOW_HOURS
) -> Dict[str, Any]:
    """Get adjacent lots (前後批) for a specific equipment.

    Finds lots processed before and after the target lot on the same equipment.
    Searches until finding a different PJ_TYPE, with minimum 3 lots in each direction.

    Args:
        equipment_id: Target equipment ID
        target_trackin_time: Target lot's TRACKINTIMESTAMP (ISO format)
        time_window_hours: Time window in hours (default 24)

    Returns:
        Dict with 'data' (adjacent lots with relative_position) and metadata.
    """
    if not all([equipment_id, target_trackin_time]):
        return {'error': '請指定設備和目標時間'}

    try:
        # Parse target time
        if isinstance(target_trackin_time, str):
            target_time = datetime.strptime(target_trackin_time, '%Y-%m-%d %H:%M:%S')
        else:
            target_time = target_trackin_time

        sql = SQLLoader.load("query_tool/adjacent_lots")
        params = {
            'equipment_id': equipment_id,
            'target_trackin_time': target_time,
            'time_window_hours': time_window_hours,
        }

        df = read_sql_df(sql, params)
        data = _df_to_records(df)

        logger.debug(f"Adjacent lots: {len(data)} records for {equipment_id}")

        return {
            'data': data,
            'total': len(data),
            'equipment_id': equipment_id,
            'target_time': target_trackin_time,
            'time_window_hours': time_window_hours,
        }

    except Exception as exc:
        logger.error(f"Adjacent lots query failed: {exc}")
        return {'error': f'查詢失敗: {str(exc)}'}


# ============================================================
# LOT Association Functions
# ============================================================

def get_lot_materials(container_id: str) -> Dict[str, Any]:
    """Get material consumption records for a LOT.

    Args:
        container_id: CONTAINERID (16-char hex)

    Returns:
        Dict with 'data' (material records) and 'total', or 'error'.
    """
    if not container_id:
        return {'error': '請指定 CONTAINERID'}

    try:
        sql = SQLLoader.load("query_tool/lot_materials")
        params = {'container_id': container_id}

        df = read_sql_df(sql, params)
        data = _df_to_records(df)

        logger.debug(f"LOT materials: {len(data)} records for {container_id}")

        return {
            'data': data,
            'total': len(data),
            'container_id': container_id,
        }

    except Exception as exc:
        logger.error(f"LOT materials query failed for {container_id}: {exc}")
        return {'error': f'查詢失敗: {str(exc)}'}


def get_lot_rejects(container_id: str) -> Dict[str, Any]:
    """Get reject (defect) records for a LOT.

    Args:
        container_id: CONTAINERID (16-char hex)

    Returns:
        Dict with 'data' (reject records) and 'total', or 'error'.
    """
    if not container_id:
        return {'error': '請指定 CONTAINERID'}

    try:
        sql = SQLLoader.load("query_tool/lot_rejects")
        params = {'container_id': container_id}

        df = read_sql_df(sql, params)
        data = _df_to_records(df)

        logger.debug(f"LOT rejects: {len(data)} records for {container_id}")

        return {
            'data': data,
            'total': len(data),
            'container_id': container_id,
        }

    except Exception as exc:
        logger.error(f"LOT rejects query failed for {container_id}: {exc}")
        return {'error': f'查詢失敗: {str(exc)}'}


def get_lot_holds(container_id: str) -> Dict[str, Any]:
    """Get HOLD/RELEASE records for a LOT.

    Args:
        container_id: CONTAINERID (16-char hex)

    Returns:
        Dict with 'data' (hold records with HOLD_STATUS and HOLD_HOURS) and 'total'.
    """
    if not container_id:
        return {'error': '請指定 CONTAINERID'}

    try:
        sql = SQLLoader.load("query_tool/lot_holds")
        params = {'container_id': container_id}

        df = read_sql_df(sql, params)
        data = _df_to_records(df)

        logger.debug(f"LOT holds: {len(data)} records for {container_id}")

        return {
            'data': data,
            'total': len(data),
            'container_id': container_id,
        }

    except Exception as exc:
        logger.error(f"LOT holds query failed for {container_id}: {exc}")
        return {'error': f'查詢失敗: {str(exc)}'}


def get_lot_split_merge_history(
    work_order: str,
    current_container_id: str = None
) -> Dict[str, Any]:
    """Get complete split/merge history for a work order (完整拆併批歷史).

    Queries DW_MES_HM_LOTMOVEOUT for SplitLot and CombineLot operations
    throughout the entire production history.

    Uses MFGORDERNAME (indexed) instead of CONTAINERID for much better performance.

    Operation sources (CALLBYCDONAME):
    - AssemblyMotherLotSchePrep: Assembly mother lot scheduling
    - LotSplit: Standard lot split
    - PJ_TMTTCombine: TMTT combine operation

    LOT ID patterns:
    - A00-001-01: Split at production station (製程站點拆分)
    - A00-001-01C: Split at TMTT (TMTT 拆分)

    Args:
        work_order: MFGORDERNAME value (e.g., GA25120713)
        current_container_id: Current LOT's CONTAINERID for highlighting

    Returns:
        Dict with 'data' (split/merge history records) and 'total', or 'error'.
    """
    if not work_order:
        return {'error': '請指定工單號', 'data': [], 'total': 0}

    try:
        sql = SQLLoader.load("query_tool/lot_split_merge_history")
        params = {'work_order': work_order}

        logger.info(f"Starting split/merge history query for MFGORDERNAME={work_order}")

        # Use slow query connection with 120s timeout
        # Note: DW_MES_HM_LOTMOVEOUT has 48M rows, no index on CONTAINERID/FROMCONTAINERID
        # Query by MFGORDERNAME is faster but still needs extra time
        df = read_sql_df_slow(sql, params, timeout_seconds=120)
        data = _df_to_records(df)

        # Process records for display
        processed = []
        for record in data:
            op_type = record.get('OPERATION_TYPE', '')

            # Determine operation display name
            if op_type == 'SplitLot':
                op_display = '拆批'
            elif op_type == 'CombineLot':
                op_display = '併批'
            else:
                op_display = op_type

            target_cid = record.get('TARGET_CONTAINERID')
            source_cid = record.get('SOURCE_CONTAINERID')

            processed.append({
                'history_id': record.get('HISTORYMAINLINEID'),
                'operation_type': op_type,
                'operation_type_display': op_display,
                'target_container_id': target_cid,
                'target_lot': record.get('TARGET_LOT'),
                'source_container_id': source_cid,
                'source_lot': record.get('SOURCE_LOT'),
                'target_qty': record.get('TARGET_QTY'),
                'txn_date': record.get('TXNDATE'),
                # Highlight if this record involves the current LOT
                'is_current_lot_source': current_container_id and source_cid == current_container_id,
                'is_current_lot_target': current_container_id and target_cid == current_container_id,
            })

        logger.info(f"Split/merge history completed: {len(processed)} records for MFGORDERNAME={work_order}")

        return {
            'data': processed,
            'total': len(processed),
            'work_order': work_order,
        }

    except Exception as exc:
        error_str = str(exc)
        logger.error(f"Split/merge history query failed for MFGORDERNAME={work_order}: {exc}")

        # Check for timeout error (DPY-4024, ORA-01013, or TimeoutError from read_sql_df_slow)
        if 'timeout' in error_str.lower() or 'DPY-4024' in error_str or 'ORA-01013' in error_str:
            return {
                'error': f'查詢逾時（超過 120 秒）',
                'timeout': True,
                'data': [],
                'total': 0
            }

        return {'error': f'查詢失敗: {error_str}', 'data': [], 'total': 0}


def _get_mfg_order_for_lot(container_id: str) -> Optional[str]:
    """Get MFGORDERNAME for a LOT from DW_MES_CONTAINER.

    Note: MFGORDERNAME is the field used in DW_MES_HM_LOTMOVEOUT (indexed).
    This may differ from PJ_WORKORDER in some cases.

    Args:
        container_id: CONTAINERID (16-char hex)

    Returns:
        MFGORDERNAME string (e.g., 'GA25120713') or None if not found.
    """
    try:
        sql = """
        SELECT MFGORDERNAME
        FROM DWH.DW_MES_CONTAINER
        WHERE CONTAINERID = :container_id
          AND MFGORDERNAME IS NOT NULL
        """
        df = read_sql_df(sql, {'container_id': container_id})
        if not df.empty:
            return df.iloc[0]['MFGORDERNAME']
        return None
    except Exception as exc:
        logger.warning(f"Failed to get MFGORDERNAME for {container_id}: {exc}")
        return None


def get_lot_splits(
    container_id: str,
    include_production_history: bool = True  # Uses dedicated slow query connection with 120s timeout
) -> Dict[str, Any]:
    """Get combined split/merge data for a LOT (拆併批紀錄).

    Data sources:
    1. TMTT serial number mapping (DW_MES_PJ_COMBINEDASSYLOTS) - always included, fast
    2. Production split/merge history (DW_MES_HM_LOTMOVEOUT) - uses MFGORDERNAME index

    PERFORMANCE NOTE:
    Production history now queries by MFGORDERNAME (indexed) instead of CONTAINERID
    for much better performance (~1 second vs 40+ seconds).

    Args:
        container_id: CONTAINERID (16-char hex)
        include_production_history: If True (default), include production history query.

    Returns:
        Dict with 'production_history', 'serial_numbers', and totals.
    """
    if not container_id:
        return {'error': '請指定 CONTAINERID'}

    result = {
        'production_history': [],
        'serial_numbers': [],
        'total_history': 0,
        'total_serial_numbers': 0,
        'container_id': container_id,
        'production_history_skipped': not include_production_history,
    }

    # Add skip reason message if production history is disabled
    if not include_production_history:
        result['production_history_skip_reason'] = (
            '生產拆併批歷史查詢已暫時停用（資料表 DW_MES_HM_LOTMOVEOUT 目前無索引）。'
            '目前僅顯示 TMTT 成品流水號對應資料。'
        )

    # 1. Get production split/merge history by MFGORDERNAME (indexed, fast)
    if include_production_history:
        # Get MFGORDERNAME for this LOT (used in DW_MES_HM_LOTMOVEOUT)
        logger.info(f"[DEBUG] Getting MFGORDERNAME for container_id={container_id}")
        mfg_order = _get_mfg_order_for_lot(container_id)
        logger.info(f"[DEBUG] Got MFGORDERNAME={mfg_order} for container_id={container_id}")

        if mfg_order:
            logger.info(f"Querying production history for MFGORDERNAME={mfg_order} (LOT: {container_id})")
            history_result = get_lot_split_merge_history(
                work_order=mfg_order,
                current_container_id=container_id
            )
            logger.info(f"[DEBUG] history_result keys: {list(history_result.keys())}")
            logger.info(f"[DEBUG] history_result total: {history_result.get('total', 0)}")

            if 'error' not in history_result:
                result['production_history'] = history_result.get('data', [])
                result['total_history'] = history_result.get('total', 0)
                result['work_order'] = mfg_order
                logger.info(f"[DEBUG] production_history has {len(result['production_history'])} records")
            elif history_result.get('timeout'):
                # Timeout error - show user-friendly message
                result['production_history_timeout'] = True
                result['production_history_timeout_message'] = (
                    '生產拆併批歷史查詢超時（超過 120 秒）。此表格（DW_MES_HM_LOTMOVEOUT）'
                    '有 4800 萬筆資料且無索引，查詢時間無法預估。僅顯示 TMTT 成品流水號對應資料。'
                )
                result['work_order'] = mfg_order
                logger.warning(f"Production history query timed out for {mfg_order}")
            else:
                # Other error
                result['production_history_error'] = history_result.get('error')
                logger.error(f"[DEBUG] history_result error: {history_result.get('error')}")
        else:
            logger.warning(f"Could not find MFGORDERNAME for {container_id}, skipping production history")
            result['production_history_skip_reason'] = '無法取得工單號，跳過生產拆併批查詢。'

    # 2. Get TMTT serial number mapping (fast - CONTAINERID has index)
    try:
        sql = SQLLoader.load("query_tool/lot_splits")
        params = {'container_id': container_id}

        df = read_sql_df(sql, params)
        data = _df_to_records(df)

        # Group by FINISHEDNAME to show combined structure
        grouped = {}
        total_good_die = 0

        for record in data:
            sn = record.get('FINISHEDNAME', '')
            if not sn or sn == 'Unknown':
                continue

            if sn not in grouped:
                grouped[sn] = {
                    'serial_number': sn,
                    'lots': [],
                    'total_good_die': 0,
                }

            ratio = record.get('PJ_COMBINEDRATIO')
            good_die = record.get('PJ_GOODDIEQTY')

            grouped[sn]['lots'].append({
                'container_id': record.get('CONTAINERID'),
                'lot_id': record.get('LOT_ID'),
                'work_order': record.get('PJ_WORKORDER'),
                'combine_ratio': ratio,
                'combine_ratio_pct': f"{ratio * 100:.1f}%" if ratio else '-',
                'good_die_qty': good_die,
                'original_good_die_qty': record.get('PJ_ORIGINALGOODDIEQTY'),
                'original_start_date': record.get('ORIGINALSTARTDATE'),
                'is_current': record.get('CONTAINERID') == container_id,
            })

            if good_die:
                grouped[sn]['total_good_die'] += good_die
                total_good_die += good_die

        result['serial_numbers'] = list(grouped.values())
        result['total_serial_numbers'] = len(grouped)
        result['total_good_die'] = total_good_die

        logger.debug(f"LOT splits: {result['total_history']} history + {result['total_serial_numbers']} serial numbers for {container_id}")

    except Exception as exc:
        logger.error(f"LOT splits query failed for {container_id}: {exc}")
        # Don't fail completely if serial number query fails
        result['serial_number_error'] = str(exc)

    return result


def get_lot_jobs(
    equipment_id: str,
    time_start: str,
    time_end: str
) -> Dict[str, Any]:
    """Get JOB records for equipment during LOT processing time.

    Note: EQUIPMENTID = RESOURCEID (same ID system).

    Args:
        equipment_id: Equipment ID (EQUIPMENTID from LOTWIPHISTORY)
        time_start: Start time (ISO format)
        time_end: End time (ISO format)

    Returns:
        Dict with 'data' (job records) and 'total', or 'error'.
    """
    if not all([equipment_id, time_start, time_end]):
        return {'error': '請指定設備和時間範圍'}

    try:
        # Parse times
        if isinstance(time_start, str):
            start = datetime.strptime(time_start, '%Y-%m-%d %H:%M:%S')
        else:
            start = time_start

        if isinstance(time_end, str):
            end = datetime.strptime(time_end, '%Y-%m-%d %H:%M:%S')
        else:
            end = time_end

        sql = SQLLoader.load("query_tool/lot_jobs")
        params = {
            'equipment_id': equipment_id,
            'time_start': start,
            'time_end': end,
        }

        df = read_sql_df(sql, params)
        data = _df_to_records(df)

        logger.debug(f"LOT jobs: {len(data)} records for {equipment_id}")

        return {
            'data': data,
            'total': len(data),
            'equipment_id': equipment_id,
            'time_range': {'start': time_start, 'end': time_end},
        }

    except Exception as exc:
        logger.error(f"LOT jobs query failed for {equipment_id}: {exc}")
        return {'error': f'查詢失敗: {str(exc)}'}


# ============================================================
# Equipment Period Query Functions
# ============================================================

def get_equipment_status_hours(
    equipment_ids: List[str],
    start_date: str,
    end_date: str
) -> Dict[str, Any]:
    """Get status hours statistics for equipment in a time period.

    Calculates OU% = PRD / (PRD + SBY + UDT) × 100%

    Args:
        equipment_ids: List of equipment IDs
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)

    Returns:
        Dict with 'data' (status hours per equipment) and aggregated totals.
    """
    # Validate inputs
    validation_error = validate_equipment_input(equipment_ids)
    if validation_error:
        return {'error': validation_error}

    validation_error = validate_date_range(start_date, end_date)
    if validation_error:
        return {'error': validation_error}

    try:
        # Build filter on HISTORYID (which maps to RESOURCEID)
        equipment_filter = _build_in_filter(equipment_ids, 'r.RESOURCEID')

        sql = SQLLoader.load("query_tool/equipment_status_hours")
        sql = sql.replace("{{ EQUIPMENT_FILTER }}", equipment_filter)

        params = {'start_date': start_date, 'end_date': end_date}
        df = read_sql_df(sql, params)
        data = _df_to_records(df)

        # Calculate totals
        total_prd = sum(r.get('PRD_HOURS', 0) or 0 for r in data)
        total_sby = sum(r.get('SBY_HOURS', 0) or 0 for r in data)
        total_udt = sum(r.get('UDT_HOURS', 0) or 0 for r in data)
        total_sdt = sum(r.get('SDT_HOURS', 0) or 0 for r in data)
        total_egt = sum(r.get('EGT_HOURS', 0) or 0 for r in data)
        total_nst = sum(r.get('NST_HOURS', 0) or 0 for r in data)
        total_hours = sum(r.get('TOTAL_HOURS', 0) or 0 for r in data)

        denominator = total_prd + total_sby + total_udt
        total_ou = round(total_prd * 100.0 / denominator, 2) if denominator > 0 else 0

        logger.info(f"Equipment status hours: {len(data)} equipment records")

        return {
            'data': data,
            'total': len(data),
            'totals': {
                'PRD_HOURS': total_prd,
                'SBY_HOURS': total_sby,
                'UDT_HOURS': total_udt,
                'SDT_HOURS': total_sdt,
                'EGT_HOURS': total_egt,
                'NST_HOURS': total_nst,
                'TOTAL_HOURS': total_hours,
                'OU_PERCENT': total_ou,
            },
            'date_range': {'start': start_date, 'end': end_date},
        }

    except Exception as exc:
        logger.error(f"Equipment status hours query failed: {exc}")
        return {'error': f'查詢失敗: {str(exc)}'}


def get_equipment_lots(
    equipment_ids: List[str],
    start_date: str,
    end_date: str
) -> Dict[str, Any]:
    """Get lots processed by equipment in a time period.

    Args:
        equipment_ids: List of equipment IDs
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)

    Returns:
        Dict with 'data' (lot records) and 'total'.
    """
    # Validate inputs
    validation_error = validate_equipment_input(equipment_ids)
    if validation_error:
        return {'error': validation_error}

    validation_error = validate_date_range(start_date, end_date)
    if validation_error:
        return {'error': validation_error}

    try:
        equipment_filter = _build_in_filter(equipment_ids, 'h.EQUIPMENTID')

        sql = SQLLoader.load("query_tool/equipment_lots")
        sql = sql.replace("{{ EQUIPMENT_FILTER }}", equipment_filter)

        params = {'start_date': start_date, 'end_date': end_date}
        df = read_sql_df(sql, params)
        data = _df_to_records(df)

        logger.info(f"Equipment lots: {len(data)} records")

        return {
            'data': data,
            'total': len(data),
            'date_range': {'start': start_date, 'end': end_date},
        }

    except Exception as exc:
        logger.error(f"Equipment lots query failed: {exc}")
        return {'error': f'查詢失敗: {str(exc)}'}


def get_equipment_materials(
    equipment_names: List[str],
    start_date: str,
    end_date: str
) -> Dict[str, Any]:
    """Get material consumption summary for equipment in a time period.

    Note: LOTMATERIALSHISTORY uses EQUIPMENTNAME for filtering.

    Args:
        equipment_names: List of equipment names
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)

    Returns:
        Dict with 'data' (material summary) and 'total'.
    """
    if not equipment_names:
        return {'error': '請選擇至少一台設備'}

    validation_error = validate_date_range(start_date, end_date)
    if validation_error:
        return {'error': validation_error}

    try:
        equipment_filter = _build_in_filter(equipment_names, 'EQUIPMENTNAME')

        sql = SQLLoader.load("query_tool/equipment_materials")
        sql = sql.replace("{{ EQUIPMENT_FILTER }}", equipment_filter)

        params = {'start_date': start_date, 'end_date': end_date}
        df = read_sql_df(sql, params)
        data = _df_to_records(df)

        logger.info(f"Equipment materials: {len(data)} records")

        return {
            'data': data,
            'total': len(data),
            'date_range': {'start': start_date, 'end': end_date},
        }

    except Exception as exc:
        logger.error(f"Equipment materials query failed: {exc}")
        return {'error': f'查詢失敗: {str(exc)}'}


def get_equipment_rejects(
    equipment_names: List[str],
    start_date: str,
    end_date: str
) -> Dict[str, Any]:
    """Get reject statistics for equipment in a time period.

    Note: LOTREJECTHISTORY only has EQUIPMENTNAME, not EQUIPMENTID.

    Args:
        equipment_names: List of equipment names
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)

    Returns:
        Dict with 'data' (reject summary) and 'total'.
    """
    if not equipment_names:
        return {'error': '請選擇至少一台設備'}

    validation_error = validate_date_range(start_date, end_date)
    if validation_error:
        return {'error': validation_error}

    try:
        equipment_filter = _build_in_filter(equipment_names, 'EQUIPMENTNAME')

        sql = SQLLoader.load("query_tool/equipment_rejects")
        sql = sql.replace("{{ EQUIPMENT_FILTER }}", equipment_filter)

        params = {'start_date': start_date, 'end_date': end_date}
        df = read_sql_df(sql, params)
        data = _df_to_records(df)

        logger.info(f"Equipment rejects: {len(data)} records")

        return {
            'data': data,
            'total': len(data),
            'date_range': {'start': start_date, 'end': end_date},
        }

    except Exception as exc:
        logger.error(f"Equipment rejects query failed: {exc}")
        return {'error': f'查詢失敗: {str(exc)}'}


def get_equipment_jobs(
    equipment_ids: List[str],
    start_date: str,
    end_date: str
) -> Dict[str, Any]:
    """Get JOB records for equipment in a time period.

    Note: DW_MES_JOB uses RESOURCEID (= EQUIPMENTID).

    Args:
        equipment_ids: List of equipment IDs (RESOURCEID)
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)

    Returns:
        Dict with 'data' (job records) and 'total'.
    """
    # Validate inputs
    validation_error = validate_equipment_input(equipment_ids)
    if validation_error:
        return {'error': validation_error}

    validation_error = validate_date_range(start_date, end_date)
    if validation_error:
        return {'error': validation_error}

    try:
        equipment_filter = _build_in_filter(equipment_ids, 'RESOURCEID')

        sql = SQLLoader.load("query_tool/equipment_jobs")
        sql = sql.replace("{{ EQUIPMENT_FILTER }}", equipment_filter)

        params = {'start_date': start_date, 'end_date': end_date}
        df = read_sql_df(sql, params)
        data = _df_to_records(df)

        logger.info(f"Equipment jobs: {len(data)} records")

        return {
            'data': data,
            'total': len(data),
            'date_range': {'start': start_date, 'end': end_date},
        }

    except Exception as exc:
        logger.error(f"Equipment jobs query failed: {exc}")
        return {'error': f'查詢失敗: {str(exc)}'}


# ============================================================
# Export Functions
# ============================================================

def export_to_csv(
    data: List[Dict[str, Any]],
    columns: Optional[List[str]] = None
) -> str:
    """Export data to CSV string.

    Args:
        data: List of records to export
        columns: Optional column order. If None, uses keys from first record.

    Returns:
        CSV string with UTF-8 BOM for Excel compatibility.
    """
    if not data:
        return ''

    output = io.StringIO()
    output.write('\ufeff')  # UTF-8 BOM for Excel

    # Determine columns
    if columns is None:
        columns = list(data[0].keys())

    writer = csv.writer(output)
    writer.writerow(columns)

    for record in data:
        row = []
        for col in columns:
            value = record.get(col)
            if value is None:
                row.append('')
            else:
                row.append(str(value))
        writer.writerow(row)

    return output.getvalue()


def generate_csv_stream(
    data: List[Dict[str, Any]],
    columns: Optional[List[str]] = None
) -> Generator[str, None, None]:
    """Generate CSV content as a stream.

    Args:
        data: List of records to export
        columns: Optional column order

    Yields:
        CSV rows as strings
    """
    if not data:
        return

    # Determine columns
    if columns is None:
        columns = list(data[0].keys())

    output = io.StringIO()
    writer = csv.writer(output)

    # Write BOM and header
    output.write('\ufeff')
    writer.writerow(columns)
    yield output.getvalue()
    output.truncate(0)
    output.seek(0)

    # Write data rows
    for record in data:
        row = []
        for col in columns:
            value = record.get(col)
            if value is None:
                row.append('')
            else:
                row.append(str(value))
        writer.writerow(row)
        yield output.getvalue()
        output.truncate(0)
        output.seek(0)
