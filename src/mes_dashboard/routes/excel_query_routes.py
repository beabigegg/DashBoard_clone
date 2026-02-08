# -*- coding: utf-8 -*-
"""API routes for Excel batch query functionality.

Provides endpoints for:
- Excel file upload and parsing
- Column value extraction
- Batch query execution
- CSV export
"""

from flask import Blueprint, jsonify, request, Response

from mes_dashboard.config.tables import TABLES_CONFIG
from mes_dashboard.core.database import get_table_columns, get_table_column_metadata
from mes_dashboard.services.excel_query_service import (
    parse_excel,
    get_column_unique_values,
    execute_batch_query,
    execute_advanced_batch_query,
    generate_csv_content,
    detect_excel_column_type,
    LARGE_TABLE_THRESHOLD,
)


excel_query_bp = Blueprint('excel_query', __name__, url_prefix='/api/excel-query')

# Store uploaded Excel data in memory (session-based in production)
_uploaded_excel_cache = {}


@excel_query_bp.route('/upload', methods=['POST'])
def upload_excel():
    """Upload and parse Excel file.

    Returns column list and preview data.
    """
    if 'file' not in request.files:
        return jsonify({'error': '未選擇檔案'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': '未選擇檔案'}), 400

    # Check file extension
    allowed_extensions = {'.xlsx', '.xls'}
    import os
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in allowed_extensions:
        return jsonify({'error': '只支援 .xlsx 或 .xls 檔案'}), 400

    # Parse Excel
    result = parse_excel(file)
    if 'error' in result:
        return jsonify(result), 400

    # Cache the file content for later use
    file.seek(0)
    _uploaded_excel_cache['current'] = file.read()
    _uploaded_excel_cache['filename'] = file.filename

    return jsonify(result)


@excel_query_bp.route('/column-values', methods=['POST'])
def get_column_values():
    """Get unique values from selected Excel column."""
    data = request.get_json()
    column_name = data.get('column_name')

    if not column_name:
        return jsonify({'error': '請指定欄位名稱'}), 400

    if 'current' not in _uploaded_excel_cache:
        return jsonify({'error': '請先上傳 Excel 檔案'}), 400

    # Create file-like object from cached content
    import io
    file_like = io.BytesIO(_uploaded_excel_cache['current'])

    result = get_column_unique_values(file_like, column_name)
    if 'error' in result:
        return jsonify(result), 400

    return jsonify(result)


@excel_query_bp.route('/tables', methods=['GET'])
def get_tables():
    """Get available tables for querying."""
    tables = []
    for category, table_list in TABLES_CONFIG.items():
        for table in table_list:
            tables.append({
                'name': table['name'],
                'display_name': table['display_name'],
                'category': category
            })
    return jsonify({'tables': tables})


@excel_query_bp.route('/table-columns', methods=['POST'])
def get_table_cols():
    """Get columns for a specific table."""
    data = request.get_json()
    table_name = data.get('table_name')

    if not table_name:
        return jsonify({'error': '請指定資料表名稱'}), 400

    columns = get_table_columns(table_name)
    if not columns:
        return jsonify({'error': f'無法取得資料表 {table_name} 的欄位'}), 400

    return jsonify({'columns': columns})


@excel_query_bp.route('/table-metadata', methods=['POST'])
def get_table_metadata():
    """Get enriched table metadata including column types.

    Returns:
        - columns: List of column info with data types
        - time_field: Configured time field from TABLES_CONFIG (or null)
        - description: Table description from TABLES_CONFIG
        - row_count: Approximate row count from TABLES_CONFIG
        - performance_warning: Warning message if table is large
    """
    data = request.get_json()
    table_name = data.get('table_name')

    if not table_name:
        return jsonify({'error': '請指定資料表名稱'}), 400

    # Get column metadata from Oracle
    metadata = get_table_column_metadata(table_name)
    if 'error' in metadata and not metadata.get('columns'):
        return jsonify({'error': f'無法取得資料表 {table_name} 的欄位資訊'}), 400

    # Find table config for additional info
    table_config = None
    for category, table_list in TABLES_CONFIG.items():
        for table in table_list:
            if table['name'] == table_name:
                table_config = table
                break
        if table_config:
            break

    # Build response
    result = {
        'columns': metadata.get('columns', []),
        'time_field': table_config.get('time_field') if table_config else None,
        'description': table_config.get('description', '') if table_config else '',
        'row_count': table_config.get('row_count', 0) if table_config else 0,
        'performance_warning': None
    }

    # Add performance warning for large tables
    if result['row_count'] and result['row_count'] > LARGE_TABLE_THRESHOLD:
        result['performance_warning'] = (
            f'此資料表超過 {LARGE_TABLE_THRESHOLD // 1_000_000} 千萬筆，'
            '包含查詢可能較慢，建議配合日期範圍縮小查詢範圍'
        )

    return jsonify(result)


@excel_query_bp.route('/column-type', methods=['POST'])
def get_excel_column_type():
    """Detect Excel column data type from cached file.

    Expects JSON body:
        {"column_name": "LOT_ID"}

    Returns column type info.
    """
    data = request.get_json()
    column_name = data.get('column_name')

    if not column_name:
        return jsonify({'error': '請指定欄位名稱'}), 400

    if 'current' not in _uploaded_excel_cache:
        return jsonify({'error': '請先上傳 Excel 檔案'}), 400

    import io
    file_like = io.BytesIO(_uploaded_excel_cache['current'])

    # Get unique values first
    from mes_dashboard.services.excel_query_service import get_column_unique_values
    values_result = get_column_unique_values(file_like, column_name)
    if 'error' in values_result:
        return jsonify(values_result), 400

    # Detect type from values
    type_info = detect_excel_column_type(values_result['values'])

    return jsonify({
        'column_name': column_name,
        **type_info
    })


@excel_query_bp.route('/execute-advanced', methods=['POST'])
def execute_advanced_query():
    """Execute advanced batch query with multiple condition types.

    Expects JSON body:
    {
        "table_name": "DWH.DW_MES_WIP",
        "search_column": "LOT_ID",
        "return_columns": ["LOT_ID", "SPEC", "QTY"],
        "search_values": ["val1", "val2", ...],
        "query_type": "in" | "like_contains" | "like_prefix" | "like_suffix",
        "date_column": "TXNDATE",  // optional
        "date_from": "2024-01-01",  // optional (YYYY-MM-DD)
        "date_to": "2024-12-31"     // optional (YYYY-MM-DD)
    }
    """
    data = request.get_json()

    table_name = data.get('table_name')
    search_column = data.get('search_column')
    return_columns = data.get('return_columns')
    search_values = data.get('search_values')
    query_type = data.get('query_type', 'in')
    date_column = data.get('date_column')
    date_from = data.get('date_from')
    date_to = data.get('date_to')

    # Validation
    if not table_name:
        return jsonify({'error': '請指定資料表'}), 400
    if not search_column:
        return jsonify({'error': '請指定查詢欄位'}), 400
    if not return_columns or not isinstance(return_columns, list):
        return jsonify({'error': '請指定回傳欄位'}), 400
    if not search_values or not isinstance(search_values, list):
        return jsonify({'error': '無查詢值'}), 400

    # Validate query_type
    valid_types = {'in', 'like_contains', 'like_prefix', 'like_suffix'}
    if query_type not in valid_types:
        return jsonify({'error': f'無效的查詢類型: {query_type}'}), 400

    # Validate date range if provided
    if date_from and date_to:
        try:
            from datetime import datetime
            d_from = datetime.strptime(date_from, '%Y-%m-%d')
            d_to = datetime.strptime(date_to, '%Y-%m-%d')
            if d_from > d_to:
                return jsonify({'error': '起始日期不可晚於結束日期'}), 400
            if (d_to - d_from).days > 365:
                return jsonify({'error': '日期範圍不可超過 365 天'}), 400
        except ValueError:
            return jsonify({'error': '日期格式錯誤，請使用 YYYY-MM-DD'}), 400

    result = execute_advanced_batch_query(
        table_name=table_name,
        search_column=search_column,
        return_columns=return_columns,
        search_values=search_values,
        query_type=query_type,
        date_column=date_column,
        date_from=date_from,
        date_to=date_to
    )

    if 'error' in result:
        return jsonify(result), 400

    return jsonify(result)


@excel_query_bp.route('/execute', methods=['POST'])
def execute_query():
    """Execute batch query with Excel values.

    Expects JSON body:
    {
        "table_name": "DWH.DW_MES_WIP",
        "search_column": "LOT_ID",
        "return_columns": ["LOT_ID", "SPEC", "QTY"],
        "search_values": ["val1", "val2", ...]
    }
    """
    data = request.get_json()

    table_name = data.get('table_name')
    search_column = data.get('search_column')
    return_columns = data.get('return_columns')
    search_values = data.get('search_values')

    # Validation
    if not table_name:
        return jsonify({'error': '請指定資料表'}), 400
    if not search_column:
        return jsonify({'error': '請指定查詢欄位'}), 400
    if not return_columns or not isinstance(return_columns, list):
        return jsonify({'error': '請指定回傳欄位'}), 400
    if not search_values or not isinstance(search_values, list):
        return jsonify({'error': '無查詢值'}), 400

    result = execute_batch_query(
        table_name=table_name,
        search_column=search_column,
        return_columns=return_columns,
        search_values=search_values
    )

    if 'error' in result:
        return jsonify(result), 400

    return jsonify(result)


@excel_query_bp.route('/export-csv', methods=['POST'])
def export_csv():
    """Export query results as CSV file.

    Same parameters as /execute endpoint.
    """
    data = request.get_json()

    table_name = data.get('table_name')
    search_column = data.get('search_column')
    return_columns = data.get('return_columns')
    search_values = data.get('search_values')

    # Validation
    if not all([table_name, search_column, return_columns, search_values]):
        return jsonify({'error': '缺少必要參數'}), 400

    result = execute_batch_query(
        table_name=table_name,
        search_column=search_column,
        return_columns=return_columns,
        search_values=search_values
    )

    if 'error' in result:
        return jsonify(result), 400

    # Generate CSV
    csv_content = generate_csv_content(result['data'], result['columns'])

    return Response(
        csv_content,
        mimetype='text/csv; charset=utf-8',
        headers={
            'Content-Disposition': 'attachment; filename=query_result.csv'
        }
    )
