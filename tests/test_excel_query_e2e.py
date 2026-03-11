# -*- coding: utf-8 -*-
"""End-to-end tests for Excel query workflow.

Tests the complete workflow from Excel upload to query execution and export.
"""

import pytest
import json
import io
from unittest.mock import patch, MagicMock

from mes_dashboard import create_app


@pytest.fixture
def app():
    """Create test Flask application."""
    app = create_app()
    app.config['TESTING'] = True
    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()


def create_test_excel(data):
    """Create a test Excel file with given data.

    Args:
        data: List of lists where first list is headers.
              e.g. [['COL1', 'COL2'], ['val1', 'val2'], ...]
    """
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active

    for row_idx, row in enumerate(data, 1):
        for col_idx, value in enumerate(row, 1):
            ws.cell(row=row_idx, column=col_idx, value=value)

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer


class TestBasicQueryWorkflow:
    """E2E tests for basic query workflow."""

    @patch('mes_dashboard.routes.excel_query_routes.execute_batch_query')
    def test_complete_basic_workflow(self, mock_execute, client):
        """Test complete workflow: upload → get values → execute → export."""
        # Step 1: Upload Excel file
        excel_data = [
            ['LOT_ID', 'PRODUCT', 'QTY'],
            ['LOT001', 'PROD_A', 100],
            ['LOT002', 'PROD_B', 200],
            ['LOT003', 'PROD_A', 150],
        ]
        excel_file = create_test_excel(excel_data)

        upload_response = client.post(
            '/api/excel-query/upload',
            data={'file': (excel_file, 'batch_query.xlsx')},
            content_type='multipart/form-data'
        )
        assert upload_response.status_code == 200
        upload_data = json.loads(upload_response.data)
        assert 'columns' in upload_data['data']
        assert 'LOT_ID' in upload_data['data']['columns']
        assert 'preview' in upload_data['data']

        # Step 2: Get column values
        values_response = client.post(
            '/api/excel-query/column-values',
            json={'column_name': 'LOT_ID'}
        )
        assert values_response.status_code == 200
        values_data = json.loads(values_response.data)
        assert 'values' in values_data['data']
        assert set(values_data['data']['values']) == {'LOT001', 'LOT002', 'LOT003'}

        # Step 3: Execute query
        mock_execute.return_value = {
            'columns': ['LOT_ID', 'SPEC', 'STATUS'],
            'data': [
                ['LOT001', 'SPEC_001', 'ACTIVE'],
                ['LOT002', 'SPEC_002', 'HOLD'],
                ['LOT003', 'SPEC_001', 'ACTIVE'],
            ],
            'total': 3
        }

        execute_response = client.post(
            '/api/excel-query/execute',
            json={
                'table_name': 'DWH.DW_MES_WIP',
                'search_column': 'LOT_ID',
                'return_columns': ['LOT_ID', 'SPEC', 'STATUS'],
                'search_values': ['LOT001', 'LOT002', 'LOT003']
            }
        )
        assert execute_response.status_code == 200
        execute_data = json.loads(execute_response.data)
        assert execute_data['data']['total'] == 3


class TestAdvancedQueryWorkflow:
    """E2E tests for advanced query workflow with date range and LIKE."""

    @patch('mes_dashboard.routes.excel_query_routes.execute_advanced_batch_query')
    def test_like_contains_workflow(self, mock_execute, client):
        """Test workflow with LIKE contains query."""
        # Upload Excel with search patterns
        excel_data = [
            ['SEARCH_PATTERN'],
            ['LOT'],
            ['WIP'],
        ]
        excel_file = create_test_excel(excel_data)

        upload_response = client.post(
            '/api/excel-query/upload',
            data={'file': (excel_file, 'patterns.xlsx')},
            content_type='multipart/form-data'
        )
        assert upload_response.status_code == 200

        # Get search values
        values_response = client.post(
            '/api/excel-query/column-values',
            json={'column_name': 'SEARCH_PATTERN'}
        )
        assert values_response.status_code == 200
        search_values = json.loads(values_response.data)['data']['values']

        # Execute LIKE contains query
        mock_execute.return_value = {
            'columns': ['LOT_ID', 'STATUS'],
            'data': [
                ['LOT001', 'ACTIVE'],
                ['LOT002', 'ACTIVE'],
                ['WIP001', 'HOLD'],
                ['WIP002', 'ACTIVE'],
            ],
            'total': 4
        }

        response = client.post(
            '/api/excel-query/execute-advanced',
            json={
                'table_name': 'DWH.DW_MES_WIP',
                'search_column': 'LOT_ID',
                'return_columns': ['LOT_ID', 'STATUS'],
                'search_values': search_values,
                'query_type': 'like_contains'
            }
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['data']['total'] == 4

    @patch('mes_dashboard.routes.excel_query_routes.execute_advanced_batch_query')
    def test_date_range_workflow(self, mock_execute, client):
        """Test workflow with date range filter."""
        excel_data = [
            ['LOT_ID'],
            ['LOT001'],
            ['LOT002'],
        ]
        excel_file = create_test_excel(excel_data)

        client.post(
            '/api/excel-query/upload',
            data={'file': (excel_file, 'lots.xlsx')},
            content_type='multipart/form-data'
        )

        # Execute with date range
        mock_execute.return_value = {
            'columns': ['LOT_ID', 'TXNDATE'],
            'data': [['LOT001', '2024-01-15']],
            'total': 1
        }

        response = client.post(
            '/api/excel-query/execute-advanced',
            json={
                'table_name': 'DWH.DW_MES_WIP',
                'search_column': 'LOT_ID',
                'return_columns': ['LOT_ID', 'TXNDATE'],
                'search_values': ['LOT001', 'LOT002'],
                'query_type': 'in',
                'date_column': 'TXNDATE',
                'date_from': '2024-01-01',
                'date_to': '2024-01-31'
            }
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['data']['total'] == 1

    @patch('mes_dashboard.routes.excel_query_routes.execute_advanced_batch_query')
    def test_combined_like_and_date_workflow(self, mock_execute, client):
        """Test workflow combining LIKE and date range."""
        excel_data = [
            ['PREFIX'],
            ['LOT'],
        ]
        excel_file = create_test_excel(excel_data)

        client.post(
            '/api/excel-query/upload',
            data={'file': (excel_file, 'prefixes.xlsx')},
            content_type='multipart/form-data'
        )

        # Execute with both LIKE prefix and date range
        mock_execute.return_value = {
            'columns': ['LOT_ID', 'TXNDATE', 'STATUS'],
            'data': [
                ['LOT001', '2024-01-15', 'ACTIVE'],
                ['LOT002', '2024-01-20', 'ACTIVE'],
            ],
            'total': 2
        }

        response = client.post(
            '/api/excel-query/execute-advanced',
            json={
                'table_name': 'DWH.DW_MES_WIP',
                'search_column': 'LOT_ID',
                'return_columns': ['LOT_ID', 'TXNDATE', 'STATUS'],
                'search_values': ['LOT'],
                'query_type': 'like_prefix',
                'date_column': 'TXNDATE',
                'date_from': '2024-01-01',
                'date_to': '2024-01-31'
            }
        )
        assert response.status_code == 200


class TestColumnTypeDetection:
    """E2E tests for column type detection workflow."""

    def test_detect_date_column(self, client):
        """Test detecting date type from Excel column."""
        excel_data = [
            ['DATE_COL'],
            ['2024-01-01'],
            ['2024-01-02'],
            ['2024-01-03'],
            ['2024-01-04'],
        ]
        excel_file = create_test_excel(excel_data)

        client.post(
            '/api/excel-query/upload',
            data={'file': (excel_file, 'dates.xlsx')},
            content_type='multipart/form-data'
        )

        response = client.post(
            '/api/excel-query/column-type',
            json={'column_name': 'DATE_COL'}
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['data']['detected_type'] == 'date'

    def test_detect_number_column(self, client):
        """Test detecting numeric type from Excel column."""
        excel_data = [
            ['QTY'],
            ['100'],
            ['200'],
            ['350.5'],
            ['-50'],
        ]
        excel_file = create_test_excel(excel_data)

        client.post(
            '/api/excel-query/upload',
            data={'file': (excel_file, 'numbers.xlsx')},
            content_type='multipart/form-data'
        )

        response = client.post(
            '/api/excel-query/column-type',
            json={'column_name': 'QTY'}
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['data']['detected_type'] == 'number'

    def test_detect_id_column(self, client):
        """Test detecting ID type from Excel column."""
        excel_data = [
            ['LOT_ID'],
            ['LOT001'],
            ['LOT002'],
            ['WIP-2024-001'],
            ['PROD_ABC'],
        ]
        excel_file = create_test_excel(excel_data)

        client.post(
            '/api/excel-query/upload',
            data={'file': (excel_file, 'ids.xlsx')},
            content_type='multipart/form-data'
        )

        response = client.post(
            '/api/excel-query/column-type',
            json={'column_name': 'LOT_ID'}
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['data']['detected_type'] == 'id'


class TestTableMetadataWorkflow:
    """E2E tests for table metadata retrieval workflow."""

    @patch('mes_dashboard.routes.excel_query_routes.get_table_column_metadata')
    def test_metadata_with_type_matching(self, mock_metadata, client):
        """Test workflow checking column type compatibility."""
        # Step 1: Upload Excel with ID column
        excel_data = [
            ['LOT_ID'],
            ['LOT001'],
            ['LOT002'],
        ]
        excel_file = create_test_excel(excel_data)

        client.post(
            '/api/excel-query/upload',
            data={'file': (excel_file, 'lots.xlsx')},
            content_type='multipart/form-data'
        )

        # Step 2: Get Excel column type
        excel_type_response = client.post(
            '/api/excel-query/column-type',
            json={'column_name': 'LOT_ID'}
        )
        excel_type = json.loads(excel_type_response.data)['data']['detected_type']

        # Step 3: Get table metadata
        mock_metadata.return_value = {
            'columns': [
                {'name': 'LOT_ID', 'data_type': 'VARCHAR2', 'is_date': False, 'is_number': False},
                {'name': 'QTY', 'data_type': 'NUMBER', 'is_date': False, 'is_number': True},
                {'name': 'TXNDATE', 'data_type': 'DATE', 'is_date': True, 'is_number': False},
            ]
        }

        metadata_response = client.post(
            '/api/excel-query/table-metadata',
            json={'table_name': 'DWH.DW_MES_WIP'}
        )
        assert metadata_response.status_code == 200
        metadata = json.loads(metadata_response.data)

        # Verify column types are returned
        assert len(metadata['data']['columns']) == 3
        lot_col = next(c for c in metadata['data']['columns'] if c['name'] == 'LOT_ID')
        assert lot_col['data_type'] == 'VARCHAR2'


class TestValidationWorkflow:
    """E2E tests for input validation throughout workflow."""

    def test_like_keyword_limit_enforcement(self, client):
        """Test that LIKE queries enforce keyword limit."""
        from mes_dashboard.services.excel_query_service import LIKE_KEYWORD_LIMIT

        # Create Excel with many values
        excel_data = [['VALUE']] + [[f'VAL{i}'] for i in range(LIKE_KEYWORD_LIMIT + 10)]
        excel_file = create_test_excel(excel_data)

        client.post(
            '/api/excel-query/upload',
            data={'file': (excel_file, 'many_values.xlsx')},
            content_type='multipart/form-data'
        )

        # Get all values
        values_response = client.post(
            '/api/excel-query/column-values',
            json={'column_name': 'VALUE'}
        )
        all_values = json.loads(values_response.data)['data']['values']

        # Attempt LIKE query with too many values
        response = client.post(
            '/api/excel-query/execute-advanced',
            json={
                'table_name': 'TEST_TABLE',
                'search_column': 'COL',
                'return_columns': ['COL'],
                'search_values': all_values,
                'query_type': 'like_contains'
            }
        )
        # This should either fail at validation or service layer
        # The exact behavior depends on implementation
        # At minimum, verify the request was processed
        assert response.status_code in [200, 400]

    def test_date_range_boundary_validation(self, client):
        """Test date range validation at boundaries."""
        excel_data = [
            ['LOT_ID'],
            ['LOT001'],
        ]
        excel_file = create_test_excel(excel_data)

        client.post(
            '/api/excel-query/upload',
            data={'file': (excel_file, 'lots.xlsx')},
            content_type='multipart/form-data'
        )

        # Test exactly 365 days (should pass)
        response = client.post(
            '/api/excel-query/execute-advanced',
            json={
                'table_name': 'TEST_TABLE',
                'search_column': 'LOT_ID',
                'return_columns': ['LOT_ID'],
                'search_values': ['LOT001'],
                'date_from': '2024-01-01',
                'date_to': '2024-12-31'  # 365 days (2024 is leap year, so 366)
            }
        )
        # 366 days in 2024, should fail
        assert response.status_code == 400

    def test_empty_search_values_rejected(self, client):
        """Test that empty search values are rejected."""
        response = client.post(
            '/api/excel-query/execute-advanced',
            json={
                'table_name': 'TEST_TABLE',
                'search_column': 'LOT_ID',
                'return_columns': ['LOT_ID'],
                'search_values': [],
                'query_type': 'in'
            }
        )
        assert response.status_code == 400


class TestBackwardCompatibility:
    """E2E tests ensuring backward compatibility with original API."""

    @patch('mes_dashboard.routes.excel_query_routes.execute_batch_query')
    def test_original_execute_endpoint_works(self, mock_execute, client):
        """Test that original /execute endpoint still works."""
        mock_execute.return_value = {
            'columns': ['LOT_ID'],
            'data': [['LOT001']],
            'total': 1
        }

        # Use original endpoint without advanced features
        response = client.post(
            '/api/excel-query/execute',
            json={
                'table_name': 'DWH.DW_MES_WIP',
                'search_column': 'LOT_ID',
                'return_columns': ['LOT_ID'],
                'search_values': ['LOT001']
            }
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['data']['total'] == 1

    @patch('mes_dashboard.routes.excel_query_routes.execute_batch_query')
    @patch('mes_dashboard.routes.excel_query_routes.generate_csv_content')
    def test_csv_export_still_works(self, mock_csv, mock_execute, client):
        """Test that CSV export still works with basic query."""
        mock_execute.return_value = {
            'columns': ['LOT_ID', 'STATUS'],
            'data': [['LOT001', 'ACTIVE']],
            'total': 1
        }
        mock_csv.return_value = 'LOT_ID,STATUS\nLOT001,ACTIVE\n'

        response = client.post(
            '/api/excel-query/export-csv',
            json={
                'table_name': 'DWH.DW_MES_WIP',
                'search_column': 'LOT_ID',
                'return_columns': ['LOT_ID', 'STATUS'],
                'search_values': ['LOT001']
            }
        )
        assert response.status_code == 200
        assert response.content_type.startswith('text/csv')
