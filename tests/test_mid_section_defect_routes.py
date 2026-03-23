# -*- coding: utf-8 -*-
"""Route tests for mid-section defect APIs."""

from __future__ import annotations

from unittest.mock import patch

import mes_dashboard.core.database as db
from mes_dashboard.app import create_app
from mes_dashboard.core.rate_limit import reset_rate_limits_for_tests


def _client():
    db._ENGINE = None
    app = create_app('testing')
    app.config['TESTING'] = True
    return app.test_client()


def setup_function():
    reset_rate_limits_for_tests()


def teardown_function():
    reset_rate_limits_for_tests()


@patch('mes_dashboard.routes.mid_section_defect_routes.query_analysis')
@patch('mes_dashboard.routes.mid_section_defect_routes.is_async_available', return_value=False)
def test_analysis_success(_mock_async, mock_query_analysis):
    mock_query_analysis.return_value = {
        'kpi': {'total_input': 100},
        'charts': {'by_station': []},
        'daily_trend': [],
        'available_loss_reasons': ['A'],
        'genealogy_status': 'ready',
        'detail': [{}, {}],
    }

    client = _client()
    response = client.get(
        '/api/mid-section-defect/analysis?start_date=2025-01-01&end_date=2025-01-31&loss_reasons=A,B'
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['success'] is True
    assert payload['data']['detail_total_count'] == 2
    assert payload['data']['kpi']['total_input'] == 100
    mock_query_analysis.assert_called_once_with(
        '2025-01-01', '2025-01-31', ['A', 'B'], '測試', 'backward',
    )


@patch('mes_dashboard.routes.mid_section_defect_routes.query_analysis')
@patch('mes_dashboard.routes.mid_section_defect_routes.is_async_available', return_value=False)
def test_analysis_with_station_and_direction(_mock_async, mock_query_analysis):
    mock_query_analysis.return_value = {
        'kpi': {'detection_lot_count': 50},
        'charts': {'by_downstream_station': []},
        'daily_trend': [],
        'available_loss_reasons': [],
        'genealogy_status': 'ready',
        'detail': [],
    }

    client = _client()
    response = client.get(
        '/api/mid-section-defect/analysis?start_date=2025-01-01&end_date=2025-01-31&station=成型&direction=forward'
    )

    assert response.status_code == 200
    mock_query_analysis.assert_called_once_with(
        '2025-01-01', '2025-01-31', None, '成型', 'forward',
    )


def test_analysis_missing_dates_returns_400():
    client = _client()
    response = client.get('/api/mid-section-defect/analysis?start_date=2025-01-01')

    assert response.status_code == 400
    payload = response.get_json()
    assert payload['success'] is False


@patch('mes_dashboard.routes.mid_section_defect_routes.query_analysis')
@patch('mes_dashboard.routes.mid_section_defect_routes.is_async_available', return_value=False)
def test_analysis_service_failure_returns_500(_mock_async, mock_query_analysis):
    mock_query_analysis.return_value = None

    client = _client()
    response = client.get('/api/mid-section-defect/analysis?start_date=2025-01-01&end_date=2025-01-31')

    assert response.status_code == 500
    payload = response.get_json()
    assert payload['success'] is False


@patch('mes_dashboard.routes.mid_section_defect_routes.query_analysis')
@patch('mes_dashboard.core.rate_limit.check_and_record', return_value=(True, 7))
def test_analysis_rate_limited_returns_429(_mock_rate_limit, mock_query_analysis):
    client = _client()
    response = client.get('/api/mid-section-defect/analysis?start_date=2025-01-01&end_date=2025-01-31')

    assert response.status_code == 429
    assert response.headers.get('Retry-After') == '7'
    payload = response.get_json()
    assert payload['error']['code'] == 'TOO_MANY_REQUESTS'
    mock_query_analysis.assert_not_called()


@patch('mes_dashboard.routes.mid_section_defect_routes.enqueue_msd_analysis', return_value=('msd-abc123', None))
@patch('mes_dashboard.routes.mid_section_defect_routes.is_async_available', return_value=True)
@patch('mes_dashboard.routes.mid_section_defect_routes.query_analysis')
def test_analysis_async_returns_202(_mock_query_analysis, _mock_async, _mock_enqueue):
    client = _client()
    response = client.get(
        '/api/mid-section-defect/analysis?start_date=2025-01-01&end_date=2025-01-31'
    )

    assert response.status_code == 202
    payload = response.get_json()
    assert payload['success'] is True
    assert payload['data']['async'] is True
    assert payload['data']['job_id'] == 'msd-abc123'
    assert '/api/mid-section-defect/analysis/job/msd-abc123' in payload['data']['status_url']


@patch('mes_dashboard.routes.mid_section_defect_routes.get_msd_job_status', return_value=None)
def test_analysis_job_status_not_found_returns_404(_mock_status):
    client = _client()
    response = client.get('/api/mid-section-defect/analysis/job/msd-missing')
    assert response.status_code == 404


@patch('mes_dashboard.routes.mid_section_defect_routes.get_msd_job_status')
def test_analysis_job_status_success(mock_status):
    mock_status.return_value = {'job_id': 'msd-1', 'status': 'running'}
    client = _client()
    response = client.get('/api/mid-section-defect/analysis/job/msd-1')
    assert response.status_code == 200
    payload = response.get_json()
    assert payload['data']['status'] == 'running'


@patch('mes_dashboard.routes.mid_section_defect_routes.get_msd_job_status')
def test_analysis_job_result_returns_409_when_not_completed(mock_status):
    mock_status.return_value = {'job_id': 'msd-1', 'status': 'running'}
    client = _client()
    response = client.get('/api/mid-section-defect/analysis/job/msd-1/result')
    assert response.status_code == 409


@patch('mes_dashboard.routes.mid_section_defect_routes.get_msd_job_result')
@patch('mes_dashboard.routes.mid_section_defect_routes.get_msd_job_status')
def test_analysis_job_result_success(mock_status, mock_result):
    mock_status.return_value = {
        'job_id': 'msd-1',
        'status': 'completed',
        'query_id': 'mid_section_defect:None:{}',
    }
    mock_result.return_value = {
        'kpi': {'total_input': 123},
        'charts': {},
        'daily_trend': [],
        'available_loss_reasons': [],
        'genealogy_status': 'ready',
        'detail': [{'a': 1}],
        'attribution': [],
    }
    client = _client()
    response = client.get('/api/mid-section-defect/analysis/job/msd-1/result')
    assert response.status_code == 200
    payload = response.get_json()
    assert payload['data']['kpi']['total_input'] == 123
    assert payload['data']['detail_total_count'] == 1


@patch('mes_dashboard.routes.mid_section_defect_routes.query_analysis_detail')
def test_detail_success(mock_query_detail):
    mock_query_detail.return_value = {
        'detail': [{'CONTAINERNAME': 'LOT-1'}],
        'pagination': {'page': 2, 'page_size': 200, 'total_count': 350, 'total_pages': 2},
    }

    client = _client()
    response = client.get(
        '/api/mid-section-defect/analysis/detail?start_date=2025-01-01&end_date=2025-01-31&page=2&page_size=200'
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['success'] is True
    assert payload['data']['pagination']['page'] == 2
    mock_query_detail.assert_called_once_with(
        '2025-01-01',
        '2025-01-31',
        None,
        '測試',
        'backward',
        page=2,
        page_size=200,
    )


def test_detail_missing_dates_returns_400():
    client = _client()
    response = client.get('/api/mid-section-defect/analysis/detail?end_date=2025-01-31')

    assert response.status_code == 400
    payload = response.get_json()
    assert payload['success'] is False


@patch('mes_dashboard.routes.mid_section_defect_routes.query_analysis_detail')
@patch('mes_dashboard.core.rate_limit.check_and_record', return_value=(True, 5))
def test_detail_rate_limited_returns_429(_mock_rate_limit, mock_query_detail):
    client = _client()
    response = client.get('/api/mid-section-defect/analysis/detail?start_date=2025-01-01&end_date=2025-01-31')

    assert response.status_code == 429
    assert response.headers.get('Retry-After') == '5'
    payload = response.get_json()
    assert payload['error']['code'] == 'TOO_MANY_REQUESTS'
    mock_query_detail.assert_not_called()


@patch('mes_dashboard.routes.mid_section_defect_routes.export_csv')
def test_export_success(mock_export_csv):
    mock_export_csv.return_value = iter([
        '\ufeff',
        'LOT ID,TYPE\r\n',
        'A001,T1\r\n',
    ])

    client = _client()
    response = client.get(
        '/api/mid-section-defect/export?start_date=2025-01-01&end_date=2025-01-31&loss_reasons=A,B'
    )

    assert response.status_code == 200
    assert 'text/csv' in response.content_type
    assert 'attachment;' in response.headers.get('Content-Disposition', '')
    mock_export_csv.assert_called_once_with(
        '2025-01-01', '2025-01-31', ['A', 'B'], '測試', 'backward',
    )


@patch('mes_dashboard.routes.mid_section_defect_routes.export_csv')
@patch('mes_dashboard.core.rate_limit.check_and_record', return_value=(True, 9))
def test_export_rate_limited_returns_429(_mock_rate_limit, mock_export_csv):
    client = _client()
    response = client.get('/api/mid-section-defect/export?start_date=2025-01-01&end_date=2025-01-31')

    assert response.status_code == 429
    assert response.headers.get('Retry-After') == '9'
    payload = response.get_json()
    assert payload['error']['code'] == 'TOO_MANY_REQUESTS'
    mock_export_csv.assert_not_called()


@patch('mes_dashboard.routes.mid_section_defect_routes.query_station_options')
def test_station_options_success(mock_query_station_options):
    mock_query_station_options.return_value = [
        {'name': '切割', 'order': 0},
        {'name': '測試', 'order': 11},
    ]

    client = _client()
    response = client.get('/api/mid-section-defect/station-options')

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['success'] is True
    assert len(payload['data']) == 2
    assert payload['data'][0]['name'] == '切割'
