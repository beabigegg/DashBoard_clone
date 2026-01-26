# -*- coding: utf-8 -*-
"""Excel batch query service for MES Dashboard.

Provides Excel parsing, batch query execution, and CSV export functions.
Supports large datasets (7000+ rows) by splitting queries into batches.
"""

import re
from datetime import datetime
from typing import Any, Dict, List, Tuple

import pandas as pd

from mes_dashboard.core.database import get_db_connection


# Oracle IN clause limit
BATCH_SIZE = 1000


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
        return {'error': f'Excel 解析失敗: {str(exc)}'}


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
        return {'error': f'讀取欄位失敗: {str(exc)}'}


def sanitize_column_name(name: str) -> str:
    """Sanitize column name to prevent SQL injection."""
    return re.sub(r'[^a-zA-Z0-9_]', '', name)


def validate_table_name(table_name: str) -> bool:
    """Validate table name format."""
    return bool(re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', table_name))


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
        return {'error': f'查詢失敗: {str(exc)}'}


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
