# -*- coding: utf-8 -*-
"""Service tests for mid-section defect analysis."""

from __future__ import annotations

from unittest.mock import patch

import pandas as pd

from mes_dashboard.services.mid_section_defect_service import (
    _attribute_materials,
    _attribute_wafer_roots,
    _build_detail_table,
    build_trace_aggregation_from_events,
    export_csv,
    query_analysis,
    query_analysis_detail,
    query_all_loss_reasons,
    query_station_options,
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
    result = query_analysis('2025-01-01', '2026-01-02')

    assert 'error' in result
    assert '365' in result['error']


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
@patch('mes_dashboard.services.mid_section_defect_service._fetch_station_detection_data')
def test_trace_aggregation_matches_query_analysis_summary(
    mock_fetch_detection_data,
    mock_resolve_genealogy,
    mock_fetch_upstream_history,
    _mock_lock,
    _mock_release_lock,
    _mock_cache_get,
    _mock_cache_set,
):
    detection_df = pd.DataFrame([
        {
            'CONTAINERID': 'CID-001',
            'CONTAINERNAME': 'LOT-001',
            'TRACKINQTY': 100,
            'REJECTQTY': 5,
            'LOSSREASONNAME': 'R1',
            'WORKFLOW': 'WF-A',
            'PRODUCTLINENAME': 'PKG-A',
            'PJ_TYPE': 'TYPE-A',
            'DETECTION_EQUIPMENTNAME': 'EQ-01',
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
            'DETECTION_EQUIPMENTNAME': 'EQ-02',
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

    mock_fetch_detection_data.return_value = detection_df
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


def test_query_station_options_returns_ordered_list():
    result = query_station_options()
    assert isinstance(result, list)
    assert len(result) == 12
    assert result[0]['name'] == '切割'
    assert result[0]['order'] == 0
    assert result[-1]['name'] == '測試'
    assert result[-1]['order'] == 11


# --- _attribute_materials tests ---

def _make_detection_data(entries):
    """Helper: build detection_data dict from simplified entries."""
    data = {}
    for e in entries:
        data[e['cid']] = {
            'containername': e.get('name', e['cid']),
            'trackinqty': e['trackinqty'],
            'rejectqty_by_reason': e.get('reasons', {}),
        }
    return data


def test_attribute_materials_basic_rate_calculation():
    detection_data = _make_detection_data([
        {'cid': 'C1', 'trackinqty': 100, 'reasons': {'R1': 5}},
        {'cid': 'C2', 'trackinqty': 200, 'reasons': {'R1': 10}},
    ])
    ancestors = {'C1': {'A1'}, 'C2': {'A1'}}
    materials_by_cid = {
        'A1': [{'MATERIALPARTNAME': 'PART-A', 'MATERIALLOTNAME': 'LOT-X'}],
    }

    result = _attribute_materials(detection_data, ancestors, materials_by_cid)

    assert len(result) == 1
    assert result[0]['MATERIAL_KEY'] == 'PART-A (LOT-X)'
    assert result[0]['INPUT_QTY'] == 300
    assert result[0]['DEFECT_QTY'] == 15
    assert abs(result[0]['DEFECT_RATE'] - 5.0) < 0.01
    assert result[0]['DETECTION_LOT_COUNT'] == 2


def test_attribute_materials_null_lot_name():
    detection_data = _make_detection_data([
        {'cid': 'C1', 'trackinqty': 100, 'reasons': {'R1': 3}},
    ])
    ancestors = {'C1': {'A1'}}
    materials_by_cid = {
        'A1': [{'MATERIALPARTNAME': 'PART-B', 'MATERIALLOTNAME': None}],
    }

    result = _attribute_materials(detection_data, ancestors, materials_by_cid)

    assert len(result) == 1
    assert result[0]['MATERIAL_KEY'] == 'PART-B'
    assert result[0]['MATERIAL_LOT_NAME'] == ''


def test_attribute_materials_with_loss_reason_filter():
    detection_data = _make_detection_data([
        {'cid': 'C1', 'trackinqty': 100, 'reasons': {'R1': 5, 'R2': 3}},
    ])
    ancestors = {'C1': {'A1'}}
    materials_by_cid = {
        'A1': [{'MATERIALPARTNAME': 'P', 'MATERIALLOTNAME': 'L'}],
    }

    result = _attribute_materials(detection_data, ancestors, materials_by_cid, loss_reasons=['R1'])

    assert result[0]['DEFECT_QTY'] == 5


# --- _attribute_wafer_roots tests ---

def test_attribute_wafer_roots_basic():
    detection_data = _make_detection_data([
        {'cid': 'C1', 'name': 'LOT-1', 'trackinqty': 100, 'reasons': {'R1': 5}},
        {'cid': 'C2', 'name': 'LOT-2', 'trackinqty': 200, 'reasons': {'R1': 10}},
    ])
    roots = {'C1': 'ROOT-A', 'C2': 'ROOT-A'}

    result = _attribute_wafer_roots(detection_data, roots)

    assert len(result) == 1
    assert result[0]['ROOT_CONTAINER_NAME'] == 'ROOT-A'
    assert result[0]['INPUT_QTY'] == 300
    assert result[0]['DEFECT_QTY'] == 15


def test_attribute_wafer_roots_self_root():
    """LOTs with no root mapping should use their own container name."""
    detection_data = _make_detection_data([
        {'cid': 'C1', 'name': 'LOT-SELF', 'trackinqty': 100, 'reasons': {'R1': 2}},
    ])
    roots = {}  # No root for C1

    result = _attribute_wafer_roots(detection_data, roots)

    assert len(result) == 1
    assert result[0]['ROOT_CONTAINER_NAME'] == 'LOT-SELF'


def test_attribute_wafer_roots_multiple_roots():
    detection_data = _make_detection_data([
        {'cid': 'C1', 'name': 'L1', 'trackinqty': 100, 'reasons': {'R1': 5}},
        {'cid': 'C2', 'name': 'L2', 'trackinqty': 200, 'reasons': {'R1': 20}},
    ])
    roots = {'C1': 'ROOT-A', 'C2': 'ROOT-B'}

    result = _attribute_wafer_roots(detection_data, roots)

    assert len(result) == 2
    # Sorted by DEFECT_RATE desc
    assert result[0]['ROOT_CONTAINER_NAME'] == 'ROOT-B'
    assert result[1]['ROOT_CONTAINER_NAME'] == 'ROOT-A'


# --- _build_detail_table tests ---

def _make_detection_df(rows):
    """Helper: build a DataFrame like _fetch_station_detection_data output."""
    return pd.DataFrame(rows)


def test_build_detail_table_structured_upstream_machines():
    """UPSTREAM_MACHINES should be a list of {station, machine} objects."""
    df = _make_detection_df([
        {
            'CONTAINERID': 'C1', 'CONTAINERNAME': 'LOT-1', 'PJ_TYPE': 'T',
            'PRODUCTLINENAME': 'P', 'WORKFLOW': 'W', 'FINISHEDRUNCARD': 'FR',
            'DETECTION_EQUIPMENTNAME': 'DET-01', 'TRACKINQTY': 100,
            'REJECTQTY': 5, 'LOSSREASONNAME': 'R1',
        },
    ])
    ancestors = {'C1': {'A1'}}
    upstream_by_cid = {
        'A1': [
            {'workcenter_group': '中段', 'equipment_name': 'WIRE-01'},
            {'workcenter_group': '後段', 'equipment_name': 'DIE-01'},
        ],
        'C1': [
            {'workcenter_group': '測試', 'equipment_name': 'TEST-01'},
        ],
    }

    result = _build_detail_table(df, ancestors, upstream_by_cid)

    assert len(result) == 1
    row = result[0]
    machines = row['UPSTREAM_MACHINES']
    assert isinstance(machines, list)
    assert len(machines) == 3
    assert {'station': '中段', 'machine': 'WIRE-01'} in machines
    assert {'station': '後段', 'machine': 'DIE-01'} in machines
    assert {'station': '測試', 'machine': 'TEST-01'} in machines
    assert row['UPSTREAM_MACHINE_COUNT'] == 3


def test_build_detail_table_structured_upstream_materials():
    """UPSTREAM_MATERIALS should be a list of {part, lot} objects."""
    df = _make_detection_df([
        {
            'CONTAINERID': 'C1', 'CONTAINERNAME': 'LOT-1', 'PJ_TYPE': 'T',
            'PRODUCTLINENAME': 'P', 'WORKFLOW': 'W', 'FINISHEDRUNCARD': 'FR',
            'DETECTION_EQUIPMENTNAME': 'DET-01', 'TRACKINQTY': 100,
            'REJECTQTY': 0, 'LOSSREASONNAME': '',
        },
    ])
    ancestors = {'C1': {'A1'}}
    upstream_by_cid = {}
    materials_by_cid = {
        'A1': [
            {'MATERIALPARTNAME': 'PART-X', 'MATERIALLOTNAME': 'ML-1'},
            {'MATERIALPARTNAME': 'PART-Y', 'MATERIALLOTNAME': ''},
        ],
    }

    result = _build_detail_table(
        df, ancestors, upstream_by_cid, materials_by_cid=materials_by_cid,
    )

    assert len(result) == 1
    materials = result[0]['UPSTREAM_MATERIALS']
    assert isinstance(materials, list)
    assert len(materials) == 2
    assert {'part': 'PART-X', 'lot': 'ML-1'} in materials
    assert {'part': 'PART-Y', 'lot': ''} in materials


def test_build_detail_table_wafer_root():
    """WAFER_ROOT should be the root ancestor container name."""
    df = _make_detection_df([
        {
            'CONTAINERID': 'C1', 'CONTAINERNAME': 'LOT-1', 'PJ_TYPE': 'T',
            'PRODUCTLINENAME': 'P', 'WORKFLOW': 'W', 'FINISHEDRUNCARD': 'FR',
            'DETECTION_EQUIPMENTNAME': 'D', 'TRACKINQTY': 100,
            'REJECTQTY': 3, 'LOSSREASONNAME': 'R1',
        },
    ])
    ancestors = {'C1': set()}
    upstream_by_cid = {}
    roots = {'C1': 'WAFER-ROOT-001'}

    result = _build_detail_table(
        df, ancestors, upstream_by_cid, roots=roots,
    )

    assert result[0]['WAFER_ROOT'] == 'WAFER-ROOT-001'


def test_build_detail_table_multiple_defect_reasons_expand_rows():
    """LOT with multiple defect reasons should produce one row per reason."""
    df = _make_detection_df([
        {
            'CONTAINERID': 'C1', 'CONTAINERNAME': 'LOT-1', 'PJ_TYPE': 'T',
            'PRODUCTLINENAME': 'P', 'WORKFLOW': 'W', 'FINISHEDRUNCARD': 'FR',
            'DETECTION_EQUIPMENTNAME': 'D', 'TRACKINQTY': 200,
            'REJECTQTY': 5, 'LOSSREASONNAME': 'R1',
        },
        {
            'CONTAINERID': 'C1', 'CONTAINERNAME': 'LOT-1', 'PJ_TYPE': 'T',
            'PRODUCTLINENAME': 'P', 'WORKFLOW': 'W', 'FINISHEDRUNCARD': 'FR',
            'DETECTION_EQUIPMENTNAME': 'D', 'TRACKINQTY': 200,
            'REJECTQTY': 3, 'LOSSREASONNAME': 'R2',
        },
    ])

    result = _build_detail_table(df, {'C1': set()}, {})

    assert len(result) == 2
    reasons = [r['LOSS_REASON'] for r in result]
    assert 'R1' in reasons
    assert 'R2' in reasons
    assert result[0]['DEFECT_QTY'] + result[1]['DEFECT_QTY'] == 8


def test_build_detail_table_deduplicates_machines():
    """Same machine appearing in multiple ancestors should appear only once."""
    df = _make_detection_df([
        {
            'CONTAINERID': 'C1', 'CONTAINERNAME': 'LOT-1', 'PJ_TYPE': 'T',
            'PRODUCTLINENAME': 'P', 'WORKFLOW': 'W', 'FINISHEDRUNCARD': 'FR',
            'DETECTION_EQUIPMENTNAME': 'D', 'TRACKINQTY': 100,
            'REJECTQTY': 1, 'LOSSREASONNAME': 'R1',
        },
    ])
    ancestors = {'C1': {'A1', 'A2'}}
    # Same machine in both ancestors
    upstream_by_cid = {
        'A1': [{'workcenter_group': '中段', 'equipment_name': 'EQ-01'}],
        'A2': [{'workcenter_group': '中段', 'equipment_name': 'EQ-01'}],
    }

    result = _build_detail_table(df, ancestors, upstream_by_cid)

    assert result[0]['UPSTREAM_MACHINE_COUNT'] == 1
    assert len(result[0]['UPSTREAM_MACHINES']) == 1


@patch('mes_dashboard.services.mid_section_defect_service.query_analysis')
def test_export_csv_flattens_structured_fields(mock_query_analysis):
    """CSV export should flatten UPSTREAM_MACHINES and UPSTREAM_MATERIALS to strings."""
    mock_query_analysis.return_value = {
        'detail': [
            {
                'CONTAINERNAME': 'LOT-1',
                'PJ_TYPE': 'T',
                'PRODUCTLINENAME': 'P',
                'WORKFLOW': 'W',
                'FINISHEDRUNCARD': 'FR',
                'DETECTION_EQUIPMENTNAME': 'D',
                'INPUT_QTY': 100,
                'LOSS_REASON': 'R1',
                'DEFECT_QTY': 5,
                'DEFECT_RATE': 5.0,
                'ANCESTOR_COUNT': 1,
                'UPSTREAM_MACHINE_COUNT': 2,
                'UPSTREAM_MACHINES': [
                    {'station': '中段', 'machine': 'WIRE-01'},
                    {'station': '後段', 'machine': 'DIE-02'},
                ],
                'UPSTREAM_MATERIALS': [
                    {'part': 'PART-A', 'lot': 'ML-1'},
                ],
                'WAFER_ROOT': 'ROOT-001',
            },
        ],
    }

    lines = list(export_csv('2025-01-01', '2025-01-31', direction='backward'))

    # First line is BOM, second is header, third is data
    assert len(lines) == 3
    data_line = lines[2]
    assert '中段/WIRE-01, 後段/DIE-02' in data_line
    assert 'PART-A/ML-1' in data_line
