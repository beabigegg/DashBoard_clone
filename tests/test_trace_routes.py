# -*- coding: utf-8 -*-
"""Route tests for staged trace API endpoints."""

from __future__ import annotations

from unittest.mock import patch

import mes_dashboard.core.database as db
from mes_dashboard.app import create_app
from mes_dashboard.core.cache import NoOpCache
from mes_dashboard.core.rate_limit import reset_rate_limits_for_tests


def _client():
    db._ENGINE = None
    app = create_app('testing')
    app.config['TESTING'] = True
    app.extensions["cache"] = NoOpCache()
    return app.test_client()


def setup_function():
    reset_rate_limits_for_tests()


def teardown_function():
    reset_rate_limits_for_tests()


@patch('mes_dashboard.routes.trace_routes.resolve_lots')
def test_seed_resolve_query_tool_success(mock_resolve_lots):
    mock_resolve_lots.return_value = {
        'data': [
            {
                'container_id': 'CID-001',
                'lot_id': 'LOT-001',
            }
        ]
    }

    client = _client()
    response = client.post(
        '/api/trace/seed-resolve',
        json={
            'profile': 'query_tool',
            'params': {
                'resolve_type': 'lot_id',
                'values': ['LOT-001'],
            },
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['stage'] == 'seed-resolve'
    assert payload['seed_count'] == 1
    assert payload['seeds'][0]['container_id'] == 'CID-001'
    assert payload['seeds'][0]['container_name'] == 'LOT-001'
    assert payload['cache_key'].startswith('trace:seed:query_tool:')


def test_seed_resolve_invalid_profile_returns_400():
    client = _client()
    response = client.post(
        '/api/trace/seed-resolve',
        json={
            'profile': 'invalid',
            'params': {},
        },
    )

    assert response.status_code == 400
    payload = response.get_json()
    assert payload['error']['code'] == 'INVALID_PROFILE'


@patch('mes_dashboard.core.rate_limit.check_and_record', return_value=(True, 8))
def test_seed_resolve_rate_limited_returns_429(_mock_rate_limit):
    client = _client()
    response = client.post(
        '/api/trace/seed-resolve',
        json={
            'profile': 'query_tool',
            'params': {'resolve_type': 'lot_id', 'values': ['LOT-001']},
        },
    )

    assert response.status_code == 429
    assert response.headers.get('Retry-After') == '8'
    payload = response.get_json()
    assert payload['error']['code'] == 'TOO_MANY_REQUESTS'


@patch('mes_dashboard.routes.trace_routes.LineageEngine.resolve_forward_tree')
def test_lineage_success_returns_forward_tree(mock_resolve_tree):
    mock_resolve_tree.return_value = {
        'roots': ['CID-ROOT'],
        'children_map': {'CID-ROOT': ['CID-A'], 'CID-A': ['CID-001']},
        'leaf_serials': {'CID-001': ['SN-001']},
        'cid_to_name': {'CID-ROOT': 'WAFER-001', 'CID-A': 'LOT-A', 'CID-001': 'LOT-001'},
        'total_nodes': 3,
    }

    client = _client()
    response = client.post(
        '/api/trace/lineage',
        json={
            'profile': 'query_tool',
            'container_ids': ['CID-001'],
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['stage'] == 'lineage'
    assert payload['roots'] == ['CID-ROOT']
    assert payload['children_map']['CID-ROOT'] == ['CID-A']
    assert payload['children_map']['CID-A'] == ['CID-001']
    assert payload['leaf_serials']['CID-001'] == ['SN-001']
    assert payload['total_nodes'] == 3
    assert payload['names']['CID-ROOT'] == 'WAFER-001'
    assert payload['names']['CID-A'] == 'LOT-A'


@patch(
    'mes_dashboard.routes.trace_routes.LineageEngine.resolve_forward_tree',
    side_effect=TimeoutError('lineage timed out'),
)
def test_lineage_timeout_returns_504(_mock_resolve_tree):
    client = _client()
    response = client.post(
        '/api/trace/lineage',
        json={
            'profile': 'query_tool',
            'container_ids': ['CID-001'],
        },
    )

    assert response.status_code == 504
    payload = response.get_json()
    assert payload['error']['code'] == 'LINEAGE_TIMEOUT'


@patch('mes_dashboard.core.rate_limit.check_and_record', return_value=(True, 6))
def test_lineage_rate_limited_returns_429(_mock_rate_limit):
    client = _client()
    response = client.post(
        '/api/trace/lineage',
        json={
            'profile': 'query_tool',
            'container_ids': ['CID-001'],
        },
    )

    assert response.status_code == 429
    assert response.headers.get('Retry-After') == '6'
    payload = response.get_json()
    assert payload['error']['code'] == 'TOO_MANY_REQUESTS'


@patch('mes_dashboard.routes.trace_routes.EventFetcher.fetch_events')
def test_events_partial_failure_returns_200_with_code(mock_fetch_events):
    def _side_effect(_container_ids, domain):
        if domain == 'history':
            return {
                'CID-001': [{'CONTAINERID': 'CID-001', 'EVENTTYPE': 'TRACK_IN'}]
            }
        raise RuntimeError('domain failed')

    mock_fetch_events.side_effect = _side_effect

    client = _client()
    response = client.post(
        '/api/trace/events',
        json={
            'profile': 'query_tool',
            'container_ids': ['CID-001'],
            'domains': ['history', 'materials'],
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['stage'] == 'events'
    assert payload['code'] == 'EVENTS_PARTIAL_FAILURE'
    assert 'materials' in payload['failed_domains']
    assert payload['results']['history']['count'] == 1


@patch('mes_dashboard.routes.trace_routes.build_trace_aggregation_from_events')
@patch('mes_dashboard.routes.trace_routes.EventFetcher.fetch_events')
def test_events_mid_section_defect_with_aggregation(
    mock_fetch_events,
    mock_build_aggregation,
):
    mock_fetch_events.return_value = {
        'CID-001': [
            {
                'CONTAINERID': 'CID-001',
                'WORKCENTER_GROUP': '測試',
                'EQUIPMENTID': 'EQ-01',
                'EQUIPMENTNAME': 'EQ-01',
            }
        ]
    }
    mock_build_aggregation.return_value = {
        'kpi': {'total_input': 100},
        'charts': {'by_station': []},
        'daily_trend': [],
        'available_loss_reasons': [],
        'genealogy_status': 'ready',
        'detail_total_count': 0,
    }

    client = _client()
    response = client.post(
        '/api/trace/events',
        json={
            'profile': 'mid_section_defect',
            'container_ids': ['CID-001'],
            'domains': ['upstream_history'],
            'params': {
                'start_date': '2025-01-01',
                'end_date': '2025-01-31',
            },
            'lineage': {'ancestors': {'CID-001': ['CID-A']}},
            'seed_container_ids': ['CID-001'],
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['aggregation']['kpi']['total_input'] == 100
    assert payload['aggregation']['genealogy_status'] == 'ready'
    mock_build_aggregation.assert_called_once()


@patch('mes_dashboard.core.rate_limit.check_and_record', return_value=(True, 5))
def test_events_rate_limited_returns_429(_mock_rate_limit):
    client = _client()
    response = client.post(
        '/api/trace/events',
        json={
            'profile': 'query_tool',
            'container_ids': ['CID-001'],
            'domains': ['history'],
        },
    )

    assert response.status_code == 429
    assert response.headers.get('Retry-After') == '5'
    payload = response.get_json()
    assert payload['error']['code'] == 'TOO_MANY_REQUESTS'
