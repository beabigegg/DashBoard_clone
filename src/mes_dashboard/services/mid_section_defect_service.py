# -*- coding: utf-8 -*-
"""Defect Traceability Analysis Service.

Bidirectional traceability from any detection station:
  - Backward: detection station defects → trace upstream → attribute to upstream machines
  - Forward: detection station defects → trace surviving lots downstream → downstream reject rates

Data Pipeline (Backward):
    Query 1:  Station Detection  → detection lots with ALL loss reasons (parameterized station)
    Query 2a: Split Chain BFS    → CONTAINER.SPLITFROMID upward traversal
    Query 2b: Merge Expansion    → COMBINEDASSYLOTS reverse merge lookup
    Query 3:  Upstream History   → LOTWIPHISTORY for ALL ancestor CONTAINERIDs
    Python:   Resolve ancestors  → Attribute defects → Aggregate

Data Pipeline (Forward):
    Query 1:  Station Detection  → detection lots with ALL loss reasons (parameterized station)
    Query 2:  Forward Lineage    → resolve_forward_tree for descendants
    Query 3:  WIP History        → LOTWIPHISTORY for ALL tracked CONTAINERIDs
    Query 4:  Downstream Rejects → LOTREJECTHISTORY for downstream stations
    Python:   Forward attribution → Aggregate

Attribution Method (Backward - Sum):
    For upstream machine M at station S:
      attributed_rejectqty = SUM(detection REJECTQTY for all linked lots)
      attributed_trackinqty = SUM(detection TRACKINQTY for all linked lots)
      rate = attributed_rejectqty / attributed_trackinqty × 100

Attribution Method (Forward):
    For downstream station Y (order > detection station order):
      total_input = SUM(TRACKINQTY for lots reaching Y)
      total_reject = SUM(REJECT_TOTAL_QTY at Y)
      rate = total_reject / total_input × 100
"""

import csv
import hashlib
import io
import logging
import math
import os
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Optional, Dict, List, Any, Set, Tuple, Generator

import pandas as pd

from mes_dashboard.core.database import read_sql_df
from mes_dashboard.core.cache import cache_get, cache_set, make_cache_key
from mes_dashboard.core.redis_client import try_acquire_lock, release_lock
from mes_dashboard.sql import SQLLoader
from mes_dashboard.services.event_fetcher import EventFetcher
from mes_dashboard.services.lineage_engine import LineageEngine
from mes_dashboard.config.workcenter_groups import WORKCENTER_GROUPS, get_group_order

logger = logging.getLogger('mes_dashboard.mid_section_defect')

# Constants
MAX_QUERY_DAYS = 180
CACHE_TTL_DETECTION = 300       # 5 min for detection data
CACHE_TTL_LOSS_REASONS = 86400  # 24h for loss reason list (daily sync)

FORWARD_PIPELINE_MAX_WORKERS = int(os.getenv('FORWARD_PIPELINE_MAX_WORKERS', '2'))

# Distributed lock settings for query_analysis cold-cache path
ANALYSIS_LOCK_TTL_SECONDS = 120
ANALYSIS_LOCK_WAIT_TIMEOUT_SECONDS = 90
ANALYSIS_LOCK_POLL_INTERVAL_SECONDS = 0.5

# Top N for chart display (rest grouped as "其他")
TOP_N = 10

# Dimension column mapping for backward attribution charts
DIMENSION_MAP = {
    'by_station': 'WORKCENTER_GROUP',
    'by_machine': 'EQUIPMENT_NAME',
    'by_workflow': 'WORKFLOW',
    'by_package': 'PRODUCTLINENAME',
    'by_pj_type': 'PJ_TYPE',
    'by_detection_machine': 'DETECTION_EQUIPMENTNAME',
}

# Forward dimension column mapping
FORWARD_DIMENSION_MAP = {
    'by_downstream_station': 'WORKCENTER_GROUP',
    'by_downstream_machine': 'EQUIPMENT_NAME',
    'by_downstream_loss_reason': 'LOSSREASONNAME',
    'by_detection_machine': 'DETECTION_EQUIPMENTNAME',
}

# CSV export column config (backward)
CSV_COLUMNS_BACKWARD = [
    ('CONTAINERNAME', 'LOT ID'),
    ('PJ_TYPE', 'TYPE'),
    ('PRODUCTLINENAME', 'PACKAGE'),
    ('WORKFLOW', 'WORKFLOW'),
    ('FINISHEDRUNCARD', '完工流水碼'),
    ('DETECTION_EQUIPMENTNAME', '偵測設備'),
    ('INPUT_QTY', '投入數'),
    ('LOSS_REASON', '不良原因'),
    ('DEFECT_QTY', '不良數'),
    ('DEFECT_RATE', '不良率(%)'),
    ('ANCESTOR_COUNT', '上游LOT數'),
    ('UPSTREAM_MACHINES', '上游機台'),
]

# CSV export column config (forward)
CSV_COLUMNS_FORWARD = [
    ('CONTAINERNAME', 'LOT ID'),
    ('PJ_TYPE', 'TYPE'),
    ('PRODUCTLINENAME', 'PACKAGE'),
    ('WORKFLOW', 'WORKFLOW'),
    ('DETECTION_EQUIPMENTNAME', '偵測設備'),
    ('INPUT_QTY', '偵測投入'),
    ('DEFECT_QTY', '偵測不良'),
    ('DOWNSTREAM_STATIONS', '下游到達站數'),
    ('DOWNSTREAM_REJECTS', '下游不良總數'),
    ('DOWNSTREAM_REJECT_RATE', '下游不良率(%)'),
    ('WORST_DOWNSTREAM', '最差下游站'),
]

# Valid direction values
VALID_DIRECTIONS = ('backward', 'forward')


# ============================================================
# Public API
# ============================================================

def query_analysis(
    start_date: str,
    end_date: str,
    loss_reasons: Optional[List[str]] = None,
    station: str = '測試',
    direction: str = 'backward',
) -> Optional[Dict[str, Any]]:
    """Main entry point for defect traceability analysis.

    Args:
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        loss_reasons: Optional list of loss reasons to filter (None = all)
        station: Workcenter group name for detection station (default '測試')
        direction: 'backward' or 'forward'

    Returns:
        Dict with kpi, charts, detail, available_loss_reasons, genealogy_status.
    """
    error = _validate_params(start_date, end_date, station, direction)
    if error:
        return {'error': error}

    # Check full analysis cache
    cache_key = make_cache_key(
        "mid_section_defect",
        filters={
            'start_date': start_date,
            'end_date': end_date,
            'loss_reasons': sorted(loss_reasons) if loss_reasons else None,
            'station': station,
            'direction': direction,
        },
    )
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    lock_name = (
        f"mid_section_defect:analysis:{hashlib.md5(cache_key.encode('utf-8')).hexdigest()}"
    )
    lock_acquired = False

    # Prevent duplicate cold-cache pipeline execution across workers.
    lock_acquired = try_acquire_lock(lock_name, ttl_seconds=ANALYSIS_LOCK_TTL_SECONDS)
    if not lock_acquired:
        wait_start = time.monotonic()
        while (
            time.monotonic() - wait_start
            < ANALYSIS_LOCK_WAIT_TIMEOUT_SECONDS
        ):
            cached = cache_get(cache_key)
            if cached is not None:
                return cached
            time.sleep(ANALYSIS_LOCK_POLL_INTERVAL_SECONDS)

        logger.warning(
            "Timed out waiting for in-flight mid_section_defect analysis cache; "
            "continuing with fail-open pipeline execution"
        )
    else:
        # Double-check cache after lock acquisition.
        cached = cache_get(cache_key)
        if cached is not None:
            return cached

    try:
        if direction == 'forward':
            result = _run_forward_pipeline(
                start_date, end_date, station, loss_reasons,
            )
        else:
            result = _run_backward_pipeline(
                start_date, end_date, station, loss_reasons,
            )

        if result is None:
            return None

        # Only cache successful results
        genealogy_status = result.get('genealogy_status', 'ready')
        if genealogy_status == 'ready':
            cache_set(cache_key, result, ttl=CACHE_TTL_DETECTION)
        return result
    finally:
        if lock_acquired:
            release_lock(lock_name)


def parse_loss_reasons_param(loss_reasons: Any) -> Optional[List[str]]:
    """Normalize loss reason input from API payloads.

    Accepts comma-separated strings or list-like inputs.
    Returns None when no valid value is provided.
    """
    if loss_reasons is None:
        return None

    values: List[str]
    if isinstance(loss_reasons, str):
        values = [item.strip() for item in loss_reasons.split(',') if item.strip()]
    elif isinstance(loss_reasons, (list, tuple, set)):
        values = []
        for item in loss_reasons:
            if not isinstance(item, str):
                continue
            text = item.strip()
            if text:
                values.append(text)
    else:
        return None

    if not values:
        return None

    deduped: List[str] = []
    seen = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped or None


def resolve_trace_seed_lots(
    start_date: str,
    end_date: str,
    station: str = '測試',
) -> Optional[Dict[str, Any]]:
    """Resolve seed lots for staged mid-section trace API."""
    error = _validate_date_range(start_date, end_date)
    if error:
        return {'error': error}

    detection_df = _fetch_station_detection_data(start_date, end_date, station)
    if detection_df is None:
        return None
    if detection_df.empty:
        return {'seeds': [], 'seed_count': 0}

    seeds = []
    unique_rows = detection_df.drop_duplicates(subset=['CONTAINERID'])
    for _, row in unique_rows.iterrows():
        cid = _safe_str(row.get('CONTAINERID'))
        if not cid:
            continue
        lot_id = _safe_str(row.get('CONTAINERNAME')) or cid
        seeds.append({
            'container_id': cid,
            'container_name': lot_id,
            'lot_id': lot_id,
        })

    seeds.sort(key=lambda item: (item.get('lot_id', ''), item.get('container_id', '')))
    return {
        'seeds': seeds,
        'seed_count': len(seeds),
    }


def build_trace_aggregation_from_events(
    start_date: Optional[str],
    end_date: Optional[str],
    *,
    loss_reasons: Optional[List[str]] = None,
    seed_container_ids: Optional[List[str]] = None,
    lineage_ancestors: Optional[Dict[str, Any]] = None,
    upstream_events_by_cid: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    downstream_events_by_cid: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    station: str = '測試',
    direction: str = 'backward',
    mode: str = 'date_range',
) -> Optional[Dict[str, Any]]:
    """Build mid-section summary payload from staged events data."""
    if mode == 'container':
        return _build_trace_aggregation_container_mode(
            loss_reasons=loss_reasons,
            seed_container_ids=seed_container_ids,
            lineage_ancestors=lineage_ancestors,
            upstream_events_by_cid=upstream_events_by_cid,
            downstream_events_by_cid=downstream_events_by_cid,
            station=station,
            direction=direction,
        )

    # date_range mode
    error = _validate_date_range(start_date, end_date)
    if error:
        return {'error': error}

    normalized_loss_reasons = parse_loss_reasons_param(loss_reasons)

    detection_df = _fetch_station_detection_data(start_date, end_date, station)
    if detection_df is None:
        return None
    if detection_df.empty:
        empty_result = _empty_result(direction)
        return {
            'kpi': empty_result['kpi'],
            'charts': empty_result['charts'],
            'daily_trend': empty_result['daily_trend'],
            'available_loss_reasons': empty_result['available_loss_reasons'],
            'genealogy_status': empty_result['genealogy_status'],
            'detail_total_count': 0,
        }

    available_loss_reasons = sorted(
        detection_df.loc[detection_df['REJECTQTY'] > 0, 'LOSSREASONNAME']
        .dropna().unique().tolist()
    )

    if normalized_loss_reasons:
        filtered_df = detection_df[
            (detection_df['LOSSREASONNAME'].isin(normalized_loss_reasons))
            | (detection_df['REJECTQTY'] == 0)
            | (detection_df['LOSSREASONNAME'].isna())
        ].copy()
    else:
        filtered_df = detection_df

    detection_data = _build_detection_lookup(filtered_df)

    seed_ids = [
        cid for cid in (seed_container_ids or list(detection_data.keys()))
        if isinstance(cid, str) and cid.strip()
    ]
    genealogy_status = 'ready'
    if seed_ids and lineage_ancestors is None:
        genealogy_status = 'error'

    # Forward direction: use forward pipeline
    if direction == 'forward':
        station_order = get_group_order(station)
        defect_cids = filtered_df.loc[
            filtered_df['REJECTQTY'] > 0, 'CONTAINERID'
        ].unique().tolist()

        wip_by_cid = _normalize_upstream_event_records(upstream_events_by_cid or {})
        downstream_rejects = _normalize_downstream_event_records(downstream_events_by_cid or {})

        forward_attr = _attribute_forward_defects(
            detection_data, defect_cids, wip_by_cid, downstream_rejects, station_order,
        )
        detail = _build_forward_detail_table(
            filtered_df, defect_cids, wip_by_cid, downstream_rejects, station_order,
        )

        return {
            'kpi': _build_forward_kpi(detection_data, forward_attr),
            'charts': _build_forward_charts(forward_attr, detection_data),
            'daily_trend': _build_daily_trend(filtered_df, normalized_loss_reasons),
            'available_loss_reasons': available_loss_reasons,
            'genealogy_status': genealogy_status,
            'detail_total_count': len(detail),
            'attribution': [],
        }

    # Backward direction
    normalized_ancestors = _normalize_lineage_ancestors(
        lineage_ancestors,
        seed_container_ids=seed_container_ids,
        fallback_seed_ids=list(detection_data.keys()),
    )
    normalized_upstream = _normalize_upstream_event_records(upstream_events_by_cid or {})

    attribution = _attribute_defects(
        detection_data,
        normalized_ancestors,
        normalized_upstream,
        normalized_loss_reasons,
    )
    detail = _build_detail_table(filtered_df, normalized_ancestors, normalized_upstream)

    return {
        'kpi': _build_kpi(filtered_df, attribution, normalized_loss_reasons),
        'charts': _build_all_charts(attribution, detection_data),
        'daily_trend': _build_daily_trend(filtered_df, normalized_loss_reasons),
        'available_loss_reasons': available_loss_reasons,
        'genealogy_status': genealogy_status,
        'detail_total_count': len(detail),
        'attribution': attribution,
    }


def _build_trace_aggregation_container_mode(
    *,
    loss_reasons: Optional[List[str]] = None,
    seed_container_ids: Optional[List[str]] = None,
    lineage_ancestors: Optional[Dict[str, Any]] = None,
    upstream_events_by_cid: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    downstream_events_by_cid: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    station: str = '測試',
    direction: str = 'backward',
) -> Optional[Dict[str, Any]]:
    """Container mode aggregation: same attribution pipeline, no date range."""
    if not seed_container_ids:
        empty_result = _empty_result(direction)
        return {
            'kpi': empty_result['kpi'],
            'charts': empty_result['charts'],
            'daily_trend': [],
            'available_loss_reasons': [],
            'genealogy_status': 'ready',
            'detail_total_count': 0,
            'attribution': [],
        }

    normalized_loss_reasons = parse_loss_reasons_param(loss_reasons)

    detection_df = _fetch_detection_by_container_ids(seed_container_ids, station)
    if detection_df is None:
        return None
    if detection_df.empty:
        empty_result = _empty_result(direction)
        return {
            'kpi': empty_result['kpi'],
            'charts': empty_result['charts'],
            'daily_trend': [],
            'available_loss_reasons': [],
            'genealogy_status': 'ready',
            'detail_total_count': 0,
            'attribution': [],
            'container_mode_hint': '所選容器在此偵測站無記錄',
        }

    available_loss_reasons = sorted(
        detection_df.loc[detection_df['REJECTQTY'] > 0, 'LOSSREASONNAME']
        .dropna().unique().tolist()
    )

    if normalized_loss_reasons:
        filtered_df = detection_df[
            (detection_df['LOSSREASONNAME'].isin(normalized_loss_reasons))
            | (detection_df['REJECTQTY'] == 0)
            | (detection_df['LOSSREASONNAME'].isna())
        ].copy()
    else:
        filtered_df = detection_df

    detection_data = _build_detection_lookup(filtered_df)

    seed_ids = [
        cid for cid in seed_container_ids
        if isinstance(cid, str) and cid.strip()
    ]
    genealogy_status = 'ready'
    if seed_ids and lineage_ancestors is None:
        genealogy_status = 'error'

    # Forward direction
    if direction == 'forward':
        station_order = get_group_order(station)
        defect_cids = filtered_df.loc[
            filtered_df['REJECTQTY'] > 0, 'CONTAINERID'
        ].unique().tolist()

        wip_by_cid = _normalize_upstream_event_records(upstream_events_by_cid or {})
        downstream_rejects = _normalize_downstream_event_records(downstream_events_by_cid or {})

        forward_attr = _attribute_forward_defects(
            detection_data, defect_cids, wip_by_cid, downstream_rejects, station_order,
        )
        detail = _build_forward_detail_table(
            filtered_df, defect_cids, wip_by_cid, downstream_rejects, station_order,
        )

        return {
            'kpi': _build_forward_kpi(detection_data, forward_attr),
            'charts': _build_forward_charts(forward_attr, detection_data),
            'daily_trend': [],
            'available_loss_reasons': available_loss_reasons,
            'genealogy_status': genealogy_status,
            'detail_total_count': len(detail),
            'attribution': [],
        }

    # Backward direction
    normalized_ancestors = _normalize_lineage_ancestors(
        lineage_ancestors,
        seed_container_ids=seed_container_ids,
        fallback_seed_ids=list(detection_data.keys()),
    )
    normalized_upstream = _normalize_upstream_event_records(upstream_events_by_cid or {})

    attribution = _attribute_defects(
        detection_data,
        normalized_ancestors,
        normalized_upstream,
        normalized_loss_reasons,
    )
    detail = _build_detail_table(filtered_df, normalized_ancestors, normalized_upstream)

    return {
        'kpi': _build_kpi(filtered_df, attribution, normalized_loss_reasons),
        'charts': _build_all_charts(attribution, detection_data),
        'daily_trend': [],
        'available_loss_reasons': available_loss_reasons,
        'genealogy_status': genealogy_status,
        'detail_total_count': len(detail),
        'attribution': attribution,
    }


def query_analysis_detail(
    start_date: str,
    end_date: str,
    loss_reasons: Optional[List[str]] = None,
    station: str = '測試',
    direction: str = 'backward',
    page: int = 1,
    page_size: int = 200,
) -> Optional[Dict[str, Any]]:
    """Return a paginated slice of the detail table from cached analysis.

    Calls query_analysis() which handles caching internally.
    Sorts detail by DEFECT_RATE descending (worst first) before paginating.
    """
    result = query_analysis(start_date, end_date, loss_reasons, station, direction)
    if result is None:
        return None
    if 'error' in result:
        return result

    detail = result.get('detail', [])
    sort_key = 'DOWNSTREAM_REJECT_RATE' if direction == 'forward' else 'DEFECT_RATE'
    detail_sorted = sorted(
        detail, key=lambda r: r.get(sort_key, 0), reverse=True,
    )

    total_count = len(detail_sorted)
    total_pages = max(1, (total_count + page_size - 1) // page_size)
    page = max(1, min(page, total_pages))
    offset = (page - 1) * page_size

    return {
        'detail': detail_sorted[offset:offset + page_size],
        'pagination': {
            'page': page,
            'page_size': page_size,
            'total_count': total_count,
            'total_pages': total_pages,
        },
    }


def query_all_loss_reasons() -> Optional[Dict[str, Any]]:
    """Get all loss reasons (cached daily in Redis).

    Lightweight query: DISTINCT LOSSREASONNAME from last 180 days.
    Cached with 24h TTL — suitable for dropdown population on page load.

    Returns:
        Dict with 'loss_reasons' list, or None on failure.
    """
    cache_key = make_cache_key("mid_section_loss_reasons")
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        sql = SQLLoader.load("mid_section_defect/all_loss_reasons")
        df = read_sql_df(sql, {})
        if df is None:
            logger.error("Loss reasons query returned None")
            return None

        reasons = sorted(df['LOSSREASONNAME'].dropna().unique().tolist())
        result = {'loss_reasons': reasons}
        logger.info(f"Loss reasons: {len(reasons)} distinct values cached (24h TTL)")
        cache_set(cache_key, result, ttl=CACHE_TTL_LOSS_REASONS)
        return result
    except Exception as exc:
        logger.error(f"Loss reasons query failed: {exc}", exc_info=True)
        return None


def export_csv(
    start_date: str,
    end_date: str,
    loss_reasons: Optional[List[str]] = None,
    station: str = '測試',
    direction: str = 'backward',
) -> Generator[str, None, None]:
    """Stream CSV export of detail data.

    Yields:
        CSV lines as strings.
    """
    result = query_analysis(start_date, end_date, loss_reasons, station, direction)
    columns = CSV_COLUMNS_FORWARD if direction == 'forward' else CSV_COLUMNS_BACKWARD

    # BOM for Excel UTF-8 compatibility
    yield '\ufeff'

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([label for _, label in columns])
    yield output.getvalue()
    output.seek(0)
    output.truncate(0)

    if result is None or 'error' in result:
        return

    for row in result.get('detail', []):
        writer.writerow([row.get(col, '') for col, _ in columns])
        yield output.getvalue()
        output.seek(0)
        output.truncate(0)


def query_station_options() -> List[Dict[str, Any]]:
    """Return ordered list of workcenter groups for station dropdown.

    Each entry includes:
        name:  group key (used as the station parameter value)
        label: primary DB pattern name for display (e.g. 'TMTT' for '測試')
        order: display sequence
    """
    options = []
    for name, cfg in WORKCENTER_GROUPS.items():
        primary_pattern = cfg['patterns'][0] if cfg.get('patterns') else name
        options.append({'name': name, 'label': primary_pattern, 'order': cfg['order']})
    return sorted(options, key=lambda x: x['order'])


# ============================================================
# Helpers
# ============================================================

def _safe_str(v, default=''):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return default
    try:
        if pd.isna(v):
            return default
    except (TypeError, ValueError):
        pass
    return str(v)


def _safe_float(v, default=0.0):
    if v is None:
        return default
    try:
        f = float(v)
        if math.isnan(f) or math.isinf(f):
            return default
        return f
    except (TypeError, ValueError):
        return default


def _safe_int(v, default=0):
    return int(_safe_float(v, float(default)))


def _empty_result(direction: str = 'backward') -> Dict[str, Any]:
    if direction == 'forward':
        return {
            'kpi': {
                'detection_lot_count': 0, 'detection_defect_qty': 0,
                'tracked_lot_count': 0, 'downstream_stations_reached': 0,
                'downstream_total_reject': 0, 'downstream_reject_rate': 0.0,
            },
            'available_loss_reasons': [],
            'charts': {k: [] for k in FORWARD_DIMENSION_MAP},
            'daily_trend': [],
            'detail': [],
            'genealogy_status': 'ready',
        }
    return {
        'kpi': {
            'total_input': 0, 'lot_count': 0,
            'total_defect_qty': 0, 'total_defect_rate': 0.0,
            'top_loss_reason': '', 'affected_machine_count': 0,
        },
        'available_loss_reasons': [],
        'charts': {k: [] for k in DIMENSION_MAP},
        'daily_trend': [],
        'detail': [],
        'genealogy_status': 'ready',
        'attribution': [],
    }


# ============================================================
# Validation
# ============================================================

def _validate_date_range(start_date: str, end_date: str) -> Optional[str]:
    try:
        start = datetime.strptime(start_date, '%Y-%m-%d')
        end = datetime.strptime(end_date, '%Y-%m-%d')
    except (ValueError, TypeError):
        return '日期格式無效，請使用 YYYY-MM-DD'

    if start > end:
        return '起始日期不能晚於結束日期'

    if (end - start).days > MAX_QUERY_DAYS:
        return f'查詢範圍不能超過 {MAX_QUERY_DAYS} 天'

    return None


def _validate_station(station: str) -> Optional[str]:
    if station not in WORKCENTER_GROUPS:
        valid_names = ', '.join(sorted(WORKCENTER_GROUPS.keys()))
        return f'無效偵測站: {station}（有效值: {valid_names}）'
    return None


def _validate_params(
    start_date: str, end_date: str, station: str, direction: str,
) -> Optional[str]:
    error = _validate_date_range(start_date, end_date)
    if error:
        return error
    error = _validate_station(station)
    if error:
        return error
    if direction not in VALID_DIRECTIONS:
        return f'無效方向: {direction}（有效值: backward, forward）'
    return None


# ============================================================
# Station Filter Builder
# ============================================================

def _build_station_filter(
    station_name: str,
    column_prefix: str = 'h',
) -> Tuple[str, Dict[str, str]]:
    """Build SQL WHERE fragment for station workcenter name matching.

    Args:
        station_name: Workcenter group name (key in WORKCENTER_GROUPS)
        column_prefix: Table alias prefix (e.g. 'h' for h.WORKCENTERNAME)

    Returns:
        (sql_fragment, bind_params) tuple.
    """
    config = WORKCENTER_GROUPS[station_name]
    patterns = config['patterns']
    excludes = config.get('exclude', [])

    col = f"UPPER({column_prefix}.WORKCENTERNAME)"
    parts = []
    params = {}

    for i, pattern in enumerate(patterns):
        param_name = f"wc_p{i}"
        parts.append(f"{col} LIKE :{param_name}")
        params[param_name] = f"%{pattern.upper()}%"

    include_sql = ' OR '.join(parts)

    if excludes:
        excl_parts = []
        for i, excl in enumerate(excludes):
            param_name = f"wc_ex{i}"
            excl_parts.append(f"{col} NOT LIKE :{param_name}")
            params[param_name] = f"%{excl.upper()}%"
        exclude_sql = ' AND '.join(excl_parts)
        fragment = f"({include_sql}) AND ({exclude_sql})"
    else:
        fragment = f"({include_sql})"

    return fragment, params


# ============================================================
# Query 1: Station Detection Data (parameterized)
# ============================================================

def _fetch_station_detection_data(
    start_date: str,
    end_date: str,
    station: str = '測試',
) -> Optional[pd.DataFrame]:
    """Execute station_detection.sql and return raw DataFrame."""
    cache_key = make_cache_key(
        "mid_section_detection",
        filters={
            'start_date': start_date,
            'end_date': end_date,
            'station': station,
        },
    )
    cached = cache_get(cache_key)
    if cached is not None:
        if isinstance(cached, list):
            return pd.DataFrame(cached) if cached else pd.DataFrame()
        return None

    try:
        wip_filter, wip_params = _build_station_filter(station, 'h')
        rej_filter, rej_params = _build_station_filter(station, 'r')

        sql = SQLLoader.load_with_params(
            "mid_section_defect/station_detection",
            STATION_FILTER=wip_filter,
            STATION_FILTER_REJECTS=rej_filter,
        )
        bind_params = {
            'start_date': start_date,
            'end_date': end_date,
            **wip_params,
            **rej_params,
        }
        df = read_sql_df(sql, bind_params)
        if df is None:
            logger.error("Station detection query returned None (station=%s)", station)
            return None
        logger.info(
            "Station detection (%s): %d rows, %d unique lots",
            station,
            len(df),
            df['CONTAINERID'].nunique() if not df.empty else 0,
        )
        cache_set(cache_key, df.to_dict('records'), ttl=CACHE_TTL_DETECTION)
        return df
    except Exception as exc:
        logger.error("Station detection query failed (station=%s): %s", station, exc, exc_info=True)
        return None


def _fetch_detection_by_container_ids(
    container_ids: List[str],
    station: str = '測試',
) -> Optional[pd.DataFrame]:
    """Fetch detection data for explicit container IDs (container query mode).

    Uses station_detection_by_ids.sql with CONTAINERID IN clause.
    """
    if not container_ids:
        return pd.DataFrame()

    cache_key = make_cache_key(
        "mid_section_detection_by_ids",
        filters={
            'cids': sorted(container_ids),
            'station': station,
        },
    )
    cached = cache_get(cache_key)
    if cached is not None:
        if isinstance(cached, list):
            return pd.DataFrame(cached) if cached else pd.DataFrame()
        return None

    try:
        wip_filter, wip_params = _build_station_filter(station, 'h')
        rej_filter, rej_params = _build_station_filter(station, 'r')

        # Build CONTAINERID IN clause with quoted values
        quoted_ids = ", ".join(f"'{cid}'" for cid in container_ids)

        sql = SQLLoader.load_with_params(
            "mid_section_defect/station_detection_by_ids",
            CONTAINER_IDS=quoted_ids,
            STATION_FILTER=wip_filter,
            STATION_FILTER_REJECTS=rej_filter,
        )
        bind_params = {**wip_params, **rej_params}
        df = read_sql_df(sql, bind_params)
        if df is None:
            logger.error("Container detection query returned None (station=%s)", station)
            return None
        logger.info(
            "Container detection (%s): %d rows, %d unique lots from %d input IDs",
            station,
            len(df),
            df['CONTAINERID'].nunique() if not df.empty else 0,
            len(container_ids),
        )
        cache_set(cache_key, df.to_dict('records'), ttl=CACHE_TTL_DETECTION)
        return df
    except Exception as exc:
        logger.error("Container detection query failed (station=%s): %s", station, exc, exc_info=True)
        return None


# ============================================================
# Backward Pipeline
# ============================================================

def _run_backward_pipeline(
    start_date: str,
    end_date: str,
    station: str,
    loss_reasons: Optional[List[str]],
) -> Optional[Dict[str, Any]]:
    """Run the backward traceability pipeline (detection → upstream attribution)."""
    detection_df = _fetch_station_detection_data(start_date, end_date, station)
    if detection_df is None:
        return None
    if detection_df.empty:
        return _empty_result('backward')

    # Extract available loss reasons before filtering
    available_loss_reasons = sorted(
        detection_df.loc[detection_df['REJECTQTY'] > 0, 'LOSSREASONNAME']
        .dropna().unique().tolist()
    )

    # Apply loss reason filter if specified
    if loss_reasons:
        filtered_df = detection_df[
            (detection_df['LOSSREASONNAME'].isin(loss_reasons))
            | (detection_df['REJECTQTY'] == 0)
            | (detection_df['LOSSREASONNAME'].isna())
        ].copy()
    else:
        filtered_df = detection_df

    # Stage 2: Genealogy resolution (split chain + merge expansion)
    detection_cids = detection_df['CONTAINERID'].unique().tolist()
    detection_names = {}
    for _, r in detection_df.drop_duplicates('CONTAINERID').iterrows():
        detection_names[r['CONTAINERID']] = _safe_str(r.get('CONTAINERNAME'))

    ancestors = {}
    genealogy_status = 'ready'

    if detection_cids:
        try:
            ancestors = _resolve_full_genealogy(detection_cids, detection_names)
        except Exception as exc:
            logger.error(f"Genealogy resolution failed: {exc}", exc_info=True)
            genealogy_status = 'error'

    # Stage 3: Upstream history for ALL CIDs (detection lots + ancestors)
    all_query_cids = set(detection_cids)
    for anc_set in ancestors.values():
        all_query_cids.update(anc_set)
    all_query_cids = {c for c in all_query_cids if isinstance(c, str) and c}

    upstream_by_cid = {}
    if all_query_cids:
        try:
            upstream_by_cid = _fetch_upstream_history(list(all_query_cids))
        except Exception as exc:
            logger.error(f"Upstream history query failed: {exc}", exc_info=True)
            genealogy_status = 'error'

    detection_data = _build_detection_lookup(filtered_df)
    attribution = _attribute_defects(
        detection_data, ancestors, upstream_by_cid, loss_reasons,
    )

    return {
        'kpi': _build_kpi(filtered_df, attribution, loss_reasons),
        'available_loss_reasons': available_loss_reasons,
        'charts': _build_all_charts(attribution, detection_data),
        'daily_trend': _build_daily_trend(filtered_df, loss_reasons),
        'detail': _build_detail_table(filtered_df, ancestors, upstream_by_cid),
        'genealogy_status': genealogy_status,
        'attribution': attribution,
    }


# ============================================================
# Forward Pipeline
# ============================================================

def _run_forward_pipeline(
    start_date: str,
    end_date: str,
    station: str,
    loss_reasons: Optional[List[str]],
) -> Optional[Dict[str, Any]]:
    """Run the forward traceability pipeline (detection → downstream reject rates)."""
    station_order = get_group_order(station)

    # Stage 1: Detection data
    detection_df = _fetch_station_detection_data(start_date, end_date, station)
    if detection_df is None:
        return None
    if detection_df.empty:
        return _empty_result('forward')

    available_loss_reasons = sorted(
        detection_df.loc[detection_df['REJECTQTY'] > 0, 'LOSSREASONNAME']
        .dropna().unique().tolist()
    )

    # Apply loss reason filter
    if loss_reasons:
        filtered_df = detection_df[
            (detection_df['LOSSREASONNAME'].isin(loss_reasons))
            | (detection_df['REJECTQTY'] == 0)
            | (detection_df['LOSSREASONNAME'].isna())
        ].copy()
    else:
        filtered_df = detection_df

    # Stage 2: Filter to lots WITH rejects
    defect_cids = filtered_df.loc[
        filtered_df['REJECTQTY'] > 0, 'CONTAINERID'
    ].unique().tolist()
    if not defect_cids:
        result = _empty_result('forward')
        result['available_loss_reasons'] = available_loss_reasons
        return result

    detection_names = {}
    for _, r in detection_df.drop_duplicates('CONTAINERID').iterrows():
        detection_names[r['CONTAINERID']] = _safe_str(r.get('CONTAINERNAME'))

    # Stage 3: Forward lineage (descendants)
    genealogy_status = 'ready'
    children_map = {}
    try:
        forward_result = LineageEngine.resolve_forward_tree(defect_cids, detection_names)
        children_map = forward_result.get('children_map', {})
    except Exception as exc:
        logger.error("Forward lineage resolution failed: %s", exc, exc_info=True)
        genealogy_status = 'error'

    # Stage 4: Collect all tracked CIDs (detection + all descendants)
    tracked_cids = set(defect_cids)
    for parent, children in children_map.items():
        if isinstance(children, (list, set)):
            tracked_cids.update(c for c in children if isinstance(c, str) and c)
    tracked_cids = {c for c in tracked_cids if isinstance(c, str) and c}

    # Stages 5+6: WIP history and downstream rejects in parallel
    wip_by_cid = {}
    downstream_rejects = {}
    if tracked_cids:
        tracked_list = list(tracked_cids)
        with ThreadPoolExecutor(max_workers=FORWARD_PIPELINE_MAX_WORKERS) as executor:
            wip_future = executor.submit(_fetch_upstream_history, tracked_list)
            rejects_future = executor.submit(_fetch_downstream_rejects, tracked_list)

            try:
                wip_by_cid = wip_future.result()
            except Exception as exc:
                logger.error("Forward WIP history query failed: %s", exc, exc_info=True)
                genealogy_status = 'error'

            try:
                downstream_rejects = rejects_future.result()
            except Exception as exc:
                logger.error("Downstream rejects query failed: %s", exc, exc_info=True)
                genealogy_status = 'error'

    # Stage 7: Forward attribution
    detection_data = _build_detection_lookup(filtered_df)
    forward_attr = _attribute_forward_defects(
        detection_data, defect_cids, wip_by_cid, downstream_rejects, station_order,
    )

    # Stage 8: Build result
    return {
        'kpi': _build_forward_kpi(detection_data, forward_attr),
        'available_loss_reasons': available_loss_reasons,
        'charts': _build_forward_charts(forward_attr, detection_data),
        'daily_trend': _build_daily_trend(filtered_df, loss_reasons),
        'detail': _build_forward_detail_table(
            filtered_df, defect_cids, wip_by_cid, downstream_rejects, station_order,
        ),
        'genealogy_status': genealogy_status,
    }


# ============================================================
# Query 2: LOT Genealogy
# ============================================================

def _resolve_full_genealogy(
    detection_cids: List[str],
    detection_names: Dict[str, str],
) -> Dict[str, Set[str]]:
    """Resolve full genealogy for detection lots via shared LineageEngine."""
    result = LineageEngine.resolve_full_genealogy(detection_cids, detection_names)
    ancestors = result.get("ancestors", {}) if isinstance(result, dict) else result
    _log_genealogy_summary(ancestors, detection_cids, 0)
    return ancestors


def _log_genealogy_summary(
    ancestors: Dict[str, Set[str]],
    detection_cids: List[str],
    merge_count: int,
) -> None:
    total_ancestors = sum(len(v) for v in ancestors.values())
    lots_with_ancestors = sum(1 for v in ancestors.values() if v)
    logger.info(
        f"Genealogy resolved: {lots_with_ancestors}/{len(detection_cids)} lots have ancestors, "
        f"{total_ancestors} total ancestor links, "
        f"{merge_count} merge sources"
    )


# ============================================================
# Query 3: Upstream Production History
# ============================================================

def _fetch_upstream_history(
    all_cids: List[str],
) -> Dict[str, List[Dict[str, Any]]]:
    """Fetch upstream production history for ancestor CONTAINERIDs.

    Batches queries to respect Oracle IN clause limit.
    WORKCENTER_GROUP classification is computed in SQL (CASE WHEN).

    Returns:
        {containerid: [{'workcenter_group': ..., 'equipment_name': ..., ...}, ...]}
    """
    if not all_cids:
        return {}

    unique_cids = list(set(all_cids))
    events_by_cid = EventFetcher.fetch_events(unique_cids, "upstream_history")
    result = _normalize_upstream_event_records(events_by_cid)

    logger.info(
        f"Upstream history: {len(result)} lots with classified records, "
        f"from {len(unique_cids)} queried CIDs"
    )
    return dict(result)


# ============================================================
# Query 4: Downstream Reject Records (Forward)
# ============================================================

def _fetch_downstream_rejects(
    tracked_cids: List[str],
) -> Dict[str, List[Dict[str, Any]]]:
    """Fetch downstream reject records for tracked CONTAINERIDs.

    Returns:
        {containerid: [{'workcenter_group': ..., 'lossreasonname': ..., ...}]}
    """
    if not tracked_cids:
        return {}

    unique_cids = list(set(tracked_cids))
    events_by_cid = EventFetcher.fetch_events(unique_cids, "downstream_rejects")

    result: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for cid, events in events_by_cid.items():
        cid_value = _safe_str(cid)
        if not cid_value:
            continue
        for event in events:
            group_name = _safe_str(event.get('WORKCENTER_GROUP'))
            if not group_name:
                continue
            result[cid_value].append({
                'workcenter_group': group_name,
                'lossreasonname': _safe_str(event.get('LOSSREASONNAME')),
                'equipment_name': _safe_str(event.get('EQUIPMENTNAME')),
                'reject_total_qty': _safe_int(event.get('REJECT_TOTAL_QTY')),
                'txndate': _safe_str(event.get('TXNDATE')),
            })

    logger.info(
        "Downstream rejects: %d lots with records, from %d queried CIDs",
        len(result), len(unique_cids),
    )
    return dict(result)


def _normalize_lineage_ancestors(
    lineage_ancestors: Optional[Dict[str, Any]],
    *,
    seed_container_ids: Optional[List[str]] = None,
    fallback_seed_ids: Optional[List[str]] = None,
) -> Dict[str, Set[str]]:
    """Normalize lineage payload to {seed_cid: set(ancestor_cid)}."""
    ancestors: Dict[str, Set[str]] = {}

    if isinstance(lineage_ancestors, dict):
        for seed, raw_values in lineage_ancestors.items():
            seed_cid = _safe_str(seed)
            if not seed_cid:
                continue

            values = raw_values if isinstance(raw_values, (list, tuple, set)) else []
            normalized_values: Set[str] = set()
            for value in values:
                ancestor_cid = _safe_str(value)
                if ancestor_cid and ancestor_cid != seed_cid:
                    normalized_values.add(ancestor_cid)
            ancestors[seed_cid] = normalized_values

    candidate_seeds = []
    for seed in (seed_container_ids or []):
        seed_cid = _safe_str(seed)
        if seed_cid:
            candidate_seeds.append(seed_cid)
    if not candidate_seeds:
        for seed in (fallback_seed_ids or []):
            seed_cid = _safe_str(seed)
            if seed_cid:
                candidate_seeds.append(seed_cid)

    for seed_cid in candidate_seeds:
        ancestors.setdefault(seed_cid, set())

    return ancestors


def _normalize_upstream_event_records(
    events_by_cid: Dict[str, List[Dict[str, Any]]],
) -> Dict[str, List[Dict[str, Any]]]:
    """Normalize EventFetcher upstream payload into attribution-ready records."""
    result: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for cid, events in events_by_cid.items():
        cid_value = _safe_str(cid)
        if not cid_value:
            continue
        for event in events:
            group_name = _safe_str(event.get('WORKCENTER_GROUP'))
            if not group_name:
                group_name = '(未知)'
            result[cid_value].append({
                'workcenter_group': group_name,
                'equipment_id': _safe_str(event.get('EQUIPMENTID')),
                'equipment_name': _safe_str(event.get('EQUIPMENTNAME')),
                'spec_name': _safe_str(event.get('SPECNAME')),
                'track_in_time': _safe_str(event.get('TRACKINTIMESTAMP')),
                'trackinqty': _safe_int(event.get('TRACKINQTY')),
            })
    return dict(result)


def _normalize_downstream_event_records(
    events_by_cid: Dict[str, List[Dict[str, Any]]],
) -> Dict[str, List[Dict[str, Any]]]:
    """Normalize EventFetcher downstream_rejects payload into forward-pipeline-ready records."""
    result: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for cid, events in events_by_cid.items():
        cid_value = _safe_str(cid)
        if not cid_value:
            continue
        for event in events:
            group_name = _safe_str(event.get('WORKCENTER_GROUP'))
            if not group_name:
                continue
            result[cid_value].append({
                'workcenter_group': group_name,
                'lossreasonname': _safe_str(event.get('LOSSREASONNAME')),
                'equipment_name': _safe_str(event.get('EQUIPMENTNAME')),
                'reject_total_qty': _safe_int(event.get('REJECT_TOTAL_QTY')),
                'txndate': _safe_str(event.get('TXNDATE')),
            })
    return dict(result)


# ============================================================
# Detection Data Lookup
# ============================================================

def _build_detection_lookup(
    df: pd.DataFrame,
) -> Dict[str, Dict[str, Any]]:
    """Build lookup dict from detection DataFrame.

    Returns:
        {containerid: {
            'trackinqty': int,
            'rejectqty_by_reason': {reason: qty},
            'containername': str,
            'workflow': str,
            'productlinename': str,
            'pj_type': str,
            'detection_equipmentname': str,
            'trackintimestamp': str,
        }}
    """
    if df.empty:
        return {}

    lookup: Dict[str, Dict[str, Any]] = {}
    for _, row in df.iterrows():
        cid = row['CONTAINERID']
        if cid not in lookup:
            lookup[cid] = {
                'trackinqty': _safe_int(row.get('TRACKINQTY')),
                'rejectqty_by_reason': {},
                'containername': _safe_str(row.get('CONTAINERNAME')),
                'workflow': _safe_str(row.get('WORKFLOW')),
                'productlinename': _safe_str(row.get('PRODUCTLINENAME')),
                'pj_type': _safe_str(row.get('PJ_TYPE')),
                'detection_equipmentname': _safe_str(row.get('DETECTION_EQUIPMENTNAME')),
                'trackintimestamp': _safe_str(row.get('TRACKINTIMESTAMP')),
            }

        reason = row.get('LOSSREASONNAME')
        qty = _safe_int(row.get('REJECTQTY'))
        if reason and qty > 0:
            lookup[cid]['rejectqty_by_reason'][reason] = (
                lookup[cid]['rejectqty_by_reason'].get(reason, 0) + qty
            )

    return lookup


# ============================================================
# Backward Defect Attribution Engine
# ============================================================

def _attribute_defects(
    detection_data: Dict[str, Dict[str, Any]],
    ancestors: Dict[str, Set[str]],
    upstream_by_cid: Dict[str, List[Dict[str, Any]]],
    loss_reasons: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Attribute detection station defects to upstream machines.

    For each upstream machine M at station S:
      - Find all detection lots whose ancestors (or self) used M
      - attributed_rejectqty = SUM(selected REJECTQTY)
      - attributed_trackinqty = SUM(TRACKINQTY)
      - rate = attributed_rejectqty / attributed_trackinqty × 100

    Returns:
        List of attribution records, one per (workcenter_group, equipment_name).
    """
    machine_to_detection: Dict[Tuple[str, str, str], Set[str]] = defaultdict(set)

    for det_cid, data in detection_data.items():
        ancestor_set = ancestors.get(det_cid, set())
        all_cids = ancestor_set | {det_cid}

        for anc_cid in all_cids:
            for record in upstream_by_cid.get(anc_cid, []):
                machine_key = (
                    record['workcenter_group'],
                    record['equipment_name'],
                    record['equipment_id'],
                )
                machine_to_detection[machine_key].add(det_cid)

    # Look up equipment model (RESOURCEFAMILYNAME) from resource cache
    all_eq_ids = list({eq_id for _, _, eq_id in machine_to_detection.keys() if eq_id})
    eq_family_map: Dict[str, str] = {}
    if all_eq_ids:
        from mes_dashboard.services.resource_cache import get_resources_by_ids
        resources = get_resources_by_ids(all_eq_ids)
        for r in resources:
            rid = str(r.get('RESOURCEID', ''))
            family = r.get('RESOURCEFAMILYNAME') or ''
            if rid and family:
                eq_family_map[rid] = family

    attribution = []
    for machine_key, det_lot_set in machine_to_detection.items():
        wc_group, eq_name, eq_id = machine_key

        total_trackinqty = sum(
            detection_data[cid]['trackinqty'] for cid in det_lot_set
            if cid in detection_data
        )

        total_rejectqty = 0
        for cid in det_lot_set:
            if cid not in detection_data:
                continue
            by_reason = detection_data[cid]['rejectqty_by_reason']
            if loss_reasons:
                for reason in loss_reasons:
                    total_rejectqty += by_reason.get(reason, 0)
            else:
                total_rejectqty += sum(by_reason.values())

        rate = round(total_rejectqty / total_trackinqty * 100, 4) if total_trackinqty else 0.0

        workflows = set()
        packages = set()
        pj_types = set()
        detection_machines = set()
        for cid in det_lot_set:
            if cid not in detection_data:
                continue
            d = detection_data[cid]
            if d['workflow']:
                workflows.add(d['workflow'])
            if d['productlinename']:
                packages.add(d['productlinename'])
            if d['pj_type']:
                pj_types.add(d['pj_type'])
            if d['detection_equipmentname']:
                detection_machines.add(d['detection_equipmentname'])

        attribution.append({
            'WORKCENTER_GROUP': wc_group,
            'EQUIPMENT_NAME': eq_name,
            'EQUIPMENT_ID': eq_id,
            'RESOURCEFAMILYNAME': eq_family_map.get(eq_id, '(未知)'),
            'DETECTION_LOT_COUNT': len(det_lot_set),
            'INPUT_QTY': total_trackinqty,
            'DEFECT_QTY': total_rejectqty,
            'DEFECT_RATE': rate,
            'WORKFLOW': ', '.join(sorted(workflows)) if workflows else '(未知)',
            'PRODUCTLINENAME': ', '.join(sorted(packages)) if packages else '(未知)',
            'PJ_TYPE': ', '.join(sorted(pj_types)) if pj_types else '(未知)',
            'DETECTION_EQUIPMENTNAME': ', '.join(sorted(detection_machines)) if detection_machines else '(未知)',
        })

    attribution.sort(key=lambda x: x['DEFECT_RATE'], reverse=True)
    return attribution


# ============================================================
# Forward Defect Attribution Engine
# ============================================================

def _attribute_forward_defects(
    detection_data: Dict[str, Dict[str, Any]],
    defect_cids: List[str],
    wip_by_cid: Dict[str, List[Dict[str, Any]]],
    downstream_rejects: Dict[str, List[Dict[str, Any]]],
    station_order: int,
) -> Dict[str, Dict[str, Any]]:
    """Attribute forward: for each downstream station, compute reject rate.

    Only stations with order > detection station_order are included.

    Returns:
        {workcenter_group: {
            'lots_reached': int, 'total_input': int, 'total_reject': int,
            'reject_rate': float,
            'machines': {eq_name: {'input': int, 'reject': int}},
            'loss_reasons': {reason: qty},
        }}
    """
    station_agg: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
        'lots_reached': set(),
        'total_input': 0,
        'total_reject': 0,
        'machines': defaultdict(lambda: {'input': 0, 'reject': 0}),
        'loss_reasons': defaultdict(int),
    })

    # Aggregate WIP records at downstream stations
    for cid in wip_by_cid:
        for record in wip_by_cid[cid]:
            wc_group = record.get('workcenter_group', '')
            if not wc_group:
                continue
            group_order = get_group_order(wc_group)
            if group_order <= station_order:
                continue
            eq_name = record.get('equipment_name', '(NA)')
            trackinqty = record.get('trackinqty', 0)

            agg = station_agg[wc_group]
            agg['lots_reached'].add(cid)
            agg['total_input'] += trackinqty
            agg['machines'][eq_name]['input'] += trackinqty

    # Aggregate reject records at downstream stations
    for cid in downstream_rejects:
        for record in downstream_rejects[cid]:
            wc_group = record.get('workcenter_group', '')
            if not wc_group:
                continue
            group_order = get_group_order(wc_group)
            if group_order <= station_order:
                continue
            eq_name = record.get('equipment_name', '(NA)')
            reject_qty = record.get('reject_total_qty', 0)
            reason = record.get('lossreasonname', '(未填寫)')

            agg = station_agg[wc_group]
            agg['total_reject'] += reject_qty
            agg['machines'][eq_name]['reject'] += reject_qty
            agg['loss_reasons'][reason] += reject_qty

    # Finalize
    result = {}
    for wc_group, agg in station_agg.items():
        total_input = agg['total_input']
        total_reject = agg['total_reject']
        reject_rate = round(total_reject / total_input * 100, 4) if total_input else 0.0
        result[wc_group] = {
            'lots_reached': len(agg['lots_reached']),
            'total_input': total_input,
            'total_reject': total_reject,
            'reject_rate': reject_rate,
            'machines': dict(agg['machines']),
            'loss_reasons': dict(agg['loss_reasons']),
        }

    return result


# ============================================================
# KPI Builders
# ============================================================

def _build_kpi(
    df: pd.DataFrame,
    attribution: List[Dict[str, Any]],
    loss_reasons: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Build backward KPI summary."""
    if df.empty:
        return {
            'total_input': 0, 'lot_count': 0,
            'total_defect_qty': 0, 'total_defect_rate': 0.0,
            'top_loss_reason': '', 'affected_machine_count': 0,
        }

    unique_lots = df.drop_duplicates(subset=['CONTAINERID'])
    total_input = int(unique_lots['TRACKINQTY'].sum())
    lot_count = len(unique_lots)

    defect_rows = df[df['REJECTQTY'] > 0]
    if loss_reasons:
        defect_rows = defect_rows[defect_rows['LOSSREASONNAME'].isin(loss_reasons)]

    total_defect_qty = int(defect_rows['REJECTQTY'].sum()) if not defect_rows.empty else 0
    total_defect_rate = round(
        total_defect_qty / total_input * 100, 4
    ) if total_input else 0.0

    top_reason = ''
    if not defect_rows.empty:
        reason_sums = defect_rows.groupby('LOSSREASONNAME')['REJECTQTY'].sum()
        if not reason_sums.empty:
            top_reason = _safe_str(reason_sums.idxmax())

    affected_machines = sum(1 for a in attribution if a['DEFECT_QTY'] > 0)

    return {
        'total_input': total_input,
        'lot_count': lot_count,
        'total_defect_qty': total_defect_qty,
        'total_defect_rate': total_defect_rate,
        'top_loss_reason': top_reason,
        'affected_machine_count': affected_machines,
    }


def _build_forward_kpi(
    detection_data: Dict[str, Dict[str, Any]],
    forward_attr: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """Build forward KPI summary."""
    detection_lot_count = len(detection_data)
    detection_defect_qty = sum(
        sum(d['rejectqty_by_reason'].values()) for d in detection_data.values()
    )

    tracked_lot_count = detection_lot_count
    downstream_stations_reached = len(forward_attr)
    downstream_total_reject = sum(a['total_reject'] for a in forward_attr.values())
    downstream_total_input = sum(a['total_input'] for a in forward_attr.values())
    downstream_reject_rate = (
        round(downstream_total_reject / downstream_total_input * 100, 4)
        if downstream_total_input else 0.0
    )

    return {
        'detection_lot_count': detection_lot_count,
        'detection_defect_qty': detection_defect_qty,
        'tracked_lot_count': tracked_lot_count,
        'downstream_stations_reached': downstream_stations_reached,
        'downstream_total_reject': downstream_total_reject,
        'downstream_reject_rate': downstream_reject_rate,
    }


# ============================================================
# Chart Builders
# ============================================================

def _build_chart_data(
    records: List[Dict[str, Any]],
    dimension: str,
) -> List[Dict[str, Any]]:
    """Build Top N + Other Pareto chart data for a given dimension."""
    if not records:
        return []

    dim_agg: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {'input_qty': 0, 'defect_qty': 0, 'lot_count': 0}
    )
    for rec in records:
        key = rec.get(dimension, '(未知)') or '(未知)'
        if ',' in key:
            keys = [k.strip() for k in key.split(',')]
        else:
            keys = [key]
        for k in keys:
            dim_agg[k]['input_qty'] += rec['INPUT_QTY']
            dim_agg[k]['defect_qty'] += rec['DEFECT_QTY']
            dim_agg[k]['lot_count'] += rec['DETECTION_LOT_COUNT']

    sorted_items = sorted(dim_agg.items(), key=lambda x: x[1]['defect_qty'], reverse=True)

    items = []
    other = {'input_qty': 0, 'defect_qty': 0, 'lot_count': 0}
    for i, (name, data) in enumerate(sorted_items):
        if i < TOP_N:
            rate = round(data['defect_qty'] / data['input_qty'] * 100, 4) if data['input_qty'] else 0.0
            items.append({
                'name': name,
                'input_qty': data['input_qty'],
                'defect_qty': data['defect_qty'],
                'defect_rate': rate,
                'lot_count': data['lot_count'],
            })
        else:
            other['input_qty'] += data['input_qty']
            other['defect_qty'] += data['defect_qty']
            other['lot_count'] += data['lot_count']

    if other['defect_qty'] > 0 or other['input_qty'] > 0:
        rate = round(other['defect_qty'] / other['input_qty'] * 100, 4) if other['input_qty'] else 0.0
        items.append({
            'name': '其他',
            'input_qty': other['input_qty'],
            'defect_qty': other['defect_qty'],
            'defect_rate': rate,
            'lot_count': other['lot_count'],
        })

    total_defects = sum(item['defect_qty'] for item in items)
    cumsum = 0
    for item in items:
        cumsum += item['defect_qty']
        item['cumulative_pct'] = round(cumsum / total_defects * 100, 2) if total_defects else 0.0

    return items


def _build_loss_reason_chart(
    df: pd.DataFrame,
    loss_reasons: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Build loss reason distribution chart from detection data (not attribution)."""
    if df.empty:
        return []

    defect_rows = df[df['REJECTQTY'] > 0].copy()
    if loss_reasons:
        defect_rows = defect_rows[defect_rows['LOSSREASONNAME'].isin(loss_reasons)]

    if defect_rows.empty:
        return []

    reason_agg = defect_rows.groupby('LOSSREASONNAME')['REJECTQTY'].sum()
    reason_agg = reason_agg.sort_values(ascending=False)

    unique_lots = df.drop_duplicates(subset=['CONTAINERID'])
    total_input = int(unique_lots['TRACKINQTY'].sum())

    items = []
    total_defects = int(reason_agg.sum())
    cumsum = 0
    for reason, qty in reason_agg.items():
        qty_int = int(qty)
        cumsum += qty_int
        rate = round(qty_int / total_input * 100, 4) if total_input else 0.0
        items.append({
            'name': _safe_str(reason),
            'defect_qty': qty_int,
            'defect_rate': rate,
            'cumulative_pct': round(cumsum / total_defects * 100, 2) if total_defects else 0.0,
        })

    return items


def _build_all_charts(
    attribution: List[Dict[str, Any]],
    detection_data: Dict[str, Dict[str, Any]],
) -> Dict[str, List[Dict]]:
    """Build chart data for all backward dimensions."""
    charts = {}
    for key, dim_col in DIMENSION_MAP.items():
        charts[key] = _build_chart_data(attribution, dim_col)

    loss_rows = []
    for cid, data in detection_data.items():
        trackinqty = data['trackinqty']
        if data['rejectqty_by_reason']:
            for reason, qty in data['rejectqty_by_reason'].items():
                loss_rows.append({
                    'CONTAINERID': cid,
                    'TRACKINQTY': trackinqty,
                    'LOSSREASONNAME': reason,
                    'REJECTQTY': qty,
                })
        else:
            loss_rows.append({
                'CONTAINERID': cid,
                'TRACKINQTY': trackinqty,
                'LOSSREASONNAME': None,
                'REJECTQTY': 0,
            })
    if loss_rows:
        loss_df = pd.DataFrame(loss_rows)
        charts['by_loss_reason'] = _build_loss_reason_chart(loss_df)
    else:
        charts['by_loss_reason'] = []

    return charts


def _build_forward_charts(
    forward_attr: Dict[str, Dict[str, Any]],
    detection_data: Dict[str, Dict[str, Any]],
) -> Dict[str, List[Dict]]:
    """Build chart data for forward direction."""
    charts = {}

    # by_downstream_station
    station_items = []
    for wc_group, agg in forward_attr.items():
        station_items.append({
            'name': wc_group,
            'input_qty': agg['total_input'],
            'defect_qty': agg['total_reject'],
            'defect_rate': agg['reject_rate'],
            'lot_count': agg['lots_reached'],
        })
    station_items.sort(key=lambda x: x['defect_qty'], reverse=True)
    total_defects = sum(s['defect_qty'] for s in station_items)
    cumsum = 0
    for item in station_items:
        cumsum += item['defect_qty']
        item['cumulative_pct'] = round(cumsum / total_defects * 100, 2) if total_defects else 0.0
    charts['by_downstream_station'] = station_items

    # by_downstream_machine
    machine_agg: Dict[str, Dict[str, int]] = defaultdict(
        lambda: {'input': 0, 'reject': 0},
    )
    for wc_group, agg in forward_attr.items():
        for eq_name, m_data in agg['machines'].items():
            machine_agg[eq_name]['input'] += m_data['input']
            machine_agg[eq_name]['reject'] += m_data['reject']

    machine_items = []
    for eq_name, data in sorted(machine_agg.items(), key=lambda x: x[1]['reject'], reverse=True):
        rate = round(data['reject'] / data['input'] * 100, 4) if data['input'] else 0.0
        machine_items.append({
            'name': eq_name,
            'input_qty': data['input'],
            'defect_qty': data['reject'],
            'defect_rate': rate,
        })
    if len(machine_items) > TOP_N:
        top = machine_items[:TOP_N]
        other_input = sum(m['input_qty'] for m in machine_items[TOP_N:])
        other_reject = sum(m['defect_qty'] for m in machine_items[TOP_N:])
        rate = round(other_reject / other_input * 100, 4) if other_input else 0.0
        top.append({'name': '其他', 'input_qty': other_input, 'defect_qty': other_reject, 'defect_rate': rate})
        machine_items = top
    total_defects = sum(m['defect_qty'] for m in machine_items)
    cumsum = 0
    for item in machine_items:
        cumsum += item['defect_qty']
        item['cumulative_pct'] = round(cumsum / total_defects * 100, 2) if total_defects else 0.0
    charts['by_downstream_machine'] = machine_items

    # by_downstream_loss_reason
    reason_agg: Dict[str, int] = defaultdict(int)
    for wc_group, agg in forward_attr.items():
        for reason, qty in agg['loss_reasons'].items():
            reason_agg[reason] += qty
    reason_items = []
    for reason, qty in sorted(reason_agg.items(), key=lambda x: x[1], reverse=True):
        reason_items.append({'name': reason, 'defect_qty': qty})
    if len(reason_items) > TOP_N:
        top = reason_items[:TOP_N]
        other_qty = sum(r['defect_qty'] for r in reason_items[TOP_N:])
        top.append({'name': '其他', 'defect_qty': other_qty})
        reason_items = top
    total_defects = sum(r['defect_qty'] for r in reason_items)
    cumsum = 0
    for item in reason_items:
        cumsum += item['defect_qty']
        item['cumulative_pct'] = round(cumsum / total_defects * 100, 2) if total_defects else 0.0
    charts['by_downstream_loss_reason'] = reason_items

    # by_detection_machine
    det_machine_agg: Dict[str, Dict[str, int]] = defaultdict(
        lambda: {'input_qty': 0, 'defect_qty': 0, 'lot_count': 0},
    )
    for cid, data in detection_data.items():
        eq = data['detection_equipmentname'] or '(未知)'
        det_machine_agg[eq]['input_qty'] += data['trackinqty']
        det_machine_agg[eq]['defect_qty'] += sum(data['rejectqty_by_reason'].values())
        det_machine_agg[eq]['lot_count'] += 1
    det_items = []
    for eq, data in sorted(det_machine_agg.items(), key=lambda x: x[1]['defect_qty'], reverse=True):
        rate = round(data['defect_qty'] / data['input_qty'] * 100, 4) if data['input_qty'] else 0.0
        det_items.append({
            'name': eq, 'input_qty': data['input_qty'], 'defect_qty': data['defect_qty'],
            'defect_rate': rate, 'lot_count': data['lot_count'],
        })
    if len(det_items) > TOP_N:
        top = det_items[:TOP_N]
        other_input = sum(d['input_qty'] for d in det_items[TOP_N:])
        other_defect = sum(d['defect_qty'] for d in det_items[TOP_N:])
        other_lots = sum(d['lot_count'] for d in det_items[TOP_N:])
        rate = round(other_defect / other_input * 100, 4) if other_input else 0.0
        top.append({'name': '其他', 'input_qty': other_input, 'defect_qty': other_defect, 'defect_rate': rate, 'lot_count': other_lots})
        det_items = top
    total_defects = sum(d['defect_qty'] for d in det_items)
    cumsum = 0
    for item in det_items:
        cumsum += item['defect_qty']
        item['cumulative_pct'] = round(cumsum / total_defects * 100, 2) if total_defects else 0.0
    charts['by_detection_machine'] = det_items

    return charts


# ============================================================
# Daily Trend
# ============================================================

def _build_daily_trend(
    df: pd.DataFrame,
    loss_reasons: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Build daily defect rate trend data."""
    if df.empty:
        return []

    work_df = df.copy()
    work_df['DATE'] = pd.to_datetime(work_df['TRACKINTIMESTAMP']).dt.strftime('%Y-%m-%d')

    daily_input = (
        work_df.drop_duplicates(subset=['CONTAINERID', 'DATE'])
        .groupby('DATE')['TRACKINQTY']
        .sum()
    )

    defect_rows = work_df[work_df['REJECTQTY'] > 0]
    if loss_reasons:
        defect_rows = defect_rows[defect_rows['LOSSREASONNAME'].isin(loss_reasons)]

    daily_defects = (
        defect_rows.groupby('DATE')['REJECTQTY'].sum()
        if not defect_rows.empty
        else pd.Series(dtype=float)
    )

    combined = pd.DataFrame({
        'input_qty': daily_input,
        'defect_qty': daily_defects,
    }).fillna(0).astype({'defect_qty': int, 'input_qty': int})

    combined['defect_rate'] = (
        combined['defect_qty'] / combined['input_qty'] * 100
    ).round(4).where(combined['input_qty'] > 0, 0.0)

    combined = combined.sort_index()

    result = []
    for date, row in combined.iterrows():
        result.append({
            'date': str(date),
            'input_qty': _safe_int(row['input_qty']),
            'defect_qty': _safe_int(row['defect_qty']),
            'defect_rate': _safe_float(row['defect_rate']),
        })

    return result


# ============================================================
# Detail Tables
# ============================================================

def _build_detail_table(
    df: pd.DataFrame,
    ancestors: Dict[str, Set[str]],
    upstream_by_cid: Dict[str, List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    """Build LOT-level detail table with upstream machine info (backward)."""
    if df.empty:
        return []

    lot_cols = [
        'CONTAINERID', 'CONTAINERNAME', 'PJ_TYPE', 'PRODUCTLINENAME',
        'WORKFLOW', 'FINISHEDRUNCARD', 'DETECTION_EQUIPMENTNAME', 'TRACKINQTY',
    ]
    lots = df.drop_duplicates(subset=['CONTAINERID'])[
        [c for c in lot_cols if c in df.columns]
    ].copy()

    defect_rows = df[df['REJECTQTY'] > 0]
    lot_defects: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for _, row in defect_rows.iterrows():
        cid = row['CONTAINERID']
        reason = _safe_str(row.get('LOSSREASONNAME'))
        qty = _safe_int(row.get('REJECTQTY'))
        if reason and qty > 0:
            lot_defects[cid][reason] += qty

    result = []
    for _, row in lots.iterrows():
        cid = row['CONTAINERID']
        input_qty = _safe_int(row.get('TRACKINQTY'))
        ancestor_set = ancestors.get(cid, set())
        all_cids = ancestor_set | {cid}

        upstream_machines = set()
        for anc_cid in all_cids:
            for rec in upstream_by_cid.get(anc_cid, []):
                upstream_machines.add(f"{rec['workcenter_group']}/{rec['equipment_name']}")

        reasons = lot_defects.get(cid, {})
        if reasons:
            for reason, qty in sorted(reasons.items()):
                rate = round(qty / input_qty * 100, 4) if input_qty else 0.0
                result.append({
                    'CONTAINERNAME': _safe_str(row.get('CONTAINERNAME')),
                    'PJ_TYPE': _safe_str(row.get('PJ_TYPE')),
                    'PRODUCTLINENAME': _safe_str(row.get('PRODUCTLINENAME')),
                    'WORKFLOW': _safe_str(row.get('WORKFLOW')),
                    'FINISHEDRUNCARD': _safe_str(row.get('FINISHEDRUNCARD')),
                    'DETECTION_EQUIPMENTNAME': _safe_str(row.get('DETECTION_EQUIPMENTNAME')),
                    'INPUT_QTY': input_qty,
                    'LOSS_REASON': reason,
                    'DEFECT_QTY': qty,
                    'DEFECT_RATE': rate,
                    'ANCESTOR_COUNT': len(ancestor_set),
                    'UPSTREAM_MACHINES': ', '.join(sorted(upstream_machines)),
                })
        else:
            result.append({
                'CONTAINERNAME': _safe_str(row.get('CONTAINERNAME')),
                'PJ_TYPE': _safe_str(row.get('PJ_TYPE')),
                'PRODUCTLINENAME': _safe_str(row.get('PRODUCTLINENAME')),
                'WORKFLOW': _safe_str(row.get('WORKFLOW')),
                'FINISHEDRUNCARD': _safe_str(row.get('FINISHEDRUNCARD')),
                'DETECTION_EQUIPMENTNAME': _safe_str(row.get('DETECTION_EQUIPMENTNAME')),
                'INPUT_QTY': input_qty,
                'LOSS_REASON': '',
                'DEFECT_QTY': 0,
                'DEFECT_RATE': 0.0,
                'ANCESTOR_COUNT': len(ancestor_set),
                'UPSTREAM_MACHINES': ', '.join(sorted(upstream_machines)),
            })

    return result


def _build_forward_detail_table(
    df: pd.DataFrame,
    defect_cids: List[str],
    wip_by_cid: Dict[str, List[Dict[str, Any]]],
    downstream_rejects: Dict[str, List[Dict[str, Any]]],
    station_order: int,
) -> List[Dict[str, Any]]:
    """Build LOT-level detail table for forward tracing."""
    if df.empty:
        return []

    lot_cols = [
        'CONTAINERID', 'CONTAINERNAME', 'PJ_TYPE', 'PRODUCTLINENAME',
        'WORKFLOW', 'DETECTION_EQUIPMENTNAME', 'TRACKINQTY',
    ]
    lots = df[df['CONTAINERID'].isin(defect_cids)].drop_duplicates(subset=['CONTAINERID'])[
        [c for c in lot_cols if c in df.columns]
    ].copy()

    # Aggregate defects per LOT at detection station
    defect_rows = df[(df['REJECTQTY'] > 0) & (df['CONTAINERID'].isin(defect_cids))]
    lot_defect_qty: Dict[str, int] = defaultdict(int)
    for _, row in defect_rows.iterrows():
        cid = row['CONTAINERID']
        lot_defect_qty[cid] += _safe_int(row.get('REJECTQTY'))

    result = []
    for _, row in lots.iterrows():
        cid = row['CONTAINERID']
        input_qty = _safe_int(row.get('TRACKINQTY'))
        det_defect = lot_defect_qty.get(cid, 0)

        ds_stations = set()
        ds_total_reject = 0
        ds_station_reject: Dict[str, int] = defaultdict(int)

        for record in wip_by_cid.get(cid, []):
            wc = record.get('workcenter_group', '')
            if wc and get_group_order(wc) > station_order:
                ds_stations.add(wc)

        for record in downstream_rejects.get(cid, []):
            wc = record.get('workcenter_group', '')
            if wc and get_group_order(wc) > station_order:
                qty = record.get('reject_total_qty', 0)
                ds_total_reject += qty
                ds_station_reject[wc] += qty
                ds_stations.add(wc)

        ds_rate = round(ds_total_reject / input_qty * 100, 4) if input_qty else 0.0

        worst = ''
        if ds_station_reject:
            worst = max(ds_station_reject, key=ds_station_reject.get)

        result.append({
            'CONTAINERNAME': _safe_str(row.get('CONTAINERNAME')),
            'PJ_TYPE': _safe_str(row.get('PJ_TYPE')),
            'PRODUCTLINENAME': _safe_str(row.get('PRODUCTLINENAME')),
            'WORKFLOW': _safe_str(row.get('WORKFLOW')),
            'DETECTION_EQUIPMENTNAME': _safe_str(row.get('DETECTION_EQUIPMENTNAME')),
            'INPUT_QTY': input_qty,
            'DEFECT_QTY': det_defect,
            'DOWNSTREAM_STATIONS': len(ds_stations),
            'DOWNSTREAM_REJECTS': ds_total_reject,
            'DOWNSTREAM_REJECT_RATE': ds_rate,
            'WORST_DOWNSTREAM': worst,
        })

    return result
