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
from mes_dashboard.core.database import get_table_columns
from mes_dashboard.services.excel_query_service import (
    parse_excel,
    get_column_unique_values,
    execute_batch_query,
    generate_csv_content,
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


@excel_query_bp.route('/execute', methods=['POST'])
def execute_query():
    """Execute batch query with Excel values.

    Expects JSON body:
    {
        "table_name": "DW_MES_WIP",
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
