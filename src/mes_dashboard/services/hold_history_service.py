# -*- coding: utf-8 -*-
"""Hold History dashboard service layer."""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterator, Optional

import pandas as pd

from mes_dashboard.core.database import (
    DatabaseCircuitOpenError,
    DatabasePoolExhaustedError,
    read_sql_df_slow as read_sql_df,
)
from mes_dashboard.core.redis_client import get_key, get_redis_client
from mes_dashboard.services.filter_cache import get_workcenter_group as _get_wc_group
from mes_dashboard.sql.filters import CommonFilters

logger = logging.getLogger('mes_dashboard.hold_history_service')

_SQL_DIR = Path(__file__).resolve().parent.parent / 'sql' / 'hold_history'
_VALID_HOLD_TYPES = {'quality', 'non-quality', 'all'}
from mes_dashboard.config.constants import CACHE_TTL_HOLD_TREND
_TREND_CACHE_TTL_SECONDS = CACHE_TTL_HOLD_TREND
_TREND_CACHE_KEY_PREFIX = 'hold_history:daily'


@lru_cache(maxsize=16)
def _load_hold_history_sql(name: str) -> str:
    """Load hold history SQL by file name without extension."""
    path = _SQL_DIR / f'{name}.sql'
    if not path.exists():
        raise FileNotFoundError(f'SQL file not found: {path}')

    sql = path.read_text(encoding='utf-8')
    if '{{ NON_QUALITY_REASONS }}' in sql:
        sql = sql.replace('{{ NON_QUALITY_REASONS }}', CommonFilters.get_non_quality_reasons_sql())
    return sql


def _parse_iso_date(value: str) -> date:
    return datetime.strptime(str(value), '%Y-%m-%d').date()


def _format_iso_date(value: date) -> str:
    return value.strftime('%Y-%m-%d')


def _iter_days(start: date, end: date) -> Iterator[date]:
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def _iter_month_starts(start: date, end: date) -> Iterator[date]:
    current = start.replace(day=1)
    while current <= end:
        yield current
        current = (current.replace(day=28) + timedelta(days=4)).replace(day=1)


def _month_end(month_start: date) -> date:
    next_month_start = (month_start.replace(day=28) + timedelta(days=4)).replace(day=1)
    return next_month_start - timedelta(days=1)


def _is_cacheable_month(month_start: date, today: Optional[date] = None) -> bool:
    current = (today or date.today()).replace(day=1)
    previous = (current - timedelta(days=1)).replace(day=1)
    return month_start in {current, previous}


def _trend_cache_key(month_start: date) -> str:
    return get_key(f'{_TREND_CACHE_KEY_PREFIX}:{month_start.strftime("%Y-%m")}')


def _normalize_hold_type(hold_type: Optional[str], default: str = 'quality') -> str:
    normalized = str(hold_type or default).strip().lower()
    if normalized not in _VALID_HOLD_TYPES:
        return default
    return normalized


def _record_type_flags(record_type: Any) -> Dict[str, int]:
    """Convert record_type value(s) to SQL boolean flags."""
    if isinstance(record_type, (list, tuple, set)):
        types = {str(t).strip().lower() for t in record_type}
    else:
        types = {t.strip().lower() for t in str(record_type or 'new').split(',')}
    return {
        'include_new': 1 if 'new' in types else 0,
        'include_on_hold': 1 if 'on_hold' in types else 0,
        'include_released': 1 if 'released' in types else 0,
    }


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

    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, pd.Timestamp):
        dt = value.to_pydatetime()
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            dt = pd.to_datetime(text).to_pydatetime()
        except Exception:
            return text
    else:
        try:
            dt = pd.to_datetime(value).to_pydatetime()
        except Exception:
            return str(value)

    return dt.strftime('%Y-%m-%d %H:%M:%S')


def _empty_trend_metrics() -> Dict[str, int]:
    return {
        'holdQty': 0,
        'newHoldQty': 0,
        'releaseQty': 0,
        'futureHoldQty': 0,
        'repeatQualityHoldQty': 0,
    }


def _empty_trend_day(day: str) -> Dict[str, Any]:
    return {
        'date': day,
        'quality': _empty_trend_metrics(),
        'non_quality': _empty_trend_metrics(),
        'all': _empty_trend_metrics(),
    }


def _normalize_trend_day(payload: Dict[str, Any], fallback_day: Optional[str] = None) -> Dict[str, Any]:
    day = str(payload.get('date') or fallback_day or '').strip()
    normalized = _empty_trend_day(day)

    for source_key, target_key in (
        ('quality', 'quality'),
        ('non_quality', 'non_quality'),
        ('non-quality', 'non_quality'),
        ('all', 'all'),
    ):
        section = payload.get(source_key)
        if not isinstance(section, dict):
            continue
        normalized[target_key] = {
            'holdQty': _safe_int(section.get('holdQty')),
            'newHoldQty': _safe_int(section.get('newHoldQty')),
            'releaseQty': _safe_int(section.get('releaseQty')),
            'futureHoldQty': _safe_int(section.get('futureHoldQty')),
            'repeatQualityHoldQty': _safe_int(section.get('repeatQualityHoldQty')),
        }

    return normalized


def _build_month_trend_from_df(df: pd.DataFrame) -> list[Dict[str, Any]]:
    if df is None or df.empty:
        return []

    day_map: Dict[str, Dict[str, Any]] = {}

    for _, row in df.iterrows():
        day = str(row.get('TXN_DATE') or '').strip()
        if not day:
            continue

        if day not in day_map:
            day_map[day] = _empty_trend_day(day)

        hold_type = str(row.get('HOLD_TYPE') or '').strip().lower()
        if hold_type == 'non-quality':
            target_key = 'non_quality'
        elif hold_type in {'quality', 'all'}:
            target_key = hold_type
        else:
            continue

        day_map[day][target_key] = {
            'holdQty': _safe_int(row.get('HOLD_QTY')),
            'newHoldQty': _safe_int(row.get('NEW_HOLD_QTY')),
            'releaseQty': _safe_int(row.get('RELEASE_QTY')),
            'futureHoldQty': _safe_int(row.get('FUTURE_HOLD_QTY')),
            'repeatQualityHoldQty': _safe_int(row.get('REPEAT_QUALITY_HOLD_QTY')),
        }

    return [day_map[key] for key in sorted(day_map)]


def _query_month_trend(month_start: date) -> list[Dict[str, Any]]:
    month_end = _month_end(month_start)
    sql = _load_hold_history_sql('trend')
    params = {
        'start_date': _format_iso_date(month_start),
        'end_date': _format_iso_date(month_end),
    }
    df = read_sql_df(sql, params)
    return _build_month_trend_from_df(df)


def _get_month_trend_cache(month_start: date) -> Optional[list[Dict[str, Any]]]:
    client = get_redis_client()
    if client is None:
        return None

    key = _trend_cache_key(month_start)
    try:
        payload = client.get(key)
        if not payload:
            return None
        decoded = json.loads(payload)
        if not isinstance(decoded, list):
            return None

        items: list[Dict[str, Any]] = []
        for item in decoded:
            if not isinstance(item, dict):
                continue
            normalized = _normalize_trend_day(item)
            if normalized.get('date'):
                items.append(normalized)
        if not items:
            return None
        return items
    except Exception as exc:
        logger.warning('Failed reading hold-history trend cache key %s: %s', key, exc)
        return None


def _set_month_trend_cache(month_start: date, items: list[Dict[str, Any]]) -> None:
    client = get_redis_client()
    if client is None:
        return

    key = _trend_cache_key(month_start)
    try:
        client.setex(
            key,
            _TREND_CACHE_TTL_SECONDS,
            json.dumps(items, ensure_ascii=False),
        )
    except Exception as exc:
        logger.warning('Failed writing hold-history trend cache key %s: %s', key, exc)


def _get_month_trend_data(month_start: date) -> list[Dict[str, Any]]:
    if _is_cacheable_month(month_start):
        cached = _get_month_trend_cache(month_start)
        if cached is not None:
            return cached

        queried = _query_month_trend(month_start)
        _set_month_trend_cache(month_start, queried)
        return queried

    return _query_month_trend(month_start)


def get_hold_history_trend(start_date: str, end_date: str) -> Optional[Dict[str, Any]]:
    """Get daily trend data for all hold-type variants."""
    try:
        start = _parse_iso_date(start_date)
        end = _parse_iso_date(end_date)
        if end < start:
            return {'days': []}

        day_map: Dict[str, Dict[str, Any]] = {}
        for month_start in _iter_month_starts(start, end):
            month_days = _get_month_trend_data(month_start)
            for item in month_days:
                normalized = _normalize_trend_day(item)
                day = normalized.get('date')
                if day:
                    day_map[day] = normalized

        days: list[Dict[str, Any]] = []
        for current in _iter_days(start, end):
            current_key = _format_iso_date(current)
            days.append(day_map.get(current_key, _empty_trend_day(current_key)))

        return {'days': days}
    except (DatabasePoolExhaustedError, DatabaseCircuitOpenError):
        raise
    except Exception as exc:
        logger.error('Hold history trend query failed: %s', exc)
        return None


def get_hold_history_reason_pareto(
    start_date: str,
    end_date: str,
    hold_type: str,
    record_type: str = 'new',
) -> Optional[Dict[str, Any]]:
    """Get reason Pareto items."""
    try:
        sql = _load_hold_history_sql('reason_pareto')
        params = {
            'start_date': start_date,
            'end_date': end_date,
            'hold_type': _normalize_hold_type(hold_type),
            **_record_type_flags(record_type),
        }
        df = read_sql_df(sql, params)

        items: list[Dict[str, Any]] = []
        if df is not None and not df.empty:
            for _, row in df.iterrows():
                items.append({
                    'reason': _clean_text(row.get('REASON')) or '(未填寫)',
                    'count': _safe_int(row.get('ITEM_COUNT')),
                    'qty': _safe_int(row.get('QTY')),
                    'pct': round(_safe_float(row.get('PCT')), 2),
                    'cumPct': round(_safe_float(row.get('CUM_PCT')), 2),
                })

        return {'items': items}
    except (DatabasePoolExhaustedError, DatabaseCircuitOpenError):
        raise
    except Exception as exc:
        logger.error('Hold history reason pareto query failed: %s', exc)
        return None


def get_hold_history_duration(
    start_date: str,
    end_date: str,
    hold_type: str,
    record_type: str = 'new',
) -> Optional[Dict[str, Any]]:
    """Get hold duration distribution buckets."""
    try:
        sql = _load_hold_history_sql('duration')
        params = {
            'start_date': start_date,
            'end_date': end_date,
            'hold_type': _normalize_hold_type(hold_type),
            **_record_type_flags(record_type),
        }
        df = read_sql_df(sql, params)

        items: list[Dict[str, Any]] = []
        avg_released_hours = 0.0
        avg_on_hold_hours = 0.0
        max_released_hours = 0.0
        max_on_hold_hours = 0.0
        if df is not None and not df.empty:
            for i, (_, row) in enumerate(df.iterrows()):
                items.append({
                    'range': _clean_text(row.get('RANGE_LABEL')) or '-',
                    'count': _safe_int(row.get('ITEM_COUNT')),
                    'qty': _safe_int(row.get('QTY')),
                    'pct': round(_safe_float(row.get('PCT')), 2),
                })
                if i == 0:
                    avg_released_hours = round(_safe_float(row.get('AVG_RELEASED_HOURS')), 2)
                    avg_on_hold_hours = round(_safe_float(row.get('AVG_ON_HOLD_HOURS')), 2)
                    max_released_hours = round(_safe_float(row.get('MAX_RELEASED_HOURS')), 2)
                    max_on_hold_hours = round(_safe_float(row.get('MAX_ON_HOLD_HOURS')), 2)

        return {
            'items': items,
            'avgReleasedHours': avg_released_hours,
            'avgOnHoldHours': avg_on_hold_hours,
            'maxReleasedHours': max_released_hours,
            'maxOnHoldHours': max_on_hold_hours,
        }
    except (DatabasePoolExhaustedError, DatabaseCircuitOpenError):
        raise
    except Exception as exc:
        logger.error('Hold history duration query failed: %s', exc)
        return None


def get_hold_history_list(
    start_date: str,
    end_date: str,
    hold_type: str,
    reason: Optional[str] = None,
    record_type: str = 'new',
    duration_range: Optional[str] = None,
    page: int = 1,
    per_page: int = 50,
) -> Optional[Dict[str, Any]]:
    """Get paginated hold history detail list."""
    try:
        page = max(int(page or 1), 1)
        per_page = max(1, min(int(per_page or 50), 200))
        offset = (page - 1) * per_page

        sql = _load_hold_history_sql('list')
        params = {
            'start_date': start_date,
            'end_date': end_date,
            'hold_type': _normalize_hold_type(hold_type),
            'reason': reason,
            **_record_type_flags(record_type),
            'duration_range': duration_range,
            'offset': offset,
            'limit': per_page,
        }
        df = read_sql_df(sql, params)

        items: list[Dict[str, Any]] = []
        total = 0

        if df is not None and not df.empty:
            for _, row in df.iterrows():
                if total == 0:
                    total = _safe_int(row.get('TOTAL_COUNT'))

                wc_name = _clean_text(row.get('WORKCENTER'))
                wc_group = _get_wc_group(wc_name) if wc_name else None
                items.append({
                    'lotId': _clean_text(row.get('LOT_ID')),
                    'workorder': _clean_text(row.get('WORKORDER')),
                    'product': _clean_text(row.get('PRODUCT')),
                    'workcenter': wc_group or wc_name,
                    'holdReason': _clean_text(row.get('HOLD_REASON')),
                    'qty': _safe_int(row.get('QTY')),
                    'holdDate': _format_datetime(row.get('HOLD_DATE')),
                    'holdEmp': _clean_text(row.get('HOLD_EMP')),
                    'holdComment': _clean_text(row.get('HOLD_COMMENT')),
                    'releaseDate': _format_datetime(row.get('RELEASE_DATE')),
                    'releaseEmp': _clean_text(row.get('RELEASE_EMP')),
                    'releaseComment': _clean_text(row.get('RELEASE_COMMENT')),
                    'holdHours': round(_safe_float(row.get('HOLD_HOURS')), 2),
                    'ncr': _clean_text(row.get('NCR_ID')),
                    'futureHoldComment': _clean_text(row.get('FUTURE_HOLD_COMMENT')),
                })

        total_pages = (total + per_page - 1) // per_page if total > 0 else 1

        return {
            'items': items,
            'pagination': {
                'page': page,
                'perPage': per_page,
                'total': total,
                'totalPages': total_pages,
            },
        }
    except (DatabasePoolExhaustedError, DatabaseCircuitOpenError):
        raise
    except Exception as exc:
        logger.error('Hold history list query failed: %s', exc)
        return None
