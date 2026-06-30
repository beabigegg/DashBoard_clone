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


@pytest.mark.parametrize(
    ("resolve_type", "input_value"),
    [
        ("gd_work_order", "GD25060001"),
        ("gd_lot_id", "GD25060502-A11"),
        ("work_order", "GA26010001"),
        ("lot_id", "LOT-001"),
        ("wafer_lot", "WAFER-001"),
    ],
)
@patch('mes_dashboard.routes.trace_routes.resolve_msd_seeds_at_station')
def test_seed_resolve_mid_section_defect_container_station_resolve_types_use_detection_history(
    mock_resolve_station,
    resolve_type,
    input_value,
):
    mock_resolve_station.return_value = (
        [
            {
                'container_id': 'CID-MSD',
                'container_name': 'LOT-MSD',
                'lot_id': 'LOT-MSD',
            }
        ],
        None,
    )

    client = _client()
    response = client.post(
        '/api/trace/seed-resolve',
        json={
            'profile': 'mid_section_defect',
            'params': {
                'mode': 'container',
                'resolve_type': resolve_type,
                'values': [input_value],
                'station': '測試',
            },
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['data']['seed_count'] == 1
    assert payload['data']['seeds'][0]['container_id'] == 'CID-MSD'
    mock_resolve_station.assert_called_once_with(resolve_type, [input_value], '測試')


@patch('mes_dashboard.routes.trace_routes.resolve_msd_seeds_at_station')
def test_seed_resolve_mid_section_defect_container_station_resolve_types_return_404_when_no_detection_records(
    mock_resolve_station,
):
    mock_resolve_station.return_value = ([], None)

    client = _client()
    response = client.post(
        '/api/trace/seed-resolve',
        json={
            'profile': 'mid_section_defect',
            'params': {
                'mode': 'container',
                'resolve_type': 'gd_work_order',
                'values': ['GD25060001'],
                'station': '測試',
            },
        },
    )

    assert response.status_code == 404
    payload = response.get_json()
    assert payload['error']['code'] == 'NO_DETECTION_RECORDS'


@patch('mes_dashboard.routes.trace_routes.resolve_trace_seed_lots')
def test_seed_resolve_mid_section_defect_date_range_returns_compact_ids(mock_resolve):
    mock_resolve.return_value = {
        'seeds': [
            {'container_id': 'CID-001', 'container_name': 'LOT-001'},
            {'container_id': 'CID-002', 'container_name': 'LOT-002'},
        ],
        'seed_count': 2,
    }

    client = _client()
    response = client.post(
        '/api/trace/seed-resolve',
        json={
            'profile': 'mid_section_defect',
            'params': {
                'start_date': '2025-01-01',
                'end_date': '2025-01-31',
                'station': '測試',
            },
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['data']['seed_container_ids'] == ['CID-001', 'CID-002']
    assert 'seeds' not in payload['data']


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


@patch('mes_dashboard.routes.trace_routes.is_async_available', return_value=True)
@patch('mes_dashboard.routes.trace_routes.enqueue_trace_lineage')
def test_lineage_query_tool_routes_to_async(mock_enqueue, _mock_async):
    mock_enqueue.return_value = ('trace-lineage-abc', None, 'trace-lineage-query-tool-123')

    client = _client()
    response = client.post(
        '/api/trace/lineage',
        json={
            'profile': 'query_tool',
            'container_ids': ['CID-001'],
        },
    )

    assert response.status_code == 202
    payload = response.get_json()
    assert payload['data']['stage'] == 'lineage'
    assert payload['data']['async'] is True
    assert payload['data']['job_id'] == 'trace-lineage-abc'
    assert payload['data']['query_id'] == 'trace-lineage-query-tool-123'
    assert payload['data']['status_url'] == '/api/trace/lineage/job/trace-lineage-abc'


@patch('mes_dashboard.routes.trace_routes.load_trace_lineage_result')
def test_lineage_reverse_profile_returns_cached_ancestors(mock_load_result):
    mock_load_result.return_value = {
        'stage': 'lineage',
        'roots': ['CID-SN'],
        'ancestors': {'CID-SN': ['CID-A', 'CID-B']},
        'names': {
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


@patch('mes_dashboard.routes.trace_routes.load_trace_lineage_result')
def test_lineage_mid_section_defect_returns_compact_payload(mock_load_result):
    mock_load_result.return_value = {
        'stage': 'lineage',
        'ancestors': {'CID-001': ['CID-A', 'CID-B']},
        'seed_roots': {'CID-001': 'ROOT-001'},
        'total_nodes': 3,
        'total_ancestor_count': 2,
    }

    client = _client()
    response = client.post(
        '/api/trace/lineage',
        json={
            'profile': 'mid_section_defect',
            'container_ids': ['CID-001'],
            'params': {'direction': 'backward'},
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['data']['query_id'].startswith('trace-lineage-mid-section-defect-')
    assert payload['data']['total_ancestor_count'] == 2
    assert payload['data']['seed_roots']['CID-001'] == 'ROOT-001'
    assert 'ancestors' not in payload['data']


@patch('mes_dashboard.routes.trace_routes.is_async_available', return_value=False)
def test_lineage_returns_503_when_async_unavailable(_mock_async):
    client = _client()
    response = client.post(
        '/api/trace/lineage',
        json={
            'profile': 'query_tool',
            'container_ids': ['CID-001'],
        },
    )

    assert response.status_code == 503
    payload = response.get_json()
    assert payload['error']['code'] == 'SERVICE_UNAVAILABLE'


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


@patch('mes_dashboard.routes.trace_routes.enqueue_trace_events_job', return_value=('trace-evt-legacy-001', None))
@patch('mes_dashboard.routes.trace_routes.is_async_available', return_value=True)
def test_events_partial_failure_path_now_routes_to_async(_mock_async, _mock_enqueue):
    client = _client()
    response = client.post(
        '/api/trace/events',
        json={
            'profile': 'query_tool',
            'container_ids': ['CID-001'],
            'domains': ['history', 'materials'],
        },
    )

    assert response.status_code == 202
    payload = response.get_json()
    assert payload['data']['async'] is True
    assert payload['data']['job_id'] == 'trace-evt-legacy-001'


@patch('mes_dashboard.services.msd_duckdb_runtime.MsdDuckdbRuntime')
def test_events_mid_section_defect_with_aggregation(mock_runtime_cls):
    mock_runtime = mock_runtime_cls.return_value
    mock_runtime.is_available.return_value = True
    mock_runtime.get_summary.return_value = {
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
                'direction': 'backward',
                'loss_reasons': ['R1'],
            },
            'lineage': {'ancestors': {'CID-001': ['CID-A']}},
            'seed_container_ids': ['CID-001'],
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['data']['spool_hit'] is True
    assert payload['data']['aggregation']['kpi']['total_input'] == 100
    assert payload['data']['aggregation']['genealogy_status'] == 'ready'
    mock_runtime.get_summary.assert_called_once_with(
        direction='backward',
        loss_reasons=['R1'],
        pj_types=None,
        packages=None,
    )


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


@patch('mes_dashboard.routes.trace_routes.enqueue_trace_events_job')
@patch('mes_dashboard.routes.trace_routes.is_async_available', return_value=True)
def test_msd_events_recomputes_aggregation_on_each_call(
    _mock_async,
    mock_enqueue,
):
    """MSD events should NOT use events-level cache; each spool miss re-enqueues."""
    mock_enqueue.side_effect = [
        ('trace-msd-001', None),
        ('trace-msd-002', None),
    ]

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
    assert resp1.status_code == 202

    # Second call with different loss_reasons — route should enqueue again
    body['params']['loss_reasons'] = ['Reason-B']
    resp2 = client.post('/api/trace/events', json=body)
    assert resp2.status_code == 202

    assert mock_enqueue.call_count == 2


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


# ---- Async-only events routing tests ----


@patch('mes_dashboard.routes.trace_routes.is_async_available', return_value=False)
def test_events_non_msd_returns_503_when_async_unavailable(mock_async_available):
    """Spool miss should return 503 when the async worker path is unavailable."""
    client = _client()
    response = client.post(
        '/api/trace/events',
        json={
            'profile': 'query_tool',
            'container_ids': [f'CID-{i}' for i in range(10)],
            'domains': ['history'],
        },
    )

    assert response.status_code == 503
    payload = response.get_json()
    assert payload['error']['code'] == 'SERVICE_UNAVAILABLE'


@patch('mes_dashboard.routes.trace_routes.is_async_available', return_value=False)
def test_events_msd_returns_503_without_async(mock_async_available):
    """MSD spool miss should return 503 when the async worker path is unavailable."""
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

    assert response.status_code == 503
    payload = response.get_json()
    assert payload['error']['code'] == 'SERVICE_UNAVAILABLE'


@patch('mes_dashboard.routes.trace_routes.enqueue_trace_events_job')
@patch('mes_dashboard.routes.trace_routes.is_async_available', return_value=True)
def test_events_msd_spool_miss_returns_202_with_async(
    mock_async_available,
    mock_enqueue,
):
    """MSD spool miss should enqueue async work when async is available."""
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


@patch('mes_dashboard.routes.trace_routes.enqueue_trace_events_job')
@patch('mes_dashboard.routes.trace_routes.is_async_available', return_value=True)
def test_events_non_msd_spool_miss_enqueues_async(_mock_async, mock_enqueue):
    """Non-MSD spool miss should enqueue async work instead of running sync fetches."""
    mock_enqueue.return_value = ('trace-evt-short-001', None)
    client = _client()
    response = client.post(
        '/api/trace/events',
        json={
            'profile': 'query_tool',
            'container_ids': ['CID-001'],
            'domains': ['history'],
        },
    )

    assert response.status_code == 202
    payload = response.get_json()
    assert payload['data']['job_id'] == 'trace-evt-short-001'


# ---- Async job queue tests ----


@patch('mes_dashboard.routes.trace_routes.enqueue_trace_events_job')
@patch('mes_dashboard.routes.trace_routes.is_async_available', return_value=True)
def test_events_routes_to_async_above_threshold(
    mock_async_avail,
    mock_enqueue,
):
    """Spool miss should return 202 with job metadata."""
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


@patch('mes_dashboard.routes.trace_routes.is_async_available', return_value=False)
def test_events_returns_503_when_async_unavailable(
    mock_async_avail,
):
    """When async is unavailable, spool miss should return 503."""
    client = _client()
    response = client.post(
        '/api/trace/events',
        json={
            'profile': 'query_tool',
            'container_ids': [f'CID-{i}' for i in range(3)],
            'domains': ['history'],
        },
    )

    assert response.status_code == 503
    payload = response.get_json()
    assert payload['error']['code'] == 'SERVICE_UNAVAILABLE'


@patch('mes_dashboard.routes.trace_routes.enqueue_trace_events_job')
@patch('mes_dashboard.routes.trace_routes.is_async_available', return_value=True)
def test_events_spool_miss_routes_to_async_when_available(
    _mock_async_avail,
    mock_enqueue,
):
    """General spool miss should route to async when queue is available."""
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


@patch('mes_dashboard.routes.trace_routes.is_async_available', return_value=False)
def test_events_rss_guard_returns_503_when_async_unavailable(
    _mock_async_avail,
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


@patch('mes_dashboard.routes.trace_routes.enqueue_trace_events_job')
@patch('mes_dashboard.routes.trace_routes.is_async_available', return_value=True)
def test_events_returns_503_when_enqueue_fails(
    mock_async_avail,
    mock_enqueue,
):
    """When enqueue fails, the route should fail closed with 503."""
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

    assert response.status_code == 503
    payload = response.get_json()
    assert payload['error']['code'] == 'SERVICE_UNAVAILABLE'


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


@patch('mes_dashboard.routes.trace_routes.is_async_available', return_value=True)
@patch('mes_dashboard.routes.trace_routes.enqueue_trace_lineage')
def test_lineage_msd_async_returns_202(
    mock_enqueue,
    _mock_async,
):
    mock_enqueue.return_value = ('trace-lineage-msd', None, 'trace-lineage-mid-section-defect-123')

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
    assert payload['data']['job_id'] == 'trace-lineage-msd'
    assert payload['data']['query_id'] == 'trace-lineage-mid-section-defect-123'
    assert payload['data']['status_url'] == '/api/trace/lineage/job/trace-lineage-msd'


@patch('mes_dashboard.routes.trace_routes.get_trace_lineage_job_status')
def test_lineage_job_status_endpoint_found(mock_status):
    """GET /api/trace/lineage/job/<id> should return job status."""
    mock_status.return_value = {
        'job_id': 'trace-lineage-abc',
        'status': 'running',
        'progress': 'resolving lineage',
        'elapsed_seconds': 12.5,
    }

    reset_rate_limits_for_tests()
    client = _client()
    response = client.get('/api/trace/lineage/job/trace-lineage-abc')

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['data']['status'] == 'running'
    assert payload['data']['job_id'] == 'trace-lineage-abc'


@patch('mes_dashboard.routes.trace_routes.get_trace_lineage_job_status', return_value=None)
@patch('mes_dashboard.routes.trace_routes.get_msd_lineage_job_status', return_value=None)
def test_lineage_job_status_endpoint_not_found(_mock_msd_status, _mock_status):
    """GET /api/trace/lineage/job/<id> should return 404 for unknown job."""
    reset_rate_limits_for_tests()
    client = _client()
    response = client.get('/api/trace/lineage/job/nonexistent')

    assert response.status_code == 404


@patch('mes_dashboard.routes.trace_routes.get_trace_lineage_job_result')
@patch('mes_dashboard.routes.trace_routes.get_trace_lineage_job_status')
def test_lineage_job_result_endpoint_success(mock_status, mock_result):
    """GET /api/trace/lineage/job/<id>/result should return reconstructed lineage."""
    mock_status.return_value = {'status': 'completed', 'job_id': 'trace-lineage-abc'}
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
    response = client.get('/api/trace/lineage/job/trace-lineage-abc/result')

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['data']['stage'] == 'lineage'
    assert 'SEED1' in payload['data']['ancestors']


@patch('mes_dashboard.routes.trace_routes.get_trace_lineage_job_result')
@patch('mes_dashboard.routes.trace_routes.get_trace_lineage_job_status')
def test_lineage_job_result_endpoint_mid_section_defect_returns_compact_payload(mock_status, mock_result):
    mock_status.return_value = {
        'status': 'completed',
        'job_id': 'trace-lineage-msd',
        'profile': 'mid_section_defect',
        'query_id': 'trace-lineage-mid-section-defect-123',
    }
    mock_result.return_value = {
        'stage': 'lineage',
        'ancestors': {'SEED1': ['ANC1', 'ANC2']},
        'seed_roots': {'SEED1': 'ROOT-1'},
        'total_nodes': 3,
        'total_ancestor_count': 2,
    }

    reset_rate_limits_for_tests()
    client = _client()
    response = client.get('/api/trace/lineage/job/trace-lineage-msd/result')

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['data']['query_id'] == 'trace-lineage-mid-section-defect-123'
    assert payload['data']['total_ancestor_count'] == 2
    assert 'ancestors' not in payload['data']


@patch('mes_dashboard.routes.trace_routes.get_trace_lineage_job_result')
@patch('mes_dashboard.routes.trace_routes.get_trace_lineage_job_status')
def test_lineage_job_result_endpoint_mid_section_defect_infers_compact_payload_from_query_id(mock_status, mock_result):
    mock_status.return_value = {
        'status': 'completed',
        'job_id': 'trace-lineage-msd',
        'query_id': 'trace-lineage-mid-section-defect-123',
    }
    mock_result.return_value = {
        'stage': 'lineage',
        'ancestors': {'SEED1': ['ANC1', 'ANC2']},
        'seed_roots': {'SEED1': 'ROOT-1'},
        'total_nodes': 3,
        'total_ancestor_count': 2,
    }

    reset_rate_limits_for_tests()
    client = _client()
    response = client.get('/api/trace/lineage/job/trace-lineage-msd/result')

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['data']['query_id'] == 'trace-lineage-mid-section-defect-123'
    assert payload['data']['total_ancestor_count'] == 2
    assert 'ancestors' not in payload['data']


@patch('mes_dashboard.routes.trace_routes.get_trace_lineage_job_status')
def test_lineage_job_result_endpoint_job_still_running(mock_status):
    """GET /api/trace/lineage/job/<id>/result should return 409 when job not yet complete."""
    mock_status.return_value = {'status': 'running', 'job_id': 'trace-lineage-abc'}

    reset_rate_limits_for_tests()
    client = _client()
    response = client.get('/api/trace/lineage/job/trace-lineage-abc/result')

    assert response.status_code == 409
