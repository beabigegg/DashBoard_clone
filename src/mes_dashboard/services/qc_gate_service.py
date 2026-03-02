# -*- coding: utf-8 -*-
"""QC-GATE summary service built from cached WIP data."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import pandas as pd

from mes_dashboard.core.cache import (
    get_cached_wip_data,
    get_cached_sys_date,
    get_cache_updated_at,
)
from mes_dashboard.services.filter_cache import get_spec_order_mapping

logger = logging.getLogger('mes_dashboard.qc_gate_service')

_DEFAULT_SPEC_ORDER = 999999
_BUCKET_TEMPLATE = {
    'lt_6h': 0,
    '6h_12h': 0,
    '12h_24h': 0,
    'gt_24h': 0,
}


def _safe_value(value: Any) -> Any:
    """Normalize pandas NaN/NaT values to None."""
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


def _safe_int(value: Any, default: int = 0) -> int:
    value = _safe_value(value)
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any) -> Optional[float]:
    value = _safe_value(value)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_text(value: Any) -> str:
    value = _safe_value(value)
    if value is None:
        return ''
    return str(value).strip()


def _normalize_spec(spec_name: Any) -> str:
    return _normalize_text(spec_name).upper()


def _classify_wait_bucket(wait_hours: float) -> str:
    if wait_hours < 6:
        return 'lt_6h'
    if wait_hours < 12:
        return '6h_12h'
    if wait_hours < 24:
        return '12h_24h'
    return 'gt_24h'


def _resolve_reference_time(cache_time: Optional[str], df: pd.DataFrame) -> Optional[pd.Timestamp]:
    ts = pd.to_datetime(cache_time, errors='coerce')
    if pd.notna(ts):
        return ts

    if 'SYS_DATE' in df.columns:
        sys_dates = pd.to_datetime(df['SYS_DATE'], errors='coerce')
        if not sys_dates.empty:
            max_ts = sys_dates.max()
            if pd.notna(max_ts):
                return max_ts

    return None


def _resolve_move_in_time(row: pd.Series) -> Optional[pd.Timestamp]:
    for column in ('MOVEINTIMESTAMP', 'TRACKINTIMESTAMP', 'LOTTRACKINTIME', 'STARTDATE'):
        if column not in row.index:
            continue
        ts = pd.to_datetime(row.get(column), errors='coerce')
        if pd.notna(ts):
            return ts
    return None


def _resolve_wait_hours(row: pd.Series, reference_time: Optional[pd.Timestamp], move_in_time: Optional[pd.Timestamp]) -> float:
    if reference_time is not None and move_in_time is not None:
        delta = (reference_time - move_in_time).total_seconds() / 3600.0
        if delta >= 0:
            return float(delta)

    age_days = _safe_float(row.get('AGEBYDAYS'))
    if age_days is not None and age_days >= 0:
        return float(age_days * 24)

    return 0.0


def _derive_wip_status(row: pd.Series) -> str:
    direct = _normalize_text(row.get('WIP_STATUS') or row.get('STATUS'))
    if direct:
        return direct.upper()

    equipment_count = _safe_int(row.get('EQUIPMENTCOUNT'))
    hold_count = _safe_int(row.get('CURRENTHOLDCOUNT'))
    if equipment_count > 0:
        return 'RUN'
    if hold_count > 0:
        return 'HOLD'
    return 'QUEUE'


def _build_lot_payload(row: pd.Series, reference_time: Optional[pd.Timestamp]) -> Dict[str, Any]:
    move_in_time = _resolve_move_in_time(row)
    wait_hours = _resolve_wait_hours(row, reference_time, move_in_time)
    bucket = _classify_wait_bucket(wait_hours)

    move_in_display = None
    if move_in_time is not None:
        move_in_display = move_in_time.isoformat()

    step = _normalize_text(row.get('SPECNAME'))
    lot_id = _safe_value(row.get('LOTID') or row.get('CONTAINERNAME'))
    container_id = _safe_value(row.get('CONTAINERID') or row.get('CONTAINERNAME') or lot_id)

    product = (
        _safe_value(row.get('PRODUCT'))
        or _safe_value(row.get('PACKAGE_LEF'))
        or _safe_value(row.get('PRODUCTLINENAME'))
    )

    return {
        'lot_id': lot_id,
        'container_id': container_id,
        'package': _safe_value(row.get('PACKAGE_LEF')),
        'product': product,
        'qty': _safe_int(row.get('QTY')),
        'step': step,
        'workorder': _safe_value(row.get('WORKORDER')),
        'move_in_time': move_in_display,
        'wait_hours': round(wait_hours, 2),
        'bucket': bucket,
        'status': _derive_wip_status(row),
        'equipment': _safe_value(row.get('EQUIPMENTS') or row.get('EQUIPMENTNAME')),
    }


def get_qc_gate_summary() -> Optional[Dict[str, Any]]:
    """Get QC-GATE lot summary from Redis-cached WIP snapshot.

    Returns:
        Dict with cache_time and per-station lot summary, or None on failure.
    """
    cache_time = get_cached_sys_date() or get_cache_updated_at()

    try:
        df = get_cached_wip_data()
        if df is None or df.empty or 'SPECNAME' not in df.columns:
            return {
                'cache_time': cache_time,
                'stations': [],
            }

        spec_series = df['SPECNAME'].fillna('').astype(str).str.upper()
        qc_gate_mask = spec_series.str.contains('QC', na=False) & spec_series.str.contains('GATE', na=False)
        qc_gate_df = df[qc_gate_mask].copy()

        if qc_gate_df.empty:
            return {
                'cache_time': cache_time,
                'stations': [],
            }

        reference_time = _resolve_reference_time(cache_time, qc_gate_df)
        spec_order_mapping = get_spec_order_mapping() or {}

        stations_by_spec: Dict[str, Dict[str, Any]] = {}
        for _, row in qc_gate_df.iterrows():
            spec_name = _normalize_text(row.get('SPECNAME'))
            if not spec_name:
                continue

            normalized_spec = _normalize_spec(spec_name)
            spec_order = int(spec_order_mapping.get(normalized_spec, _DEFAULT_SPEC_ORDER))
            lot_payload = _build_lot_payload(row, reference_time)

            station = stations_by_spec.get(spec_name)
            if station is None:
                station = {
                    'specname': spec_name,
                    'spec_order': spec_order,
                    'buckets': dict(_BUCKET_TEMPLATE),
                    'total': 0,
                    'lots': [],
                }
                stations_by_spec[spec_name] = station

            station['buckets'][lot_payload['bucket']] += 1
            station['total'] += 1
            station['lots'].append(lot_payload)

        stations = list(stations_by_spec.values())
        for station in stations:
            station['lots'].sort(
                key=lambda lot: float(lot.get('wait_hours') or 0),
                reverse=True,
            )

        stations.sort(
            key=lambda station: (
                int(station.get('spec_order', _DEFAULT_SPEC_ORDER)),
                station.get('specname', ''),
            )
        )

        return {
            'cache_time': cache_time,
            'stations': stations,
        }
    except Exception as exc:
        logger.exception('Failed to build QC-GATE summary: %s', exc)
        return None
