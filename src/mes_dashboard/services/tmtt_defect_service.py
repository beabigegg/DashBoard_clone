# -*- coding: utf-8 -*-
"""TMTT Defect Analysis Service.

Provides functions for analyzing printing (印字) and lead form (腳型) defects
at TMTT stations, with MOLD equipment correlation and multi-dimension Pareto analysis.

Defect rates are calculated separately by LOSSREASONNAME:
- Print defect rate = 277_印字不良 / TMTT INPUT
- Lead defect rate = 276_腳型不良 / TMTT INPUT
"""

import csv
import io
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any, Generator

import math

import pandas as pd

from mes_dashboard.core.database import read_sql_df
from mes_dashboard.core.cache import cache_get, cache_set, make_cache_key
from mes_dashboard.sql import SQLLoader

logger = logging.getLogger('mes_dashboard.tmtt_defect')

# Constants
MAX_QUERY_DAYS = 180
CACHE_TTL = 300  # 5 minutes

PRINT_DEFECT = '277_印字不良'
LEAD_DEFECT = '276_腳型不良'

# Dimension column mapping for chart aggregation
DIMENSION_MAP = {
    'by_workflow': 'WORKFLOW',
    'by_package': 'PRODUCTLINENAME',
    'by_type': 'PJ_TYPE',
    'by_tmtt_machine': 'TMTT_EQUIPMENTNAME',
    'by_mold_machine': 'MOLD_EQUIPMENTNAME',
}

# CSV export column config
CSV_COLUMNS = [
    ('CONTAINERNAME', 'LOT ID'),
    ('PJ_TYPE', 'TYPE'),
    ('PRODUCTLINENAME', 'PACKAGE'),
    ('WORKFLOW', 'WORKFLOW'),
    ('FINISHEDRUNCARD', '完工流水碼'),
    ('TMTT_EQUIPMENTNAME', 'TMTT設備'),
    ('MOLD_EQUIPMENTNAME', 'MOLD設備'),
    ('INPUT_QTY', '投入數'),
    ('PRINT_DEFECT_QTY', '印字不良數'),
    ('PRINT_DEFECT_RATE', '印字不良率(%)'),
    ('LEAD_DEFECT_QTY', '腳型不良數'),
    ('LEAD_DEFECT_RATE', '腳型不良率(%)'),
]


# ============================================================
# Public API
# ============================================================

def query_tmtt_defect_analysis(
    start_date: str,
    end_date: str,
) -> Optional[Dict[str, Any]]:
    """Main entry point for TMTT defect analysis.

    Args:
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)

    Returns:
        Dict with kpi, charts, detail sections, or dict with 'error' key.
    """
    # Validate dates
    error = _validate_date_range(start_date, end_date)
    if error:
        return {'error': error}

    # Check cache
    cache_key = make_cache_key(
        "tmtt_defect_analysis",
        filters={'start_date': start_date, 'end_date': end_date},
    )
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    # Fetch data
    df = _fetch_base_data(start_date, end_date)
    if df is None:
        return None

    # Build response
    result = {
        'kpi': _build_kpi(df),
        'charts': _build_all_charts(df),
        'daily_trend': _build_daily_trend(df),
        'detail': _build_detail_table(df),
    }

    cache_set(cache_key, result, ttl=CACHE_TTL)
    return result


def export_csv(
    start_date: str,
    end_date: str,
) -> Generator[str, None, None]:
    """Stream CSV export of detail data.

    Args:
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)

    Yields:
        CSV lines as strings.
    """
    df = _fetch_base_data(start_date, end_date)

    # BOM for Excel UTF-8 compatibility
    yield '\ufeff'

    output = io.StringIO()
    writer = csv.writer(output)

    # Header row
    writer.writerow([label for _, label in CSV_COLUMNS])
    yield output.getvalue()
    output.seek(0)
    output.truncate(0)

    if df is None or df.empty:
        return

    detail = _build_detail_table(df)
    for row in detail:
        writer.writerow([row.get(col, '') for col, _ in CSV_COLUMNS])
        yield output.getvalue()
        output.seek(0)
        output.truncate(0)


# ============================================================
# Helpers
# ============================================================

def _safe_str(v, default=''):
    """Return a JSON-safe string. Converts NaN/None to default."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return default
    try:
        if pd.isna(v):
            return default
    except (TypeError, ValueError):
        pass
    return str(v)


def _safe_float(v, default=0.0):
    """Return a JSON-safe float. Converts NaN/None to default."""
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
    """Return a JSON-safe int. Converts NaN/None to default."""
    return int(_safe_float(v, float(default)))


# ============================================================
# Internal Functions
# ============================================================

def _validate_date_range(start_date: str, end_date: str) -> Optional[str]:
    """Validate date range parameters.

    Returns:
        Error message string, or None if valid.
    """
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


def _fetch_base_data(start_date: str, end_date: str) -> Optional[pd.DataFrame]:
    """Execute base_data.sql and return raw DataFrame.

    Args:
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)

    Returns:
        DataFrame or None on error.
    """
    try:
        sql = SQLLoader.load("tmtt_defect/base_data")
        params = {
            'start_date': start_date,
            'end_date': end_date,
        }
        df = read_sql_df(sql, params)
        if df is None:
            logger.error("TMTT defect base query returned None")
            return None
        logger.info(
            f"TMTT defect query: {len(df)} rows, "
            f"{df['CONTAINERID'].nunique() if not df.empty else 0} unique lots"
        )
        return df
    except Exception as exc:
        logger.error(f"TMTT defect query failed: {exc}", exc_info=True)
        return None


def _build_kpi(df: pd.DataFrame) -> Dict[str, Any]:
    """Build KPI summary from base data.

    Defect rates are calculated separately by LOSSREASONNAME.
    INPUT is deduplicated by CONTAINERID (a LOT may have multiple defect rows).

    Args:
        df: Base data DataFrame.

    Returns:
        KPI dict with total_input, lot_count, print/lead defect qty and rate.
    """
    if df.empty:
        return {
            'total_input': 0,
            'lot_count': 0,
            'print_defect_qty': 0,
            'print_defect_rate': 0.0,
            'lead_defect_qty': 0,
            'lead_defect_rate': 0.0,
        }

    # Deduplicate for INPUT: one TRACKINQTY per unique CONTAINERID
    unique_lots = df.drop_duplicates(subset=['CONTAINERID'])
    total_input = int(unique_lots['TRACKINQTY'].sum())
    lot_count = len(unique_lots)

    # Defect totals by type
    defect_rows = df[df['REJECTQTY'] > 0]
    print_qty = int(
        defect_rows.loc[
            defect_rows['LOSSREASONNAME'] == PRINT_DEFECT, 'REJECTQTY'
        ].sum()
    )
    lead_qty = int(
        defect_rows.loc[
            defect_rows['LOSSREASONNAME'] == LEAD_DEFECT, 'REJECTQTY'
        ].sum()
    )

    return {
        'total_input': total_input,
        'lot_count': lot_count,
        'print_defect_qty': print_qty,
        'print_defect_rate': round(print_qty / total_input * 100, 4) if total_input else 0.0,
        'lead_defect_qty': lead_qty,
        'lead_defect_rate': round(lead_qty / total_input * 100, 4) if total_input else 0.0,
    }


def _build_chart_data(
    df: pd.DataFrame,
    dimension: str,
) -> List[Dict[str, Any]]:
    """Build Pareto chart data for a given dimension.

    Each item includes separate print and lead defect quantities/rates.

    Args:
        df: Base data DataFrame.
        dimension: Column name to group by.

    Returns:
        List of dicts sorted by total defect qty DESC, with cumulative_pct.
    """
    if df.empty:
        return []

    # Fill NaN dimension values
    work_df = df.copy()
    work_df[dimension] = work_df[dimension].fillna('(未知)')

    # INPUT per dimension (deduplicated by CONTAINERID within each group)
    input_by_dim = (
        work_df.drop_duplicates(subset=['CONTAINERID', dimension])
        .groupby(dimension)['TRACKINQTY']
        .sum()
    )

    # Defect qty per dimension per type
    defect_rows = work_df[work_df['REJECTQTY'] > 0]

    print_by_dim = (
        defect_rows[defect_rows['LOSSREASONNAME'] == PRINT_DEFECT]
        .groupby(dimension)['REJECTQTY']
        .sum()
    )
    lead_by_dim = (
        defect_rows[defect_rows['LOSSREASONNAME'] == LEAD_DEFECT]
        .groupby(dimension)['REJECTQTY']
        .sum()
    )

    # Combine
    combined = pd.DataFrame({
        'input_qty': input_by_dim,
        'print_defect_qty': print_by_dim,
        'lead_defect_qty': lead_by_dim,
    }).fillna(0).astype({'print_defect_qty': int, 'lead_defect_qty': int, 'input_qty': int})

    combined['total_defect_qty'] = combined['print_defect_qty'] + combined['lead_defect_qty']
    combined = combined.sort_values('total_defect_qty', ascending=False)

    # Cumulative percentage
    total_defects = combined['total_defect_qty'].sum()
    if total_defects > 0:
        combined['cumulative_pct'] = (
            combined['total_defect_qty'].cumsum() / total_defects * 100
        ).round(2)
    else:
        combined['cumulative_pct'] = 0.0

    # Defect rates
    combined['print_defect_rate'] = (
        combined['print_defect_qty'] / combined['input_qty'] * 100
    ).round(4).where(combined['input_qty'] > 0, 0.0)
    combined['lead_defect_rate'] = (
        combined['lead_defect_qty'] / combined['input_qty'] * 100
    ).round(4).where(combined['input_qty'] > 0, 0.0)

    result = []
    for name, row in combined.iterrows():
        result.append({
            'name': _safe_str(name),
            'input_qty': _safe_int(row['input_qty']),
            'print_defect_qty': _safe_int(row['print_defect_qty']),
            'print_defect_rate': _safe_float(row['print_defect_rate']),
            'lead_defect_qty': _safe_int(row['lead_defect_qty']),
            'lead_defect_rate': _safe_float(row['lead_defect_rate']),
            'total_defect_qty': _safe_int(row['total_defect_qty']),
            'cumulative_pct': _safe_float(row['cumulative_pct']),
        })

    return result


def _build_all_charts(df: pd.DataFrame) -> Dict[str, List[Dict]]:
    """Build chart data for all 5 dimensions.

    Args:
        df: Base data DataFrame.

    Returns:
        Dict mapping chart key to Pareto data list.
    """
    return {
        key: _build_chart_data(df, col)
        for key, col in DIMENSION_MAP.items()
    }


def _build_daily_trend(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """Build daily defect rate trend data.

    Groups by TRACKINTIMESTAMP date, calculates daily print/lead defect rates.

    Args:
        df: Base data DataFrame.

    Returns:
        List of dicts sorted by date ASC, each with date, input_qty,
        print/lead defect qty and rate.
    """
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

    # Daily defects by type
    defect_rows = work_df[work_df['REJECTQTY'] > 0]

    daily_print = (
        defect_rows[defect_rows['LOSSREASONNAME'] == PRINT_DEFECT]
        .groupby('DATE')['REJECTQTY']
        .sum()
    )
    daily_lead = (
        defect_rows[defect_rows['LOSSREASONNAME'] == LEAD_DEFECT]
        .groupby('DATE')['REJECTQTY']
        .sum()
    )

    combined = pd.DataFrame({
        'input_qty': daily_input,
        'print_defect_qty': daily_print,
        'lead_defect_qty': daily_lead,
    }).fillna(0).astype({'print_defect_qty': int, 'lead_defect_qty': int, 'input_qty': int})

    combined['print_defect_rate'] = (
        combined['print_defect_qty'] / combined['input_qty'] * 100
    ).round(4).where(combined['input_qty'] > 0, 0.0)
    combined['lead_defect_rate'] = (
        combined['lead_defect_qty'] / combined['input_qty'] * 100
    ).round(4).where(combined['input_qty'] > 0, 0.0)

    combined = combined.sort_index()

    result = []
    for date, row in combined.iterrows():
        result.append({
            'date': str(date),
            'input_qty': _safe_int(row['input_qty']),
            'print_defect_qty': _safe_int(row['print_defect_qty']),
            'print_defect_rate': _safe_float(row['print_defect_rate']),
            'lead_defect_qty': _safe_int(row['lead_defect_qty']),
            'lead_defect_rate': _safe_float(row['lead_defect_rate']),
        })

    return result


def _build_detail_table(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """Build detail table rows, one per LOT.

    Aggregates defect quantities per LOT across defect types.

    Args:
        df: Base data DataFrame.

    Returns:
        List of dicts, one per LOT.
    """
    if df.empty:
        return []

    # Pivot defects per LOT
    lot_group_cols = [
        'CONTAINERID', 'CONTAINERNAME', 'PJ_TYPE', 'PRODUCTLINENAME',
        'WORKFLOW', 'FINISHEDRUNCARD', 'TMTT_EQUIPMENTNAME',
        'MOLD_EQUIPMENTNAME', 'TRACKINQTY',
    ]

    # Get unique LOT info (first occurrence)
    lots = df.drop_duplicates(subset=['CONTAINERID'])[lot_group_cols].copy()

    # Aggregate defects per LOT per type
    defect_rows = df[df['REJECTQTY'] > 0]

    print_defects = (
        defect_rows[defect_rows['LOSSREASONNAME'] == PRINT_DEFECT]
        .groupby('CONTAINERID')['REJECTQTY']
        .sum()
        .rename('PRINT_DEFECT_QTY')
    )
    lead_defects = (
        defect_rows[defect_rows['LOSSREASONNAME'] == LEAD_DEFECT]
        .groupby('CONTAINERID')['REJECTQTY']
        .sum()
        .rename('LEAD_DEFECT_QTY')
    )

    lots = lots.set_index('CONTAINERID')
    lots = lots.join(print_defects, how='left')
    lots = lots.join(lead_defects, how='left')
    lots['PRINT_DEFECT_QTY'] = lots['PRINT_DEFECT_QTY'].fillna(0).astype(int)
    lots['LEAD_DEFECT_QTY'] = lots['LEAD_DEFECT_QTY'].fillna(0).astype(int)

    # Calculate rates
    lots['INPUT_QTY'] = lots['TRACKINQTY'].astype(int)
    lots['PRINT_DEFECT_RATE'] = (
        lots['PRINT_DEFECT_QTY'] / lots['INPUT_QTY'] * 100
    ).round(4).where(lots['INPUT_QTY'] > 0, 0.0)
    lots['LEAD_DEFECT_RATE'] = (
        lots['LEAD_DEFECT_QTY'] / lots['INPUT_QTY'] * 100
    ).round(4).where(lots['INPUT_QTY'] > 0, 0.0)

    # Convert to list of dicts
    lots = lots.reset_index()
    result = []
    for _, row in lots.iterrows():
        result.append({
            'CONTAINERNAME': _safe_str(row.get('CONTAINERNAME')),
            'PJ_TYPE': _safe_str(row.get('PJ_TYPE')),
            'PRODUCTLINENAME': _safe_str(row.get('PRODUCTLINENAME')),
            'WORKFLOW': _safe_str(row.get('WORKFLOW')),
            'FINISHEDRUNCARD': _safe_str(row.get('FINISHEDRUNCARD')),
            'TMTT_EQUIPMENTNAME': _safe_str(row.get('TMTT_EQUIPMENTNAME')),
            'MOLD_EQUIPMENTNAME': _safe_str(row.get('MOLD_EQUIPMENTNAME')),
            'INPUT_QTY': _safe_int(row.get('INPUT_QTY')),
            'PRINT_DEFECT_QTY': _safe_int(row.get('PRINT_DEFECT_QTY')),
            'PRINT_DEFECT_RATE': _safe_float(row.get('PRINT_DEFECT_RATE')),
            'LEAD_DEFECT_QTY': _safe_int(row.get('LEAD_DEFECT_QTY')),
            'LEAD_DEFECT_RATE': _safe_float(row.get('LEAD_DEFECT_RATE')),
        })

    return result
