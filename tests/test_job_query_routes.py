# -*- coding: utf-8 -*-
"""Integration tests for Job Query API routes.

Tests the API endpoints with mocked service dependencies.
"""

import pytest
import json
from unittest.mock import patch

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


class TestJobQueryPage:
    """Tests for /job-query page route."""

    def test_page_returns_html(self, client):
        """Should redirect direct entry to canonical shell page."""
        response = client.get('/job-query', follow_redirects=False)
        assert response.status_code == 302
        assert response.location.endswith('/portal-shell/job-query')


class TestGetResources:
    """Tests for /api/job-query/resources endpoint."""

    @patch('mes_dashboard.services.resource_cache.get_all_resources')
    def test_get_resources_success(self, mock_get_resources, client):
        """Should return resources list."""
        mock_get_resources.return_value = [
            {
                'RESOURCEID': 'RES001',
                'RESOURCENAME': 'Machine-01',
                'WORKCENTERNAME': 'WC-A',
                'RESOURCEFAMILYNAME': 'FAM-01'
            },
            {
                'RESOURCEID': 'RES002',
                'RESOURCENAME': 'Machine-02',
                'WORKCENTERNAME': 'WC-B',
                'RESOURCEFAMILYNAME': 'FAM-02'
            }
        ]

        response = client.get('/api/job-query/resources')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'data' in data
        inner = data['data']
        assert isinstance(inner, dict)
        assert isinstance(inner['data'], list)
        assert len(inner['data']) == 2
        assert inner['data'][0]['RESOURCEID'] in ['RES001', 'RES002']

    @patch('mes_dashboard.services.resource_cache.get_all_resources')
    def test_get_resources_empty(self, mock_get_resources, client):
        """Should return error when no resources available."""
        mock_get_resources.return_value = []

        response = client.get('/api/job-query/resources')
        assert response.status_code == 500
        data = json.loads(response.data)
        assert 'error' in data

    @patch('mes_dashboard.services.resource_cache.get_all_resources')
    def test_get_resources_exception(self, mock_get_resources, client):
        """Should handle exception gracefully."""
        mock_get_resources.side_effect = Exception('ORA-01017 invalid username/password')

        response = client.get('/api/job-query/resources')
        assert response.status_code == 503
        data = json.loads(response.data)
        assert 'error' in data
        assert '服務暫時無法使用' in data['error']['message']
        assert 'ORA-01017' not in str(data['error'])


class TestQueryJobs:
    """Tests for /api/job-query/jobs endpoint."""

    @patch('mes_dashboard.routes.job_query_routes.get_jobs_by_resources')
    def test_non_json_payload_returns_415(self, mock_query, client):
        response = client.post(
            '/api/job-query/jobs',
            data='plain-text',
            content_type='text/plain',
        )
        assert response.status_code == 415
        payload = response.get_json()
        assert 'error' in payload
        mock_query.assert_not_called()

    @patch('mes_dashboard.routes.job_query_routes.get_jobs_by_resources')
    def test_malformed_json_returns_400(self, mock_query, client):
        response = client.post(
            '/api/job-query/jobs',
            data='{"resource_ids":',
            content_type='application/json',
        )
        assert response.status_code == 400
        payload = response.get_json()
        assert 'error' in payload
        mock_query.assert_not_called()

    @patch('mes_dashboard.routes.job_query_routes.get_jobs_by_resources')
    def test_payload_too_large_returns_413(self, mock_query, client):
        client.application.config['MAX_JSON_BODY_BYTES'] = 8
        response = client.post(
            '/api/job-query/jobs',
            data='{"resource_ids":["RES001"]}',
            content_type='application/json',
        )
        assert response.status_code == 413
        payload = response.get_json()
        assert 'error' in payload
        mock_query.assert_not_called()

    def test_missing_resource_ids(self, client):
        """Should return error without resource_ids."""
        response = client.post(
            '/api/job-query/jobs',
            json={
                'start_date': '2024-01-01',
                'end_date': '2024-01-31'
            }
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data
        assert '設備' in data['error']['message']

    def test_empty_resource_ids(self, client):
        """Should return error for empty resource_ids."""
        response = client.post(
            '/api/job-query/jobs',
            json={
                'resource_ids': [],
                'start_date': '2024-01-01',
                'end_date': '2024-01-31'
            }
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data

    def test_missing_start_date(self, client):
        """Should return error without start_date."""
        response = client.post(
            '/api/job-query/jobs',
            json={
                'resource_ids': ['RES001'],
                'end_date': '2024-01-31'
            }
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data
        assert '日期' in data['error']['message']

    def test_missing_end_date(self, client):
        """Should return error without end_date."""
        response = client.post(
            '/api/job-query/jobs',
            json={
                'resource_ids': ['RES001'],
                'start_date': '2024-01-01'
            }
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data

    def test_invalid_date_range(self, client):
        """Should return error for invalid date range."""
        response = client.post(
            '/api/job-query/jobs',
            json={
                'resource_ids': ['RES001'],
                'start_date': '2024-12-31',
                'end_date': '2024-01-01'
            }
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data
        assert '結束日期' in data['error']['message'] or '早於' in data['error']['message']

    def test_date_range_exceeds_limit(self, client):
        """Should reject date range > 730 days (2 years)."""
        response = client.post(
            '/api/job-query/jobs',
            json={
                'resource_ids': ['RES001'],
                'start_date': '2023-01-01',
                'end_date': '2025-02-28'
            }
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data
        assert '730' in data['error']['message']

    @patch('mes_dashboard.routes.job_query_routes.get_jobs_by_resources')
    def test_query_jobs_success(self, mock_query, client):
        """Should return jobs list on success."""
        mock_query.return_value = {
            'data': [
                {'JOBID': 'JOB001', 'RESOURCENAME': 'Machine-01', 'JOBSTATUS': 'Complete'}
            ],
            'total': 1,
            'resource_count': 1
        }

        response = client.post(
            '/api/job-query/jobs',
            json={
                'resource_ids': ['RES001'],
                'start_date': '2024-01-01',
                'end_date': '2024-01-31'
            }
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'data' in data
        inner = data['data']
        assert isinstance(inner, dict)
        assert isinstance(inner['data'], list)
        assert len(inner['data']) == 1
        assert inner['data'][0]['JOBID'] == 'JOB001'

    @patch('mes_dashboard.routes.job_query_routes.get_jobs_by_resources')
    def test_query_jobs_service_error(self, mock_query, client):
        """Should return error from service."""
        mock_query.return_value = {'error': '查詢失敗: Database error'}

        response = client.post(
            '/api/job-query/jobs',
            json={
                'resource_ids': ['RES001'],
                'start_date': '2024-01-01',
                'end_date': '2024-01-31'
            }
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data


class TestQueryJobTxnHistory:
    """Tests for /api/job-query/txn/<job_id> endpoint."""

    @patch('mes_dashboard.routes.job_query_routes.get_job_txn_history')
    def test_get_txn_history_success(self, mock_query, client):
        """Should return transaction history."""
        mock_query.return_value = {
            'data': [
                {
                    'JOBTXNHISTORYID': 'TXN001',
                    'JOBID': 'JOB001',
                    'TXNDATE': '2024-01-15 10:30:00',
                    'FROMJOBSTATUS': 'Open',
                    'JOBSTATUS': 'In Progress'
                }
            ],
            'total': 1,
            'job_id': 'JOB001'
        }

        response = client.get('/api/job-query/txn/JOB001')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'data' in data
        inner = data['data']
        assert isinstance(inner, dict)
        assert isinstance(inner['data'], list)
        assert len(inner['data']) == 1
        assert inner['data'][0]['JOBTXNHISTORYID'] == 'TXN001'

    @patch('mes_dashboard.routes.job_query_routes.get_job_txn_history')
    def test_get_txn_history_service_error(self, mock_query, client):
        """Should return error from service."""
        mock_query.return_value = {'error': '查詢失敗: Job not found'}

        response = client.get('/api/job-query/txn/INVALID_JOB')
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data


class TestExportJobs:
    """Tests for /api/job-query/export endpoint."""

    @patch('mes_dashboard.routes.job_query_routes.export_jobs_with_history')
    def test_non_json_payload_returns_415(self, mock_export, client):
        response = client.post(
            '/api/job-query/export',
            data='plain-text',
            content_type='text/plain',
        )
        assert response.status_code == 415
        payload = response.get_json()
        assert 'error' in payload
        mock_export.assert_not_called()

    @patch('mes_dashboard.routes.job_query_routes.export_jobs_with_history')
    def test_malformed_json_returns_400(self, mock_export, client):
        response = client.post(
            '/api/job-query/export',
            data='{"resource_ids":',
            content_type='application/json',
        )
        assert response.status_code == 400
        payload = response.get_json()
        assert 'error' in payload
        mock_export.assert_not_called()

    def test_missing_resource_ids(self, client):
        """Should return error without resource_ids."""
        response = client.post(
            '/api/job-query/export',
            json={
                'start_date': '2024-01-01',
                'end_date': '2024-01-31'
            }
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data

    def test_missing_dates(self, client):
        """Should return error without dates."""
        response = client.post(
            '/api/job-query/export',
            json={
                'resource_ids': ['RES001']
            }
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data

    def test_invalid_date_range(self, client):
        """Should return error for invalid date range."""
        response = client.post(
            '/api/job-query/export',
            json={
                'resource_ids': ['RES001'],
                'start_date': '2024-12-31',
                'end_date': '2024-01-01'
            }
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data

    @patch('mes_dashboard.routes.job_query_routes.export_jobs_with_history')
    def test_export_success(self, mock_export, client):
        """Should return CSV streaming response."""
        # Mock generator that yields CSV content
        def mock_generator(*args):
            yield '\ufeff設備名稱,工單ID\n'
            yield 'Machine-01,JOB001\n'

        mock_export.return_value = mock_generator()

        response = client.post(
            '/api/job-query/export',
            json={
                'resource_ids': ['RES001'],
                'start_date': '2024-01-01',
                'end_date': '2024-01-31'
            }
        )
        assert response.status_code == 200
        assert 'text/csv' in response.content_type
        assert 'attachment' in response.headers.get('Content-Disposition', '')
        assert 'job_history_export.csv' in response.headers.get('Content-Disposition', '')
