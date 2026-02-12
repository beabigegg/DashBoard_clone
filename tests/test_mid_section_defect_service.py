# -*- coding: utf-8 -*-
"""Service tests for mid-section defect analysis."""

from __future__ import annotations

from unittest.mock import patch

import pandas as pd

from mes_dashboard.services.mid_section_defect_service import (
    build_trace_aggregation_from_events,
    query_analysis,
    query_analysis_detail,
    query_all_loss_reasons,
)


def test_query_analysis_invalid_date_format_returns_error():
    result = query_analysis('2025/01/01', '2025-01-31')

    assert 'error' in result
    assert 'YYYY-MM-DD' in result['error']


def test_query_analysis_start_after_end_returns_error():
    result = query_analysis('2025-02-01', '2025-01-31')

    assert 'error' in result
    assert '起始日期不能晚於結束日期' in result['error']


def test_query_analysis_exceeds_max_days_returns_error():
    result = query_analysis('2025-01-01', '2025-12-31')

    assert 'error' in result
    assert '180' in result['error']


@patch('mes_dashboard.services.mid_section_defect_service.query_analysis')
def test_query_analysis_detail_returns_sorted_first_page(mock_query_analysis):
    mock_query_analysis.return_value = {
        'detail': [
            {'CONTAINERNAME': 'C', 'DEFECT_RATE': 0.3},
            {'CONTAINERNAME': 'A', 'DEFECT_RATE': 5.2},
            {'CONTAINERNAME': 'B', 'DEFECT_RATE': 3.1},
        ]
    }

    result = query_analysis_detail('2025-01-01', '2025-01-31', page=1, page_size=2)

    assert [row['CONTAINERNAME'] for row in result['detail']] == ['A', 'B']
    assert result['pagination'] == {
        'page': 1,
        'page_size': 2,
        'total_count': 3,
        'total_pages': 2,
    }


@patch('mes_dashboard.services.mid_section_defect_service.query_analysis')
def test_query_analysis_detail_clamps_page_to_last_page(mock_query_analysis):
    mock_query_analysis.return_value = {
        'detail': [
            {'CONTAINERNAME': 'A', 'DEFECT_RATE': 9.9},
            {'CONTAINERNAME': 'B', 'DEFECT_RATE': 8.8},
            {'CONTAINERNAME': 'C', 'DEFECT_RATE': 7.7},
        ]
    }

    result = query_analysis_detail('2025-01-01', '2025-01-31', page=10, page_size=2)

    assert result['pagination']['page'] == 2
    assert result['pagination']['total_pages'] == 2
    assert len(result['detail']) == 1
    assert result['detail'][0]['CONTAINERNAME'] == 'C'


@patch('mes_dashboard.services.mid_section_defect_service.query_analysis')
def test_query_analysis_detail_returns_error_passthrough(mock_query_analysis):
    mock_query_analysis.return_value = {'error': '日期格式無效'}

    result = query_analysis_detail('2025-01-01', '2025-01-31', page=1, page_size=200)

    assert result == {'error': '日期格式無效'}


@patch('mes_dashboard.services.mid_section_defect_service.query_analysis')
def test_query_analysis_detail_returns_none_on_service_failure(mock_query_analysis):
    mock_query_analysis.return_value = None

    result = query_analysis_detail('2025-01-01', '2025-01-31', page=1, page_size=200)

    assert result is None


@patch('mes_dashboard.services.mid_section_defect_service.cache_get')
@patch('mes_dashboard.services.mid_section_defect_service.read_sql_df')
def test_query_all_loss_reasons_cache_hit_skips_query(mock_read_sql_df, mock_cache_get):
    mock_cache_get.return_value = {'loss_reasons': ['Cached_A', 'Cached_B']}

    result = query_all_loss_reasons()

    assert result == {'loss_reasons': ['Cached_A', 'Cached_B']}
    mock_read_sql_df.assert_not_called()


@patch('mes_dashboard.services.mid_section_defect_service.cache_get', return_value=None)
@patch('mes_dashboard.services.mid_section_defect_service.cache_set')
@patch('mes_dashboard.services.mid_section_defect_service.read_sql_df')
@patch('mes_dashboard.services.mid_section_defect_service.SQLLoader.load')
def test_query_all_loss_reasons_cache_miss_queries_and_caches_sorted_values(
    mock_sql_load,
    mock_read_sql_df,
    mock_cache_set,
    _mock_cache_get,
):
    mock_sql_load.return_value = 'SELECT ...'
    mock_read_sql_df.return_value = pd.DataFrame(
        {'LOSSREASONNAME': ['B_REASON', None, 'A_REASON', 'B_REASON']}
    )

    result = query_all_loss_reasons()

    assert result == {'loss_reasons': ['A_REASON', 'B_REASON']}
    mock_cache_set.assert_called_once_with(
        'mid_section_loss_reasons:None:',
        {'loss_reasons': ['A_REASON', 'B_REASON']},
        ttl=86400,
    )


@patch('mes_dashboard.services.mid_section_defect_service.cache_set')
@patch('mes_dashboard.services.mid_section_defect_service.cache_get', return_value=None)
@patch('mes_dashboard.services.mid_section_defect_service.release_lock')
@patch('mes_dashboard.services.mid_section_defect_service.try_acquire_lock', return_value=True)
@patch('mes_dashboard.services.mid_section_defect_service._fetch_upstream_history')
@patch('mes_dashboard.services.mid_section_defect_service._resolve_full_genealogy')
@patch('mes_dashboard.services.mid_section_defect_service._fetch_tmtt_data')
def test_trace_aggregation_matches_query_analysis_summary(
    mock_fetch_tmtt_data,
    mock_resolve_genealogy,
    mock_fetch_upstream_history,
    _mock_lock,
    _mock_release_lock,
    _mock_cache_get,
    _mock_cache_set,
):
    tmtt_df = pd.DataFrame([
        {
            'CONTAINERID': 'CID-001',
            'CONTAINERNAME': 'LOT-001',
            'TRACKINQTY': 100,
            'REJECTQTY': 5,
            'LOSSREASONNAME': 'R1',
            'WORKFLOW': 'WF-A',
            'PRODUCTLINENAME': 'PKG-A',
            'PJ_TYPE': 'TYPE-A',
            'TMTT_EQUIPMENTNAME': 'TMTT-01',
            'TRACKINTIMESTAMP': '2025-01-10 10:00:00',
            'FINISHEDRUNCARD': 'FR-001',
        },
        {
            'CONTAINERID': 'CID-002',
            'CONTAINERNAME': 'LOT-002',
            'TRACKINQTY': 120,
            'REJECTQTY': 6,
            'LOSSREASONNAME': 'R2',
            'WORKFLOW': 'WF-B',
            'PRODUCTLINENAME': 'PKG-B',
            'PJ_TYPE': 'TYPE-B',
            'TMTT_EQUIPMENTNAME': 'TMTT-02',
            'TRACKINTIMESTAMP': '2025-01-11 10:00:00',
            'FINISHEDRUNCARD': 'FR-002',
        },
    ])

    ancestors = {
        'CID-001': {'CID-101'},
        'CID-002': set(),
    }
    upstream_normalized = {
        'CID-101': [{
            'workcenter_group': '中段',
            'equipment_id': 'EQ-01',
            'equipment_name': 'EQ-01',
            'spec_name': 'SPEC-A',
            'track_in_time': '2025-01-09 08:00:00',
        }],
        'CID-002': [{
            'workcenter_group': '中段',
            'equipment_id': 'EQ-02',
            'equipment_name': 'EQ-02',
            'spec_name': 'SPEC-B',
            'track_in_time': '2025-01-11 08:00:00',
        }],
    }
    upstream_events = {
        'CID-101': [{
            'WORKCENTER_GROUP': '中段',
            'EQUIPMENTID': 'EQ-01',
            'EQUIPMENTNAME': 'EQ-01',
            'SPECNAME': 'SPEC-A',
            'TRACKINTIMESTAMP': '2025-01-09 08:00:00',
        }],
        'CID-002': [{
            'WORKCENTER_GROUP': '中段',
            'EQUIPMENTID': 'EQ-02',
            'EQUIPMENTNAME': 'EQ-02',
            'SPECNAME': 'SPEC-B',
            'TRACKINTIMESTAMP': '2025-01-11 08:00:00',
        }],
    }

    mock_fetch_tmtt_data.return_value = tmtt_df
    mock_resolve_genealogy.return_value = ancestors
    mock_fetch_upstream_history.return_value = upstream_normalized

    summary = query_analysis('2025-01-01', '2025-01-31')
    staged_summary = build_trace_aggregation_from_events(
        '2025-01-01',
        '2025-01-31',
        seed_container_ids=['CID-001', 'CID-002'],
        lineage_ancestors={
            'CID-001': ['CID-101'],
            'CID-002': [],
        },
        upstream_events_by_cid=upstream_events,
    )

    assert staged_summary['available_loss_reasons'] == summary['available_loss_reasons']
    assert staged_summary['genealogy_status'] == summary['genealogy_status']
    assert staged_summary['detail_total_count'] == len(summary['detail'])

    assert staged_summary['kpi']['total_input'] == summary['kpi']['total_input']
    assert staged_summary['kpi']['lot_count'] == summary['kpi']['lot_count']
    assert staged_summary['kpi']['total_defect_qty'] == summary['kpi']['total_defect_qty']
    assert abs(
        staged_summary['kpi']['total_defect_rate'] - summary['kpi']['total_defect_rate']
    ) <= 0.01

    assert staged_summary['daily_trend'] == summary['daily_trend']
    assert staged_summary['charts'].keys() == summary['charts'].keys()
