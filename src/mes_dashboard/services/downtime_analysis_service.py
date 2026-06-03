# -*- coding: utf-8 -*-
"""Downtime Analysis Service.

Implements DA-01..DA-06:
- E10 status filter: only UDT/SDT/EGT from DW_MES_RESOURCESTATUS_SHIFT (DA-01)
- Cross-shift event merge with 60s contiguity rule (DA-02)
- JOBID bridge: Path A (direct) + Path B (overlap tiebreak) + no-match (DA-03)
- Big-category taxonomy mapping (DA-04)
- Wait/repair hours derivation (DA-05)
- DOWNTIME_BRIDGE_VERSION embedded in cache key (DA-06)
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Dict, Generator, List, Optional, Tuple

import pandas as pd

from mes_dashboard.config.constants import DOWNTIME_BRIDGE_VERSION

logger = logging.getLogger("mes_dashboard.downtime_analysis_service")

# ============================================================
# Big-category taxonomy (DA-04)
# Authoritative source: specs/changes/downtime-analysis-page/design.md §Big-category taxonomy
# Apply str(v).strip() at dict-build time (already done here).
# Per-record lookup: reason.strip() before lookup (see _map_big_category).
# ============================================================

_BIG_CATEGORY_MAP: Dict[str, str] = {
    'EE Repair': '維修',
    'EAP Minor stoppage': '維修',
    'EE_PM': '保養',
    'MF_PM': '保養',
    'PD_PM': '保養',
    'Change Type': '換型換線',
    'Change Package': '換型換線',
    'Re Layout': '換型換線',
    'Change Marking Code': '換型換線',
    'Change Model': '換型換線',
    'Change Tool/Consumables': '換刀清模',
    'Clean Mold': '換刀清模',
    'Prod_QC_Inspection': '檢查',
    'Prod_PD_inspection': '檢查',
    'Wait For Instructions': '待料待指示',
    'No Operator': '待料待指示',
    'No Raw Material': '待料待指示',
}

# Prefix-based category rules (TMTT_* → 檢查)
_PREFIX_CATEGORIES: List[Tuple[str, str]] = [('TMTT_', '檢查')]

# Freeze the map at module load time (dict is already immutable-equivalent via convention)
_BIG_CATEGORY_MAP = {str(k).strip(): str(v).strip() for k, v in _BIG_CATEGORY_MAP.items()}


def _map_big_category(reason: Optional[str], status: str) -> str:
    """Map OLDREASONNAME + OLDSTATUSNAME → big category (DA-04).

    Rules (in priority order):
    1. EGT status always → '工程' regardless of reason.
    2. Strip reason; check exact _BIG_CATEGORY_MAP lookup.
    3. Check _PREFIX_CATEGORIES prefix match.
    4. Fallback → '其他/未分類'.
    """
    # Rule 1: EGT → 工程
    if str(status).strip() == 'EGT':
        return '工程'

    # Strip reason (Oracle CHAR trailing-space handling)
    raw = reason if reason is not None else ''
    reason_stripped = str(raw).strip()

    # Rule 2: exact map lookup
    if reason_stripped in _BIG_CATEGORY_MAP:
        return _BIG_CATEGORY_MAP[reason_stripped]

    # Rule 3: prefix match
    for prefix, cat in _PREFIX_CATEGORIES:
        if reason_stripped.startswith(prefix):
            return cat

    # Rule 4: fallback
    return '其他/未分類'


# ============================================================
# Cross-shift event merge (DA-02)
# ============================================================

_MERGE_GAP_SECONDS = 60  # contiguity tolerance


def _merge_cross_shift_events(df: pd.DataFrame) -> pd.DataFrame:
    """Merge cross-shift fragments into logical events (DA-02).

    Sort by (HISTORYID, OLDSTATUSNAME, OLDREASONNAME, OLDLASTSTATUSCHANGEDATE).
    Walk rows; start new run when gap between prev.LASTSTATUSCHANGEDATE and
    cur.OLDLASTSTATUSCHANGEDATE > 60 seconds.
    Aggregate: hours=SUM(HOURS), event_start=MIN(OLDLASTSTATUSCHANGEDATE),
               event_end=MAX(LASTSTATUSCHANGEDATE), fragment_count=COUNT(*).

    Defensive float coercion on HOURS to avoid string-concat bug.
    """
    if df.empty:
        return df.iloc[0:0].copy()  # return empty DataFrame with same columns

    # Defensive coerce HOURS to float
    df = df.copy()
    df['HOURS'] = pd.to_numeric(df['HOURS'], errors='coerce').fillna(0.0)

    # Ensure datetime columns are actual datetime (not string)
    for col in ('OLDLASTSTATUSCHANGEDATE', 'LASTSTATUSCHANGEDATE'):
        if col in df.columns and df[col].dtype == object:
            df[col] = pd.to_datetime(df[col], errors='coerce')

    # Sort by merge key
    df = df.sort_values(
        ['HISTORYID', 'OLDSTATUSNAME', 'OLDREASONNAME', 'OLDLASTSTATUSCHANGEDATE'],
        na_position='last',
    ).reset_index(drop=True)

    merged_rows: List[Dict[str, Any]] = []
    group_key: Optional[Tuple] = None
    run_hours = 0.0
    run_start: Optional[Any] = None
    run_end: Optional[Any] = None
    run_count = 0
    prev_end: Optional[Any] = None
    pending_jobid: Optional[Any] = None

    for _, row in df.iterrows():
        cur_key = (
            str(row['HISTORYID']).strip(),
            str(row['OLDSTATUSNAME']).strip(),
            str(row['OLDREASONNAME']).strip() if pd.notna(row.get('OLDREASONNAME')) else '',
        )
        cur_start = row['OLDLASTSTATUSCHANGEDATE']
        cur_end = row['LASTSTATUSCHANGEDATE']
        cur_hours = float(row['HOURS'])
        cur_jobid = row.get('JOBID')

        # Check contiguity
        new_run = False
        if group_key is None:
            new_run = True
        elif cur_key != group_key:
            new_run = True
        else:
            # Same key — check gap
            if prev_end is not None and cur_start is not None:
                try:
                    gap = (cur_start - prev_end).total_seconds()
                    if gap > _MERGE_GAP_SECONDS:
                        new_run = True
                except Exception:
                    new_run = True
            else:
                new_run = True

        if new_run:
            # Flush previous run
            if group_key is not None:
                merged_rows.append(_build_merged_row(
                    group_key, run_start, run_end, run_hours, run_count, pending_jobid,
                ))
            # Start new run
            group_key = cur_key
            run_hours = cur_hours
            run_start = cur_start
            run_end = cur_end
            run_count = 1
            pending_jobid = cur_jobid
        else:
            run_hours += cur_hours
            if run_start is None or (cur_start is not None and cur_start < run_start):
                run_start = cur_start
            if run_end is None or (cur_end is not None and cur_end > run_end):
                run_end = cur_end
            run_count += 1
            # Prefer non-null JOBID
            if pending_jobid is None and cur_jobid is not None:
                pending_jobid = cur_jobid

        prev_end = cur_end

    # Flush last run
    if group_key is not None:
        merged_rows.append(_build_merged_row(
            group_key, run_start, run_end, run_hours, run_count, pending_jobid,
        ))

    if not merged_rows:
        return pd.DataFrame(columns=[
            'HISTORYID', 'OLDSTATUSNAME', 'OLDREASONNAME',
            'event_start', 'event_end', 'hours', 'fragment_count', 'JOBID',
        ])

    return pd.DataFrame(merged_rows)


def _build_merged_row(
    key: Tuple[str, str, str],
    event_start: Any,
    event_end: Any,
    hours: float,
    fragment_count: int,
    jobid: Any,
) -> Dict[str, Any]:
    hist_id, status, reason = key
    return {
        'HISTORYID': hist_id,
        'OLDSTATUSNAME': status,
        'OLDREASONNAME': reason if reason else None,
        'event_start': event_start,
        'event_end': event_end,
        'hours': round(hours, 6),
        'fragment_count': fragment_count,
        'JOBID': jobid,
    }


# ============================================================
# JOBID bridge (DA-03)
# ============================================================

def _bridge_jobid(events_df: pd.DataFrame, jobs_df: pd.DataFrame) -> pd.DataFrame:
    """Attach JOB enrichment to each logical event (DA-03).

    Path A: JOBID not null → direct join on JOBID → match_source='jobid'.
    Path B: JOBID null → overlap candidates:
        JOB.RESOURCEID == SHIFT.HISTORYID AND
        event_start < JOB.COMPLETEDATE AND event_end > JOB.CREATEDATE
      Tiebreak: largest temporal overlap (LEAST(end,COMPLETEDATE) - GREATEST(start,CREATEDATE))
      Ties: JOB.CREATEDATE ASC, JOB.JOBID ASC
      match_ambiguous=True when runner-up overlap >= 80% of winner.
    No-match: all JOB fields None, match_source='none'.
    """
    if events_df.empty:
        return _add_empty_job_columns(events_df)

    # Ensure datetime types
    for col in ('event_start', 'event_end'):
        if col in events_df.columns and events_df[col].dtype == object:
            events_df = events_df.copy()
            events_df[col] = pd.to_datetime(events_df[col], errors='coerce')

    if not jobs_df.empty:
        for col in ('CREATEDATE', 'COMPLETEDATE', 'FIRSTCLOCKONDATE', 'LASTCLOCKOFFDATE'):
            if col in jobs_df.columns and jobs_df[col].dtype == object:
                jobs_df = jobs_df.copy()
                jobs_df[col] = pd.to_datetime(jobs_df[col], errors='coerce')

    results = []
    for _, event in events_df.iterrows():
        jobid = event.get('JOBID')
        hist_id = str(event['HISTORYID']).strip()
        e_start = event['event_start']
        e_end = event['event_end']

        if jobid is not None and str(jobid).strip() not in ('', 'None', 'nan'):
            # Path A: direct join
            if not jobs_df.empty:
                matched = jobs_df[jobs_df['JOBID'].astype(str) == str(jobid).strip()]
                if not matched.empty:
                    job_row = matched.iloc[0]
                    enriched = _enrich_event(event, job_row, match_source='jobid', match_ambiguous=False)
                    results.append(enriched)
                    continue
            # JOBID referenced but not found in jobs table — treat as no-match
            results.append(_no_match_event(event))
        else:
            # Path B: overlap fallback
            if jobs_df.empty:
                results.append(_no_match_event(event))
                continue

            # Strip RESOURCEID for comparison
            jobs_df_working = jobs_df.copy()
            jobs_df_working['_RESOURCEID_stripped'] = (
                jobs_df_working['RESOURCEID'].apply(lambda x: str(x).strip() if pd.notna(x) else '')
            )
            candidates = jobs_df_working[
                (jobs_df_working['_RESOURCEID_stripped'] == hist_id) &
                (jobs_df_working['COMPLETEDATE'] > e_start) &
                (jobs_df_working['CREATEDATE'] < e_end)
            ].copy()

            if candidates.empty:
                results.append(_no_match_event(event))
                continue

            # Compute overlap duration for each candidate
            candidates['_overlap'] = candidates.apply(
                lambda r: _compute_overlap_seconds(e_start, e_end, r['CREATEDATE'], r['COMPLETEDATE']),
                axis=1,
            )

            # Tiebreak: largest overlap DESC, then CREATEDATE ASC, then JOBID ASC
            candidates = candidates.sort_values(
                ['_overlap', 'CREATEDATE', 'JOBID'],
                ascending=[False, True, True],
            )

            winner = candidates.iloc[0]
            winner_overlap = winner['_overlap']

            # match_ambiguous: runner-up overlap >= 80% of winner
            match_ambiguous = False
            if len(candidates) > 1:
                runner_overlap = candidates.iloc[1]['_overlap']
                if winner_overlap > 0 and runner_overlap >= 0.8 * winner_overlap:
                    match_ambiguous = True

            enriched = _enrich_event(event, winner, match_source='overlap', match_ambiguous=match_ambiguous)
            results.append(enriched)

    if not results:
        return _add_empty_job_columns(events_df)

    return pd.DataFrame(results)


def _compute_overlap_seconds(e_start: Any, e_end: Any, j_start: Any, j_end: Any) -> float:
    """Compute overlap in seconds between two datetime intervals."""
    try:
        overlap_start = max(e_start, j_start)
        overlap_end = min(e_end, j_end)
        if overlap_end <= overlap_start:
            return 0.0
        return (overlap_end - overlap_start).total_seconds()
    except Exception:
        return 0.0


def _enrich_event(
    event: pd.Series,
    job: pd.Series,
    match_source: str,
    match_ambiguous: bool,
) -> Dict[str, Any]:
    """Build enriched event dict from event row + matched job row (DA-03, DA-05)."""
    row = event.to_dict()

    # Wait/repair hours (DA-05)
    first_clock = job.get('FIRSTCLOCKONDATE')
    last_clock = job.get('LASTCLOCKOFFDATE')
    create_date = job.get('CREATEDATE')

    wait_min = None
    repair_min = None

    if first_clock is not None and pd.notna(first_clock) and create_date is not None and pd.notna(create_date):
        try:
            wait_min = round((first_clock - create_date).total_seconds() / 60.0, 2)
        except Exception:
            wait_min = None

    if first_clock is not None and pd.notna(first_clock) and last_clock is not None and pd.notna(last_clock):
        try:
            repair_min = round((last_clock - first_clock).total_seconds() / 60.0, 2)
        except Exception:
            repair_min = None

    row['match_source'] = match_source
    row['match_ambiguous'] = match_ambiguous
    row['job_id'] = _safe_str(job.get('JOBID'))
    row['job_order_name'] = _safe_str(job.get('JOBORDERNAME'))
    row['job_model'] = _safe_str(job.get('JOBMODELNAME'))
    row['symptom'] = _safe_str(job.get('SYMPTOMCODENAME'))
    row['cause'] = _safe_str(job.get('CAUSECODENAME'))
    row['repair'] = _safe_str(job.get('REPAIRCODENAME'))
    row['handler'] = _safe_str(job.get('COMPLETE_FULLNAME'))
    row['wait_min'] = wait_min
    row['repair_min'] = repair_min
    return row


def _no_match_event(event: pd.Series) -> Dict[str, Any]:
    """Build event dict with all JOB fields null (no-match branch)."""
    row = event.to_dict()
    row['match_source'] = 'none'
    row['match_ambiguous'] = False
    row['job_id'] = None
    row['job_order_name'] = None
    row['job_model'] = None
    row['symptom'] = None
    row['cause'] = None
    row['repair'] = None
    row['handler'] = None
    row['wait_min'] = None
    row['repair_min'] = None
    return row


def _add_empty_job_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Add empty JOB enrichment columns to an event DataFrame."""
    df = df.copy()
    for col in ('match_source', 'match_ambiguous', 'job_id', 'job_order_name', 'job_model',
                'symptom', 'cause', 'repair', 'handler', 'wait_min', 'repair_min'):
        if col not in df.columns:
            df[col] = None if col != 'match_source' else 'none'
    if 'match_ambiguous' in df.columns:
        df['match_ambiguous'] = df['match_ambiguous'].fillna(False)
    return df


def _safe_str(val: Any) -> Optional[str]:
    """Return None for null/empty, stripped string otherwise."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    s = str(val).strip()
    return s if s else None


# ============================================================
# Event enrichment: category + event_id
# ============================================================

def _enrich_events_df(df: pd.DataFrame) -> pd.DataFrame:
    """Add category and event_id columns to the merged+bridged event DataFrame."""
    df = df.copy()

    # Big category (DA-04)
    df['category'] = df.apply(
        lambda r: _map_big_category(r.get('OLDREASONNAME'), r.get('OLDSTATUSNAME', '')),
        axis=1,
    )

    # Stable event_id: (HISTORYID, OLDSTATUSNAME, OLDREASONNAME, event_start_iso)
    def _make_event_id(r: pd.Series) -> str:
        parts = [
            str(r.get('HISTORYID', '')).strip(),
            str(r.get('OLDSTATUSNAME', '')).strip(),
            str(r.get('OLDREASONNAME', '') or '').strip(),
            _ts_to_iso(r.get('event_start')),
        ]
        return '|'.join(parts)

    df['event_id'] = df.apply(_make_event_id, axis=1)

    # Rename columns to API names
    df = df.rename(columns={
        'HISTORYID': 'resource_id',
        'OLDSTATUSNAME': 'status',
        'OLDREASONNAME': 'reason',
    })

    # Ensure start_ts / end_ts as ISO strings
    df['start_ts'] = df['event_start'].apply(_ts_to_iso)
    df['end_ts'] = df['event_end'].apply(_ts_to_iso)

    return df


def _ts_to_iso(ts: Any) -> Optional[str]:
    """Convert timestamp to ISO 8601 string; None on failure."""
    if ts is None:
        return None
    try:
        if hasattr(ts, 'isoformat'):
            return ts.isoformat()
        return str(ts)
    except Exception:
        return None


# ============================================================
# Query cache key
# ============================================================

def make_downtime_query_id(params: dict) -> str:
    """Deterministic hash from query params + DOWNTIME_BRIDGE_VERSION (DA-06)."""
    keyed = dict(params)
    keyed['_bridge_version'] = DOWNTIME_BRIDGE_VERSION
    canonical = json.dumps(keyed, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:16]


# ============================================================
# Filter options (DA-01, AC-6)
# ============================================================

def get_filter_options(
    workcenter_groups: Optional[List[str]] = None,
    families: Optional[List[str]] = None,
    resource_ids: Optional[List[str]] = None,
    package_groups: Optional[List[str]] = None,
    is_production: bool = False,
    is_key: bool = False,
    is_monitor: bool = False,
) -> Optional[Dict[str, Any]]:
    """Return filter options for the downtime-analysis page.

    Reuses resource_cache for workcenter/family/resource/package_group dimensions.
    Also provides big_categories and reasons from the taxonomy.
    resource_ids contains RESOURCENAME values (display names, not IDs).
    """
    try:
        from mes_dashboard.services.resource_cache import get_all_resources, get_package_group_name
        from mes_dashboard.services.filter_cache import get_workcenter_mapping

        resources = get_all_resources() or []
        wc_mapping = get_workcenter_mapping() or {}

        # Build workcenter group → workcenter set
        wc_groups: List[str] = sorted({
            info.get('group', wc_name) or wc_name
            for wc_name, info in wc_mapping.items()
            if info.get('group')
        })

        # Apply cross-narrow filters
        filtered = resources
        if workcenter_groups:
            allowed_wcs = {
                wc for wc, info in wc_mapping.items()
                if info.get('group') in workcenter_groups
            }
            filtered = [r for r in filtered if r.get('WORKCENTERNAME') in allowed_wcs]

        if families:
            filtered = [r for r in filtered if r.get('RESOURCEFAMILYNAME') in families]

        # resource_ids contains resource names (RESOURCENAME), not IDs
        if resource_ids:
            name_set = {str(x).strip() for x in resource_ids}
            filtered = [r for r in filtered if str(r.get('RESOURCENAME', '')).strip() in name_set]

        if package_groups:
            pg_set = set(package_groups)
            filtered_pg = []
            for r in filtered:
                pg_name = get_package_group_name(r.get('PACKAGEGROUPID'))
                if pg_name in pg_set:
                    filtered_pg.append(r)
            filtered = filtered_pg

        # Equipment type flags
        if is_production:
            filtered = [r for r in filtered if r.get('PJ_ISPRODUCTION') == 1]
        if is_key:
            filtered = [r for r in filtered if r.get('PJ_ISKEY') == 1]
        if is_monitor:
            filtered = [r for r in filtered if r.get('PJ_ISMONITOR') == 1]

        fam_list = sorted({r.get('RESOURCEFAMILYNAME') or '' for r in filtered if r.get('RESOURCEFAMILYNAME')})
        # Return resource names for display
        res_list = sorted({str(r.get('RESOURCENAME', '')).strip() for r in filtered if r.get('RESOURCENAME')})

        # Package groups from filtered resources
        pg_list = sorted({
            get_package_group_name(r.get('PACKAGEGROUPID'))
            for r in filtered
            if get_package_group_name(r.get('PACKAGEGROUPID'))
        })

        # Big categories and reasons from taxonomy
        big_cats = ['維修', '保養', '換型換線', '換刀清模', '檢查', '待料待指示', '工程', '其他/未分類']
        reasons = sorted(_BIG_CATEGORY_MAP.keys())

        return {
            'workcenter_groups': wc_groups,
            'families': fam_list,
            'resources': res_list,
            'package_groups': pg_list,
            'big_categories': big_cats,
            'reasons': reasons,
        }
    except Exception as exc:
        logger.error("get_filter_options failed: %s", exc)
        return None


# ============================================================
# Primary dataset query
# ============================================================

def query_downtime_dataset(
    *,
    start_date: str,
    end_date: str,
    workcenter_groups: Optional[List[str]] = None,
    families: Optional[List[str]] = None,
    resource_ids: Optional[List[str]] = None,
    package_groups: Optional[List[str]] = None,
    big_categories: Optional[List[str]] = None,
    status_types: Optional[List[str]] = None,
    is_production: bool = False,
    is_key: bool = False,
    is_monitor: bool = False,
) -> Dict[str, Any]:
    """Execute Oracle query via BatchQueryEngine → post-merge stage → spool.

    Migration (BQE-07, ADR-0003): base_events are loaded via execute_plan
    (whole-dataset, single chunk — permanently excluded from USE_ROW_COUNT_CHUNKING).
    _merge_cross_shift_events and _bridge_jobid are applied as post-merge stage
    on the assembled DataFrame.  Spool namespace and cache key are unchanged.

    Returns query_id + summary + daily_trend + big_category + top_reasons.
    """
    from mes_dashboard.core.database import read_sql_df_slow as _read_sql_df
    from mes_dashboard.services.downtime_analysis_cache import (
        store_downtime_events,
        has_downtime_events,
        load_downtime_events,
    )
    from mes_dashboard.services.batch_query_engine import (
        compute_query_hash as _compute_query_hash,
        execute_plan,
        merge_chunks_to_spool,
    )
    from mes_dashboard.core.query_spool_store import (
        QUERY_SPOOL_DIR,
        register_spool_file,
    )
    from pathlib import Path

    query_id_input = {
        'start_date': start_date,
        'end_date': end_date,
        'workcenter_groups': sorted(workcenter_groups or []),
        'families': sorted(families or []),
        'resource_ids': sorted(resource_ids or []),
        'package_groups': sorted(package_groups or []),
        'big_categories': sorted(big_categories or []),
        'status_types': sorted(status_types or []),
    }
    query_id = make_downtime_query_id(query_id_input)

    if has_downtime_events(query_id):
        events_df = load_downtime_events(query_id)
        if events_df is not None and not events_df.empty:
            return _build_response(query_id, events_df)

    # --- BatchQueryEngine path (BQE-07) ---
    # ADR-0003: whole-dataset single chunk only; no row-count chunking ever.
    sql_dir = Path(__file__).resolve().parent.parent / 'sql' / 'downtime_analysis'
    base_sql = (sql_dir / 'base_events.sql').read_text(encoding='utf-8')
    job_sql = (sql_dir / 'job_bridge.sql').read_text(encoding='utf-8')

    base_params = {'start_date': start_date, 'end_date': end_date}

    # Single whole-dataset chunk covering the entire date range (ADR-0003).
    whole_dataset_chunk = [{'start_date': start_date, 'end_date': end_date}]
    engine_hash = _compute_query_hash({
        'downtime_base_events': True,
        'start_date': start_date,
        'end_date': end_date,
    })

    def _run_base_chunk(chunk, max_rows_per_chunk=None):
        params = {
            'start_date': chunk['start_date'],
            'end_date': chunk['end_date'],
        }
        result = _read_sql_df(base_sql, params, caller='downtime_analysis:base_events')
        return result if result is not None else pd.DataFrame()

    execute_plan(
        whole_dataset_chunk,
        _run_base_chunk,
        parallel=1,  # whole-dataset single chunk; parallel=1 per ADR-0003
        query_hash=engine_hash,
        cache_prefix='downtime_analysis',
    )

    _spool_dir = QUERY_SPOOL_DIR / 'downtime_analysis'
    tmp_path, _total_rows = merge_chunks_to_spool(
        'downtime_analysis',
        engine_hash,
        spool_dir=_spool_dir,
    )

    # Assemble base_df from the spool (post-merge stage for ADR-0003 reductions)
    if tmp_path is not None and tmp_path.exists():
        base_df = pd.read_parquet(str(tmp_path))
        try:
            tmp_path.unlink()  # clean up temp spool; final events go to store_downtime_events
        except Exception:
            pass
    else:
        base_df = pd.DataFrame()

    # Build RESOURCEID IN filter from base_events HISTORYIDs so job_bridge only
    # scans equipment that actually has downtime records in this date range.
    if not base_df.empty:
        from mes_dashboard.sql.builder import QueryBuilder as _QB
        hist_ids = sorted({str(x).strip() for x in base_df['HISTORYID'].dropna() if str(x).strip()})
        _jb_builder = _QB()
        _jb_builder.add_in_condition('j.RESOURCEID', hist_ids)
        resource_filter_sql = _jb_builder.get_conditions_sql() or '1=1'
        job_sql_rendered = job_sql.replace('{{ RESOURCE_FILTER }}', resource_filter_sql)
        job_params = {**base_params, **_jb_builder.params}
    else:
        job_sql_rendered = job_sql.replace('{{ RESOURCE_FILTER }}', '1=0')
        job_params = base_params

    # Also read job bridge data (still via direct read_sql_df — not chunked)
    job_df = _read_sql_df(job_sql_rendered, job_params, caller='downtime_analysis:job_bridge')
    if job_df is None:
        job_df = pd.DataFrame()

    # Apply resource filters (workcenter/family/resource_id/package_group/flags)
    if not base_df.empty:
        base_df = _apply_resource_filters(
            base_df, workcenter_groups, families, resource_ids, package_groups,
            is_production=is_production, is_key=is_key, is_monitor=is_monitor,
        )

    # Post-merge stage: cross-shift merge (DA-02) — must run on whole dataset (ADR-0003)
    if not base_df.empty:
        merged_df = _merge_cross_shift_events(base_df)
    else:
        merged_df = pd.DataFrame()

    # Post-merge stage: JOBID bridge (DA-03) — cross-product join over whole dataset
    if not merged_df.empty:
        bridged_df = _bridge_jobid(merged_df, job_df)
    else:
        bridged_df = pd.DataFrame()

    # Enrich with category, event_id, renamed columns
    if not bridged_df.empty:
        events_df = _enrich_events_df(bridged_df)
    else:
        events_df = _empty_events_df()

    # Apply big_category / status_type filters post-enrichment
    if not events_df.empty and big_categories:
        events_df = events_df[events_df['category'].isin(big_categories)]
    if not events_df.empty and status_types:
        events_df = events_df[events_df['status'].isin(status_types)]

    # Spool final enriched events (DA-06: cache key includes DOWNTIME_BRIDGE_VERSION)
    store_downtime_events(query_id, events_df, end_date=end_date)

    return _build_response(query_id, events_df)


def _apply_resource_filters(
    df: pd.DataFrame,
    workcenter_groups: Optional[List[str]],
    families: Optional[List[str]],
    resource_ids: Optional[List[str]],
    package_groups: Optional[List[str]],
    is_production: bool = False,
    is_key: bool = False,
    is_monitor: bool = False,
) -> pd.DataFrame:
    """Filter events DataFrame by resource dimension filters.

    Always restricts to HISTORYIDs present in resource_cache (applies
    EQUIPMENT_TYPE_FILTER + EXCLUDED_LOCATIONS + EXCLUDED_ASSET_STATUSES as the
    baseline), then further narrows by any user-supplied filters.

    resource_ids contains RESOURCENAME values (display names); they are resolved
    to RESOURCEID for HISTORYID matching against the events DataFrame.
    """
    try:
        from mes_dashboard.services.resource_cache import get_all_resources, get_package_group_name
        from mes_dashboard.services.filter_cache import get_workcenter_mapping

        resources = get_all_resources() or []
        wc_mapping = get_workcenter_mapping() or {}

        # Baseline: only HISTORYIDs recognised by resource_cache (enforces global
        # exclusion rules regardless of user filter selection).
        base_ids = {str(r.get('RESOURCEID', '')).strip() for r in resources if r.get('RESOURCEID')}
        df = df[df['HISTORYID'].apply(lambda x: str(x).strip()).isin(base_ids)]

        if df.empty:
            return df

        allowed_hist_ids: Optional[set] = None

        if workcenter_groups or families or package_groups or is_production or is_key or is_monitor:
            allowed_wcs = None
            if workcenter_groups:
                allowed_wcs = {
                    wc for wc, info in wc_mapping.items()
                    if info.get('group') in workcenter_groups
                }
            filtered = resources
            if allowed_wcs is not None:
                filtered = [r for r in filtered if r.get('WORKCENTERNAME') in allowed_wcs]
            if families:
                filtered = [r for r in filtered if r.get('RESOURCEFAMILYNAME') in families]
            if package_groups:
                pg_set = set(package_groups)
                filtered = [
                    r for r in filtered
                    if get_package_group_name(r.get('PACKAGEGROUPID')) in pg_set
                ]
            if is_production:
                filtered = [r for r in filtered if r.get('PJ_ISPRODUCTION') == 1]
            if is_key:
                filtered = [r for r in filtered if r.get('PJ_ISKEY') == 1]
            if is_monitor:
                filtered = [r for r in filtered if r.get('PJ_ISMONITOR') == 1]
            allowed_hist_ids = {str(r.get('RESOURCEID', '')).strip() for r in filtered if r.get('RESOURCEID')}

        if resource_ids:
            # resource_ids contains RESOURCENAME values; resolve to RESOURCEID
            name_set = {str(x).strip() for x in resource_ids}
            name_to_id = {
                str(r.get('RESOURCENAME', '')).strip(): str(r.get('RESOURCEID', '')).strip()
                for r in resources if r.get('RESOURCENAME') and r.get('RESOURCEID')
            }
            rid_set = {name_to_id[n] for n in name_set if n in name_to_id}
            if allowed_hist_ids is not None:
                allowed_hist_ids = allowed_hist_ids & rid_set
            else:
                allowed_hist_ids = rid_set

        if allowed_hist_ids is not None:
            df = df[df['HISTORYID'].apply(lambda x: str(x).strip()).isin(allowed_hist_ids)]
    except Exception as exc:
        logger.warning("Resource filter failed, returning unfiltered: %s", exc)

    return df


def _empty_events_df() -> pd.DataFrame:
    return pd.DataFrame(columns=[
        'event_id', 'resource_id', 'status', 'reason', 'category',
        'start_ts', 'end_ts', 'hours', 'fragment_count',
        'match_source', 'match_ambiguous',
        'job_id', 'job_order_name', 'job_model', 'symptom', 'cause', 'repair',
        'handler', 'wait_min', 'repair_min',
    ])


# ============================================================
# Build API response from events DataFrame
# ============================================================

def _build_response(query_id: str, events_df: pd.DataFrame) -> Dict[str, Any]:
    """Build the primary query response dict from the events DataFrame."""
    summary = _build_summary(events_df)
    daily_trend = _build_daily_trend(events_df)
    big_category = _build_big_category(events_df)
    top_reasons = _build_top_reasons(events_df, top_n=10)

    return {
        'query_id': query_id,
        'summary': summary,
        'daily_trend': daily_trend,
        'big_category': big_category,
        'top_reasons': top_reasons,
    }


def _build_summary(df: pd.DataFrame) -> Dict[str, Any]:
    """Build DowntimeKpiShape (§3.12.1)."""
    if df.empty:
        return {
            'total_hours': 0.0,
            'udt_hours': 0.0,
            'sdt_hours': 0.0,
            'egt_hours': 0.0,
            'event_count': 0,
            'avg_event_min': 0.0,
        }

    total = float(df['hours'].sum())
    udt = float(df.loc[df['status'] == 'UDT', 'hours'].sum())
    sdt = float(df.loc[df['status'] == 'SDT', 'hours'].sum())
    egt = float(df.loc[df['status'] == 'EGT', 'hours'].sum())
    cnt = len(df)
    avg = round(total / cnt * 60.0, 2) if cnt > 0 else 0.0

    return {
        'total_hours': round(total, 4),
        'udt_hours': round(udt, 4),
        'sdt_hours': round(sdt, 4),
        'egt_hours': round(egt, 4),
        'event_count': cnt,
        'avg_event_min': avg,
    }


def _build_daily_trend(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """Build DailyTrendRow list (§3.12.2)."""
    if df.empty:
        return []

    df = df.copy()
    df['date'] = pd.to_datetime(df['start_ts'], errors='coerce').dt.date
    grouped = df.groupby('date')

    rows = []
    for d, grp in sorted(grouped, key=lambda x: x[0]):
        udt = float(grp.loc[grp['status'] == 'UDT', 'hours'].sum())
        sdt = float(grp.loc[grp['status'] == 'SDT', 'hours'].sum())
        egt = float(grp.loc[grp['status'] == 'EGT', 'hours'].sum())
        rows.append({
            'date': str(d),
            'udt_hours': round(udt, 4),
            'sdt_hours': round(sdt, 4),
            'egt_hours': round(egt, 4),
            'total_hours': round(udt + sdt + egt, 4),
        })
    return rows


def _build_big_category(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """Build BigCategoryRow list (§3.12.3)."""
    if df.empty:
        return []

    total_hours = float(df['hours'].sum())
    grouped = df.groupby('category')

    rows = []
    for cat, grp in grouped:
        h = float(grp['hours'].sum())
        cnt = len(grp)
        pct = round(h / total_hours * 100.0, 2) if total_hours > 0 else 0.0
        rows.append({
            'category': cat,
            'hours': round(h, 4),
            'event_count': cnt,
            'pct': pct,
        })
    return sorted(rows, key=lambda x: x['hours'], reverse=True)


def _build_top_reasons(df: pd.DataFrame, top_n: int = 10) -> List[Dict[str, Any]]:
    """Build TopReasonRow list (§3.12.4)."""
    if df.empty:
        return []

    df = df.copy()
    df['reason'] = df['reason'].fillna('').apply(
        lambda x: x.strip() if x else '(未填寫)'
    )
    df['reason'] = df['reason'].replace('', '(未填寫)')

    grouped = df.groupby(['reason', 'status'])
    rows = []
    for (reason, status), grp in grouped:
        h = float(grp['hours'].sum())
        cnt = len(grp)
        avg = round(h / cnt * 60.0, 2) if cnt > 0 else 0.0
        rows.append({
            'reason': reason,
            'status': status,
            'hours': round(h, 4),
            'event_count': cnt,
            'avg_min': avg,
        })

    rows.sort(key=lambda x: x['hours'], reverse=True)
    return rows[:top_n]


# ============================================================
# apply_view — DuckDB view re-queries from spool
# ============================================================

def apply_view(
    view_name: str,
    query_id: str,
    granularity: str = 'day',
    top_n: int = 10,
    page: int = 1,
    page_size: int = 50,
    resource_lookup: Optional[Dict[str, Any]] = None,
    big_category: Optional[str] = None,
    status_types: Optional[List[str]] = None,
    resource_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Serve a view from the spool without Oracle re-query.

    Returns None when spool is expired (→ route returns 410).

    Optional filter params (in-memory pandas slice, no Oracle re-query):
        big_category:  narrow by events_df['category'] == big_category
        status_types:  narrow by events_df['status'].isin(status_types)
        resource_id:   narrow by events_df['resource_id'] == resource_id
    """
    from mes_dashboard.services.downtime_analysis_cache import load_downtime_events

    events_df = load_downtime_events(query_id)
    if events_df is None:
        return None

    # Apply in-memory filters BEFORE routing to view builders (DQ-1 / DQ-4).
    # Omit-all path is byte-for-byte unchanged (falsy params are no-ops).
    if big_category and not events_df.empty:
        events_df = events_df[events_df['category'] == big_category]
    if status_types and not events_df.empty:
        events_df = events_df[events_df['status'].isin(status_types)]
    if resource_id and not events_df.empty:
        events_df = events_df[events_df['resource_id'] == resource_id]

    if view_name == 'summary':
        return {
            'summary': _build_summary(events_df),
            'daily_trend': _build_daily_trend(events_df),
            'big_category': _build_big_category(events_df),
            'top_reasons': _build_top_reasons(events_df, top_n=top_n),
        }

    if view_name == 'big_category':
        return {'big_category': _build_big_category(events_df)}

    if view_name == 'top_reasons':
        return {'top_reasons': _build_top_reasons(events_df, top_n=top_n)}

    if view_name == 'equipment_detail':
        return _build_equipment_detail_page(events_df, resource_lookup or {}, page=page, page_size=page_size)

    if view_name == 'event_detail':
        return _build_event_detail_page(events_df, page=page, page_size=page_size, resource_lookup=resource_lookup or {})

    logger.warning("apply_view: unknown view_name=%s", view_name)
    return None


def _build_equipment_detail_page(
    df: pd.DataFrame,
    resource_lookup: Dict[str, Any],
    page: int = 1,
    page_size: int = 20,
) -> Dict[str, Any]:
    """Build paginated EquipmentDetailRow list."""
    page_size = min(max(int(page_size), 1), 1000)  # cap raised to 1000 (DQ-2)
    page = max(int(page), 1)

    rows = _build_equipment_detail(df, resource_lookup)

    total_rows = len(rows)
    total_pages = max(1, (total_rows + page_size - 1) // page_size) if total_rows > 0 else 0
    offset = (page - 1) * page_size
    page_rows = rows[offset:offset + page_size]

    return {
        'equipment_detail': page_rows,
        'pagination': {
            'page': page,
            'page_size': page_size,
            'total_rows': total_rows,
            'total_pages': total_pages,
        },
    }


def _build_equipment_detail(
    df: pd.DataFrame,
    resource_lookup: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Build EquipmentDetailRow list (§3.12.5)."""
    if df.empty:
        return []

    grouped = df.groupby('resource_id')
    rows = []
    for rid, grp in grouped:
        res_info = resource_lookup.get(str(rid).strip(), {})
        udt = float(grp.loc[grp['status'] == 'UDT', 'hours'].sum())
        sdt = float(grp.loc[grp['status'] == 'SDT', 'hours'].sum())
        egt = float(grp.loc[grp['status'] == 'EGT', 'hours'].sum())
        total = udt + sdt + egt
        cnt = len(grp)
        # top_reason: reason with highest hours
        reason_grp = grp.groupby('reason')['hours'].sum().reset_index()
        top_reason = None
        if not reason_grp.empty:
            top_reason = reason_grp.loc[reason_grp['hours'].idxmax(), 'reason']
            top_reason = str(top_reason).strip() if top_reason else None

        rows.append({
            'resource_id': str(rid).strip(),
            'resource_name': res_info.get('RESOURCENAME'),
            'workcenter': res_info.get('WORKCENTERNAME'),
            'family': res_info.get('RESOURCEFAMILYNAME'),
            'udt_hours': round(udt, 4),
            'sdt_hours': round(sdt, 4),
            'egt_hours': round(egt, 4),
            'total_hours': round(total, 4),
            'event_count': cnt,
            'top_reason': top_reason,
        })

    return sorted(rows, key=lambda x: x['total_hours'], reverse=True)


def _build_event_detail_page(
    df: pd.DataFrame,
    page: int,
    page_size: int,
    resource_lookup: Dict[str, Any],
) -> Dict[str, Any]:
    """Build paginated EventDetailRow list (§3.12.6)."""
    page_size = min(max(int(page_size), 1), 200)
    page = max(int(page), 1)

    total_rows = len(df)
    total_pages = max(1, (total_rows + page_size - 1) // page_size) if total_rows > 0 else 0

    offset = (page - 1) * page_size
    page_df = df.iloc[offset:offset + page_size] if not df.empty else df

    rows = []
    for _, row in page_df.iterrows():
        rid = str(row.get('resource_id', '')).strip()
        res_info = resource_lookup.get(rid, {})

        # JobEnrichment sub-object
        ms = row.get('match_source', 'none')
        if ms == 'none':
            job_obj = None
        else:
            job_obj = {
                'job_id': row.get('job_id'),
                'job_order_name': row.get('job_order_name'),
                'job_model': row.get('job_model'),
                'symptom': row.get('symptom'),
                'cause': row.get('cause'),
                'repair': row.get('repair'),
                'wait_min': row.get('wait_min'),
                'repair_min': row.get('repair_min'),
                'handler': row.get('handler'),
                'match_ambiguous': bool(row.get('match_ambiguous', False)),
            }

        rows.append({
            'event_id': row.get('event_id', ''),
            'resource_id': rid,
            'resource_name': res_info.get('RESOURCENAME'),
            'status': row.get('status', ''),
            'reason': row.get('reason') or None,
            'category': row.get('category', ''),
            'start_ts': row.get('start_ts') or '',
            'end_ts': row.get('end_ts') or '',
            'hours': float(row.get('hours', 0.0)),
            'match_source': ms,
            'job': job_obj,
        })

    return {
        'events': rows,
        'pagination': {
            'page': page,
            'page_size': page_size,
            'total_rows': total_rows,
            'total_pages': total_pages,
        },
    }


# ============================================================
# CSV export helpers
# ============================================================


def export_equipment_detail_csv(query_id: str) -> Optional[Generator[bytes, None, None]]:
    """Stream equipment detail as CSV bytes (utf-8-sig for Excel compatibility)."""
    from mes_dashboard.services.downtime_analysis_cache import load_downtime_events
    from mes_dashboard.services.resource_cache import get_all_resources
    import io
    import csv

    events_df = load_downtime_events(query_id)
    if events_df is None:
        return None

    resource_lookup: Dict[str, Any] = {}
    try:
        resources = get_all_resources()
        for r in resources:
            rid = str(r.get('HISTORYID', '')).strip()
            resource_lookup[rid] = r
    except Exception:
        pass

    rows = _build_equipment_detail(events_df, resource_lookup)

    def _gen() -> Generator[bytes, None, None]:
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(['設備名稱', '工作站', '機種', 'UDT (h)', 'SDT (h)', 'EGT (h)', '總計 (h)', '事件數', '主要原因'])
        yield buf.getvalue().encode('utf-8-sig')
        for row in rows:
            buf = io.StringIO()
            writer = csv.writer(buf)
            writer.writerow([
                row.get('resource_name') or row.get('resource_id', ''),
                row.get('workcenter') or '',
                row.get('family') or '',
                row.get('udt_hours', 0),
                row.get('sdt_hours', 0),
                row.get('egt_hours', 0),
                row.get('total_hours', 0),
                row.get('event_count', 0),
                row.get('top_reason') or '',
            ])
            yield buf.getvalue().encode('utf-8-sig')

    return _gen()


def export_event_detail_csv(query_id: str) -> Optional[Generator[bytes, None, None]]:
    """Stream event detail as CSV bytes (utf-8-sig for Excel compatibility)."""
    from mes_dashboard.services.downtime_analysis_cache import load_downtime_events
    from mes_dashboard.services.resource_cache import get_all_resources
    import io
    import csv

    events_df = load_downtime_events(query_id)
    if events_df is None:
        return None

    resource_lookup: Dict[str, Any] = {}
    try:
        resources = get_all_resources()
        for r in resources:
            rid = str(r.get('HISTORYID', '')).strip()
            resource_lookup[rid] = r
    except Exception:
        pass

    def _gen() -> Generator[bytes, None, None]:
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow([
            '設備名稱', '狀態', '原因', '類別',
            '開始時間', '結束時間', '時數 (h)', '橋接來源',
            'JOB ID', '機型', '症狀', '原因碼', '修復', '待料 (min)', '維修 (min)', '負責人',
        ])
        yield buf.getvalue().encode('utf-8-sig')

        for _, row in events_df.iterrows():
            rid = str(row.get('resource_id', '')).strip()
            res_info = resource_lookup.get(rid, {})
            ms = row.get('match_source', 'none')

            match_label = {'jobid': 'JOBID', 'overlap': '時間重疊', 'none': '未匹配'}.get(str(ms), str(ms))

            buf = io.StringIO()
            writer = csv.writer(buf)
            writer.writerow([
                res_info.get('RESOURCENAME') or rid,
                row.get('status', ''),
                row.get('reason') or '',
                row.get('category', ''),
                row.get('start_ts') or '',
                row.get('end_ts') or '',
                row.get('hours', 0),
                match_label,
                row.get('job_id') or '' if ms != 'none' else '',
                row.get('job_model') or '' if ms != 'none' else '',
                row.get('symptom') or '' if ms != 'none' else '',
                row.get('cause') or '' if ms != 'none' else '',
                row.get('repair') or '' if ms != 'none' else '',
                row.get('wait_min') or '' if ms != 'none' else '',
                row.get('repair_min') or '' if ms != 'none' else '',
                row.get('handler') or '' if ms != 'none' else '',
            ])
            yield buf.getvalue().encode('utf-8-sig')

    return _gen()
