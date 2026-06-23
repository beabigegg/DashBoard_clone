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
import os
from pathlib import Path
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
    'Facilities related Down': '維修',
    'Group Equipment Down': '維修',
    'Test Run': '維修',
    'FAC Repair': '維修',
    'EE_PM': '保養',
    'MF_PM': '保養',
    'PD_PM': '保養',
    'Cmk inspection': '保養',
    'Machine Calibration': '保養',
    'Change Type': '改機換料',
    'Change Package': '改機換料',
    'Re Layout': '改機換料',
    'Change Marking Code': '改機換料',
    'Change Model': '改機換料',
    'Change Tool/Consumables': '治工具更換與模具清潔',
    'Change Tool/Consumables in process': '治工具更換與模具清潔',
    'Clean Mold': '治工具更換與模具清潔',
    'Prod_QC_Inspection': '檢查',
    'Prod_PD_inspection': '檢查',
    'Wait For Instructions': '待料待指示',
    'No Operator': '待料待指示',
    'No Raw Material': '待料待指示',
    'Programing': '教讀程式',
}

# Prefix-based category rules (TMTT_* → 檢查)
_PREFIX_CATEGORIES: List[Tuple[str, str]] = [('TMTT_', '檢查')]

# Freeze the map at module load time (dict is already immutable-equivalent via convention)
_BIG_CATEGORY_MAP = {str(k).strip(): str(v).strip() for k, v in _BIG_CATEGORY_MAP.items()}

_DOWNTIME_ENGINE_PARALLEL = max(1, int(os.getenv("DOWNTIME_ENGINE_PARALLEL", "3")))

# ── Feature flag: browser-DuckDB path (AC-6, design.md Migration) ─────────────
# Default false at initial ship (env-contract 1.0.7); set DOWNTIME_BROWSER_DUCKDB=true
# to enable the new response shape {base_spool_url, jobs_spool_url, query_id, taxonomy}.
# Module-level constant — frozen at import time; tests must use monkeypatch.setattr,
# never os.environ (CLAUDE.md env-var-default discipline).
_BROWSER_DUCKDB_ENABLED: bool = os.getenv(
    "DOWNTIME_BROWSER_DUCKDB", "false"
).lower() in ("1", "true", "yes")


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

# _CROSS_SHIFT_MERGE_SQL is the DuckDB SQL equivalent of _merge_cross_shift_events.
# It reads from a view named "base_events" (registered by the caller) and returns
# the merged events.  Uses window functions (LAG + SUM cumsum) instead of pandas
# shift/cumsum, processes the parquet on disk without loading into Python RAM.
_CROSS_SHIFT_MERGE_SQL = """
WITH sorted_events AS (
    SELECT
        *,
        COALESCE(TRY_CAST(HOURS AS DOUBLE), 0.0)        AS _hours_num,
        TRY_CAST(OLDLASTSTATUSCHANGEDATE AS TIMESTAMP)   AS _estart,
        TRY_CAST(LASTSTATUSCHANGEDATE    AS TIMESTAMP)   AS _eend,
        TRIM(CAST(HISTORYID      AS VARCHAR))             AS _h,
        TRIM(CAST(OLDSTATUSNAME  AS VARCHAR))             AS _s,
        COALESCE(NULLIF(TRIM(CAST(OLDREASONNAME AS VARCHAR)), ''), '') AS _r
    FROM base_events
    ORDER BY
        TRIM(CAST(HISTORYID     AS VARCHAR)),
        TRIM(CAST(OLDSTATUSNAME AS VARCHAR)),
        COALESCE(NULLIF(TRIM(CAST(OLDREASONNAME AS VARCHAR)), ''), ''),
        TRY_CAST(OLDLASTSTATUSCHANGEDATE AS TIMESTAMP) NULLS LAST
),
numbered AS (
    SELECT *, ROW_NUMBER() OVER () AS _srn
    FROM sorted_events
),
lagged AS (
    SELECT *,
        LAG(_h)    OVER (ORDER BY _srn) AS _ph,
        LAG(_s)    OVER (ORDER BY _srn) AS _ps,
        LAG(_r)    OVER (ORDER BY _srn) AS _pr,
        LAG(_eend) OVER (ORDER BY _srn) AS _prev_end
    FROM numbered
),
breaks AS (
    SELECT *,
        CASE
            WHEN _ph IS NULL                                                 THEN 1
            WHEN _h  != _ph                                                  THEN 1
            WHEN _s  != _ps                                                  THEN 1
            WHEN _r  != COALESCE(_pr, '')                                    THEN 1
            WHEN _prev_end IS NULL                                           THEN 1
            WHEN datediff('second', _prev_end, _estart) > {gap_seconds}      THEN 1
            ELSE 0
        END AS _is_break
    FROM lagged
),
run_ids AS (
    SELECT *,
        SUM(_is_break) OVER (
            ORDER BY _srn
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS _run_id
    FROM breaks
)
SELECT
    FIRST(_h)                                                                             AS HISTORYID,
    FIRST(_s)                                                                             AS OLDSTATUSNAME,
    FIRST(NULLIF(TRIM(CAST(OLDREASONNAME AS VARCHAR)), ''))
        FILTER (WHERE NULLIF(TRIM(CAST(OLDREASONNAME AS VARCHAR)), '') IS NOT NULL)       AS OLDREASONNAME,
    MIN(_estart)                                                                          AS event_start,
    MAX(_eend)                                                                            AS event_end,
    ROUND(SUM(_hours_num), 6)                                                             AS hours,
    COUNT(*)                                                                              AS fragment_count,
    FIRST(CAST(JOBID AS VARCHAR)) FILTER (WHERE JOBID IS NOT NULL)                        AS JOBID
FROM run_ids
GROUP BY _run_id
ORDER BY HISTORYID, event_start
"""


def _merge_cross_shift_events_from_parquet(parquet_path: Path) -> pd.DataFrame:
    """Run cross-shift merge directly on a parquet file via DuckDB.

    Avoids loading the full raw dataset into Python RAM — DuckDB reads the
    parquet in columnar streaming mode, returning only the reduced merged result.
    Falls back to the pandas path on any DuckDB error.
    """
    try:
        import duckdb
        con = duckdb.connect()
        try:
            con.execute(f"CREATE VIEW base_events AS SELECT * FROM read_parquet('{parquet_path}')")
            sql = _CROSS_SHIFT_MERGE_SQL.format(gap_seconds=_MERGE_GAP_SECONDS)
            result = con.execute(sql).df()
            # Restore empty-string OLDREASONNAME -> None (pandas path behaviour)
            if 'OLDREASONNAME' in result.columns:
                result['OLDREASONNAME'] = result['OLDREASONNAME'].replace('', None)
            return result
        finally:
            con.close()
    except Exception as exc:
        logger.warning(
            "_merge_cross_shift_events_from_parquet: DuckDB failed (%s), "
            "falling back to pandas path",
            exc,
        )
        base_df = pd.read_parquet(str(parquet_path))
        return _merge_cross_shift_events(base_df)


def _merge_cross_shift_events(df: pd.DataFrame) -> pd.DataFrame:
    """Merge cross-shift fragments into logical events (DA-02).

    Vectorized: sort → detect run breaks via shifted key/gap comparison →
    cumsum run_id → groupby aggregate.  O(N log N), no Python row loop.
    """
    if df.empty:
        return df.iloc[0:0].copy()

    df = df.copy()
    df['HOURS'] = pd.to_numeric(df['HOURS'], errors='coerce').fillna(0.0)

    for col in ('OLDLASTSTATUSCHANGEDATE', 'LASTSTATUSCHANGEDATE'):
        if col in df.columns and df[col].dtype == object:
            df[col] = pd.to_datetime(df[col], errors='coerce')

    df = df.sort_values(
        ['HISTORYID', 'OLDSTATUSNAME', 'OLDREASONNAME', 'OLDLASTSTATUSCHANGEDATE'],
        na_position='last',
    ).reset_index(drop=True)

    # Normalised key columns for break detection (strip + null→'')
    _sentinel = '\x00'
    _h = df['HISTORYID'].astype(str).str.strip()
    _s = df['OLDSTATUSNAME'].astype(str).str.strip()
    _r = df['OLDREASONNAME'].fillna('').astype(str).str.strip()

    key_changed = (
        (_h != _h.shift(fill_value=_sentinel))
        | (_s != _s.shift(fill_value=_sentinel))
        | (_r != _r.shift(fill_value=_sentinel))
    )

    prev_end = df['LASTSTATUSCHANGEDATE'].shift(1)
    gap_secs = (df['OLDLASTSTATUSCHANGEDATE'] - prev_end).dt.total_seconds()
    gap_break = gap_secs.isna() | (gap_secs > _MERGE_GAP_SECONDS)

    new_run = key_changed | gap_break
    new_run.iloc[0] = True
    df['_run_id'] = new_run.cumsum()

    # Store normalised key values so groupby first() returns stripped output
    df['_h'] = _h
    df['_s'] = _s

    def _first_nonnull(s: pd.Series) -> Any:
        valid = s.dropna()
        return valid.iloc[0] if len(valid) else None

    result = (
        df.groupby('_run_id', sort=False)
        .agg(
            HISTORYID=('_h', 'first'),
            OLDSTATUSNAME=('_s', 'first'),
            OLDREASONNAME=('OLDREASONNAME', _first_nonnull),
            event_start=('OLDLASTSTATUSCHANGEDATE', 'min'),
            event_end=('LASTSTATUSCHANGEDATE', 'max'),
            hours=('HOURS', 'sum'),
            fragment_count=('HISTORYID', 'count'),
            JOBID=('JOBID', _first_nonnull),
        )
        .reset_index(drop=True)
    )

    result['hours'] = result['hours'].round(6)
    # Empty-string OLDREASONNAME → None (preserves original semantics)
    result['OLDREASONNAME'] = result['OLDREASONNAME'].replace('', None)
    return result


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
    """Attach JOB enrichment to each logical event (DA-03). Vectorized implementation.

    Path A: JOBID not null AND found in jobs → merge on JOBID → match_source='jobid'.
            JOBID not null but NOT found in jobs → match_source='none' (orphan).
    Path B: JOBID null → merge-filter on RESOURCEID==HISTORYID + time overlap →
            tiebreak by largest overlap, then CREATEDATE ASC, then JOBID ASC →
            match_source='overlap' or 'none'.
    match_ambiguous=True when runner-up overlap >= 80% of winner (Path B only).
    """
    if events_df.empty:
        return _add_empty_job_columns(events_df)

    # Ensure datetime types on events
    for col in ('event_start', 'event_end'):
        if col in events_df.columns and events_df[col].dtype == object:
            events_df = events_df.copy()
            events_df[col] = pd.to_datetime(events_df[col], errors='coerce')

    if not jobs_df.empty:
        for col in ('CREATEDATE', 'COMPLETEDATE', 'FIRSTCLOCKONDATE', 'LASTCLOCKOFFDATE',
                    'ASSIGNED_DATE', 'ACK_DATE', 'INSPECT_START', 'INSPECT_END'):
            if col in jobs_df.columns and jobs_df[col].dtype == object:
                jobs_df = jobs_df.copy()
                jobs_df[col] = pd.to_datetime(jobs_df[col], errors='coerce')

    if jobs_df.empty:
        return _add_empty_job_columns(events_df)

    _OPTIONAL = ['ASSIGNED_DATE', 'ACK_DATE', 'INSPECT_START', 'INSPECT_END']
    _JOB_ENRICH = [
        'JOBORDERNAME', 'JOBMODELNAME', 'SYMPTOMCODENAME', 'CAUSECODENAME',
        'REPAIRCODENAME', 'COMPLETE_FULLNAME', 'FIRSTCLOCKONDATE', 'LASTCLOCKOFFDATE',
        'CREATEDATE', 'COMPLETEDATE',
    ] + [c for c in _OPTIONAL if c in jobs_df.columns]

    events_df = events_df.copy().reset_index(drop=True)
    events_df['_eidx'] = events_df.index

    # Normalize JOBID from events (None for null / empty / 'nan' / 'None')
    _jnorm = events_df['JOBID'].apply(lambda x: str(x).strip() if pd.notna(x) else None)
    events_df['_jobid_norm'] = _jnorm.apply(lambda x: None if x in ('', 'None', 'nan') else x)

    # Prepare jobs lookup
    jobs_work = jobs_df.copy()
    jobs_work['_jobid_norm'] = jobs_work['JOBID'].astype(str).str.strip()
    jobs_work['_res_norm'] = (
        jobs_work['RESOURCEID'].apply(lambda x: str(x).strip() if pd.notna(x) else '')
        if 'RESOURCEID' in jobs_work.columns else pd.Series([''] * len(jobs_work))
    )

    _enrich_cols = [c for c in _JOB_ENRICH if c in jobs_work.columns]
    jobs_for_a = (
        jobs_work[['_jobid_norm'] + _enrich_cols]
        .drop_duplicates(subset=['_jobid_norm'], keep='first')
    )
    jobs_for_b = jobs_work[['_res_norm', '_jobid_norm', 'CREATEDATE', 'COMPLETEDATE']
                           + [c for c in _enrich_cols if c not in ('CREATEDATE', 'COMPLETEDATE')]].copy()

    valid_jobid_set = set(jobs_for_a['_jobid_norm'].tolist())

    mask_has_jobid = events_df['_jobid_norm'].notna()
    mask_valid_a = mask_has_jobid & events_df['_jobid_norm'].isin(valid_jobid_set)
    mask_orphan = mask_has_jobid & ~mask_valid_a
    mask_path_b = ~mask_has_jobid

    events_a = events_df[mask_valid_a].copy()
    events_orphan = events_df[mask_orphan].copy()
    events_b = events_df[mask_path_b].copy()

    # ── Path A: direct merge on _jobid_norm ──
    if not events_a.empty:
        result_a = pd.merge(events_a, jobs_for_a, on='_jobid_norm', how='left')
        result_a['match_source'] = 'jobid'
        result_a['match_ambiguous'] = False
        result_a['_matched_jobid'] = result_a['_jobid_norm']
    else:
        result_a = pd.DataFrame()

    # ── Orphan: has JOBID but not found in jobs ──
    if not events_orphan.empty:
        result_orphan = _add_empty_job_columns(events_orphan.copy())
        result_orphan['_matched_jobid'] = None
    else:
        result_orphan = pd.DataFrame()

    # ── Path B: overlap join ──
    if not events_b.empty and 'RESOURCEID' in jobs_df.columns:
        events_b['_hist_norm'] = events_b['HISTORYID'].astype(str).str.strip()

        # Pre-filter 1: only keep jobs for resources that appear in events_b.
        # Cuts the jobs side from global count to only relevant machines.
        _hist_ids = set(events_b['_hist_norm'].dropna().unique())
        _jobs_b = jobs_for_b[jobs_for_b['_res_norm'].isin(_hist_ids)]

        # Pre-filter 2: per-resource time-span filter.
        # Drop jobs whose window does not overlap ANY event span for that resource.
        # Prevents N-events × M-jobs Cartesian explosion before the date filter.
        if not _jobs_b.empty:
            _spans = (
                events_b.groupby('_hist_norm', sort=False)
                .agg(_span_start=('event_start', 'min'), _span_end=('event_end', 'max'))
                .reset_index()
            )
            _jobs_b = pd.merge(
                _jobs_b, _spans,
                left_on='_res_norm', right_on='_hist_norm', how='left',
            )
            _eff_end_span = _jobs_b['COMPLETEDATE'].fillna(_jobs_b['LASTCLOCKOFFDATE'])
            _jobs_b = _jobs_b[
                _eff_end_span.notna() &
                (_eff_end_span > _jobs_b['_span_start']) &
                (_jobs_b['CREATEDATE'] < _jobs_b['_span_end'])
            ].drop(columns=['_span_start', '_span_end', '_hist_norm'])

        cand = pd.merge(
            events_b[['_eidx', '_hist_norm', 'event_start', 'event_end']],
            _jobs_b,
            left_on='_hist_norm',
            right_on='_res_norm',
            how='left',
        )
        cand = cand.dropna(subset=['_jobid_norm'])
        cand['_eff_end'] = cand['COMPLETEDATE'].fillna(cand['LASTCLOCKOFFDATE'])
        cand = cand[
            cand['_eff_end'].notna() &
            (cand['_eff_end'] > cand['event_start']) &
            (cand['CREATEDATE'] < cand['event_end'])
        ].copy()

        if not cand.empty:
            cand['_overlap'] = (
                cand[['event_end', '_eff_end']].min(axis=1) -
                cand[['event_start', 'CREATEDATE']].max(axis=1)
            ).dt.total_seconds().clip(lower=0)

            cand = cand.sort_values(
                ['_eidx', '_overlap', 'CREATEDATE', '_jobid_norm'],
                ascending=[True, False, True, True],
            )
            cand['_rank'] = cand.groupby('_eidx').cumcount()

            winners = cand[cand['_rank'] == 0].copy()
            runners = (
                cand[cand['_rank'] == 1][['_eidx', '_overlap']]
                .rename(columns={'_overlap': '_runner_overlap'})
            )
            winners = winners.merge(runners, on='_eidx', how='left')
            winners['match_ambiguous'] = (
                winners['_runner_overlap'].notna()
                & (winners['_overlap'] > 0)
                & (winners['_runner_overlap'] >= 0.8 * winners['_overlap'])
            )
            winners['match_source'] = 'overlap'
            winners['_matched_jobid'] = winners['_jobid_norm']

            _winner_cols = (
                ['_eidx', 'match_source', 'match_ambiguous', '_matched_jobid']
                + [c for c in _enrich_cols if c in winners.columns]
            )
            result_b = pd.merge(
                events_b.drop(columns=['_hist_norm']),
                winners[_winner_cols],
                on='_eidx',
                how='left',
            )
            result_b['match_source'] = result_b['match_source'].fillna('none')
            result_b['match_ambiguous'] = result_b['match_ambiguous'].fillna(False)
        else:
            result_b = _add_empty_job_columns(events_b.drop(columns=['_hist_norm']))
            result_b['_matched_jobid'] = None
    else:
        result_b = _add_empty_job_columns(events_b)
        result_b['_matched_jobid'] = None

    # ── Combine all paths ──
    frames = [f for f in [result_a, result_orphan, result_b] if not f.empty]
    if not frames:
        return _add_empty_job_columns(events_df)
    result = pd.concat(frames, ignore_index=True, sort=False)
    result = result.sort_values('_eidx').reset_index(drop=True)

    # ── Derived enrichment columns (vectorized) ──
    def _safe_min_s(end_col: str, start_col: str) -> pd.Series:
        if end_col not in result.columns or start_col not in result.columns:
            return pd.Series([None] * len(result), dtype=object)
        t_end = pd.to_datetime(result[end_col], errors='coerce')
        t_start = pd.to_datetime(result[start_col], errors='coerce')
        diff = (t_end - t_start).dt.total_seconds() / 60.0
        mask_valid = diff.notna() & (diff >= 0)
        out = diff.round(2).astype(object)
        out[~mask_valid] = None
        return out

    def _norm_str_col(col: str) -> pd.Series:
        if col not in result.columns:
            return pd.Series([None] * len(result), dtype=object)
        s = result[col].astype(str).str.strip()
        bad = result[col].isna() | s.isin({'', 'nan', 'None', 'NaT'})
        return s.where(~bad, other=None)

    result['job_id'] = _norm_str_col('_matched_jobid')
    result['job_order_name'] = _norm_str_col('JOBORDERNAME')
    result['job_model'] = _norm_str_col('JOBMODELNAME')
    result['symptom'] = _norm_str_col('SYMPTOMCODENAME')
    result['cause'] = _norm_str_col('CAUSECODENAME')
    result['repair'] = _norm_str_col('REPAIRCODENAME')
    result['handler'] = _norm_str_col('COMPLETE_FULLNAME')
    result['wait_min'] = _safe_min_s('FIRSTCLOCKONDATE', 'CREATEDATE')
    result['repair_min'] = _safe_min_s('LASTCLOCKOFFDATE', 'FIRSTCLOCKONDATE')
    result['wait_assign_min'] = _safe_min_s('ASSIGNED_DATE', 'CREATEDATE')
    result['wait_ack_min'] = _safe_min_s('ACK_DATE', 'ASSIGNED_DATE')
    result['inspect_min'] = _safe_min_s('INSPECT_END', 'INSPECT_START')
    result['close_wait_min'] = _safe_min_s('COMPLETEDATE', 'LASTCLOCKOFFDATE')
    _cd = pd.to_datetime(result['CREATEDATE'], errors='coerce') if 'CREATEDATE' in result.columns else None
    _cp = pd.to_datetime(result['COMPLETEDATE'], errors='coerce') if 'COMPLETEDATE' in result.columns else None
    result['job_create_date'] = _cd.apply(_ts_to_iso) if _cd is not None else None
    result['job_complete_date'] = _cp.apply(_ts_to_iso) if _cp is not None else None

    # Drop temp and raw job DB columns (all exposed via job_* derived columns)
    _drop = [
        '_eidx', '_jobid_norm', '_matched_jobid', '_res_norm', '_hist_norm',
        '_overlap', '_runner_overlap', '_rank',
        'JOBORDERNAME', 'JOBMODELNAME', 'SYMPTOMCODENAME', 'CAUSECODENAME',
        'REPAIRCODENAME', 'COMPLETE_FULLNAME', 'FIRSTCLOCKONDATE', 'LASTCLOCKOFFDATE',
        'CREATEDATE', 'COMPLETEDATE', 'ASSIGNED_DATE', 'ACK_DATE', 'INSPECT_START', 'INSPECT_END',
        'RESOURCEID',
    ]
    result = result.drop(columns=[c for c in _drop if c in result.columns])
    return result


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

    first_clock = job.get('FIRSTCLOCKONDATE')
    last_clock = job.get('LASTCLOCKOFFDATE')
    create_date = job.get('CREATEDATE')
    complete_date = job.get('COMPLETEDATE')
    assigned_date = job.get('ASSIGNED_DATE')
    ack_date = job.get('ACK_DATE')
    inspect_start = job.get('INSPECT_START')
    inspect_end = job.get('INSPECT_END')

    def _min(t_end: Any, t_start: Any) -> Optional[float]:
        if (t_end is not None and pd.notna(t_end)
                and t_start is not None and pd.notna(t_start)):
            try:
                v = round((t_end - t_start).total_seconds() / 60.0, 2)
                return v if v >= 0 else None
            except Exception:
                pass
        return None

    row['match_source'] = match_source
    row['match_ambiguous'] = match_ambiguous
    row['job_id'] = _safe_str(job.get('JOBID'))
    row['job_order_name'] = _safe_str(job.get('JOBORDERNAME'))
    row['job_model'] = _safe_str(job.get('JOBMODELNAME'))
    row['symptom'] = _safe_str(job.get('SYMPTOMCODENAME'))
    row['cause'] = _safe_str(job.get('CAUSECODENAME'))
    row['repair'] = _safe_str(job.get('REPAIRCODENAME'))
    row['handler'] = _safe_str(job.get('COMPLETE_FULLNAME'))
    # Legacy combined wait (CREATE -> FIRST_CLOCK)
    row['wait_min'] = _min(first_clock, create_date)
    row['repair_min'] = _min(last_clock, first_clock)
    # Detailed segments from JOBTXNHISTORY (None when DuckDB path or data missing)
    row['wait_assign_min'] = _min(assigned_date, create_date)
    row['wait_ack_min'] = _min(ack_date, assigned_date)
    row['inspect_min'] = _min(inspect_end, inspect_start)
    row['close_wait_min'] = _min(complete_date, last_clock)
    row['job_create_date'] = _ts_to_iso(create_date)
    row['job_complete_date'] = _ts_to_iso(complete_date)
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
    row['wait_assign_min'] = None
    row['wait_ack_min'] = None
    row['inspect_min'] = None
    row['close_wait_min'] = None
    row['job_create_date'] = None
    row['job_complete_date'] = None
    return row


def _add_empty_job_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Add empty JOB enrichment columns to an event DataFrame."""
    df = df.copy()
    for col in ('match_source', 'match_ambiguous', 'job_id', 'job_order_name', 'job_model',
                'symptom', 'cause', 'repair', 'handler', 'wait_min', 'repair_min',
                'wait_assign_min', 'wait_ack_min', 'inspect_min', 'close_wait_min',
                'job_create_date', 'job_complete_date'):
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


def make_raw_spool_query_id(params: dict) -> str:
    """Deterministic hash for raw spool cache key (DA-06 + SCHEMA_VERSION per D4).

    SCHEMA_VERSION participates alongside DOWNTIME_BRIDGE_VERSION.  Bumping either
    constant orphans existing raw parquets by key so readers miss-and-rewrite rather
    than read an incompatible file.
    """
    from mes_dashboard.services.downtime_analysis_cache import _SCHEMA_VERSION
    keyed = dict(params)
    keyed['_bridge_version'] = DOWNTIME_BRIDGE_VERSION
    keyed['_schema_version'] = _SCHEMA_VERSION
    canonical = json.dumps(keyed, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:16]


# ============================================================
# Taxonomy JSON builder (AC-4, design.md D5)
# ============================================================


def _build_taxonomy_json() -> Dict[str, Any]:
    """Serialize _BIG_CATEGORY_MAP and _PREFIX_CATEGORIES to server-authoritative taxonomy.

    Returns:
        {
            "map": [[reason, category], ...],        # exact-match rows
            "prefixes": [[prefix, category], ...],   # prefix-match rules
            "egt_category": "工程",                   # all EGT events (DA-04 Rule 1)
            "fallback": "其他/未分類"                  # unknown/blank reasons
        }

    Server is single source of truth (design.md D5; DA-04).  Browser applies
    taxonomy as a SQL CASE/join without a rebuild when reason codes change.
    """
    map_entries = [[k, v] for k, v in sorted(_BIG_CATEGORY_MAP.items())]
    prefix_entries = [[p, cat] for p, cat in _PREFIX_CATEGORIES]
    return {
        'map': map_entries,
        'prefixes': prefix_entries,
        'egt_category': '工程',
        'fallback': '其他/未分類',
    }


def _build_resource_lookup() -> Dict[str, Any]:
    """Return {historyid: {resource_name, workcenter, family}} for browser enrichment."""
    try:
        from mes_dashboard.services.resource_cache import get_all_resources
        resources = get_all_resources()
        lookup: Dict[str, Any] = {}
        for r in resources:
            rid = str(r.get('RESOURCEID', '') or '').strip()
            if rid:
                lookup[rid] = {
                    'resource_name': str(r.get('RESOURCENAME', '') or '').strip() or None,
                    'workcenter': str(r.get('WORKCENTERNAME', '') or '').strip() or None,
                    'family': str(r.get('RESOURCEFAMILYNAME', '') or '').strip() or None,
                }
        return lookup
    except Exception:
        return {}


# ============================================================
# Raw-spool writer (browser-DuckDB path, AC-2, DA-12)
# ============================================================


def query_downtime_dataset_raw(
    *,
    start_date: str,
    end_date: str,
    workcenter_groups: Optional[List[str]] = None,
    families: Optional[List[str]] = None,
    resource_ids: Optional[List[str]] = None,
    package_groups: Optional[List[str]] = None,
    locations: Optional[List[str]] = None,
    big_categories: Optional[List[str]] = None,
    status_types: Optional[List[str]] = None,
    is_production: bool = False,
    is_key: bool = False,
    is_monitor: bool = False,
) -> Dict[str, Any]:
    """Write two raw spool parquets and return their download URLs + taxonomy.

    Implements the browser-DuckDB path (design.md D7, DA-12):
    - Acquires base_events (7 cols) and job_bridge (16 cols) from DuckDB prewarm
      or Oracle BQE fallback — one whole-dataset chunk (ADR-0003).
    - Writes each DataFrame to its own spool namespace without running any
      pandas reductions (no _merge_cross_shift_events, no _bridge_jobid,
      no _enrich_events_df on the request path).
    - Returns {base_spool_url, jobs_spool_url, query_id, taxonomy}.

    Two-parquet atomicity (DA-11, AC-7): if the base spool is present but the
    job spool is absent/expired, raises RuntimeError rather than silently
    returning an empty join.
    """
    from mes_dashboard.services.downtime_analysis_cache import (
        _BASE_EVENTS_NAMESPACE,
        _JOB_BRIDGE_NAMESPACE,
        has_downtime_base_events,
        has_downtime_job_bridge,
        store_downtime_base_events,
        store_downtime_job_bridge,
    )

    query_id_input = {
        'start_date': start_date,
        'end_date': end_date,
        'workcenter_groups': sorted(workcenter_groups or []),
        'families': sorted(families or []),
        'resource_ids': sorted(resource_ids or []),
        'package_groups': sorted(package_groups or []),
        'locations': sorted(locations or []),
    }
    query_id = make_raw_spool_query_id(query_id_input)

    # ── Two-parquet atomicity check (AC-7, DA-11) ─────────────────────────────
    # If base spool exists but job spool is absent/expired, refuse to serve
    # silently empty join — raise loudly so the client gets a 500 (not empty).
    base_hit = has_downtime_base_events(query_id)
    job_hit = has_downtime_job_bridge(query_id)

    if base_hit and job_hit:
        # Both spools fresh — build URL response without hitting Oracle
        taxonomy = _build_taxonomy_json()
        return {
            'base_spool_url': f'/api/spool/{_BASE_EVENTS_NAMESPACE}/{query_id}.parquet',
            'jobs_spool_url': f'/api/spool/{_JOB_BRIDGE_NAMESPACE}/{query_id}.parquet',
            'query_id': query_id,
            'taxonomy': taxonomy,
            'resource_lookup': _build_resource_lookup(),
        }

    if base_hit and not job_hit:
        # Atomicity violation: base present, job missing/expired — raise loudly (DA-11)
        raise RuntimeError(
            f"Downtime raw spool atomicity error: base_events spool exists for "
            f"query_id={query_id} but job_bridge spool is missing or expired. "
            "This indicates a partial write or TTL mismatch. Re-run the query to refresh both spools."
        )

    # ── Data acquisition: DuckDB prewarm or Oracle BQE fallback ───────────────
    _ddb_base: Optional[pd.DataFrame] = None
    _ddb_job: Optional[pd.DataFrame] = None
    try:
        from mes_dashboard.services.downtime_analysis_duckdb_cache import (
            should_use_duckdb as _should_use_duckdb,
            query_base_from_duckdb as _qbase,
            query_job_from_duckdb as _qjob,
        )
        if _should_use_duckdb(end_date, start_date):
            _ddb_base = _qbase(start_date, end_date)
            _ddb_job = _qjob(start_date, end_date)
            logger.debug(
                "downtime_analysis_raw: DuckDB path — %d base_events, %d job_data",
                len(_ddb_base), len(_ddb_job),
            )
    except Exception as _ddb_exc:
        logger.debug(
            "downtime_analysis_raw: DuckDB path unavailable, falling back to Oracle: %s",
            _ddb_exc,
        )

    if _ddb_base is not None:
        base_df = _ddb_base
        job_df = _ddb_job if _ddb_job is not None else pd.DataFrame()
        # Apply resource filters before writing raw spool (DuckDB fast path)
        if not base_df.empty:
            base_df = _apply_resource_filters(
                base_df, workcenter_groups, families, resource_ids, package_groups,
                is_production=is_production, is_key=is_key, is_monitor=is_monitor,
                locations=locations,
            )
    else:
        # ── Oracle BQE fallback (ADR-0003: one whole-dataset chunk, no chunking) ──
        from mes_dashboard.core.database import read_sql_df_slow as _read_sql_df
        from mes_dashboard.services.batch_query_engine import (
            compute_query_hash as _compute_query_hash,
            decompose_by_time_range as _decompose_date_range,
            execute_plan,
            merge_chunks_to_spool,
        )
        from mes_dashboard.core.query_spool_store import QUERY_SPOOL_DIR

        sql_dir = Path(__file__).resolve().parent.parent / 'sql' / 'downtime_analysis'
        base_sql = (sql_dir / 'base_events.sql').read_text(encoding='utf-8')
        job_sql = (sql_dir / 'job_bridge.sql').read_text(encoding='utf-8')

        base_params = {'start_date': start_date, 'end_date': end_date}

        # One whole-dataset chunk (ADR-0003 — no USE_ROW_COUNT_CHUNKING)
        whole_dataset_chunk = _decompose_date_range(start_date, end_date)
        engine_hash = _compute_query_hash({
            'downtime_base_events_raw': True,
            'start_date': start_date,
            'end_date': end_date,
            '_schema_version': query_id,
        })

        def _run_base_chunk(chunk, max_rows_per_chunk=None):
            params = {
                'start_date': chunk['chunk_start'],
                'end_date': chunk['chunk_end'],
            }
            result = _read_sql_df(base_sql, params, caller='downtime_analysis_raw:base_events')
            return result if result is not None else pd.DataFrame()

        execute_plan(
            whole_dataset_chunk,
            _run_base_chunk,
            parallel=_DOWNTIME_ENGINE_PARALLEL,
            query_hash=engine_hash,
            cache_prefix='downtime_analysis_raw',
        )

        _spool_dir = QUERY_SPOOL_DIR / 'downtime_analysis_raw'
        tmp_path, _total_rows = merge_chunks_to_spool(
            'downtime_analysis_raw',
            engine_hash,
            spool_dir=_spool_dir,
        )

        if tmp_path is not None and tmp_path.exists():
            base_df = pd.read_parquet(str(tmp_path))
            try:
                tmp_path.unlink()
            except Exception:
                pass
        else:
            base_df = pd.DataFrame()

        # Apply resource filters on assembled DataFrame
        if not base_df.empty:
            base_df = _apply_resource_filters(
                base_df, workcenter_groups, families, resource_ids, package_groups,
                is_production=is_production, is_key=is_key, is_monitor=is_monitor,
                locations=locations,
            )

        # Job bridge Oracle query
        if not base_df.empty and 'HISTORYID' in base_df.columns:
            hist_ids = sorted({
                str(x).strip() for x in base_df['HISTORYID'].dropna() if str(x).strip()
            })
        else:
            hist_ids = []

        if hist_ids:
            from mes_dashboard.sql.builder import QueryBuilder as _QB
            _jb_builder = _QB()
            _jb_builder.add_in_condition('RESOURCEID', hist_ids)
            resource_filter_sql = _jb_builder.get_conditions_sql() or '1=1'
            job_sql_rendered = job_sql.replace('{{ RESOURCE_FILTER }}', resource_filter_sql)
            job_params = {**base_params, **_jb_builder.params}
        else:
            job_sql_rendered = job_sql.replace('{{ RESOURCE_FILTER }}', '1=0')
            job_params = base_params

        job_df = _read_sql_df(job_sql_rendered, job_params, caller='downtime_analysis_raw:job_bridge')
        if job_df is None:
            job_df = pd.DataFrame()

    # ── Write both raw spools atomically ──────────────────────────────────────
    # Write base_events first, then job_bridge.  If either write fails, the
    # next request will trigger a full re-fetch (no partial state served).
    store_downtime_base_events(query_id, base_df, end_date=end_date)
    store_downtime_job_bridge(query_id, job_df, end_date=end_date)

    taxonomy = _build_taxonomy_json()
    return {
        'base_spool_url': f'/api/spool/{_BASE_EVENTS_NAMESPACE}/{query_id}.parquet',
        'jobs_spool_url': f'/api/spool/{_JOB_BRIDGE_NAMESPACE}/{query_id}.parquet',
        'query_id': query_id,
        'taxonomy': taxonomy,
        'resource_lookup': _build_resource_lookup(),
    }


# ============================================================
# Filter options (DA-01, AC-6)
# ============================================================

def get_filter_options(
    workcenter_groups: Optional[List[str]] = None,
    families: Optional[List[str]] = None,
    resource_ids: Optional[List[str]] = None,
    package_groups: Optional[List[str]] = None,
    locations: Optional[List[str]] = None,
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

        if locations:
            loc_set = set(locations)
            filtered = [r for r in filtered if r.get('LOCATIONNAME') in loc_set]

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

        # Locations from filtered resources (guard against NaN from Oracle NULL via pandas)
        loc_list = sorted({
            v for r in filtered
            if isinstance(v := r.get('LOCATIONNAME'), str) and v
        })

        # Big categories and reasons from taxonomy
        big_cats = ['維修', '保養', '改機換料', '治工具更換與模具清潔', '教讀程式', '檢查', '待料待指示', '工程', '其他/未分類']
        reasons = sorted(_BIG_CATEGORY_MAP.keys())

        return {
            'workcenter_groups': wc_groups,
            'locations': loc_list,
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
    locations: Optional[List[str]] = None,
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
        decompose_by_time_range as _decompose_date_range,
        execute_plan,
        merge_chunks_to_spool,
    )
    from mes_dashboard.core.query_spool_store import QUERY_SPOOL_DIR
    from pathlib import Path

    query_id_input = {
        'start_date': start_date,
        'end_date': end_date,
        'workcenter_groups': sorted(workcenter_groups or []),
        'families': sorted(families or []),
        'resource_ids': sorted(resource_ids or []),
        'package_groups': sorted(package_groups or []),
        'locations': sorted(locations or []),
        'big_categories': sorted(big_categories or []),
        'status_types': sorted(status_types or []),
    }
    query_id = make_downtime_query_id(query_id_input)

    if has_downtime_events(query_id):
        events_df = load_downtime_events(query_id)
        if events_df is not None and not events_df.empty:
            return _build_response(query_id, events_df)

    # --- Data acquisition: DuckDB fast path or Oracle+BQE fallback ---
    _ddb_base: Optional[pd.DataFrame] = None
    _ddb_job: Optional[pd.DataFrame] = None
    try:
        from mes_dashboard.services.downtime_analysis_duckdb_cache import (
            should_use_duckdb as _should_use_duckdb,
            query_base_from_duckdb as _qbase,
            query_job_from_duckdb as _qjob,
        )
        if _should_use_duckdb(end_date, start_date):
            _ddb_base = _qbase(start_date, end_date)
            _ddb_job = _qjob(start_date, end_date)
            logger.debug(
                "downtime_analysis: DuckDB path — %d base_events, %d job_data",
                len(_ddb_base), len(_ddb_job),
            )
    except Exception as _ddb_exc:
        logger.debug(
            "downtime_analysis: DuckDB path unavailable, falling back to Oracle: %s", _ddb_exc
        )

    if _ddb_base is not None:
        base_df = _ddb_base
        job_df = _ddb_job if _ddb_job is not None else pd.DataFrame()
        # DuckDB fast path: apply filters and cross-shift merge on pandas DataFrame
        # (3-month pre-warmed data; smaller dataset, pandas is fine here)
        if not base_df.empty:
            base_df = _apply_resource_filters(
                base_df, workcenter_groups, families, resource_ids, package_groups,
                is_production=is_production, is_key=is_key, is_monitor=is_monitor,
                locations=locations,
            )
        merged_df = _merge_cross_shift_events(base_df) if not base_df.empty else pd.DataFrame()
    else:
        # --- BatchQueryEngine path (BQE-07) ---
        # ADR-0003: date-range chunking with parallel fetch; reductions run on fully assembled DataFrame.
        sql_dir = Path(__file__).resolve().parent.parent / 'sql' / 'downtime_analysis'
        base_sql = (sql_dir / 'base_events.sql').read_text(encoding='utf-8')
        job_sql = (sql_dir / 'job_bridge.sql').read_text(encoding='utf-8')

        base_params = {'start_date': start_date, 'end_date': end_date}

        # Date-range chunks for parallel fetch; post-merge stage (ADR-0003) runs on assembled DataFrame.
        whole_dataset_chunk = _decompose_date_range(start_date, end_date)
        engine_hash = _compute_query_hash({
            'downtime_base_events': True,
            'start_date': start_date,
            'end_date': end_date,
        })

        def _run_base_chunk(chunk, max_rows_per_chunk=None):
            params = {
                'start_date': chunk['chunk_start'],
                'end_date': chunk['chunk_end'],
            }
            result = _read_sql_df(base_sql, params, caller='downtime_analysis:base_events')
            return result if result is not None else pd.DataFrame()

        execute_plan(
            whole_dataset_chunk,
            _run_base_chunk,
            parallel=_DOWNTIME_ENGINE_PARALLEL,
            query_hash=engine_hash,
            cache_prefix='downtime_analysis',
        )

        _spool_dir = QUERY_SPOOL_DIR / 'downtime_analysis'
        tmp_path, _total_rows = merge_chunks_to_spool(
            'downtime_analysis',
            engine_hash,
            spool_dir=_spool_dir,
        )

        # --- DuckDB path: extract HISTORYIDs and run cross-shift merge without loading
        #     the full raw dataset into Python RAM (ADR-0003 reductions still apply).
        _spool_exists = tmp_path is not None and tmp_path.exists()

        # Step 1: Get DISTINCT HISTORYIDs from parquet for job_bridge filter.
        # Uses a DuckDB scan (columnar, no full load) instead of pd.read_parquet.
        if _spool_exists:
            try:
                import duckdb as _ddb_scan
                _hist_rows = _ddb_scan.sql(
                    f"SELECT DISTINCT TRIM(CAST(HISTORYID AS VARCHAR)) "
                    f"FROM read_parquet('{tmp_path}') WHERE HISTORYID IS NOT NULL"
                ).fetchall()
                hist_ids = sorted({r[0] for r in _hist_rows if r[0]})
            except Exception as _scan_exc:
                logger.warning("DuckDB HISTORYID scan failed (%s); loading parquet column", _scan_exc)
                _col_df = pd.read_parquet(str(tmp_path), columns=['HISTORYID'])
                hist_ids = sorted({str(x).strip() for x in _col_df['HISTORYID'].dropna() if str(x).strip()})
        else:
            hist_ids = []

        # Step 2: Build job_bridge RESOURCEID filter and query Oracle.
        if hist_ids:
            from mes_dashboard.sql.builder import QueryBuilder as _QB
            _jb_builder = _QB()
            _jb_builder.add_in_condition('RESOURCEID', hist_ids)
            resource_filter_sql = _jb_builder.get_conditions_sql() or '1=1'
            job_sql_rendered = job_sql.replace('{{ RESOURCE_FILTER }}', resource_filter_sql)
            job_params = {**base_params, **_jb_builder.params}
        else:
            job_sql_rendered = job_sql.replace('{{ RESOURCE_FILTER }}', '1=0')
            job_params = base_params

        job_df = _read_sql_df(job_sql_rendered, job_params, caller='downtime_analysis:job_bridge')
        if job_df is None:
            job_df = pd.DataFrame()

        # Step 3: DuckDB cross-shift merge — processes parquet in columnar streaming,
        # never materialises 184k raw rows in Python RAM; returns reduced merged_df.
        if _spool_exists:
            merged_df = _merge_cross_shift_events_from_parquet(tmp_path)
            try:
                tmp_path.unlink()
            except Exception:
                pass
        else:
            merged_df = pd.DataFrame()

        # Step 4: resource filters applied on the already-reduced merged_df.
        if not merged_df.empty:
            merged_df = _apply_resource_filters(
                merged_df, workcenter_groups, families, resource_ids, package_groups,
                is_production=is_production, is_key=is_key, is_monitor=is_monitor,
            )
        base_df = pd.DataFrame()  # base_df is no longer needed; clear for GC

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
    locations: Optional[List[str]] = None,
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
        if not base_ids:
            logger.warning(
                "_apply_resource_filters: resource cache empty — skipping baseline ID filter "
                "(returning all %d rows unfiltered)", len(df)
            )
        else:
            df = df[df['HISTORYID'].apply(lambda x: str(x).strip()).isin(base_ids)]

        if df.empty:
            return df

        allowed_hist_ids: Optional[set] = None

        if workcenter_groups or families or package_groups or is_production or is_key or is_monitor or locations:
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
            if locations:
                loc_set = set(locations)
                filtered = [r for r in filtered if r.get('LOCATIONNAME') in loc_set]
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
        # _map_big_category is deterministic for (reason, status), so first value is representative
        big_category = str(grp['category'].iloc[0]) if 'category' in grp.columns and len(grp) > 0 else ''
        rows.append({
            'reason': reason,
            'status': status,
            'big_category': big_category,
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
        udt_grp = grp.loc[grp['status'] == 'UDT']
        sdt_grp = grp.loc[grp['status'] == 'SDT']
        egt_grp = grp.loc[grp['status'] == 'EGT']
        udt = float(udt_grp['hours'].sum())
        sdt = float(sdt_grp['hours'].sum())
        egt = float(egt_grp['hours'].sum())
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
            'udt_event_count': len(udt_grp),
            'sdt_event_count': len(sdt_grp),
            'egt_event_count': len(egt_grp),
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
                'wait_assign_min': row.get('wait_assign_min'),
                'wait_ack_min': row.get('wait_ack_min'),
                'inspect_min': row.get('inspect_min'),
                'close_wait_min': row.get('close_wait_min'),
                'job_create_date': row.get('job_create_date'),
                'job_complete_date': row.get('job_complete_date'),
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
