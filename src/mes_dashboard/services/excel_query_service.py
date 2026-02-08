# -*- coding: utf-8 -*-
"""Excel batch query service for MES Dashboard.

Provides Excel parsing, batch query execution, and CSV export functions.
Supports large datasets (7000+ rows) by splitting queries into batches.
"""

import re
import logging
from datetime import datetime
from typing import Any, Dict, List, Tuple

import pandas as pd

from mes_dashboard.core.database import get_db_connection

logger = logging.getLogger('mes_dashboard.excel_query_service')

# Oracle IN clause limit
BATCH_SIZE = 1000

# LIKE query keyword limit
LIKE_KEYWORD_LIMIT = 100

# Large table threshold for performance warning (10 million rows)
LARGE_TABLE_THRESHOLD = 10_000_000
PARSE_ERROR_MESSAGE = "Excel 解析失敗，請確認檔案格式"
COLUMN_READ_ERROR_MESSAGE = "讀取欄位失敗，請稍後再試"
QUERY_ERROR_MESSAGE = "查詢服務暫時無法使用"


def parse_excel(file_storage) -> Dict[str, Any]:
    """Parse uploaded Excel file and return column info.

    Args:
        file_storage: Flask FileStorage object

    Returns:
        Dict with 'columns' list and 'preview' data, or 'error' if failed.
    """
    try:
        df = pd.read_excel(file_storage)
        columns = [str(col) for col in df.columns.tolist()]
        preview_df = df.head(5).copy()
        preview_df.columns = columns
        preview = preview_df.to_dict('records')

        return {
            'columns': columns,
            'preview': preview,
            'total_rows': len(df)
        }
    except Exception as exc:
        logger.exception("Excel parse failed: %s", exc)
        return {'error': PARSE_ERROR_MESSAGE}


def get_column_unique_values(file_storage, column_name: str) -> Dict[str, Any]:
    """Get unique values from a specific Excel column.

    Args:
        file_storage: Flask FileStorage object
        column_name: Name of the column to extract

    Returns:
        Dict with 'values' list and 'count', or 'error' if failed.
    """
    try:
        df = pd.read_excel(file_storage)
        df.columns = [str(col) for col in df.columns]

        if column_name not in df.columns:
            return {'error': f'欄位 {column_name} 不存在'}

        values = df[column_name].dropna().drop_duplicates()
        values_list = [str(v).strip() for v in values.tolist() if str(v).strip()]

        return {
            'values': values_list,
            'count': len(values_list)
        }
    except Exception as exc:
        logger.exception("Excel column read failed for %s: %s", column_name, exc)
        return {'error': COLUMN_READ_ERROR_MESSAGE}


def detect_excel_column_type(values: List[str]) -> Dict[str, Any]:
    """Detect the data type of Excel column values.

    Args:
        values: List of string values from Excel column

    Returns:
        Dict with:
        - detected_type: 'text', 'number', 'date', 'datetime', or 'id'
        - type_label: Display label in Chinese
        - sample_values: First 5 sample values
    """
    if not values:
        return {
            'detected_type': 'text',
            'type_label': '文字',
            'sample_values': []
        }

    # Sample first 100 non-empty values for analysis
    sample = [str(v).strip() for v in values[:100] if str(v).strip()]
    if not sample:
        return {
            'detected_type': 'text',
            'type_label': '文字',
            'sample_values': []
        }

    # Regex patterns for type detection
    date_pattern = re.compile(r'^\d{4}[-/]\d{1,2}[-/]\d{1,2}$')
    datetime_pattern = re.compile(r'^\d{4}[-/]\d{1,2}[-/]\d{1,2}[T ]\d{1,2}:\d{2}')
    number_pattern = re.compile(r'^-?\d+\.?\d*$')
    id_pattern = re.compile(r'^[A-Z0-9_-]+$', re.IGNORECASE)

    # Count matches for each type
    type_counts = {
        'datetime': 0,
        'date': 0,
        'number': 0,
        'id': 0,
        'text': 0
    }

    for val in sample:
        if datetime_pattern.match(val):
            type_counts['datetime'] += 1
        elif date_pattern.match(val):
            type_counts['date'] += 1
        elif number_pattern.match(val):
            type_counts['number'] += 1
        elif id_pattern.match(val) and len(val) >= 3:
            # ID pattern: uppercase alphanumeric, at least 3 chars
            type_counts['id'] += 1
        else:
            type_counts['text'] += 1

    # Determine type based on majority (>80%)
    threshold = len(sample) * 0.8
    detected_type = 'text'
    type_label = '文字'

    if type_counts['datetime'] >= threshold:
        detected_type = 'datetime'
        type_label = '日期時間'
    elif type_counts['date'] >= threshold:
        detected_type = 'date'
        type_label = '日期'
    elif type_counts['number'] >= threshold:
        detected_type = 'number'
        type_label = '數值'
    elif type_counts['id'] >= threshold:
        detected_type = 'id'
        type_label = '識別碼'

    return {
        'detected_type': detected_type,
        'type_label': type_label,
        'sample_values': sample[:5]
    }


def sanitize_column_name(name: str) -> str:
    """Sanitize column name to prevent SQL injection."""
    return re.sub(r'[^a-zA-Z0-9_]', '', name)


def validate_table_name(table_name: str) -> bool:
    """Validate table name format (supports schema.table format)."""
    return bool(re.match(r'^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)?$', table_name))


def escape_like_pattern(value: str) -> str:
    """Escape special characters in LIKE pattern.

    Oracle LIKE special characters: % (any chars), _ (single char)
    These need to be escaped with backslash for literal matching.

    Args:
        value: Raw search value

    Returns:
        Escaped value safe for LIKE pattern
    """
    # Escape backslash first, then special chars
    value = value.replace('\\', '\\\\')
    value = value.replace('%', '\\%')
    value = value.replace('_', '\\_')
    return value


def build_like_condition(
    column: str,
    values: List[str],
    mode: str = 'contains'
) -> Tuple[str, Dict[str, str]]:
    """Build LIKE query condition with multiple OR clauses.

    Args:
        column: Column name to search (must be sanitized)
        values: List of search keywords
        mode: 'contains' (%val%), 'prefix' (val%), or 'suffix' (%val)

    Returns:
        Tuple of (WHERE clause string, params dict)
    """
    if not values:
        return '', {}

    conditions = []
    params = {}

    for i, val in enumerate(values):
        param_name = f'like_{i}'
        escaped_val = escape_like_pattern(val)

        if mode == 'contains':
            params[param_name] = f'%{escaped_val}%'
        elif mode == 'prefix':
            params[param_name] = f'{escaped_val}%'
        elif mode == 'suffix':
            params[param_name] = f'%{escaped_val}'
        else:
            params[param_name] = f'%{escaped_val}%'

        conditions.append(f"{column} LIKE :{param_name} ESCAPE '\\'")

    where_clause = ' OR '.join(conditions)
    return f'({where_clause})', params


def build_date_range_condition(
    column: str,
    date_from: str = None,
    date_to: str = None
) -> Tuple[str, Dict[str, str]]:
    """Build date range condition for Oracle.

    Args:
        column: Date column name (must be sanitized)
        date_from: Start date in YYYY-MM-DD format
        date_to: End date in YYYY-MM-DD format

    Returns:
        Tuple of (WHERE clause string, params dict)
    """
    conditions = []
    params = {}

    if date_from:
        conditions.append(
            f"{column} >= TO_DATE(:date_from, 'YYYY-MM-DD')"
        )
        params['date_from'] = date_from

    if date_to:
        # Add 1 day to include the entire end date
        conditions.append(
            f"{column} < TO_DATE(:date_to, 'YYYY-MM-DD') + 1"
        )
        params['date_to'] = date_to

    if not conditions:
        return '', {}

    return ' AND '.join(conditions), params


def validate_like_keywords(values: List[str]) -> Dict[str, Any]:
    """Validate LIKE query keyword count.

    Args:
        values: List of search keywords

    Returns:
        Dict with 'valid' boolean and optional 'error' message
    """
    if len(values) > LIKE_KEYWORD_LIMIT:
        return {
            'valid': False,
            'error': f'LIKE 查詢最多支援 {LIKE_KEYWORD_LIMIT} 個關鍵字，目前有 {len(values)} 個'
        }
    return {'valid': True}


def execute_batch_query(
    table_name: str,
    search_column: str,
    return_columns: List[str],
    search_values: List[str]
) -> Dict[str, Any]:
    """Execute batch query with IN clause, splitting into batches for large datasets.

    Handles Oracle's 1000-value limit by executing multiple queries and merging results.

    Args:
        table_name: Target table name
        search_column: Column to search (WHERE ... IN)
        return_columns: Columns to return in SELECT
        search_values: Values to search for (can be 7000+)

    Returns:
        Dict with 'columns', 'data', 'row_count', or 'error' if failed.
    """
    # Validate inputs
    if not validate_table_name(table_name):
        return {'error': f'無效的資料表名稱: {table_name}'}

    safe_search_col = sanitize_column_name(search_column)
    safe_return_cols = [sanitize_column_name(col) for col in return_columns]

    if not safe_search_col:
        return {'error': '查詢欄位名稱無效'}
    if not safe_return_cols:
        return {'error': '回傳欄位名稱無效'}

    connection = get_db_connection()
    if not connection:
        return {'error': '資料庫連接失敗'}

    try:
        cursor = connection.cursor()
        all_data = []
        columns = None
        columns_str = ', '.join(safe_return_cols)

        # Calculate batch count for progress info
        total_batches = (len(search_values) + BATCH_SIZE - 1) // BATCH_SIZE

        # Process in batches
        for batch_idx in range(0, len(search_values), BATCH_SIZE):
            batch_values = search_values[batch_idx:batch_idx + BATCH_SIZE]

            # Build placeholders and params for this batch
            placeholders = ', '.join([f':v{j}' for j in range(len(batch_values))])
            params = {f'v{j}': str(v) for j, v in enumerate(batch_values)}

            sql = f"""
                SELECT {columns_str}
                FROM {table_name}
                WHERE {safe_search_col} IN ({placeholders})
            """

            cursor.execute(sql, params)

            # Get column names from first batch
            if columns is None:
                columns = [desc[0] for desc in cursor.description]

            rows = cursor.fetchall()

            # Convert rows to dicts
            for row in rows:
                row_dict = {}
                for i, col in enumerate(columns):
                    value = row[i]
                    if isinstance(value, datetime):
                        row_dict[col] = value.strftime('%Y-%m-%d %H:%M:%S')
                    else:
                        row_dict[col] = value
                all_data.append(row_dict)

        cursor.close()
        connection.close()

        return {
            'columns': columns or safe_return_cols,
            'data': all_data,
            'row_count': len(all_data),
            'search_count': len(search_values),
            'batch_count': total_batches
        }

    except Exception as exc:
        if connection:
            connection.close()
        logger.exception("Excel batch query failed: %s", exc)
        return {'error': QUERY_ERROR_MESSAGE}


def execute_advanced_batch_query(
    table_name: str,
    search_column: str,
    return_columns: List[str],
    search_values: List[str],
    query_type: str = 'in',
    date_column: str = None,
    date_from: str = None,
    date_to: str = None
) -> Dict[str, Any]:
    """Execute advanced batch query with multiple condition types.

    Args:
        table_name: Target table name
        search_column: Column to search
        return_columns: Columns to return in SELECT
        search_values: Values to search for
        query_type: 'in', 'like_contains', 'like_prefix', or 'like_suffix'
        date_column: Optional date column for range filter
        date_from: Optional start date (YYYY-MM-DD)
        date_to: Optional end date (YYYY-MM-DD)

    Returns:
        Dict with 'columns', 'data', 'row_count', or 'error' if failed.
    """
    # Validate inputs
    if not validate_table_name(table_name):
        return {'error': f'無效的資料表名稱: {table_name}'}

    safe_search_col = sanitize_column_name(search_column)
    safe_return_cols = [sanitize_column_name(col) for col in return_columns]

    if not safe_search_col:
        return {'error': '查詢欄位名稱無效'}
    if not safe_return_cols:
        return {'error': '回傳欄位名稱無效'}

    # Validate LIKE keyword count
    if query_type.startswith('like_'):
        validation = validate_like_keywords(search_values)
        if not validation['valid']:
            return {'error': validation['error']}

    connection = get_db_connection()
    if not connection:
        return {'error': '資料庫連接失敗'}

    try:
        cursor = connection.cursor()
        all_data = []
        columns = None
        columns_str = ', '.join(safe_return_cols)

        # Build date range condition
        date_condition = ''
        date_params = {}
        if date_column:
            safe_date_col = sanitize_column_name(date_column)
            if safe_date_col:
                date_condition, date_params = build_date_range_condition(
                    safe_date_col, date_from, date_to
                )

        # Handle different query types
        if query_type == 'in':
            # Original IN clause logic with batching
            total_batches = (len(search_values) + BATCH_SIZE - 1) // BATCH_SIZE

            for batch_idx in range(0, len(search_values), BATCH_SIZE):
                batch_values = search_values[batch_idx:batch_idx + BATCH_SIZE]
                placeholders = ', '.join([f':v{j}' for j in range(len(batch_values))])
                params = {f'v{j}': str(v) for j, v in enumerate(batch_values)}
                params.update(date_params)

                where_parts = [f'{safe_search_col} IN ({placeholders})']
                if date_condition:
                    where_parts.append(date_condition)

                sql = f"""
                    SELECT {columns_str}
                    FROM {table_name}
                    WHERE {' AND '.join(where_parts)}
                """

                cursor.execute(sql, params)

                if columns is None:
                    columns = [desc[0] for desc in cursor.description]

                rows = cursor.fetchall()
                for row in rows:
                    row_dict = {}
                    for i, col in enumerate(columns):
                        value = row[i]
                        if isinstance(value, datetime):
                            row_dict[col] = value.strftime('%Y-%m-%d %H:%M:%S')
                        else:
                            row_dict[col] = value
                    all_data.append(row_dict)

        else:
            # LIKE query - process all at once (already limited to 100 keywords)
            mode_map = {
                'like_contains': 'contains',
                'like_prefix': 'prefix',
                'like_suffix': 'suffix'
            }
            mode = mode_map.get(query_type, 'contains')
            like_condition, like_params = build_like_condition(
                safe_search_col, search_values, mode
            )

            params = {**like_params, **date_params}

            where_parts = [like_condition]
            if date_condition:
                where_parts.append(date_condition)

            sql = f"""
                SELECT {columns_str}
                FROM {table_name}
                WHERE {' AND '.join(where_parts)}
            """

            cursor.execute(sql, params)
            columns = [desc[0] for desc in cursor.description]

            rows = cursor.fetchall()
            for row in rows:
                row_dict = {}
                for i, col in enumerate(columns):
                    value = row[i]
                    if isinstance(value, datetime):
                        row_dict[col] = value.strftime('%Y-%m-%d %H:%M:%S')
                    else:
                        row_dict[col] = value
                all_data.append(row_dict)

            total_batches = 1

        cursor.close()
        connection.close()

        return {
            'columns': columns or safe_return_cols,
            'data': all_data,
            'row_count': len(all_data),
            'search_count': len(search_values),
            'batch_count': total_batches,
            'query_type': query_type
        }

    except Exception as exc:
        if connection:
            connection.close()
        logger.exception("Excel advanced batch query failed: %s", exc)
        return {'error': QUERY_ERROR_MESSAGE}


def generate_csv_content(data: List[Dict], columns: List[str]) -> str:
    """Generate CSV content from query results.

    Args:
        data: List of row dictionaries
        columns: Column names for header

    Returns:
        CSV content as string (UTF-8 with BOM for Excel compatibility)
    """
    import csv
    import io

    output = io.StringIO()
    # Add BOM for Excel UTF-8 compatibility
    output.write('\ufeff')

    writer = csv.DictWriter(output, fieldnames=columns, extrasaction='ignore')
    writer.writeheader()
    writer.writerows(data)

    return output.getvalue()
