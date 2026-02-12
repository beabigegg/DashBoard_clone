# -*- coding: utf-8 -*-
"""Mid-Section Defect Traceability Analysis Service.

Reverse traceability from TMTT (test) station back to upstream production stations.
Traces LOT genealogy (splits + merges) to attribute TMTT defects to upstream machines.

Data Pipeline:
    Query 1:  TMTT Detection    → TMTT lots with ALL loss reasons
    Query 2a: Split Chain BFS   → CONTAINER.SPLITFROMID upward traversal
    Query 2b: Merge Expansion   → COMBINEDASSYLOTS reverse merge lookup
    Query 3:  Upstream History  → LOTWIPHISTORY for ALL ancestor CONTAINERIDs
    Python:   Resolve ancestors → Attribute defects → Aggregate

Attribution Method (Sum):
    For upstream machine M at station S:
      attributed_rejectqty = SUM(TMTT REJECTQTY for all linked TMTT lots)
      attributed_trackinqty = SUM(TMTT TRACKINQTY for all linked TMTT lots)
      rate = attributed_rejectqty / attributed_trackinqty × 100
"""

import csv
import hashlib
import io
import logging
import math
import time
from collections import defaultdict
from datetime import datetime
from typing import Optional, Dict, List, Any, Set, Tuple, Generator

import pandas as pd

from mes_dashboard.core.database import read_sql_df
from mes_dashboard.core.cache import cache_get, cache_set, make_cache_key
from mes_dashboard.core.redis_client import try_acquire_lock, release_lock
from mes_dashboard.sql import SQLLoader
from mes_dashboard.services.event_fetcher import EventFetcher
from mes_dashboard.services.lineage_engine import LineageEngine

logger = logging.getLogger('mes_dashboard.mid_section_defect')

# Constants
MAX_QUERY_DAYS = 180
CACHE_TTL_TMTT = 300            # 5 min for TMTT detection data
CACHE_TTL_LOSS_REASONS = 86400  # 24h for loss reason list (daily sync)

# Distributed lock settings for query_analysis cold-cache path
ANALYSIS_LOCK_TTL_SECONDS = 120
ANALYSIS_LOCK_WAIT_TIMEOUT_SECONDS = 90
ANALYSIS_LOCK_POLL_INTERVAL_SECONDS = 0.5

# Top N for chart display (rest grouped as "其他")
TOP_N = 10

# Dimension column mapping for attribution charts
DIMENSION_MAP = {
    'by_station': 'WORKCENTER_GROUP',
    'by_machine': 'EQUIPMENT_NAME',
    'by_workflow': 'WORKFLOW',
    'by_package': 'PRODUCTLINENAME',
    'by_pj_type': 'PJ_TYPE',
    'by_tmtt_machine': 'TMTT_EQUIPMENTNAME',
}

# CSV export column config
CSV_COLUMNS = [
    ('CONTAINERNAME', 'LOT ID'),
    ('PJ_TYPE', 'TYPE'),
    ('PRODUCTLINENAME', 'PACKAGE'),
    ('WORKFLOW', 'WORKFLOW'),
    ('FINISHEDRUNCARD', '完工流水碼'),
    ('TMTT_EQUIPMENTNAME', 'TMTT設備'),
    ('INPUT_QTY', '投入數'),
    ('LOSS_REASON', '不良原因'),
    ('DEFECT_QTY', '不良數'),
    ('DEFECT_RATE', '不良率(%)'),
    ('ANCESTOR_COUNT', '上游LOT數'),
    ('UPSTREAM_MACHINES', '上游機台'),
]


# ============================================================
# Public API
# ============================================================

def query_analysis(
    start_date: str,
    end_date: str,
    loss_reasons: Optional[List[str]] = None,
) -> Optional[Dict[str, Any]]:
    """Main entry point for mid-section defect traceability analysis.

    Args:
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        loss_reasons: Optional list of loss reasons to filter (None = all)

    Returns:
        Dict with kpi, charts, detail, available_loss_reasons, genealogy_status.
    """
    error = _validate_date_range(start_date, end_date)
    if error:
        return {'error': error}

    # Check full analysis cache
    cache_key = make_cache_key(
        "mid_section_defect",
        filters={
            'start_date': start_date,
            'end_date': end_date,
            'loss_reasons': sorted(loss_reasons) if loss_reasons else None,
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
        # Stage 1: TMTT detection data
        tmtt_df = _fetch_tmtt_data(start_date, end_date)
        if tmtt_df is None:
            return None
        if tmtt_df.empty:
            return _empty_result()

        # Extract available loss reasons before filtering
        available_loss_reasons = sorted(
            tmtt_df.loc[tmtt_df['REJECTQTY'] > 0, 'LOSSREASONNAME']
            .dropna().unique().tolist()
        )

        # Apply loss reason filter if specified
        if loss_reasons:
            filtered_df = tmtt_df[
                (tmtt_df['LOSSREASONNAME'].isin(loss_reasons))
                | (tmtt_df['REJECTQTY'] == 0)
                | (tmtt_df['LOSSREASONNAME'].isna())
            ].copy()
        else:
            filtered_df = tmtt_df

        # Stage 2: Genealogy resolution (split chain + merge expansion)
        tmtt_cids = tmtt_df['CONTAINERID'].unique().tolist()
        tmtt_names = {}
        for _, r in tmtt_df.drop_duplicates('CONTAINERID').iterrows():
            tmtt_names[r['CONTAINERID']] = _safe_str(r.get('CONTAINERNAME'))

        ancestors = {}
        genealogy_status = 'ready'

        if tmtt_cids:
            try:
                ancestors = _resolve_full_genealogy(tmtt_cids, tmtt_names)
            except Exception as exc:
                logger.error(f"Genealogy resolution failed: {exc}", exc_info=True)
                genealogy_status = 'error'

        # Stage 3: Upstream history for ALL CIDs (TMTT lots + ancestors)
        all_query_cids = set(tmtt_cids)
        for anc_set in ancestors.values():
            all_query_cids.update(anc_set)
        # Filter out any non-string values (NaN/None from pandas)
        all_query_cids = {c for c in all_query_cids if isinstance(c, str) and c}

        upstream_by_cid = {}
        if all_query_cids:
            try:
                upstream_by_cid = _fetch_upstream_history(list(all_query_cids))
            except Exception as exc:
                logger.error(f"Upstream history query failed: {exc}", exc_info=True)
                genealogy_status = 'error'
        tmtt_data = _build_tmtt_lookup(filtered_df)
        attribution = _attribute_defects(
            tmtt_data, ancestors, upstream_by_cid, loss_reasons,
        )

        result = {
            'kpi': _build_kpi(filtered_df, attribution, loss_reasons),
            'available_loss_reasons': available_loss_reasons,
            'charts': _build_all_charts(attribution, tmtt_data),
            'daily_trend': _build_daily_trend(filtered_df, loss_reasons),
            'detail': _build_detail_table(filtered_df, ancestors, upstream_by_cid),
            'genealogy_status': genealogy_status,
        }

        # Only cache successful results (don't cache upstream errors)
        if genealogy_status == 'ready':
            cache_set(cache_key, result, ttl=CACHE_TTL_TMTT)
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
) -> Optional[Dict[str, Any]]:
    """Resolve seed lots for staged mid-section trace API."""
    error = _validate_date_range(start_date, end_date)
    if error:
        return {'error': error}

    tmtt_df = _fetch_tmtt_data(start_date, end_date)
    if tmtt_df is None:
        return None
    if tmtt_df.empty:
        return {'seeds': [], 'seed_count': 0}

    seeds = []
    unique_rows = tmtt_df.drop_duplicates(subset=['CONTAINERID'])
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
    start_date: str,
    end_date: str,
    *,
    loss_reasons: Optional[List[str]] = None,
    seed_container_ids: Optional[List[str]] = None,
    lineage_ancestors: Optional[Dict[str, Any]] = None,
    upstream_events_by_cid: Optional[Dict[str, List[Dict[str, Any]]]] = None,
) -> Optional[Dict[str, Any]]:
    """Build mid-section summary payload from staged events data."""
    error = _validate_date_range(start_date, end_date)
    if error:
        return {'error': error}

    normalized_loss_reasons = parse_loss_reasons_param(loss_reasons)

    tmtt_df = _fetch_tmtt_data(start_date, end_date)
    if tmtt_df is None:
        return None
    if tmtt_df.empty:
        empty_result = _empty_result()
        return {
            'kpi': empty_result['kpi'],
            'charts': empty_result['charts'],
            'daily_trend': empty_result['daily_trend'],
            'available_loss_reasons': empty_result['available_loss_reasons'],
            'genealogy_status': empty_result['genealogy_status'],
            'detail_total_count': 0,
        }

    available_loss_reasons = sorted(
        tmtt_df.loc[tmtt_df['REJECTQTY'] > 0, 'LOSSREASONNAME']
        .dropna().unique().tolist()
    )

    if normalized_loss_reasons:
        filtered_df = tmtt_df[
            (tmtt_df['LOSSREASONNAME'].isin(normalized_loss_reasons))
            | (tmtt_df['REJECTQTY'] == 0)
            | (tmtt_df['LOSSREASONNAME'].isna())
        ].copy()
    else:
        filtered_df = tmtt_df

    tmtt_data = _build_tmtt_lookup(filtered_df)
    normalized_ancestors = _normalize_lineage_ancestors(
        lineage_ancestors,
        seed_container_ids=seed_container_ids,
        fallback_seed_ids=list(tmtt_data.keys()),
    )
    normalized_upstream = _normalize_upstream_event_records(upstream_events_by_cid or {})

    attribution = _attribute_defects(
        tmtt_data,
        normalized_ancestors,
        normalized_upstream,
        normalized_loss_reasons,
    )
    detail = _build_detail_table(filtered_df, normalized_ancestors, normalized_upstream)

    seed_ids = [
        cid for cid in (seed_container_ids or list(tmtt_data.keys()))
        if isinstance(cid, str) and cid.strip()
    ]
    genealogy_status = 'ready'
    if seed_ids and lineage_ancestors is None:
        genealogy_status = 'error'

    return {
        'kpi': _build_kpi(filtered_df, attribution, normalized_loss_reasons),
        'charts': _build_all_charts(attribution, tmtt_data),
        'daily_trend': _build_daily_trend(filtered_df, normalized_loss_reasons),
        'available_loss_reasons': available_loss_reasons,
        'genealogy_status': genealogy_status,
        'detail_total_count': len(detail),
    }


def query_analysis_detail(
    start_date: str,
    end_date: str,
    loss_reasons: Optional[List[str]] = None,
    page: int = 1,
    page_size: int = 200,
) -> Optional[Dict[str, Any]]:
    """Return a paginated slice of the detail table from cached analysis.

    Calls query_analysis() which handles caching internally.
    Sorts detail by DEFECT_RATE descending (worst first) before paginating.
    """
    result = query_analysis(start_date, end_date, loss_reasons)
    if result is None:
        return None
    if 'error' in result:
        return result

    detail = result.get('detail', [])
    detail_sorted = sorted(
        detail, key=lambda r: r.get('DEFECT_RATE', 0), reverse=True,
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
    """Get all TMTT loss reasons (cached daily in Redis).

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
) -> Generator[str, None, None]:
    """Stream CSV export of detail data.

    Yields:
        CSV lines as strings.
    """
    result = query_analysis(start_date, end_date, loss_reasons)

    # BOM for Excel UTF-8 compatibility
    yield '\ufeff'

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([label for _, label in CSV_COLUMNS])
    yield output.getvalue()
    output.seek(0)
    output.truncate(0)

    if result is None or 'error' in result:
        return

    for row in result.get('detail', []):
        writer.writerow([row.get(col, '') for col, _ in CSV_COLUMNS])
        yield output.getvalue()
        output.seek(0)
        output.truncate(0)


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


def _empty_result() -> Dict[str, Any]:
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


# ============================================================
# Query 1: TMTT Detection Data
# ============================================================

def _fetch_tmtt_data(start_date: str, end_date: str) -> Optional[pd.DataFrame]:
    """Execute tmtt_detection.sql and return raw DataFrame."""
    cache_key = make_cache_key(
        "mid_section_tmtt",
        filters={'start_date': start_date, 'end_date': end_date},
    )
    cached = cache_get(cache_key)
    if cached is not None:
        # Cache stores list-of-dicts (JSON-serializable), reconstruct DataFrame
        if isinstance(cached, list):
            return pd.DataFrame(cached) if cached else pd.DataFrame()
        return None

    try:
        sql = SQLLoader.load("mid_section_defect/tmtt_detection")
        params = {'start_date': start_date, 'end_date': end_date}
        df = read_sql_df(sql, params)
        if df is None:
            logger.error("TMTT detection query returned None")
            return None
        logger.info(
            f"TMTT detection: {len(df)} rows, "
            f"{df['CONTAINERID'].nunique() if not df.empty else 0} unique lots"
        )
        # Cache as list-of-dicts for JSON serialization via Redis
        cache_set(cache_key, df.to_dict('records'), ttl=CACHE_TTL_TMTT)
        return df
    except Exception as exc:
        logger.error(f"TMTT detection query failed: {exc}", exc_info=True)
        return None


# ============================================================
# Query 2: LOT Genealogy
# ============================================================

def _resolve_full_genealogy(
    tmtt_cids: List[str],
    tmtt_names: Dict[str, str],
) -> Dict[str, Set[str]]:
    """Resolve full genealogy for TMTT lots via shared LineageEngine."""
    ancestors = LineageEngine.resolve_full_genealogy(tmtt_cids, tmtt_names)
    _log_genealogy_summary(ancestors, tmtt_cids, 0)
    return ancestors


def _log_genealogy_summary(
    ancestors: Dict[str, Set[str]],
    tmtt_cids: List[str],
    merge_count: int,
) -> None:
    total_ancestors = sum(len(v) for v in ancestors.values())
    lots_with_ancestors = sum(1 for v in ancestors.values() if v)
    logger.info(
        f"Genealogy resolved: {lots_with_ancestors}/{len(tmtt_cids)} lots have ancestors, "
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
            })
    return dict(result)


# ============================================================
# TMTT Data Lookup
# ============================================================

def _build_tmtt_lookup(
    df: pd.DataFrame,
) -> Dict[str, Dict[str, Any]]:
    """Build lookup dict from TMTT DataFrame.

    Returns:
        {containerid: {
            'trackinqty': int,
            'rejectqty_by_reason': {reason: qty},
            'containername': str,
            'workflow': str,
            'productlinename': str,
            'pj_type': str,
            'tmtt_equipmentname': str,
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
                'tmtt_equipmentname': _safe_str(row.get('TMTT_EQUIPMENTNAME')),
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
# Defect Attribution Engine
# ============================================================

def _attribute_defects(
    tmtt_data: Dict[str, Dict[str, Any]],
    ancestors: Dict[str, Set[str]],
    upstream_by_cid: Dict[str, List[Dict[str, Any]]],
    loss_reasons: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Attribute TMTT defects to upstream machines.

    For each upstream machine M at station S:
      - Find all TMTT lots whose ancestors (or self) used M
      - attributed_rejectqty = SUM(selected REJECTQTY)
      - attributed_trackinqty = SUM(TRACKINQTY)
      - rate = attributed_rejectqty / attributed_trackinqty × 100

    Returns:
        List of attribution records, one per (workcenter_group, equipment_name).
    """
    # machine_key → set of TMTT lot CIDs
    machine_to_tmtt: Dict[Tuple[str, str, str], Set[str]] = defaultdict(set)

    for tmtt_cid, data in tmtt_data.items():
        ancestor_set = ancestors.get(tmtt_cid, set())
        # Include the TMTT lot itself (it may have upstream history if no split)
        all_cids = ancestor_set | {tmtt_cid}

        for anc_cid in all_cids:
            for record in upstream_by_cid.get(anc_cid, []):
                machine_key = (
                    record['workcenter_group'],
                    record['equipment_name'],
                    record['equipment_id'],
                )
                machine_to_tmtt[machine_key].add(tmtt_cid)

    # Calculate attribution per machine
    attribution = []
    for machine_key, tmtt_lot_set in machine_to_tmtt.items():
        wc_group, eq_name, eq_id = machine_key

        total_trackinqty = sum(
            tmtt_data[cid]['trackinqty'] for cid in tmtt_lot_set
            if cid in tmtt_data
        )

        # Sum defects for selected loss reasons
        total_rejectqty = 0
        for cid in tmtt_lot_set:
            if cid not in tmtt_data:
                continue
            by_reason = tmtt_data[cid]['rejectqty_by_reason']
            if loss_reasons:
                for reason in loss_reasons:
                    total_rejectqty += by_reason.get(reason, 0)
            else:
                total_rejectqty += sum(by_reason.values())

        rate = round(total_rejectqty / total_trackinqty * 100, 4) if total_trackinqty else 0.0

        # Collect dimension metadata from linked TMTT lots
        workflows = set()
        packages = set()
        pj_types = set()
        tmtt_machines = set()
        for cid in tmtt_lot_set:
            if cid not in tmtt_data:
                continue
            d = tmtt_data[cid]
            if d['workflow']:
                workflows.add(d['workflow'])
            if d['productlinename']:
                packages.add(d['productlinename'])
            if d['pj_type']:
                pj_types.add(d['pj_type'])
            if d['tmtt_equipmentname']:
                tmtt_machines.add(d['tmtt_equipmentname'])

        attribution.append({
            'WORKCENTER_GROUP': wc_group,
            'EQUIPMENT_NAME': eq_name,
            'EQUIPMENT_ID': eq_id,
            'TMTT_LOT_COUNT': len(tmtt_lot_set),
            'INPUT_QTY': total_trackinqty,
            'DEFECT_QTY': total_rejectqty,
            'DEFECT_RATE': rate,
            # Flatten multi-valued dimensions for charting
            'WORKFLOW': ', '.join(sorted(workflows)) if workflows else '(未知)',
            'PRODUCTLINENAME': ', '.join(sorted(packages)) if packages else '(未知)',
            'PJ_TYPE': ', '.join(sorted(pj_types)) if pj_types else '(未知)',
            'TMTT_EQUIPMENTNAME': ', '.join(sorted(tmtt_machines)) if tmtt_machines else '(未知)',
        })

    # Sort by defect rate DESC
    attribution.sort(key=lambda x: x['DEFECT_RATE'], reverse=True)

    return attribution


# ============================================================
# KPI Builder
# ============================================================

def _build_kpi(
    df: pd.DataFrame,
    attribution: List[Dict[str, Any]],
    loss_reasons: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Build KPI summary."""
    if df.empty:
        return {
            'total_input': 0, 'lot_count': 0,
            'total_defect_qty': 0, 'total_defect_rate': 0.0,
            'top_loss_reason': '', 'affected_machine_count': 0,
        }

    # Deduplicate for INPUT
    unique_lots = df.drop_duplicates(subset=['CONTAINERID'])
    total_input = int(unique_lots['TRACKINQTY'].sum())
    lot_count = len(unique_lots)

    # Defect totals
    defect_rows = df[df['REJECTQTY'] > 0]
    if loss_reasons:
        defect_rows = defect_rows[defect_rows['LOSSREASONNAME'].isin(loss_reasons)]

    total_defect_qty = int(defect_rows['REJECTQTY'].sum()) if not defect_rows.empty else 0
    total_defect_rate = round(
        total_defect_qty / total_input * 100, 4
    ) if total_input else 0.0

    # Top loss reason
    top_reason = ''
    if not defect_rows.empty:
        reason_sums = defect_rows.groupby('LOSSREASONNAME')['REJECTQTY'].sum()
        if not reason_sums.empty:
            top_reason = _safe_str(reason_sums.idxmax())

    # Count unique upstream machines with defects attributed
    affected_machines = sum(1 for a in attribution if a['DEFECT_QTY'] > 0)

    return {
        'total_input': total_input,
        'lot_count': lot_count,
        'total_defect_qty': total_defect_qty,
        'total_defect_rate': total_defect_rate,
        'top_loss_reason': top_reason,
        'affected_machine_count': affected_machines,
    }


# ============================================================
# Chart Builders
# ============================================================

def _build_chart_data(
    records: List[Dict[str, Any]],
    dimension: str,
) -> List[Dict[str, Any]]:
    """Build Top N + Other Pareto chart data for a given dimension.

    Groups attribution records by dimension, sums defect qty, takes top N,
    groups rest as "其他".
    """
    if not records:
        return []

    # Aggregate by dimension
    dim_agg: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {'input_qty': 0, 'defect_qty': 0, 'lot_count': 0}
    )
    for rec in records:
        key = rec.get(dimension, '(未知)') or '(未知)'
        # For multi-valued dimensions (comma-separated), split and attribute to each
        if ',' in key:
            keys = [k.strip() for k in key.split(',')]
        else:
            keys = [key]
        for k in keys:
            dim_agg[k]['input_qty'] += rec['INPUT_QTY']
            dim_agg[k]['defect_qty'] += rec['DEFECT_QTY']
            dim_agg[k]['lot_count'] += rec['TMTT_LOT_COUNT']

    # Sort by defect qty DESC
    sorted_items = sorted(dim_agg.items(), key=lambda x: x[1]['defect_qty'], reverse=True)

    # Top N + Other
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

    # Add cumulative percentage
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
    """Build loss reason distribution chart from TMTT data (not attribution)."""
    if df.empty:
        return []

    defect_rows = df[df['REJECTQTY'] > 0].copy()
    if loss_reasons:
        defect_rows = defect_rows[defect_rows['LOSSREASONNAME'].isin(loss_reasons)]

    if defect_rows.empty:
        return []

    # Aggregate by loss reason
    reason_agg = defect_rows.groupby('LOSSREASONNAME')['REJECTQTY'].sum()
    reason_agg = reason_agg.sort_values(ascending=False)

    # Deduplicated input per loss reason
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
    tmtt_data: Dict[str, Dict[str, Any]],
) -> Dict[str, List[Dict]]:
    """Build chart data for all dimensions."""
    charts = {}
    for key, dim_col in DIMENSION_MAP.items():
        charts[key] = _build_chart_data(attribution, dim_col)

    # Loss reason chart is built from TMTT data directly (not attribution)
    # Reconstruct a minimal df from tmtt_data for the loss reason chart
    loss_rows = []
    for cid, data in tmtt_data.items():
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

    # Daily INPUT (deduplicated by CONTAINERID per date)
    daily_input = (
        work_df.drop_duplicates(subset=['CONTAINERID', 'DATE'])
        .groupby('DATE')['TRACKINQTY']
        .sum()
    )

    # Daily defects
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
# Detail Table
# ============================================================

def _build_detail_table(
    df: pd.DataFrame,
    ancestors: Dict[str, Set[str]],
    upstream_by_cid: Dict[str, List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    """Build LOT-level detail table with upstream machine info."""
    if df.empty:
        return []

    # Unique LOT info
    lot_cols = [
        'CONTAINERID', 'CONTAINERNAME', 'PJ_TYPE', 'PRODUCTLINENAME',
        'WORKFLOW', 'FINISHEDRUNCARD', 'TMTT_EQUIPMENTNAME', 'TRACKINQTY',
    ]
    lots = df.drop_duplicates(subset=['CONTAINERID'])[
        [c for c in lot_cols if c in df.columns]
    ].copy()

    # Aggregate defects per LOT per loss reason
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

        # Collect upstream machines
        upstream_machines = set()
        for anc_cid in all_cids:
            for rec in upstream_by_cid.get(anc_cid, []):
                upstream_machines.add(f"{rec['workcenter_group']}/{rec['equipment_name']}")

        # Build one row per loss reason for this LOT
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
                    'TMTT_EQUIPMENTNAME': _safe_str(row.get('TMTT_EQUIPMENTNAME')),
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
                'TMTT_EQUIPMENTNAME': _safe_str(row.get('TMTT_EQUIPMENTNAME')),
                'INPUT_QTY': input_qty,
                'LOSS_REASON': '',
                'DEFECT_QTY': 0,
                'DEFECT_RATE': 0.0,
                'ANCESTOR_COUNT': len(ancestor_set),
                'UPSTREAM_MACHINES': ', '.join(sorted(upstream_machines)),
            })

    return result
