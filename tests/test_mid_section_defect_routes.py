# -*- coding: utf-8 -*-
"""Route tests for mid-section defect APIs."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

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
def test_analysis_success(mock_query_analysis):
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
    call_args = mock_query_analysis.call_args
    assert call_args.args == ('2025-01-01', '2025-01-31', ['A', 'B'], ['測試'], 'backward')
    assert "owner" in call_args.kwargs


@patch('mes_dashboard.routes.mid_section_defect_routes.query_analysis')
def test_analysis_with_station_and_direction(mock_query_analysis):
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
    call_args = mock_query_analysis.call_args
    assert call_args.args == ('2025-01-01', '2025-01-31', None, ['成型'], 'forward')
    assert "owner" in call_args.kwargs


def test_analysis_missing_dates_returns_400():
    client = _client()
    response = client.get('/api/mid-section-defect/analysis?start_date=2025-01-01')

    assert response.status_code == 400
    payload = response.get_json()
    assert payload['success'] is False


@patch('mes_dashboard.routes.mid_section_defect_routes.query_analysis')
def test_analysis_service_failure_returns_500(mock_query_analysis):
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


@patch('mes_dashboard.routes.mid_section_defect_routes.query_analysis')
def test_analysis_returns_sync_summary(mock_query_analysis):
    mock_query_analysis.return_value = {
        'kpi': {'total_input': 123},
        'charts': {},
        'daily_trend': [],
        'available_loss_reasons': [],
        'genealogy_status': 'ready',
        'detail': [{'a': 1}],
        'attribution': [],
    }
    client = _client()
    response = client.get(
        '/api/mid-section-defect/analysis?start_date=2025-01-01&end_date=2025-01-31'
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['success'] is True
    assert payload['data']['kpi']['total_input'] == 123
    assert payload['data']['detail_total_count'] == 1


@patch('mes_dashboard.services.msd_duckdb_runtime.MsdDuckdbRuntime')
@patch('mes_dashboard.routes.mid_section_defect_routes.resolve_analysis_trace_context')
def test_detail_success(mock_resolve_context, mock_runtime_cls):
    mock_resolve_context.return_value = {
        'trace_query_id': 'msd-trace-001',
        'seed_container_ids': ['CID-001'],
    }
    mock_runtime = MagicMock()
    mock_runtime.is_available.return_value = True
    mock_runtime.get_detail.return_value = {
        'items': [{'CONTAINERNAME': 'LOT-1'}],
        'pagination': {'page': 2, 'per_page': 200, 'total': 350, 'total_pages': 2},
        'trace_query_id': 'msd-trace-001',
    }
    mock_runtime_cls.return_value = mock_runtime

    client = _client()
    response = client.get(
        '/api/mid-section-defect/analysis/detail?start_date=2025-01-01&end_date=2025-01-31&page=2&page_size=200'
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['success'] is True
    assert payload['data']['pagination']['page'] == 2
    assert payload['data']['pagination']['page_size'] == 200
    assert payload['data']['pagination']['total_count'] == 350


def test_detail_missing_dates_returns_400():
    client = _client()
    response = client.get('/api/mid-section-defect/analysis/detail?end_date=2025-01-31')

    assert response.status_code == 400
    payload = response.get_json()
    assert payload['success'] is False


@patch('mes_dashboard.core.rate_limit.check_and_record', return_value=(True, 5))
def test_detail_rate_limited_returns_429(_mock_rate_limit):
    client = _client()
    response = client.get('/api/mid-section-defect/analysis/detail?start_date=2025-01-01&end_date=2025-01-31')

    assert response.status_code == 429
    assert response.headers.get('Retry-After') == '5'
    payload = response.get_json()
    assert payload['error']['code'] == 'TOO_MANY_REQUESTS'


@patch('mes_dashboard.services.msd_duckdb_runtime.MsdDuckdbRuntime')
@patch('mes_dashboard.routes.mid_section_defect_routes.resolve_analysis_trace_context')
def test_export_success(mock_resolve_context, mock_runtime_cls):
    mock_resolve_context.return_value = {
        'trace_query_id': 'msd-trace-001',
        'seed_container_ids': ['CID-001'],
    }
    mock_runtime = MagicMock()
    mock_runtime.is_available.return_value = True
    mock_runtime.export_csv.return_value = iter([b'\xef\xbb\xbfLOT ID,TYPE\r\n', b'A001,T1\r\n'])
    mock_runtime_cls.return_value = mock_runtime

    client = _client()
    response = client.get(
        '/api/mid-section-defect/export?start_date=2025-01-01&end_date=2025-01-31&loss_reasons=A,B'
    )

    assert response.status_code == 200
    assert 'text/csv' in response.content_type
    assert 'attachment;' in response.headers.get('Content-Disposition', '')
    assert response.data.startswith(b'\xef\xbb\xbf')


@patch('mes_dashboard.core.rate_limit.check_and_record', return_value=(True, 9))
def test_export_rate_limited_returns_429(_mock_rate_limit):
    client = _client()
    response = client.get('/api/mid-section-defect/export?start_date=2025-01-01&end_date=2025-01-31')

    assert response.status_code == 429
    assert response.headers.get('Retry-After') == '9'
    payload = response.get_json()
    assert payload['error']['code'] == 'TOO_MANY_REQUESTS'


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


# ── Task 1.3: MSD detail/export spool miss → 410, no auto-dispatch ──────────

@patch('mes_dashboard.services.msd_duckdb_runtime.MsdDuckdbRuntime')
@patch('mes_dashboard.routes.mid_section_defect_routes.resolve_analysis_trace_context')
def test_detail_spool_miss_returns_410(mock_resolve_context, mock_runtime_cls):
    """When MsdDuckdbRuntime spool is unavailable, detail endpoint returns 410."""
    mock_resolve_context.return_value = {
        'trace_query_id': 'msd-trace-abc',
        'seed_container_ids': ['CID-001'],
    }
    mock_runtime = MagicMock()
    mock_runtime.is_available.return_value = False
    mock_runtime_cls.return_value = mock_runtime

    client = _client()
    response = client.get(
        '/api/mid-section-defect/analysis/detail?start_date=2025-01-01&end_date=2025-01-31'
    )

    assert response.status_code == 410
    payload = response.get_json()
    assert payload['success'] is False
    assert payload['error']['code'] == 'CACHE_EXPIRED'


@patch('mes_dashboard.services.msd_duckdb_runtime.MsdDuckdbRuntime')
@patch('mes_dashboard.routes.mid_section_defect_routes.resolve_analysis_trace_context')
def test_detail_spool_miss_does_not_dispatch_job(mock_resolve_context, mock_runtime_cls):
    """On spool miss, detail route must NOT call ensure_analysis_background_job."""
    mock_resolve_context.return_value = {
        'trace_query_id': 'msd-trace-abc',
        'seed_container_ids': ['CID-001'],
    }
    mock_runtime = MagicMock()
    mock_runtime.is_available.return_value = False
    mock_runtime_cls.return_value = mock_runtime

    with patch(
        'mes_dashboard.services.mid_section_defect_service.ensure_analysis_background_job'
    ) as mock_dispatch:
        client = _client()
        client.get(
            '/api/mid-section-defect/analysis/detail?start_date=2025-01-01&end_date=2025-01-31'
        )
        mock_dispatch.assert_not_called()


@patch('mes_dashboard.services.msd_duckdb_runtime.MsdDuckdbRuntime')
@patch('mes_dashboard.routes.mid_section_defect_routes.resolve_analysis_trace_context')
def test_export_spool_miss_returns_410(mock_resolve_context, mock_runtime_cls):
    """When MsdDuckdbRuntime spool is unavailable, export endpoint returns 410."""
    mock_resolve_context.return_value = {
        'trace_query_id': 'msd-trace-abc',
        'seed_container_ids': ['CID-001'],
    }
    mock_runtime = MagicMock()
    mock_runtime.is_available.return_value = False
    mock_runtime_cls.return_value = mock_runtime

    client = _client()
    response = client.get(
        '/api/mid-section-defect/export?start_date=2025-01-01&end_date=2025-01-31'
    )

    assert response.status_code == 410
    payload = response.get_json()
    assert payload['success'] is False
    assert payload['error']['code'] == 'CACHE_EXPIRED'


@patch('mes_dashboard.services.msd_duckdb_runtime.MsdDuckdbRuntime')
@patch('mes_dashboard.routes.mid_section_defect_routes.resolve_analysis_trace_context')
def test_export_spool_miss_does_not_dispatch_job(mock_resolve_context, mock_runtime_cls):
    """On spool miss, export route must NOT call ensure_analysis_background_job."""
    mock_resolve_context.return_value = {
        'trace_query_id': 'msd-trace-abc',
        'seed_container_ids': ['CID-001'],
    }
    mock_runtime = MagicMock()
    mock_runtime.is_available.return_value = False
    mock_runtime_cls.return_value = mock_runtime

    with patch(
        'mes_dashboard.services.mid_section_defect_service.ensure_analysis_background_job'
    ) as mock_dispatch:
        client = _client()
        client.get(
            '/api/mid-section-defect/export?start_date=2025-01-01&end_date=2025-01-31'
        )
        mock_dispatch.assert_not_called()


# ─── pj_types / packages route forwarding tests ───────────────────────────────

@patch('mes_dashboard.routes.mid_section_defect_routes.query_analysis')
def test_analysis_forwards_pj_types_kwarg(mock_query_analysis):
    """Route must forward pj_types[] as pj_types kwarg to query_analysis."""
    mock_query_analysis.return_value = {
        'kpi': {}, 'charts': {}, 'daily_trend': [],
        'available_loss_reasons': [], 'genealogy_status': 'ready',
        'detail': [],
    }

    client = _client()
    client.get(
        '/api/mid-section-defect/analysis'
        '?start_date=2025-01-01&end_date=2025-01-31'
        '&pj_types[]=TYPE-A&pj_types[]=TYPE-B'
    )

    assert mock_query_analysis.called
    assert mock_query_analysis.call_args.kwargs['pj_types'] == ['TYPE-A', 'TYPE-B']


@patch('mes_dashboard.routes.mid_section_defect_routes.query_analysis')
def test_analysis_forwards_packages_kwarg(mock_query_analysis):
    """Route must forward packages[] as packages kwarg to query_analysis."""
    mock_query_analysis.return_value = {
        'kpi': {}, 'charts': {}, 'daily_trend': [],
        'available_loss_reasons': [], 'genealogy_status': 'ready',
        'detail': [],
    }

    client = _client()
    client.get(
        '/api/mid-section-defect/analysis'
        '?start_date=2025-01-01&end_date=2025-01-31'
        '&packages[]=PKG-X&packages[]=PKG-Y'
    )

    assert mock_query_analysis.called
    assert mock_query_analysis.call_args.kwargs['packages'] == ['PKG-X', 'PKG-Y']


@patch('mes_dashboard.routes.mid_section_defect_routes.query_analysis')
def test_analysis_absent_pj_types_forwards_unchanged(mock_query_analysis):
    """When pj_types[] is absent, route forwards empty list (AC-5 baseline unchanged)."""
    mock_query_analysis.return_value = {
        'kpi': {}, 'charts': {}, 'daily_trend': [],
        'available_loss_reasons': [], 'genealogy_status': 'ready',
        'detail': [],
    }

    client = _client()
    client.get(
        '/api/mid-section-defect/analysis?start_date=2025-01-01&end_date=2025-01-31'
    )

    assert mock_query_analysis.called
    assert mock_query_analysis.call_args.kwargs['pj_types'] == []
    assert mock_query_analysis.call_args.kwargs['packages'] == []


# ─── container-filter-options route tests ─────────────────────────────────────

@patch('mes_dashboard.services.container_filter_cache.get_filter_options')
def test_container_filter_options_returns_type_and_package_lists(mock_get_filter_options):
    """GET /container-filter-options returns data with pj_types and packages arrays."""
    mock_get_filter_options.return_value = {
        'pj_types': ['TYPE-A', 'TYPE-B'],
        'packages': ['PKG-X', 'PKG-Y'],
        'bops': ['BOP-1'],
        'pj_functions': [],
        'updated_at': '2025-01-01T00:00:00+00:00',
        'schema_version': 2,
    }

    client = _client()
    response = client.get('/api/mid-section-defect/container-filter-options')

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['success'] is True
    assert 'pj_types' in payload['data']
    assert 'packages' in payload['data']
    assert payload['data']['pj_types'] == ['TYPE-A', 'TYPE-B']
    assert payload['data']['packages'] == ['PKG-X', 'PKG-Y']
    assert 'updated_at' in payload.get('meta', {})


@patch('mes_dashboard.services.container_filter_cache.get_filter_options')
def test_container_filter_options_does_not_call_read_sql_df(mock_get_filter_options):
    """Container-filter-options uses cache; read_sql_df is NOT called (AC-6)."""
    mock_get_filter_options.return_value = {
        'pj_types': [],
        'packages': [],
        'bops': [],
        'pj_functions': [],
        'updated_at': None,
        'schema_version': 2,
    }

    with patch('mes_dashboard.core.database.read_sql_df') as mock_db:
        client = _client()
        client.get('/api/mid-section-defect/container-filter-options')
        mock_db.assert_not_called()


def test_container_filter_options_malformed_selected_returns_400():
    """Malformed JSON in selected param → 400."""
    client = _client()
    response = client.get(
        '/api/mid-section-defect/container-filter-options?selected=not-json'
    )

    assert response.status_code == 400
    payload = response.get_json()
    assert payload['success'] is False


@patch('mes_dashboard.services.container_filter_cache.get_filter_options')
def test_analysis_route_malformed_pj_types_no_5xx(mock_get_filter_options):
    """Malformed pj_types param (single value, not list form) → graceful no filter, no 5xx."""
    mock_get_filter_options.return_value = {
        'pj_types': [], 'packages': [], 'bops': [], 'pj_functions': [],
        'updated_at': None, 'schema_version': 2,
    }
    with patch('mes_dashboard.routes.mid_section_defect_routes.query_analysis') as mock_qa:
        mock_qa.return_value = {
            'kpi': {}, 'charts': {}, 'daily_trend': [],
            'available_loss_reasons': [], 'genealogy_status': 'ready',
            'detail': [],
        }
        client = _client()
        # Passing as single value (non-list form) — getlist returns it as single-element list
        response = client.get(
            '/api/mid-section-defect/analysis'
            '?start_date=2025-01-01&end_date=2025-01-31&pj_types[]=single'
        )
        # Must not return 5xx
        assert response.status_code < 500
