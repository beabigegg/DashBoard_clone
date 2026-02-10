# -*- coding: utf-8 -*-
"""Service tests for mid-section defect analysis."""

from __future__ import annotations

from unittest.mock import patch

import pandas as pd

from mes_dashboard.services.mid_section_defect_service import (
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
