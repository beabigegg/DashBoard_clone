# -*- coding: utf-8 -*-
"""Service tests for mid-section defect analysis."""

from __future__ import annotations

from unittest.mock import patch

import pandas as pd

from mes_dashboard.services.mid_section_defect_service import (
    _attribute_materials,
    _attribute_wafer_roots,
    _build_detail_table,
    _normalize_upstream_event_records,
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
    # 2023-01-01 to 2025-02-28 = 789 days > 730
    result = query_analysis('2023-01-01', '2025-02-28')

    assert 'error' in result
    assert '730' in result['error']


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


@patch('mes_dashboard.services.reason_filter_cache.get_reject_reasons')
def test_query_all_loss_reasons_cache_hit_skips_query(mock_get_reasons):
    """query_all_loss_reasons delegates to reason_filter_cache.get_reject_reasons()."""
    mock_get_reasons.return_value = ['Cached_A', 'Cached_B']

    result = query_all_loss_reasons()

    assert result == {'loss_reasons': ['Cached_A', 'Cached_B']}
    mock_get_reasons.assert_called_once()


@patch('mes_dashboard.services.reason_filter_cache.get_reject_reasons')
def test_query_all_loss_reasons_cache_miss_queries_and_caches_sorted_values(
    mock_get_reasons,
):
    """query_all_loss_reasons returns values from reason_filter_cache."""
    mock_get_reasons.return_value = ['A_REASON', 'B_REASON']

    result = query_all_loss_reasons()

    assert result == {'loss_reasons': ['A_REASON', 'B_REASON']}


@patch('mes_dashboard.services.mid_section_defect_service.cache_set')
@patch('mes_dashboard.services.mid_section_defect_service.cache_get', return_value=None)
@patch('mes_dashboard.services.mid_section_defect_service._load_analysis_from_spool')
@patch('mes_dashboard.services.mid_section_defect_service._fetch_station_detection_data')
def test_query_analysis_prefers_spool_runtime(
    mock_fetch_detection_data,
    mock_load_from_spool,
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
    mock_load_from_spool.return_value = {
        'kpi': staged_summary['kpi'],
        'charts': staged_summary['charts'],
        'daily_trend': staged_summary['daily_trend'],
        'available_loss_reasons': staged_summary['available_loss_reasons'],
        'genealogy_status': staged_summary['genealogy_status'],
        'detail': [{'CONTAINERNAME': 'LOT-001'}] * staged_summary['detail_total_count'],
        'attribution': staged_summary['attribution'],
        'trace_query_id': 'msd-runtime-001',
    }

    summary = query_analysis('2025-01-01', '2025-01-31')

    assert summary['available_loss_reasons'] == staged_summary['available_loss_reasons']
    assert summary['genealogy_status'] == staged_summary['genealogy_status']
    assert len(summary['detail']) == staged_summary['detail_total_count']
    assert summary['kpi'] == staged_summary['kpi']
    assert summary['daily_trend'] == staged_summary['daily_trend']
    assert summary['charts'].keys() == staged_summary['charts'].keys()
    assert summary['trace_query_id'] == 'msd-runtime-001'


@patch('mes_dashboard.services.mid_section_defect_service.ensure_analysis_background_job', return_value='msd-compat-job')
@patch('mes_dashboard.services.mid_section_defect_service._load_analysis_from_spool', return_value=None)
@patch('mes_dashboard.services.mid_section_defect_service._fetch_station_detection_data')
def test_query_analysis_returns_pending_on_spool_miss(
    mock_fetch_detection_data,
    _mock_load,
    mock_ensure_job,
):
    mock_fetch_detection_data.return_value = pd.DataFrame([
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
    ])

    result = query_analysis('2025-01-01', '2025-01-31')

    assert result['genealogy_status'] == 'pending'
    assert result['detail'] == []
    assert result['available_loss_reasons'] == ['R1']
    assert result['trace_query_id'].startswith('msd-')
    mock_ensure_job.assert_called_once()


def test_query_station_options_returns_ordered_list():
    result = query_station_options()
    assert isinstance(result, list)
    assert len(result) == 12
    assert result[0]['name'] == '切割'
    assert result[0]['order'] == 0
    assert result[-1]['name'] == '測試'
    assert result[-1]['order'] == 11


def test_normalize_upstream_event_records_ignores_metadata_side_channel_fields():
    rows = _normalize_upstream_event_records(
        {
            "CID-1": [
                {
                    "WORKCENTER_GROUP": "測試",
                    "EQUIPMENTID": "EQ-1",
                    "EQUIPMENTNAME": "EQ-1",
                    "SPECNAME": "SPEC-1",
                    "TRACKINQTY": 10,
                }
            ],
            "__meta__": {"truncated": True},
            "CID-2": "not-a-list",
            "CID-3": [None, {"WORKCENTER_GROUP": "中段", "EQUIPMENTNAME": "EQ-3"}],
        }
    )

    assert "__meta__" not in rows
    assert "CID-2" not in rows
    assert rows["CID-1"][0]["equipment_name"] == "EQ-1"
    assert rows["CID-3"][0]["equipment_name"] == "EQ-3"


@patch('mes_dashboard.services.mid_section_defect_service._fetch_station_detection_data')
def test_build_trace_aggregation_surfaces_non_complete_quality_meta(mock_fetch_detection):
    mock_fetch_detection.return_value = pd.DataFrame([
        {
            'CONTAINERID': 'CID-001',
            'CONTAINERNAME': 'LOT-001',
            'TRACKINQTY': 100,
            'REJECTQTY': 0,
            'LOSSREASONNAME': None,
            'WORKFLOW': 'WF-A',
            'PRODUCTLINENAME': 'PKG-A',
            'PJ_TYPE': 'TYPE-A',
            'DETECTION_EQUIPMENTNAME': 'EQ-01',
            'TRACKINTIMESTAMP': '2025-01-10 10:00:00',
            'FINISHEDRUNCARD': 'FR-001',
        },
    ])

    result = build_trace_aggregation_from_events(
        '2025-01-01',
        '2025-01-31',
        seed_container_ids=['CID-001'],
        lineage_ancestors={'CID-001': []},
        upstream_events_by_cid={'CID-001': []},
        materials_events_by_cid={'CID-001': []},
        upstream_quality_meta={
            'status': 'truncated',
            'scope': 'domain',
            'domain': 'upstream_history',
            'reasons': ['max_total_rows_exceeded'],
            'observed_rows': 1000,
            'max_rows': 500,
        },
        materials_quality_meta={
            'status': 'complete',
            'scope': 'domain',
            'domain': 'materials',
            'reasons': [],
        },
    )

    assert result is not None
    assert result['quality_meta']['status'] == 'truncated'
    assert 'upstream_history' in result['quality_meta'].get('truncated_domains', [])


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
