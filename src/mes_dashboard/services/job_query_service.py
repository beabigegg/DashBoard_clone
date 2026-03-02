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
from typing import Dict, List, Any, Optional, Generator, Tuple

import pandas as pd

from mes_dashboard.core.database import read_sql_df_slow as read_sql_df, get_db_connection
from mes_dashboard.sql import SQLLoader, QueryBuilder
from mes_dashboard.config.field_contracts import get_export_headers, get_export_api_keys

logger = logging.getLogger('mes_dashboard.job_query')

# Constants
BATCH_SIZE = 1000  # Oracle IN clause limit
MAX_DATE_RANGE_DAYS = 365
QUERY_ERROR_MESSAGE = "查詢服務暫時無法使用"
EXPORT_ERROR_MESSAGE = "匯出服務暫時無法使用"


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

def _build_resource_filter(
    resource_ids: List[str], max_chunk_size: int = BATCH_SIZE
) -> List[List[str]]:
    """Build chunked resource ID lists for Oracle IN clause limits.

    Args:
        resource_ids: List of resource IDs.
        max_chunk_size: Maximum items per IN clause.

    Returns:
        Chunked resource ID values.
    """
    normalized_ids: List[str] = []
    for rid in resource_ids:
        if rid is None:
            continue
        text = str(rid).strip()
        if text:
            normalized_ids.append(text)

    if not normalized_ids:
        return []

    chunks: List[List[str]] = []
    for i in range(0, len(normalized_ids), max_chunk_size):
        chunk = normalized_ids[i:i + max_chunk_size]
        chunks.append(chunk)
    return chunks


def _build_resource_filter_sql(
    resource_ids: List[str],
    column: str = 'j.RESOURCEID',
    max_chunk_size: int = BATCH_SIZE,
    return_params: bool = False,
) -> str | Tuple[str, Dict[str, Any]]:
    """Build parameterized SQL condition for resource ID filtering.

    Uses bind variables via QueryBuilder and chunks values to satisfy Oracle
    IN-clause limits.

    Args:
        resource_ids: List of resource IDs.
        column: Column name to filter on.
        max_chunk_size: Maximum items per IN clause.
        return_params: If True, return (condition_sql, params).

    Returns:
        Condition SQL string, or tuple of condition SQL and parameters.
    """
    chunks = _build_resource_filter(resource_ids, max_chunk_size=max_chunk_size)
    if not chunks:
        result: Tuple[str, Dict[str, Any]] = ("1=0", {})
        return result if return_params else result[0]

    builder = QueryBuilder()
    for chunk in chunks:
        builder.add_in_condition(column, chunk)

    if len(builder.conditions) == 1:
        condition_sql = builder.conditions[0]
    else:
        condition_sql = "(" + " OR ".join(builder.conditions) + ")"

    result = (condition_sql, builder.params.copy())
    return result if return_params else result[0]


# ============================================================
# Query Functions
# ============================================================

_JOB_CACHE_TTL = 600  # 10 min for job query results


def get_jobs_by_resources(
    resource_ids: List[str],
    start_date: str,
    end_date: str
) -> Dict[str, Any]:
    """Query jobs for selected resources within date range.

    For date ranges exceeding BATCH_QUERY_TIME_THRESHOLD_DAYS (default 60),
    the query is decomposed into monthly chunks via BatchQueryEngine.
    Results are cached in Redis to avoid redundant Oracle queries.

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
        from mes_dashboard.services.batch_query_engine import (
            decompose_by_time_range,
            execute_plan,
            merge_chunks,
            compute_query_hash,
            should_decompose_by_time,
        )
        from mes_dashboard.core.redis_df_store import redis_load_df, redis_store_df

        # Check Redis cache first
        cache_hash = compute_query_hash({
            "resource_ids": sorted(resource_ids),
            "start_date": start_date,
            "end_date": end_date,
        })
        cache_key = f"job_query:{cache_hash}"
        cached_df = redis_load_df(cache_key)
        if cached_df is not None:
            logger.info("Job query cache hit (hash=%s)", cache_hash)
            df = cached_df
        elif should_decompose_by_time(start_date, end_date):
            # --- Engine path for long date ranges ---
            engine_chunks = decompose_by_time_range(start_date, end_date)

            # Build resource filter once (reused across all chunks)
            resource_filter, resource_params = _build_resource_filter_sql(
                resource_ids, return_params=True
            )
            sql = SQLLoader.load("job_query/job_list")
            sql = sql.replace("{{ RESOURCE_FILTER }}", resource_filter)

            def _run_job_chunk(chunk, max_rows_per_chunk=None):
                chunk_params = {
                    'start_date': chunk['chunk_start'],
                    'end_date': chunk['chunk_end'],
                    **resource_params,
                }
                result = read_sql_df(sql, chunk_params)
                return result if result is not None else pd.DataFrame()

            logger.info(
                "Engine activated for job query: %d chunks, %d resources",
                len(engine_chunks), len(resource_ids),
            )
            execute_plan(
                engine_chunks, _run_job_chunk,
                query_hash=cache_hash,
                cache_prefix="job",
                chunk_ttl=_JOB_CACHE_TTL,
            )
            df = merge_chunks("job", cache_hash)
            # Store merged result for fast re-access
            if not df.empty:
                redis_store_df(cache_key, df, ttl=_JOB_CACHE_TTL)
        else:
            # --- Direct path (short query) ---
            resource_filter, resource_params = _build_resource_filter_sql(
                resource_ids, return_params=True
            )
            sql = SQLLoader.load("job_query/job_list")
            sql = sql.replace("{{ RESOURCE_FILTER }}", resource_filter)
            params = {
                'start_date': start_date,
                'end_date': end_date,
                **resource_params,
            }
            df = read_sql_df(sql, params)
            if df is None:
                df = pd.DataFrame()
            # Cache the result
            if not df.empty:
                redis_store_df(cache_key, df, ttl=_JOB_CACHE_TTL)

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
        logger.exception("Job query failed: %s", exc)
        return {'error': QUERY_ERROR_MESSAGE}


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
        logger.exception("Transaction history query failed for job %s: %s", job_id, exc)
        return {'error': QUERY_ERROR_MESSAGE}


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
        resource_filter, resource_params = _build_resource_filter_sql(
            resource_ids, return_params=True
        )

        # Load SQL template
        sql = SQLLoader.load("job_query/job_txn_export")
        sql = sql.replace("{{ RESOURCE_FILTER }}", resource_filter)

        # Execute query
        params = {
            'start_date': start_date,
            'end_date': end_date,
            **resource_params,
        }
        df = read_sql_df(sql, params)

        if df is None or len(df) == 0:
            yield "Error: 無符合條件的資料\n"
            return

        # Write CSV header with BOM for Excel UTF-8 compatibility
        output = io.StringIO()
        output.write('\ufeff')  # UTF-8 BOM

        export_keys = get_export_api_keys('job_query')
        headers = get_export_headers('job_query')

        if not export_keys or not headers or len(export_keys) != len(headers):
            export_keys = [
                'RESOURCENAME', 'JOBID', 'JOB_FINAL_STATUS', 'JOBMODELNAME', 'JOBORDERNAME',
                'JOB_CREATEDATE', 'JOB_COMPLETEDATE', 'JOB_CAUSECODENAME', 'JOB_REPAIRCODENAME', 'JOB_SYMPTOMCODENAME',
                'TXNDATE', 'FROMJOBSTATUS', 'TXN_JOBSTATUS', 'STAGENAME',
                'TXN_CAUSECODENAME', 'TXN_REPAIRCODENAME', 'TXN_SYMPTOMCODENAME',
                'USER_NAME', 'EMP_NAME', 'COMMENTS'
            ]
            headers = export_keys

        writer = csv.writer(output)
        writer.writerow(headers)
        yield output.getvalue()
        output.truncate(0)
        output.seek(0)

        # Write data rows
        for _, row in df.iterrows():
            csv_row = []
            for col in export_keys:
                value = row.get(col)
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
        logger.exception("CSV export failed: %s", exc)
        yield f"Error: {EXPORT_ERROR_MESSAGE}\n"


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
        resource_filter, resource_params = _build_resource_filter_sql(
            resource_ids, return_params=True
        )

        # Load SQL template
        sql = SQLLoader.load("job_query/job_txn_export")
        sql = sql.replace("{{ RESOURCE_FILTER }}", resource_filter)

        # Execute query
        params = {
            'start_date': start_date,
            'end_date': end_date,
            **resource_params,
        }
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
        logger.exception("Export data query failed: %s", exc)
        return {'error': QUERY_ERROR_MESSAGE}
