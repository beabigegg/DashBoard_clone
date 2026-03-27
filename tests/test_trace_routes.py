# -*- coding: utf-8 -*-
"""Route tests for staged trace API endpoints."""

from __future__ import annotations

from unittest.mock import patch

import pytest
import mes_dashboard.core.database as db
from mes_dashboard.app import create_app
from mes_dashboard.core.cache import NoOpCache
from mes_dashboard.core.rate_limit import reset_rate_limits_for_tests
from mes_dashboard.routes.trace_routes import _lineage_cache_key, _seed_cache_key


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


def test_lineage_cache_key_is_profile_aware():
    key_forward = _lineage_cache_key("query_tool", ["CID-001", "CID-002"])
    key_reverse = _lineage_cache_key("query_tool_reverse", ["CID-001", "CID-002"])
    assert key_forward != key_reverse
    assert key_forward.startswith("trace:lineage:query_tool:")
    assert key_reverse.startswith("trace:lineage:query_tool_reverse:")


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
    assert payload['data']['stage'] == 'seed-resolve'
    assert payload['data']['seed_count'] == 1
    assert payload['data']['seeds'][0]['container_id'] == 'CID-001'
    assert payload['data']['seeds'][0]['container_name'] == 'LOT-001'
    assert payload['data']['cache_key'].startswith('trace:seed:query_tool:')


@patch('mes_dashboard.routes.trace_routes.resolve_lots')
def test_seed_resolve_query_tool_reverse_success(mock_resolve_lots):
    mock_resolve_lots.return_value = {
        'data': [
            {
                'container_id': 'CID-SN',
                'lot_id': 'LOT-SN',
            }
        ]
    }

    client = _client()
    response = client.post(
        '/api/trace/seed-resolve',
        json={
            'profile': 'query_tool_reverse',
            'params': {
                'resolve_type': 'serial_number',
                'values': ['SN-001'],
            },
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['data']['stage'] == 'seed-resolve'
    assert payload['data']['seed_count'] == 1
    assert payload['data']['seeds'][0]['container_id'] == 'CID-SN'
    assert payload['data']['seeds'][0]['container_name'] == 'LOT-SN'
    assert payload['data']['cache_key'].startswith('trace:seed:query_tool_reverse:')


@patch('mes_dashboard.routes.trace_routes.resolve_lots')
def test_seed_resolve_query_tool_reverse_gd_lot_id_success(mock_resolve_lots):
    mock_resolve_lots.return_value = {
        'data': [
            {
                'container_id': 'CID-GD',
                'lot_id': 'GD25060502-A11',
            }
        ]
    }

    client = _client()
    response = client.post(
        '/api/trace/seed-resolve',
        json={
            'profile': 'query_tool_reverse',
            'params': {
                'resolve_type': 'gd_lot_id',
                'values': ['GD25060502-A11'],
            },
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['data']['seed_count'] == 1
    assert payload['data']['seeds'][0]['container_name'] == 'GD25060502-A11'


def test_seed_resolve_query_tool_rejects_reverse_only_type():
    client = _client()
    response = client.post(
        '/api/trace/seed-resolve',
        json={
            'profile': 'query_tool',
            'params': {
                'resolve_type': 'serial_number',
                'values': ['SN-001'],
            },
        },
    )

    assert response.status_code == 400
    payload = response.get_json()
    assert payload['error']['code'] == 'INVALID_PARAMS'


@pytest.mark.parametrize(
    ("resolve_type", "input_value"),
    [
        ("serial_number", "SN-001"),
        ("gd_work_order", "GD25060001"),
        ("gd_lot_id", "GD25060502-A11"),
    ],
)
@patch('mes_dashboard.routes.trace_routes.resolve_lots')
def test_seed_resolve_mid_section_defect_container_supports_reverse_input_types(
    mock_resolve_lots,
    resolve_type,
    input_value,
):
    mock_resolve_lots.return_value = {
        'data': [
            {
                'container_id': 'CID-MSD',
                'lot_id': 'LOT-MSD',
            }
        ]
    }

    client = _client()
    response = client.post(
        '/api/trace/seed-resolve',
        json={
            'profile': 'mid_section_defect',
            'params': {
                'mode': 'container',
                'resolve_type': resolve_type,
                'values': [input_value],
            },
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['data']['stage'] == 'seed-resolve'
    assert payload['data']['seed_count'] == 1
    assert payload['data']['seeds'][0]['container_id'] == 'CID-MSD'


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
    assert payload['data']['stage'] == 'lineage'
    assert payload['data']['roots'] == ['CID-ROOT']
    assert payload['data']['children_map']['CID-ROOT'] == ['CID-A']
    assert payload['data']['children_map']['CID-A'] == ['CID-001']
    assert payload['data']['leaf_serials']['CID-001'] == ['SN-001']
    assert payload['data']['total_nodes'] == 3
    assert payload['data']['names']['CID-ROOT'] == 'WAFER-001'
    assert payload['data']['names']['CID-A'] == 'LOT-A'


@patch('mes_dashboard.routes.trace_routes.LineageEngine.resolve_full_genealogy')
def test_lineage_reverse_profile_returns_ancestors(mock_resolve_genealogy):
    mock_resolve_genealogy.return_value = {
        'ancestors': {'CID-SN': {'CID-A', 'CID-B'}},
        'cid_to_name': {
            'CID-SN': 'LOT-SN',
            'CID-A': 'LOT-A',
            'CID-B': 'LOT-B',
        },
        'parent_map': {'CID-SN': ['CID-A'], 'CID-A': ['CID-B']},
        'merge_edges': {'CID-SN': ['CID-A']},
        'nodes': {
            'CID-SN': {'container_id': 'CID-SN', 'node_type': 'GD'},
            'CID-A': {'container_id': 'CID-A', 'node_type': 'GA'},
        },
        'edges': [
            {'from_cid': 'CID-A', 'to_cid': 'CID-SN', 'edge_type': 'gd_rework_source'},
        ],
    }

    client = _client()
    response = client.post(
        '/api/trace/lineage',
        json={
            'profile': 'query_tool_reverse',
            'container_ids': ['CID-SN'],
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['data']['stage'] == 'lineage'
    assert payload['data']['roots'] == ['CID-SN']
    assert sorted(payload['data']['ancestors']['CID-SN']) == ['CID-A', 'CID-B']
    assert payload['data']['parent_map']['CID-SN'] == ['CID-A']
    assert payload['data']['merge_edges']['CID-SN'] == ['CID-A']
    assert payload['data']['names']['CID-A'] == 'LOT-A'
    assert payload['data']['nodes']['CID-SN']['node_type'] == 'GD'
    assert payload['data']['edges'][0]['edge_type'] == 'gd_rework_source'


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
                'records_by_cid': {
                    'CID-001': [{'CONTAINERID': 'CID-001', 'EVENTTYPE': 'TRACK_IN'}],
                },
                'quality_meta': {
                    'status': 'complete',
                    'scope': 'domain',
                    'domain': 'history',
                    'reasons': [],
                },
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
    assert payload['data']['stage'] == 'events'
    assert payload['data']['code'] == 'EVENTS_PARTIAL_FAILURE'
    assert 'materials' in payload['data']['failed_domains']
    assert payload['data']['results']['history']['count'] == 1
    assert payload['data']['results']['history']['quality_meta']['status'] == 'complete'
    assert payload['data']['results']['materials']['quality_meta']['status'] == 'failed'
    assert payload['data']['quality_meta']['status'] == 'partial'


@patch('mes_dashboard.routes.trace_routes.build_trace_aggregation_from_events')
@patch('mes_dashboard.routes.trace_routes.EventFetcher.fetch_events')
def test_events_mid_section_defect_with_aggregation(
    mock_fetch_events,
    mock_build_aggregation,
):
    mock_fetch_events.return_value = {
        'records_by_cid': {
            'CID-001': [
                {
                    'CONTAINERID': 'CID-001',
                    'WORKCENTER_GROUP': '測試',
                    'EQUIPMENTID': 'EQ-01',
                    'EQUIPMENTNAME': 'EQ-01',
                }
            ]
        },
        'quality_meta': {
            'status': 'complete',
            'scope': 'domain',
            'domain': 'upstream_history',
            'reasons': [],
        },
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
    assert payload['data']['aggregation']['kpi']['total_input'] == 100
    assert payload['data']['aggregation']['genealogy_status'] == 'ready'
    assert payload['data']['results']['upstream_history']['quality_meta']['status'] == 'complete'
    assert payload['data']['quality_meta']['status'] == 'complete'
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


# ---- MSD cache isolation tests ----


def test_msd_seed_cache_key_ignores_loss_reasons():
    """Changing loss_reasons should not change the seed cache key for MSD."""
    base_params = {
        'start_date': '2025-01-01',
        'end_date': '2025-01-31',
        'station': '測試',
        'direction': 'backward',
    }
    key_all = _seed_cache_key('mid_section_defect', {**base_params, 'loss_reasons': ['A', 'B', 'C']})
    key_two = _seed_cache_key('mid_section_defect', {**base_params, 'loss_reasons': ['A']})
    key_none = _seed_cache_key('mid_section_defect', base_params)

    assert key_all == key_two == key_none


def test_non_msd_seed_cache_key_includes_all_params():
    """For non-MSD profiles the seed cache key should still hash all params."""
    params_a = {'resolve_type': 'lot_id', 'values': ['LOT-001'], 'extra': 'x'}
    params_b = {'resolve_type': 'lot_id', 'values': ['LOT-001'], 'extra': 'y'}

    key_a = _seed_cache_key('query_tool', params_a)
    key_b = _seed_cache_key('query_tool', params_b)
    assert key_a != key_b


@patch('mes_dashboard.routes.trace_routes.build_trace_aggregation_from_events')
@patch('mes_dashboard.routes.trace_routes.EventFetcher.fetch_events')
def test_msd_events_recomputes_aggregation_on_each_call(
    mock_fetch_events,
    mock_build_aggregation,
):
    """MSD events should NOT use events-level cache, so aggregation is always fresh."""
    mock_fetch_events.return_value = {
        'CID-001': [{'CONTAINERID': 'CID-001', 'WORKCENTER_GROUP': '測試'}]
    }
    mock_build_aggregation.return_value = {
        'kpi': {'total_input': 100},
        'charts': {},
        'daily_trend': [],
        'available_loss_reasons': [],
        'genealogy_status': 'ready',
        'detail_total_count': 0,
    }

    client = _client()
    body = {
        'profile': 'mid_section_defect',
        'container_ids': ['CID-001'],
        'domains': ['upstream_history'],
        'params': {
            'start_date': '2025-01-01',
            'end_date': '2025-01-31',
            'loss_reasons': ['Reason-A'],
        },
        'lineage': {'ancestors': {'CID-001': ['CID-A']}},
        'seed_container_ids': ['CID-001'],
    }

    # First call
    resp1 = client.post('/api/trace/events', json=body)
    assert resp1.status_code == 200

    # Second call with different loss_reasons — aggregation must be re-invoked
    body['params']['loss_reasons'] = ['Reason-B']
    resp2 = client.post('/api/trace/events', json=body)
    assert resp2.status_code == 200

    assert mock_build_aggregation.call_count == 2


@patch('mes_dashboard.routes.trace_routes.EventFetcher.fetch_events')
@patch('mes_dashboard.routes.trace_routes.cache_get')
@patch('mes_dashboard.routes.trace_routes.cache_set')
def test_non_msd_events_cache_unchanged(mock_cache_set, mock_cache_get, mock_fetch_events):
    """Non-MSD profiles should still use events-level cache as before."""
    cached_response = {
        'stage': 'events',
        'results': {'history': {'data': [], 'count': 0}},
        'aggregation': None,
    }
    mock_cache_get.return_value = cached_response

    client = _client()
    response = client.post(
        '/api/trace/events',
        json={
            'profile': 'query_tool',
            'container_ids': ['CID-001'],
            'domains': ['history'],
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['data']['stage'] == 'events'
    # EventFetcher should NOT have been called — served from cache
    mock_fetch_events.assert_not_called()


@patch('mes_dashboard.routes.trace_routes.EventFetcher.fetch_events')
@patch('mes_dashboard.routes.trace_routes.cache_get')
@patch('mes_dashboard.routes.trace_routes.cache_set')
def test_cached_events_replay_preserves_non_complete_quality_meta(
    mock_cache_set, mock_cache_get, mock_fetch_events
):
    """Cached events replay SHALL preserve non-complete quality_meta status (parity gate).

    When a response with non-complete quality_meta is stored and later replayed from cache,
    the replayed payload must retain the non-complete completeness semantics.
    """
    non_complete_cached = {
        'stage': 'events',
        'results': {
            'history': {
                'data': [],
                'count': 0,
                'quality_meta': {'status': 'truncated', 'scope': 'domain', 'domain': 'history', 'reasons': ['max_total_rows_exceeded']},
            },
        },
        'aggregation': None,
        'quality_meta': {'status': 'truncated', 'scope': 'query', 'reasons': ['max_total_rows_exceeded']},
        'domain_quality_meta': {
            'history': {'status': 'truncated', 'scope': 'domain', 'domain': 'history', 'reasons': ['max_total_rows_exceeded']},
        },
    }
    mock_cache_get.return_value = non_complete_cached

    client = _client()
    response = client.post(
        '/api/trace/events',
        json={
            'profile': 'query_tool',
            'container_ids': ['CID-001'],
            'domains': ['history'],
        },
    )

    assert response.status_code == 200
    payload = response.get_json()

    # Completeness metadata must be preserved through cache replay
    assert payload['data']['quality_meta']['status'] == 'truncated', (
        "Cached replay must preserve non-complete quality_meta.status"
    )
    assert payload['data']['domain_quality_meta']['history']['status'] == 'truncated', (
        "Cached replay must preserve domain-level non-complete quality_meta"
    )

    # EventFetcher must NOT have been called — result served from cache
    mock_fetch_events.assert_not_called()


@patch('mes_dashboard.routes.trace_routes.EventFetcher.fetch_events')
@patch('mes_dashboard.routes.trace_routes.cache_get')
@patch('mes_dashboard.routes.trace_routes.cache_set')
def test_cached_events_replay_domain_partial_overrides_stale_complete_top_level(
    mock_cache_set, mock_cache_get, mock_fetch_events
):
    """Stale top-level complete status must NOT hide a domain-level partial status.

    A cached payload where top-level quality_meta.status='complete' but a domain
    result carries quality_meta.status='partial' must be replayed with the top-level
    re-derived from domain metas, yielding a non-complete top-level status.
    This covers the silent-hide regression: top=complete, domain=partial → should warn.
    """
    stale_top_level_cached = {
        'stage': 'events',
        'results': {
            'history': {
                'data': [],
                'count': 0,
                # domain-level says partial — authoritative
                'quality_meta': {'status': 'partial', 'scope': 'domain', 'domain': 'history', 'reasons': ['chunk_failure']},
            },
        },
        'aggregation': None,
        # top-level says complete — stale/inconsistent, must be overridden
        'quality_meta': {'status': 'complete', 'scope': 'query', 'reasons': []},
        'domain_quality_meta': {
            'history': {'status': 'partial', 'scope': 'domain', 'domain': 'history', 'reasons': ['chunk_failure']},
        },
    }
    mock_cache_get.return_value = stale_top_level_cached

    client = _client()
    response = client.post(
        '/api/trace/events',
        json={
            'profile': 'query_tool',
            'container_ids': ['CID-001'],
            'domains': ['history'],
        },
    )

    assert response.status_code == 200
    payload = response.get_json()

    # Top-level status must be re-derived from domain metas, not taken from stale cached value
    assert payload['data']['quality_meta']['status'] == 'partial', (
        "_ensure_events_quality_meta must re-derive top-level status from domain metas; "
        "stale 'complete' top-level must not hide domain-level 'partial'"
    )
    assert payload['data']['domain_quality_meta']['history']['status'] == 'partial'
    mock_fetch_events.assert_not_called()


# ---- Admission control tests ----


@patch('mes_dashboard.routes.trace_routes.is_async_available', return_value=False)
def test_events_non_msd_cid_limit_returns_413(mock_async_available, monkeypatch):
    """Non-MSD profile exceeding CID limit should return 413 when async is unavailable."""
    monkeypatch.setattr(
        'mes_dashboard.routes.trace_routes.TRACE_EVENTS_CID_LIMIT', 5,
    )

    client = _client()
    response = client.post(
        '/api/trace/events',
        json={
            'profile': 'query_tool',
            'container_ids': [f'CID-{i}' for i in range(10)],
            'domains': ['history'],
        },
    )

    assert response.status_code == 413
    payload = response.get_json()
    assert payload['error']['code'] == 'CID_LIMIT_EXCEEDED'


@patch('mes_dashboard.routes.trace_routes.is_async_available', return_value=False)
def test_events_msd_exceeding_cid_limit_returns_413_without_async(
    mock_async_available,
    monkeypatch,
):
    """MSD profile exceeding CID limit should return 413 when async is unavailable."""
    monkeypatch.setattr(
        'mes_dashboard.routes.trace_routes.TRACE_EVENTS_CID_LIMIT', 5,
    )

    client = _client()
    response = client.post(
        '/api/trace/events',
        json={
            'profile': 'mid_section_defect',
            'container_ids': [f'CID-{i}' for i in range(10)],
            'domains': ['upstream_history'],
            'params': {
                'start_date': '2025-01-01',
                'end_date': '2025-01-31',
            },
        },
    )

    assert response.status_code == 413
    payload = response.get_json()
    assert payload['error']['code'] == 'CID_LIMIT_EXCEEDED'


@patch('mes_dashboard.routes.trace_routes.enqueue_trace_events_job')
@patch('mes_dashboard.routes.trace_routes.is_async_available', return_value=True)
def test_events_msd_exceeding_cid_limit_returns_202_with_async(
    mock_async_available,
    mock_enqueue,
    monkeypatch,
):
    """MSD profile exceeding CID limit should return 202 (async) when async is available."""
    monkeypatch.setattr(
        'mes_dashboard.routes.trace_routes.TRACE_EVENTS_CID_LIMIT', 5,
    )
    monkeypatch.setattr(
        'mes_dashboard.routes.trace_routes.TRACE_ASYNC_CID_THRESHOLD', 100,
    )
    mock_enqueue.return_value = ('msd-job-abc', None)

    client = _client()
    response = client.post(
        '/api/trace/events',
        json={
            'profile': 'mid_section_defect',
            'container_ids': [f'CID-{i}' for i in range(10)],
            'domains': ['upstream_history'],
            'params': {
                'start_date': '2025-01-01',
                'end_date': '2025-01-31',
            },
        },
    )

    assert response.status_code == 202
    payload = response.get_json()
    assert payload['data']['async'] is True
    assert payload['data']['job_id'] == 'msd-job-abc'


@patch('mes_dashboard.routes.trace_routes.EventFetcher.fetch_events')
def test_events_non_msd_within_limit_proceeds(mock_fetch_events):
    """Non-MSD profile within CID limit should proceed normally."""
    mock_fetch_events.return_value = {
        'CID-001': [{'CONTAINERID': 'CID-001', 'EVENTTYPE': 'TRACK_IN'}]
    }

    client = _client()
    response = client.post(
        '/api/trace/events',
        json={
            'profile': 'query_tool',
            'container_ids': ['CID-001'],
            'domains': ['history'],
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['data']['stage'] == 'events'


# ---- Async job queue tests ----


@patch('mes_dashboard.routes.trace_routes.enqueue_trace_events_job')
@patch('mes_dashboard.routes.trace_routes.is_async_available', return_value=True)
def test_events_routes_to_async_above_threshold(
    mock_async_avail,
    mock_enqueue,
    monkeypatch,
):
    """CID count > async threshold should return 202 with job_id."""
    monkeypatch.setattr(
        'mes_dashboard.routes.trace_routes.TRACE_ASYNC_CID_THRESHOLD', 5,
    )
    mock_enqueue.return_value = ('trace-evt-abc123', None)

    client = _client()
    response = client.post(
        '/api/trace/events',
        json={
            'profile': 'query_tool',
            'container_ids': [f'CID-{i}' for i in range(10)],
            'domains': ['history'],
        },
    )

    assert response.status_code == 202
    payload = response.get_json()
    assert payload['data']['async'] is True
    assert payload['data']['job_id'] == 'trace-evt-abc123'
    assert '/api/trace/job/trace-evt-abc123' in payload['data']['status_url']


@patch('mes_dashboard.routes.trace_routes.EventFetcher.fetch_events')
@patch('mes_dashboard.routes.trace_routes.is_async_available', return_value=False)
def test_events_falls_back_to_sync_when_async_unavailable(
    mock_async_avail,
    mock_fetch_events,
    monkeypatch,
):
    """When async is unavailable, should fall through to sync processing."""
    monkeypatch.setattr(
        'mes_dashboard.routes.trace_routes.TRACE_ASYNC_CID_THRESHOLD', 2,
    )
    mock_fetch_events.return_value = {
        f'CID-{i}': [{'CONTAINERID': f'CID-{i}'}]
        for i in range(3)
    }

    client = _client()
    response = client.post(
        '/api/trace/events',
        json={
            'profile': 'query_tool',
            'container_ids': [f'CID-{i}' for i in range(3)],
            'domains': ['history'],
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['data']['stage'] == 'events'
    mock_fetch_events.assert_called()


@patch('mes_dashboard.routes.trace_routes.EventFetcher.fetch_events')
@patch('mes_dashboard.routes.trace_routes.process_rss_mb', return_value=4096.0)
@patch('mes_dashboard.routes.trace_routes.enqueue_trace_events_job')
@patch('mes_dashboard.routes.trace_routes.is_async_available', return_value=True)
def test_events_rss_guard_routes_to_async_when_available(
    _mock_async_avail,
    mock_enqueue,
    _mock_rss,
    mock_fetch_events,
    monkeypatch,
):
    """RSS guard hit should route sync requests to async when queue is available."""
    monkeypatch.setattr(
        'mes_dashboard.routes.trace_routes.TRACE_ASYNC_CID_THRESHOLD', 99999,
    )
    mock_enqueue.return_value = ('trace-evt-rss-001', None)

    client = _client()
    response = client.post(
        '/api/trace/events',
        json={
            'profile': 'query_tool',
            'container_ids': ['CID-1', 'CID-2'],
            'domains': ['history'],
        },
    )

    assert response.status_code == 202
    payload = response.get_json()
    assert payload['data']['async'] is True
    assert payload['data']['job_id'] == 'trace-evt-rss-001'
    assert '/api/trace/job/trace-evt-rss-001' in payload['data']['status_url']
    mock_fetch_events.assert_not_called()


@patch('mes_dashboard.routes.trace_routes.EventFetcher.fetch_events')
@patch('mes_dashboard.routes.trace_routes.is_async_available', return_value=False)
@patch('mes_dashboard.routes.trace_routes.process_rss_mb', return_value=4096.0)
def test_events_rss_guard_returns_503_when_async_unavailable(
    _mock_rss,
    _mock_async_avail,
    mock_fetch_events,
):
    client = _client()
    response = client.post(
        '/api/trace/events',
        json={
            'profile': 'query_tool',
            'container_ids': ['CID-1', 'CID-2'],
            'domains': ['history'],
        },
    )

    assert response.status_code == 503
    payload = response.get_json()
    assert payload['error']['code'] == 'SERVICE_UNAVAILABLE'
    assert response.headers.get('Retry-After') == '30'
    mock_fetch_events.assert_not_called()


@patch('mes_dashboard.routes.trace_routes.enqueue_trace_events_job')
@patch('mes_dashboard.routes.trace_routes.is_async_available', return_value=True)
def test_events_falls_back_to_413_when_enqueue_fails(
    mock_async_avail,
    mock_enqueue,
    monkeypatch,
):
    """When enqueue fails for non-MSD, should fall back to 413."""
    monkeypatch.setattr(
        'mes_dashboard.routes.trace_routes.TRACE_ASYNC_CID_THRESHOLD', 3,
    )
    monkeypatch.setattr(
        'mes_dashboard.routes.trace_routes.TRACE_EVENTS_CID_LIMIT', 5,
    )
    mock_enqueue.return_value = (None, 'Redis down')

    client = _client()
    response = client.post(
        '/api/trace/events',
        json={
            'profile': 'query_tool',
            'container_ids': [f'CID-{i}' for i in range(10)],
            'domains': ['history'],
        },
    )

    assert response.status_code == 413
    payload = response.get_json()
    assert payload['error']['code'] == 'CID_LIMIT_EXCEEDED'


# ---- Job status/result endpoint tests ----


@patch('mes_dashboard.routes.trace_routes.get_job_status')
def test_job_status_found(mock_status):
    """GET /api/trace/job/<id> should return status."""
    mock_status.return_value = {
        'job_id': 'trace-evt-abc',
        'status': 'started',
        'profile': 'query_tool',
        'cid_count': 100,
        'domains': ['history'],
        'progress': 'fetching events',
        'created_at': 1740000000.0,
        'elapsed_seconds': 15.0,
        'error': None,
    }

    client = _client()
    response = client.get('/api/trace/job/trace-evt-abc')

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['data']['status'] == 'started'
    assert payload['data']['job_id'] == 'trace-evt-abc'


@patch('mes_dashboard.routes.trace_routes.get_job_status', return_value=None)
def test_job_status_not_found(mock_status):
    """GET /api/trace/job/<id> should return 404 for unknown job."""
    client = _client()
    response = client.get('/api/trace/job/trace-evt-nonexist')

    assert response.status_code == 404


@patch('mes_dashboard.routes.trace_routes.get_job_result')
@patch('mes_dashboard.routes.trace_routes.get_job_status')
def test_job_result_success(mock_status, mock_result):
    """GET /api/trace/job/<id>/result should return result for finished job."""
    mock_status.return_value = {'status': 'finished', 'job_id': 'j1'}
    mock_result.return_value = {
        'stage': 'events',
        'results': {'history': {'data': [], 'count': 0}},
        'aggregation': None,
    }

    client = _client()
    response = client.get('/api/trace/job/j1/result')

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['data']['stage'] == 'events'


@patch('mes_dashboard.routes.trace_routes.get_job_status')
def test_job_result_not_complete(mock_status):
    """GET /api/trace/job/<id>/result should return 409 for non-finished job."""
    mock_status.return_value = {'status': 'started', 'job_id': 'j2'}

    client = _client()
    response = client.get('/api/trace/job/j2/result')

    assert response.status_code == 409
    payload = response.get_json()
    assert payload['error']['code'] == 'JOB_NOT_COMPLETE'


@patch('mes_dashboard.routes.trace_routes.get_job_result', return_value=None)
@patch('mes_dashboard.routes.trace_routes.get_job_status')
def test_job_result_expired(mock_status, mock_result):
    """GET /api/trace/job/<id>/result should return 404 if result expired."""
    mock_status.return_value = {'status': 'finished', 'job_id': 'j3'}

    client = _client()
    response = client.get('/api/trace/job/j3/result')

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# NDJSON stream endpoint
# ---------------------------------------------------------------------------
@patch("mes_dashboard.routes.trace_routes.stream_job_result_ndjson")
@patch("mes_dashboard.routes.trace_routes.get_job_status")
def test_job_stream_success(mock_status, mock_stream):
    """GET /api/trace/job/<id>/stream should return NDJSON for finished job."""
    mock_status.return_value = {'status': 'finished', 'job_id': 'j1'}
    mock_stream.return_value = iter([
        '{"type":"meta","job_id":"j1","domains":["history"]}\n',
        '{"type":"complete","total_records":0}\n',
    ])

    reset_rate_limits_for_tests()
    client = _client()
    response = client.get('/api/trace/job/j1/stream')

    assert response.status_code == 200
    assert response.content_type.startswith('application/x-ndjson')

    lines = [l for l in response.data.decode().strip().split('\n') if l.strip()]
    assert len(lines) == 2


@patch("mes_dashboard.routes.trace_routes.get_job_status")
def test_job_stream_not_found(mock_status):
    """GET /api/trace/job/<id>/stream should return 404 for missing job."""
    mock_status.return_value = None

    reset_rate_limits_for_tests()
    client = _client()
    response = client.get('/api/trace/job/j-missing/stream')

    assert response.status_code == 404


@patch("mes_dashboard.routes.trace_routes.get_job_status")
def test_job_stream_not_complete(mock_status):
    """GET /api/trace/job/<id>/stream should return 409 for incomplete job."""
    mock_status.return_value = {'status': 'started', 'job_id': 'j2'}

    reset_rate_limits_for_tests()
    client = _client()
    response = client.get('/api/trace/job/j2/stream')

    assert response.status_code == 409


# ---------------------------------------------------------------------------
# 202 response includes stream_url
# ---------------------------------------------------------------------------
@patch("mes_dashboard.routes.trace_routes.is_async_available", return_value=True)
@patch("mes_dashboard.routes.trace_routes.enqueue_trace_events_job")
def test_events_async_response_includes_stream_url(mock_enqueue, mock_async):
    """Events 202 response should include stream_url field."""
    mock_enqueue.return_value = ("trace-evt-xyz", None)

    reset_rate_limits_for_tests()
    client = _client()
    cids = [f"CID-{i}" for i in range(25000)]
    response = client.post('/api/trace/events', json={
        'profile': 'query_tool',
        'container_ids': cids,
        'domains': ['history'],
    })

    assert response.status_code == 202
    data = response.get_json()
    assert data["data"]["stream_url"] == "/api/trace/job/trace-evt-xyz/stream"
    assert data["data"]["status_url"] == "/api/trace/job/trace-evt-xyz"


# ---- MSD async lineage endpoint tests ----


@patch('mes_dashboard.routes.trace_routes.is_async_available', return_value=True)
@patch('mes_dashboard.routes.trace_routes.enqueue_msd_lineage')
def test_lineage_msd_async_returns_202_when_seeds_exceed_threshold(
    mock_enqueue,
    mock_async,
    monkeypatch,
):
    """MSD lineage with seeds > LINEAGE_SEED_ASYNC_THRESHOLD should return 202."""
    monkeypatch.setattr('mes_dashboard.routes.trace_routes.LINEAGE_SEED_ASYNC_THRESHOLD', 5)
    mock_enqueue.return_value = ('msd-lineage-abc', None)

    reset_rate_limits_for_tests()
    client = _client()
    response = client.post('/api/trace/lineage', json={
        'profile': 'mid_section_defect',
        'container_ids': [f'CID-{i}' for i in range(10)],
        'params': {'direction': 'backward'},
    })

    assert response.status_code == 202
    payload = response.get_json()
    assert payload['data']['async'] is True
    assert payload['data']['job_id'] == 'msd-lineage-abc'
    assert '/api/trace/lineage/job/msd-lineage-abc' in payload['data']['status_url']


@patch('mes_dashboard.routes.trace_routes.get_msd_lineage_job_status')
def test_lineage_job_status_endpoint_found(mock_status):
    """GET /api/trace/lineage/job/<id> should return job status."""
    mock_status.return_value = {
        'job_id': 'msd-lineage-abc',
        'status': 'running',
        'progress': '5/56 split batches',
        'elapsed_seconds': 12.5,
    }

    reset_rate_limits_for_tests()
    client = _client()
    response = client.get('/api/trace/lineage/job/msd-lineage-abc')

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['data']['status'] == 'running'
    assert payload['data']['job_id'] == 'msd-lineage-abc'


@patch('mes_dashboard.routes.trace_routes.get_msd_lineage_job_status', return_value=None)
def test_lineage_job_status_endpoint_not_found(mock_status):
    """GET /api/trace/lineage/job/<id> should return 404 for unknown job."""
    reset_rate_limits_for_tests()
    client = _client()
    response = client.get('/api/trace/lineage/job/nonexistent')

    assert response.status_code == 404


@patch('mes_dashboard.routes.trace_routes.get_msd_lineage_job_result')
@patch('mes_dashboard.routes.trace_routes.get_msd_lineage_job_status')
def test_lineage_job_result_endpoint_success(mock_status, mock_result):
    """GET /api/trace/lineage/job/<id>/result should return reconstructed lineage."""
    mock_status.return_value = {'status': 'completed', 'job_id': 'msd-lineage-abc'}
    mock_result.return_value = {
        'stage': 'lineage',
        'ancestors': {'SEED1': ['ANC1', 'ANC2']},
        'names': {'ANC1': 'LOT-ANC1'},
        'seed_roots': {'SEED1': 'ROOT-1'},
        'total_nodes': 3,
        'total_ancestor_count': 2,
    }

    reset_rate_limits_for_tests()
    client = _client()
    response = client.get('/api/trace/lineage/job/msd-lineage-abc/result')

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['data']['stage'] == 'lineage'
    assert 'SEED1' in payload['data']['ancestors']


@patch('mes_dashboard.routes.trace_routes.get_msd_lineage_job_status')
def test_lineage_job_result_endpoint_job_still_running(mock_status):
    """GET /api/trace/lineage/job/<id>/result should return 409 when job not yet complete."""
    mock_status.return_value = {'status': 'running', 'job_id': 'msd-lineage-abc'}

    reset_rate_limits_for_tests()
    client = _client()
    response = client.get('/api/trace/lineage/job/msd-lineage-abc/result')

    assert response.status_code == 409
