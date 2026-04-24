# -*- coding: utf-8 -*-
"""Hold Today Snapshot service — 當日 and 現況 mode snapshots."""

from __future__ import annotations

import hashlib
import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from mes_dashboard.core.database import (
    DatabaseCircuitOpenError,
    DatabasePoolExhaustedError,
    read_sql_df_slow as read_sql_df,
)
from mes_dashboard.core.redis_client import get_key, get_redis_client
from mes_dashboard.config.constants import CACHE_TTL_HOLD_TODAY
from mes_dashboard.services.filter_cache import get_workcenter_group as _get_wc_group
from mes_dashboard.sql.filters import CommonFilters

logger = logging.getLogger('mes_dashboard.hold_today_snapshot_service')

_SQL_DIR = Path(__file__).resolve().parent.parent / 'sql' / 'hold_history'
_VALID_HOLD_TYPES = {'quality', 'non-quality', 'all'}
_VALID_DURATION_RANGES = {'<4h', '4-24h', '1-3d', '>3d'}
_VALID_SNAPSHOT_MODES = {'today', 'current'}
_CACHE_NAMESPACE = 'hold_today'

_DURATION_BUCKETS = [
    ('<4h',   0,    4),
    ('4-24h', 4,    24),
    ('1-3d',  24,   72),
    ('>3d',   72,   None),
]


@lru_cache(maxsize=4)
def _load_today_snapshot_sql() -> str:
    path = _SQL_DIR / 'today_snapshot.sql'
    if not path.exists():
        raise FileNotFoundError(f'SQL file not found: {path}')
    sql = path.read_text(encoding='utf-8')
    if '{{ NON_QUALITY_REASONS }}' in sql:
        sql = sql.replace('{{ NON_QUALITY_REASONS }}', CommonFilters.get_non_quality_reasons_sql())
    return sql


@lru_cache(maxsize=4)
def _load_current_snapshot_sql() -> str:
    path = _SQL_DIR / 'current_snapshot.sql'
    if not path.exists():
        raise FileNotFoundError(f'SQL file not found: {path}')
    sql = path.read_text(encoding='utf-8')
    if '{{ NON_QUALITY_REASONS }}' in sql:
        sql = sql.replace('{{ NON_QUALITY_REASONS }}', CommonFilters.get_non_quality_reasons_sql())
    return sql


def _normalize_hold_type(value: Optional[str], default: str = 'quality') -> str:
    v = str(value or default).strip().lower()
    return v if v in _VALID_HOLD_TYPES else default


def _normalize_snapshot_mode(value: Optional[str], default: str = 'today') -> str:
    v = str(value or default).strip().lower()
    return v if v in _VALID_SNAPSHOT_MODES else default


def _safe_int(value: Any) -> int:
    if value is None:
        return 0
    try:
        if pd.isna(value):
            return 0
    except Exception:
        pass
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _safe_float(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        if pd.isna(value):
            return 0.0
    except Exception:
        pass
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _clean_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    text = str(value).strip()
    return text or None


def _format_datetime(value: Any) -> Optional[str]:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    try:
        import pandas as _pd
        ts = _pd.to_datetime(value)
        return ts.strftime('%Y-%m-%d %H:%M:%S')
    except Exception:
        return str(value)


def _cache_key(snapshot_mode: str, hold_type: str, record_type: str, reason: Optional[str],
               duration_range: Optional[str], page: int, per_page: int) -> str:
    parts = f'{snapshot_mode}:{hold_type}:{record_type}:{reason or ""}:{duration_range or ""}:{page}:{per_page}'
    digest = hashlib.md5(parts.encode()).hexdigest()[:12]
    return get_key(f'{_CACHE_NAMESPACE}:{digest}')


def _get_cache(key: str) -> Optional[Dict[str, Any]]:
    client = get_redis_client()
    if client is None:
        return None
    try:
        payload = client.get(key)
        if not payload:
            return None
        return json.loads(payload)
    except Exception as exc:
        logger.warning('hold_today cache read failed for key %s: %s', key, exc)
        return None


def _set_cache(key: str, data: Dict[str, Any]) -> None:
    client = get_redis_client()
    if client is None:
        return
    try:
        client.setex(key, CACHE_TTL_HOLD_TODAY, json.dumps(data, ensure_ascii=False, default=str))
    except Exception as exc:
        logger.warning('hold_today cache write failed for key %s: %s', key, exc)


def _apply_record_type_filter_today(df: pd.DataFrame, record_type: str) -> pd.DataFrame:
    """Filter for 當日 mode.

    on_hold → lots in the shift snapshot (hold_day <= today AND unreleased OR released after shift)
    new     → hold_day = today
    release → release_day = today
    """
    types = {t.strip().lower() for t in record_type.split(',') if t.strip()}
    masks = []
    today = df['TODAY_DATE'].iloc[0] if not df.empty else None
    if 'on_hold' in types:
        masks.append(df['RELEASETXNDATE'].isna() | (df['RELEASE_DAY'] > df['TODAY_DATE']))
    if 'new' in types:
        masks.append(df['HOLD_DAY'] == df['TODAY_DATE'])
    if 'release' in types:
        masks.append(df['RELEASE_DAY'] == df['TODAY_DATE'])
    if not masks:
        return df.iloc[0:0]
    combined = masks[0]
    for m in masks[1:]:
        combined = combined | m
    return df[combined]


def _apply_record_type_filter_current(df: pd.DataFrame, record_type: str) -> pd.DataFrame:
    """Filter for 現況 mode.

    on_hold → RELEASETXNDATE IS NULL (live unreleased)
    new     → hold_day = today_date (current shift start)
    release → release_day = today_date (current shift start)
    """
    types = {t.strip().lower() for t in record_type.split(',') if t.strip()}
    masks = []
    if 'on_hold' in types:
        masks.append(df['RELEASETXNDATE'].isna())
    if 'new' in types:
        masks.append(df['HOLD_DAY'] == df['TODAY_DATE'])
    if 'release' in types:
        masks.append(df['RELEASE_DAY'] == df['TODAY_DATE'])
    if not masks:
        return df.iloc[0:0]
    combined = masks[0]
    for m in masks[1:]:
        combined = combined | m
    return df[combined]


def _apply_reason_filter(df: pd.DataFrame, reason: Optional[str]) -> pd.DataFrame:
    if not reason:
        return df
    return df[df['HOLDREASONNAME'] == reason]


def _apply_duration_filter(df: pd.DataFrame, duration_range: Optional[str]) -> pd.DataFrame:
    if not duration_range or duration_range not in _VALID_DURATION_RANGES:
        return df
    for label, lo, hi in _DURATION_BUCKETS:
        if label == duration_range:
            mask = df['HOLD_HOURS'] >= lo
            if hi is not None:
                mask = mask & (df['HOLD_HOURS'] < hi)
            return df[mask]
    return df


def _repeat_quality_qty(df: pd.DataFrame, today_date: Any) -> int:
    """Lots with same container+reason repeated hold in the shift (RN_FUTURE_REASON > 1, quality)."""
    if df.empty:
        return 0
    shift_new = df[df['HOLD_DAY'] == today_date]
    if shift_new.empty:
        return 0
    repeat = shift_new[(shift_new['RN_FUTURE_REASON'] > 1) & (shift_new['HOLD_TYPE'] == 'quality')]
    return _safe_int(repeat['QTY'].sum())


def _build_today_summary(df: pd.DataFrame) -> Dict[str, Any]:
    """Summary for 當日 mode.

    ON HOLD = point-in-time snapshot at shift boundary:
      hold_day <= today AND (release_day IS NULL OR release_day > today)
    Hours frozen at LEAST(SYSDATE, 07:30 today) via SQL.
    """
    if df.empty:
        return {
            'onHoldLots': 0, 'onHoldQty': 0,
            'todayNewQty': 0, 'todayReleaseQty': 0, 'todayFutureHoldQty': 0,
            'repeatQualityHoldQty': 0,
            'onHoldAvgHours': 0.0, 'onHoldMaxHours': 0.0,
        }

    today = df['TODAY_DATE'].iloc[0]

    snapshot = df[
        df['RELEASETXNDATE'].isna() | (df['RELEASE_DAY'] > df['TODAY_DATE'])
    ]
    today_new = df[df['HOLD_DAY'] == today]
    today_release = df[df['RELEASE_DAY'] == today]
    today_future = today_new[today_new['FUTUREHOLDCOMMENTS'].notna()]

    return {
        'onHoldLots': int(snapshot['CONTAINERID'].nunique()),
        'onHoldQty': _safe_int(snapshot['QTY'].sum()),
        'todayNewQty': _safe_int(today_new['QTY'].sum()),
        'todayReleaseQty': _safe_int(today_release['QTY'].sum()),
        'todayFutureHoldQty': _safe_int(today_future['QTY'].sum()),
        'repeatQualityHoldQty': _repeat_quality_qty(df, today),
        'onHoldAvgHours': round(_safe_float(snapshot['HOLD_HOURS'].mean()) if not snapshot.empty else 0.0, 2),
        'onHoldMaxHours': round(_safe_float(snapshot['HOLD_HOURS'].max()) if not snapshot.empty else 0.0, 2),
    }


def _build_current_summary(df: pd.DataFrame) -> Dict[str, Any]:
    """Summary for 現況 mode.

    ON HOLD = live unreleased lots only.
    Hours use SYSDATE (live duration) via SQL.
    """
    if df.empty:
        return {
            'onHoldLots': 0, 'onHoldQty': 0,
            'currentNewQty': 0, 'currentReleaseQty': 0, 'currentFutureHoldQty': 0,
            'repeatQualityHoldQty': 0,
            'onHoldAvgHours': 0.0, 'onHoldMaxHours': 0.0,
        }

    today = df['TODAY_DATE'].iloc[0]
    on_hold = df[df['RELEASETXNDATE'].isna()]
    current_new = df[df['HOLD_DAY'] == today]
    current_release = df[df['RELEASE_DAY'] == today]
    current_future = current_new[current_new['FUTUREHOLDCOMMENTS'].notna()]

    return {
        'onHoldLots': int(on_hold['CONTAINERID'].nunique()),
        'onHoldQty': _safe_int(on_hold['QTY'].sum()),
        'currentNewQty': _safe_int(current_new['QTY'].sum()),
        'currentReleaseQty': _safe_int(current_release['QTY'].sum()),
        'currentFutureHoldQty': _safe_int(current_future['QTY'].sum()),
        'repeatQualityHoldQty': _repeat_quality_qty(df, today),
        'onHoldAvgHours': round(_safe_float(on_hold['HOLD_HOURS'].mean()) if not on_hold.empty else 0.0, 2),
        'onHoldMaxHours': round(_safe_float(on_hold['HOLD_HOURS'].max()) if not on_hold.empty else 0.0, 2),
    }


def _build_reason_pareto(df: pd.DataFrame) -> Dict[str, Any]:
    if df.empty:
        return {'items': []}
    grouped = df.groupby('HOLDREASONNAME', dropna=False).agg(
        ITEM_COUNT=('CONTAINERID', 'count'),
        QTY=('QTY', 'sum'),
    ).reset_index()
    total_qty = grouped['QTY'].sum()
    grouped = grouped.sort_values('QTY', ascending=False)
    items = []
    cum_pct = 0.0
    for _, row in grouped.iterrows():
        pct = round(float(row['QTY']) / total_qty * 100, 2) if total_qty > 0 else 0.0
        cum_pct = round(cum_pct + pct, 2)
        items.append({
            'reason': _clean_text(row['HOLDREASONNAME']) or '(未填寫)',
            'count': _safe_int(row['ITEM_COUNT']),
            'qty': _safe_int(row['QTY']),
            'pct': pct,
            'cumPct': cum_pct,
        })
    return {'items': items}


def _build_duration(df: pd.DataFrame) -> Dict[str, Any]:
    if df.empty:
        return {
            'items': [],
            'avgReleasedHours': 0.0,
            'avgOnHoldHours': 0.0,
            'maxReleasedHours': 0.0,
            'maxOnHoldHours': 0.0,
        }

    on_hold = df[df['RELEASETXNDATE'].isna()]
    released = df[df['RELEASETXNDATE'].notna()]

    total = len(df)
    items = []
    for label, lo, hi in _DURATION_BUCKETS:
        mask = df['HOLD_HOURS'] >= lo
        if hi is not None:
            mask = mask & (df['HOLD_HOURS'] < hi)
        bucket = df[mask]
        count = len(bucket)
        pct = round(count / total * 100, 2) if total > 0 else 0.0
        items.append({
            'range': label,
            'count': count,
            'qty': _safe_int(bucket['QTY'].sum()),
            'pct': pct,
        })

    return {
        'items': items,
        'avgReleasedHours': round(_safe_float(released['HOLD_HOURS'].mean()) if not released.empty else 0.0, 2),
        'avgOnHoldHours': round(_safe_float(on_hold['HOLD_HOURS'].mean()) if not on_hold.empty else 0.0, 2),
        'maxReleasedHours': round(_safe_float(released['HOLD_HOURS'].max()) if not released.empty else 0.0, 2),
        'maxOnHoldHours': round(_safe_float(on_hold['HOLD_HOURS'].max()) if not on_hold.empty else 0.0, 2),
    }


def _build_list(df: pd.DataFrame, page: int, per_page: int) -> Dict[str, Any]:
    total = len(df)
    if per_page <= 0:
        page_df = df
        page = 1
        total_pages = 1
    else:
        offset = (page - 1) * per_page
        page_df = df.iloc[offset:offset + per_page]
        total_pages = (total + per_page - 1) // per_page if total > 0 else 1
    items: List[Dict[str, Any]] = []
    for _, row in page_df.iterrows():
        wc_name = _clean_text(row.get('WORKCENTERNAME'))
        wc_group = _get_wc_group(wc_name) if wc_name else None
        items.append({
            'lotId': _clean_text(row.get('LOT_ID')),
            'workorder': _clean_text(row.get('PJ_WORKORDER')),
            'product': _clean_text(row.get('PRODUCTNAME')),
            'workcenter': wc_group or wc_name,
            'holdReason': _clean_text(row.get('HOLDREASONNAME')),
            'qty': _safe_int(row.get('QTY')),
            'holdDate': _format_datetime(row.get('HOLDTXNDATE')),
            'holdEmp': _clean_text(row.get('HOLDEMP')),
            'holdComment': _clean_text(row.get('HOLDCOMMENTS')),
            'releaseDate': _format_datetime(row.get('RELEASETXNDATE')),
            'releaseEmp': _clean_text(row.get('RELEASEEMP')),
            'releaseComment': _clean_text(row.get('RELEASECOMMENTS')),
            'holdHours': round(_safe_float(row.get('HOLD_HOURS')), 2),
            'ncr': _clean_text(row.get('NCRID')),
            'futureHoldComment': _clean_text(row.get('FUTUREHOLDCOMMENTS')),
        })
    return {
        'items': items,
        'pagination': {
            'page': page,
            'perPage': per_page,
            'total': total,
            'totalPages': total_pages,
        },
    }


def _make_query_id(snapshot_mode: str, hold_type: str) -> str:
    import time
    ts = int(time.time())
    return f'{snapshot_mode}_{hold_type}_{ts}'


def execute_today_snapshot(
    snapshot_mode: Optional[str] = None,
    hold_type: Optional[str] = None,
    record_type: str = 'on_hold',
    reason: Optional[str] = None,
    duration_range: Optional[str] = None,
    page: int = 1,
    per_page: int = 50,
    export_mode: bool = False,
) -> Dict[str, Any]:
    """Return a snapshot for 當日 or 現況 mode.

    snapshot_mode='today'   → 當日 (shift boundary snapshot, TRUNC+1 convention)
    snapshot_mode='current' → 現況 (live real-time state, START-day convention)

    When export_mode=True, all matching rows are returned without pagination and
    the result is not stored in (or read from) the per-page cache.

    Raises DatabaseCircuitOpenError or DatabasePoolExhaustedError on DB failure.
    """
    sm = _normalize_snapshot_mode(snapshot_mode)
    ht = _normalize_hold_type(hold_type)
    page = max(int(page or 1), 1)
    if export_mode:
        per_page_eff = 0  # sentinel: return all rows
    else:
        per_page_eff = max(1, min(int(per_page or 50), 200))
    if not export_mode:
        cache_key = _cache_key(sm, ht, record_type, reason, duration_range, page, per_page_eff)
        cached = _get_cache(cache_key)
        if cached is not None:
            return cached

    sql = _load_today_snapshot_sql() if sm == 'today' else _load_current_snapshot_sql()
    df = read_sql_df(sql, {})

    if df is None or df.empty:
        df = pd.DataFrame()

    if not df.empty and ht != 'all':
        df = df[df['HOLD_TYPE'] == ht]

    if sm == 'today':
        summary = _build_today_summary(df)
        df_filtered = _apply_record_type_filter_today(df, record_type) if not df.empty else df
    else:
        summary = _build_current_summary(df)
        df_filtered = _apply_record_type_filter_current(df, record_type) if not df.empty else df

    df_filtered = _apply_reason_filter(df_filtered, reason)
    df_filtered = _apply_duration_filter(df_filtered, duration_range)

    result: Dict[str, Any] = {
        'query_id': _make_query_id(sm, ht),
        'snapshot_mode': sm,
        'summary': summary,
        'reason_pareto': _build_reason_pareto(df_filtered),
        'duration': _build_duration(df_filtered),
        'list': _build_list(df_filtered, 1 if export_mode else page, per_page_eff),
    }

    if not export_mode:
        _set_cache(cache_key, result)
    return result
