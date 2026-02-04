# -*- coding: utf-8 -*-
"""Job Query Service.

Provides functions for querying maintenance job data:
- Job list by resource IDs
- Job transaction history detail
- CSV export with full history

Architecture:
- Uses resource_cache as the source for equipment master data
- Queries DW_MES_JOB for job current status
- Queries DW_MES_JOBTXNHISTORY for transaction history
- Supports batching for large resource lists (Oracle IN clause limit)
"""

import csv
import io
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional, Generator

import pandas as pd

from mes_dashboard.core.database import read_sql_df, get_db_connection
from mes_dashboard.sql import SQLLoader

logger = logging.getLogger('mes_dashboard.job_query')

# Constants
BATCH_SIZE = 1000  # Oracle IN clause limit
MAX_DATE_RANGE_DAYS = 365


# ============================================================
# Validation Functions
# ============================================================

def validate_date_range(start_date: str, end_date: str) -> Optional[str]:
    """Validate date range.

    Args:
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format

    Returns:
        Error message if validation fails, None if valid.
    """
    try:
        start = datetime.strptime(start_date, '%Y-%m-%d')
        end = datetime.strptime(end_date, '%Y-%m-%d')

        if end < start:
            return '結束日期不可早於起始日期'

        diff = (end - start).days
        if diff > MAX_DATE_RANGE_DAYS:
            return f'日期範圍不可超過 {MAX_DATE_RANGE_DAYS} 天'

        return None
    except ValueError as e:
        return f'日期格式錯誤: {e}'


# ============================================================
# Resource Filter Helpers
# ============================================================

def _build_resource_filter(resource_ids: List[str], max_chunk_size: int = BATCH_SIZE) -> List[str]:
    """Build SQL IN clause lists for resource IDs.

    Oracle has a limit of ~1000 items per IN clause, so we chunk if needed.

    Args:
        resource_ids: List of resource IDs.
        max_chunk_size: Maximum items per IN clause.

    Returns:
        List of SQL IN clause strings (e.g., "'ID1', 'ID2', 'ID3'").
    """
    if not resource_ids:
        return []

    # Escape single quotes
    escaped_ids = [rid.replace("'", "''") for rid in resource_ids]

    # Chunk into groups
    chunks = []
    for i in range(0, len(escaped_ids), max_chunk_size):
        chunk = escaped_ids[i:i + max_chunk_size]
        chunks.append("'" + "', '".join(chunk) + "'")

    return chunks


def _build_resource_filter_sql(resource_ids: List[str], column: str = 'j.RESOURCEID') -> str:
    """Build SQL WHERE clause for resource ID filtering.

    Handles chunking for large resource lists.

    Args:
        resource_ids: List of resource IDs.
        column: Column name to filter on.

    Returns:
        SQL condition string (e.g., "j.RESOURCEID IN ('ID1', 'ID2')").
    """
    chunks = _build_resource_filter(resource_ids)
    if not chunks:
        return "1=0"  # No resources = no results

    if len(chunks) == 1:
        return f"{column} IN ({chunks[0]})"

    # Multiple chunks need OR
    conditions = [f"{column} IN ({chunk})" for chunk in chunks]
    return "(" + " OR ".join(conditions) + ")"


# ============================================================
# Query Functions
# ============================================================

def get_jobs_by_resources(
    resource_ids: List[str],
    start_date: str,
    end_date: str
) -> Dict[str, Any]:
    """Query jobs for selected resources within date range.

    Args:
        resource_ids: List of RESOURCEID values to query
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format

    Returns:
        Dict with 'data' (list of job records) and 'total' (count),
        or 'error' if query fails.
    """
    # Validate inputs
    if not resource_ids:
        return {'error': '請選擇至少一台設備'}

    validation_error = validate_date_range(start_date, end_date)
    if validation_error:
        return {'error': validation_error}

    try:
        # Build resource filter
        resource_filter = _build_resource_filter_sql(resource_ids)

        # Load SQL template
        sql = SQLLoader.load("job_query/job_list")
        sql = sql.replace("{{ RESOURCE_FILTER }}", resource_filter)

        # Execute query
        params = {'start_date': start_date, 'end_date': end_date}
        df = read_sql_df(sql, params)

        # Convert to records
        data = []
        for _, row in df.iterrows():
            record = {}
            for col in df.columns:
                value = row[col]
                if pd.isna(value):
                    record[col] = None
                elif isinstance(value, datetime):
                    record[col] = value.strftime('%Y-%m-%d %H:%M:%S')
                else:
                    record[col] = value
            data.append(record)

        logger.info(f"Job query returned {len(data)} records for {len(resource_ids)} resources")

        return {
            'data': data,
            'total': len(data),
            'resource_count': len(resource_ids)
        }

    except Exception as exc:
        logger.error(f"Job query failed: {exc}")
        return {'error': f'查詢失敗: {str(exc)}'}


def get_job_txn_history(job_id: str) -> Dict[str, Any]:
    """Query transaction history for a single job.

    Args:
        job_id: The JOBID to query

    Returns:
        Dict with 'data' (list of transaction records) and 'total' (count),
        or 'error' if query fails.
    """
    if not job_id:
        return {'error': '請指定工單 ID'}

    try:
        # Load SQL template
        sql = SQLLoader.load("job_query/job_txn_detail")

        # Execute query
        params = {'job_id': job_id}
        df = read_sql_df(sql, params)

        # Convert to records
        data = []
        for _, row in df.iterrows():
            record = {}
            for col in df.columns:
                value = row[col]
                if pd.isna(value):
                    record[col] = None
                elif isinstance(value, datetime):
                    record[col] = value.strftime('%Y-%m-%d %H:%M:%S')
                else:
                    record[col] = value
            data.append(record)

        logger.debug(f"Transaction history query returned {len(data)} records for job {job_id}")

        return {
            'data': data,
            'total': len(data),
            'job_id': job_id
        }

    except Exception as exc:
        logger.error(f"Transaction history query failed for job {job_id}: {exc}")
        return {'error': f'查詢失敗: {str(exc)}'}


# ============================================================
# Export Functions
# ============================================================

def export_jobs_with_history(
    resource_ids: List[str],
    start_date: str,
    end_date: str
) -> Generator[str, None, None]:
    """Generate CSV content for jobs with full transaction history.

    Uses streaming to handle large datasets without memory issues.

    Args:
        resource_ids: List of RESOURCEID values to export
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format

    Yields:
        CSV rows as strings (including header row first)
    """
    # Validate inputs
    if not resource_ids:
        yield "Error: 請選擇至少一台設備\n"
        return

    validation_error = validate_date_range(start_date, end_date)
    if validation_error:
        yield f"Error: {validation_error}\n"
        return

    try:
        # Build resource filter
        resource_filter = _build_resource_filter_sql(resource_ids)

        # Load SQL template
        sql = SQLLoader.load("job_query/job_txn_export")
        sql = sql.replace("{{ RESOURCE_FILTER }}", resource_filter)

        # Execute query
        params = {'start_date': start_date, 'end_date': end_date}
        df = read_sql_df(sql, params)

        if df is None or len(df) == 0:
            yield "Error: 無符合條件的資料\n"
            return

        # Write CSV header with BOM for Excel UTF-8 compatibility
        output = io.StringIO()
        output.write('\ufeff')  # UTF-8 BOM

        # Define column headers (Chinese labels)
        headers = [
            '設備名稱', '工單ID', '工單最終狀態', '工單類型', '工單名稱',
            '工單建立時間', '工單完成時間', '工單故障碼', '工單維修碼', '工單症狀碼',
            '交易時間', '原狀態', '新狀態', '階段',
            '交易故障碼', '交易維修碼', '交易症狀碼',
            '操作者', '員工', '備註'
        ]

        writer = csv.writer(output)
        writer.writerow(headers)
        yield output.getvalue()
        output.truncate(0)
        output.seek(0)

        # Write data rows
        for _, row in df.iterrows():
            csv_row = []
            for col in df.columns:
                value = row[col]
                if pd.isna(value):
                    csv_row.append('')
                elif isinstance(value, datetime):
                    csv_row.append(value.strftime('%Y-%m-%d %H:%M:%S'))
                else:
                    csv_row.append(str(value))

            writer.writerow(csv_row)
            yield output.getvalue()
            output.truncate(0)
            output.seek(0)

        logger.info(f"CSV export completed: {len(df)} records")

    except Exception as exc:
        logger.error(f"CSV export failed: {exc}")
        yield f"Error: 匯出失敗 - {str(exc)}\n"


def get_export_data(
    resource_ids: List[str],
    start_date: str,
    end_date: str
) -> Dict[str, Any]:
    """Get export data as a dict (for non-streaming use cases).

    Args:
        resource_ids: List of RESOURCEID values to export
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format

    Returns:
        Dict with 'data', 'columns', 'total', or 'error' if query fails.
    """
    # Validate inputs
    if not resource_ids:
        return {'error': '請選擇至少一台設備'}

    validation_error = validate_date_range(start_date, end_date)
    if validation_error:
        return {'error': validation_error}

    try:
        # Build resource filter
        resource_filter = _build_resource_filter_sql(resource_ids)

        # Load SQL template
        sql = SQLLoader.load("job_query/job_txn_export")
        sql = sql.replace("{{ RESOURCE_FILTER }}", resource_filter)

        # Execute query
        params = {'start_date': start_date, 'end_date': end_date}
        df = read_sql_df(sql, params)

        # Convert to records
        data = []
        for _, row in df.iterrows():
            record = {}
            for col in df.columns:
                value = row[col]
                if pd.isna(value):
                    record[col] = None
                elif isinstance(value, datetime):
                    record[col] = value.strftime('%Y-%m-%d %H:%M:%S')
                else:
                    record[col] = value
            data.append(record)

        return {
            'data': data,
            'columns': list(df.columns),
            'total': len(data)
        }

    except Exception as exc:
        logger.error(f"Export data query failed: {exc}")
        return {'error': f'查詢失敗: {str(exc)}'}
