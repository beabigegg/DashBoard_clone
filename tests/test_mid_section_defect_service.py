# -*- coding: utf-8 -*-
"""Service tests for mid-section defect analysis."""

from __future__ import annotations

from unittest.mock import patch

import pandas as pd
import pytest

from mes_dashboard.services.mid_section_defect_service import (
    _attribute_materials,
    _attribute_wafer_roots,
    _build_detail_table,
    _execute_msd_compat_job,
    _normalize_upstream_event_records,
    build_trace_aggregation_from_events,
    export_csv,
    query_analysis,
    query_analysis_detail,
    query_all_loss_reasons,
    query_station_options,
    resolve_msd_seeds_at_station,
    resolve_trace_seed_lots,
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


@patch('mes_dashboard.services.mid_section_defect_service.read_sql_df')
@patch('mes_dashboard.services.mid_section_defect_service.SQLLoader.load_with_params')
@patch('mes_dashboard.services.mid_section_defect_service._build_station_filter')
def test_resolve_msd_seeds_at_station_deduplicates_results_and_uses_station_sql(
    mock_build_station_filter,
    mock_load_sql,
    mock_read_sql,
):
    mock_build_station_filter.return_value = ('h.STATION = :station', {'station': '測試'})
    mock_load_sql.return_value = 'SELECT * FROM fake_station_seed_sql'
    mock_read_sql.return_value = pd.DataFrame([
        {'CONTAINERID': 'CID-001', 'CONTAINERNAME': 'LOT-001'},
        {'CONTAINERID': 'CID-001', 'CONTAINERNAME': 'LOT-001'},
        {'CONTAINERID': 'CID-002', 'CONTAINERNAME': 'LOT-002'},
    ])

    seeds, err = resolve_msd_seeds_at_station('gd_work_order', ['WO-001', 'WO-001'], station='測試')

    assert err is None
    assert seeds == [
        {'container_id': 'CID-001', 'container_name': 'LOT-001', 'lot_id': 'LOT-001'},
        {'container_id': 'CID-002', 'container_name': 'LOT-002', 'lot_id': 'LOT-002'},
    ]
    mock_build_station_filter.assert_called_once_with('測試', 'h')
    mock_load_sql.assert_called_once()
    assert mock_load_sql.call_args.args[0] == 'mid_section_defect/station_seed_by_filter'
    assert mock_load_sql.call_args.kwargs['VALUE_FILTER'] == "c.MFGORDERNAME IN ('WO-001', 'WO-001')"
    mock_read_sql.assert_called_once_with('SELECT * FROM fake_station_seed_sql', {'station': '測試'})


def test_resolve_msd_seeds_at_station_rejects_unsupported_type():
    seeds, err = resolve_msd_seeds_at_station('serial_number', ['SN-001'])

    assert seeds == []
    assert 'not supported' in err


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

    mock_fetch_detection_data.return_value = (detection_df, {})
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
        'detail': [],
        'detail_total_count': staged_summary['detail_total_count'],
        'attribution': staged_summary['attribution'],
        'trace_query_id': 'msd-runtime-001',
    }

    summary = query_analysis('2025-01-01', '2025-01-31')

    assert summary['available_loss_reasons'] == staged_summary['available_loss_reasons']
    assert summary['genealogy_status'] == staged_summary['genealogy_status']
    assert summary['detail_total_count'] == staged_summary['detail_total_count']
    assert summary['detail'] == []
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
    mock_fetch_detection_data.return_value = (pd.DataFrame([
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
    ]), {})

    result = query_analysis('2025-01-01', '2025-01-31')

    assert result['genealogy_status'] == 'pending'
    assert result['detail'] == []
    assert result['available_loss_reasons'] == ['R1']
    assert result['trace_query_id'].startswith('msd-')
    mock_ensure_job.assert_called_once()


@patch('mes_dashboard.services.trace_job_service._write_msd_events_spool_from_paths')
@patch('mes_dashboard.services.mid_section_defect_service.EventFetcher.fetch_events_to_parquet')
@patch('mes_dashboard.services.mid_section_defect_service._write_msd_lineage_stage_spool')
@patch('mes_dashboard.services.mid_section_defect_service.LineageEngine.resolve_full_genealogy')
@patch('mes_dashboard.services.mid_section_defect_service._write_msd_detection_stage_spool')
@patch('mes_dashboard.services.mid_section_defect_service.resolve_analysis_trace_context')
@patch('mes_dashboard.services.mid_section_defect_service.update_job_progress')
@patch('mes_dashboard.services.mid_section_defect_service.complete_job')
@patch('mes_dashboard.rq_worker_preload.ensure_rq_logging')
def test_execute_msd_compat_job_registers_detection_stage_for_detail_queries(
    _mock_ensure_rq_logging,
    mock_complete_job,
    _mock_update_job_progress,
    mock_resolve_context,
    mock_write_detection_stage,
    mock_resolve_genealogy,
    mock_write_lineage_stage,
    mock_fetch_events_to_parquet,
    mock_write_events_spool,
):
    detection_df = pd.DataFrame([
        {
            'CONTAINERID': 'CID-001',
            'CONTAINERNAME': 'LOT-001',
            'TRACKINQTY': 100,
            'REJECTQTY': 5,
            'LOSSREASONNAME': 'R1',
            'DETECTION_EQUIPMENTNAME': 'EQ-01',
        },
    ])
    mock_resolve_context.return_value = {
        'detection_df': detection_df,
        'seed_container_ids': ['CID-001'],
        'seed_container_names': {'CID-001': 'LOT-001'},
    }
    mock_resolve_genealogy.return_value = {
        'ancestors': {'CID-001': ['CID-101']},
        'cid_to_name': {'CID-101': 'LOT-UP-001'},
    }
    mock_fetch_events_to_parquet.return_value = (1, {'status': 'complete'})

    _execute_msd_compat_job(
        job_id='msd-compat-1',
        start_date='2025-01-01',
        end_date='2025-01-31',
        station='測試',
        direction='backward',
        trace_query_id='msd-trace-001',
        seed_container_ids=['CID-001'],
        seed_container_names={'CID-001': 'LOT-001'},
    )

    mock_write_detection_stage.assert_called_once_with('msd-trace-001', detection_df)
    mock_write_lineage_stage.assert_called_once()
    assert mock_fetch_events_to_parquet.call_count == 2
    mock_write_events_spool.assert_called_once()
    mock_complete_job.assert_called_with('msd-compat', 'msd-compat-1', query_id='msd-trace-001')


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
    mock_fetch_detection.return_value = (pd.DataFrame([
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
    ]), {})

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


def test_attribute_defects_filters_stations_at_or_after_detection_station():
    """_attribute_defects must exclude upstream records at/after the detection station.

    For backward tracing at 焊接_WB (order=2), records from 成型 (order=4) and 測試 (order=11)
    are NOT upstream causes and must be excluded from the chart.
    """
    from mes_dashboard.services.mid_section_defect_service import _attribute_defects

    detection_data = {
        'C1': {
            'trackinqty': 100,
            'rejectqty_by_reason': {'R1': 10},
            'workflow': 'W',
            'productlinename': 'P',
            'pj_type': 'T',
            'detection_equipmentname': 'WB-01',
            'detection_station_order': 2,  # 焊接_WB
        }
    }
    ancestors = {'C1': {'A1'}}
    upstream_by_cid = {
        # A1 has records at 切割(0), 焊接_DB(1), 焊接_WB(2), 成型(4) — only 0 and 1 are upstream
        'A1': [
            {'workcenter_group': '切割', 'equipment_name': 'SAW-01', 'equipment_id': 'E1'},
            {'workcenter_group': '焊接_DB', 'equipment_name': 'DB-01', 'equipment_id': 'E2'},
            {'workcenter_group': '焊接_WB', 'equipment_name': 'WB-01', 'equipment_id': 'E3'},
            {'workcenter_group': '成型', 'equipment_name': 'MOLD-01', 'equipment_id': 'E4'},
        ],
        # C1 (detection lot itself) also has subsequent history at 測試(11)
        'C1': [
            {'workcenter_group': '測試', 'equipment_name': 'TEST-01', 'equipment_id': 'E5'},
        ],
    }

    result = _attribute_defects(detection_data, ancestors, upstream_by_cid)

    machine_names = {r['EQUIPMENT_NAME'] for r in result}
    assert 'SAW-01' in machine_names, 'cutting machine should be included (order=0 < 2)'
    assert 'DB-01' in machine_names, 'DB machine should be included (order=1 < 2)'
    assert 'WB-01' not in machine_names, 'detection station itself must not appear (order=2 >= 2)'
    assert 'MOLD-01' not in machine_names, 'downstream station 成型 must not appear (order=4 >= 2)'
    assert 'TEST-01' not in machine_names, 'downstream station 測試 must not appear (order=11 >= 2)'


def test_attribute_defects_multi_station_uses_per_lot_cutoff():
    """When detection LOTs are at different stations, each uses its own station order as cutoff."""
    from mes_dashboard.services.mid_section_defect_service import _attribute_defects

    # C1 detected at 焊接_WB (order=2), C2 detected at 測試 (order=11)
    detection_data = {
        'C1': {
            'trackinqty': 100,
            'rejectqty_by_reason': {'R1': 5},
            'workflow': 'W', 'productlinename': 'P', 'pj_type': 'T',
            'detection_equipmentname': 'WB-01',
            'detection_station_order': 2,
        },
        'C2': {
            'trackinqty': 200,
            'rejectqty_by_reason': {'R1': 15},
            'workflow': 'W', 'productlinename': 'P', 'pj_type': 'T',
            'detection_equipmentname': 'TEST-01',
            'detection_station_order': 11,
        },
    }
    ancestors = {'C1': set(), 'C2': {'A2'}}
    upstream_by_cid = {
        'C1': [
            {'workcenter_group': '切割', 'equipment_name': 'SAW-01', 'equipment_id': 'E1'},
            {'workcenter_group': '焊接_WB', 'equipment_name': 'WB-01', 'equipment_id': 'E3'},
        ],
        # A2 is ancestor of C2 (detected at 測試, order=11); its 焊接_WB record IS upstream of 測試
        'A2': [
            {'workcenter_group': '焊接_WB', 'equipment_name': 'WB-02', 'equipment_id': 'E6'},
        ],
    }

    result = _attribute_defects(detection_data, ancestors, upstream_by_cid)

    machines = {r['EQUIPMENT_NAME']: r for r in result}
    # C1: only SAW-01 passes (order=0 < 2); WB-01 at order=2 is excluded
    assert 'SAW-01' in machines
    assert 'WB-01' not in machines
    # A2's WB-02 serves C2 (detection at 測試, order=11): order=2 < 11 → included
    assert 'WB-02' in machines


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
def test_export_csv_matches_backward_detail_columns(mock_query_analysis):
    """Backward CSV columns must match the on-screen detail table (CSV_COLUMNS_BACKWARD):
    the structured upstream-machine/material/wafer columns were dropped so the export
    no longer diverges from the LOT 明細."""
    from mes_dashboard.services.mid_section_defect_service import CSV_COLUMNS_BACKWARD

    mock_query_analysis.return_value = {
        'detail': [
            {
                'CONTAINERNAME': 'LOT-1',
                'PJ_TYPE': 'T',
                'PRODUCTLINENAME': 'P',
                'WORKFLOW': 'W',
                'DETECTION_EQUIPMENTNAME': 'D',
                'INPUT_QTY': 100,
                'LOSS_REASON': 'R1',
                'DEFECT_QTY': 5,
                'DEFECT_RATE': 5.0,
                'ANCESTOR_COUNT': 1,
                'UPSTREAM_MACHINE_COUNT': 2,
                # structured fields may still be present on the row but must NOT be exported
                'UPSTREAM_MACHINES': [{'station': '中段', 'machine': 'WIRE-01'}],
                'UPSTREAM_MATERIALS': [{'part': 'PART-A', 'lot': 'ML-1'}],
                'WAFER_ROOT': 'ROOT-001',
            },
        ],
    }

    lines = list(export_csv('2025-01-01', '2025-01-31', direction='backward'))
    # BOM+header, data
    assert len(lines) == 3
    header = lines[1]
    assert header.strip() == ",".join(label for _, label in CSV_COLUMNS_BACKWARD)
    # dropped columns must not appear
    for gone in ('上游機台', '上游原物料', '源頭批次', '完工流水碼'):
        assert gone not in header
    data_line = lines[2]
    assert 'LOT-1' in data_line and 'R1' in data_line
    assert 'WIRE-01' not in data_line and 'ROOT-001' not in data_line


# ============================================================
# Task 9.5: MSD engine parallel env var tests
# ============================================================

class TestMsdEngineParallel:
    """MSD_ENGINE_PARALLEL env var controls ThreadPoolExecutor max_workers for the
    CONTAINERID-first detection pipeline (Step A time-chunks + Step B IN-batches)."""

    def _make_detection_env(self, monkeypatch, *, pool_calls):
        import mes_dashboard.services.mid_section_defect_service as msd_svc
        import mes_dashboard.core.query_spool_store as spool_mod
        import pandas as pd

        # Spool miss → forces Step A / Step B Oracle path.
        monkeypatch.setattr(spool_mod, "load_spooled_df", lambda *a, **kw: None)
        monkeypatch.setattr(spool_mod, "store_spooled_df", lambda *a, **kw: True)
        monkeypatch.setattr(msd_svc, "cache_get", lambda *a: None)
        monkeypatch.setattr(msd_svc, "cache_set", lambda *a, **kw: None)
        monkeypatch.setattr(msd_svc, "_build_station_filter", lambda station, alias: ("1=1", {}))

        def fake_read_sql(sql, params=None, **kw):
            if "SELECT DISTINCT" in sql.upper():
                # Step A: CONTAINERID resolution
                return pd.DataFrame({"CONTAINERID": ["C1", "C2"]})
            # Step B: enrichment
            return pd.DataFrame({
                "CONTAINERID": ["C1", "C2"],
                "WORKCENTERNAME": ["WC-A", "WC-B"],
                "REJECTQTY": [0, 0],
            })

        monkeypatch.setattr(msd_svc, "read_sql_df", fake_read_sql)

        # Capture ThreadPoolExecutor max_workers usage.
        real_tpe = msd_svc.ThreadPoolExecutor

        class _SpyTPE(real_tpe):
            def __init__(self, *args, **kwargs):
                pool_calls.append(kwargs.get("max_workers"))
                super().__init__(*args, **kwargs)

        monkeypatch.setattr(msd_svc, "ThreadPoolExecutor", _SpyTPE)

    def test_default_parallel_serial(self, monkeypatch):
        """MSD_ENGINE_PARALLEL=1 → serial path, ThreadPoolExecutor NOT used."""
        import mes_dashboard.services.mid_section_defect_service as msd_svc

        pool_calls = []
        monkeypatch.setattr(msd_svc, "_MSD_ENGINE_PARALLEL", 1)
        self._make_detection_env(monkeypatch, pool_calls=pool_calls)

        df, _pf = msd_svc._fetch_station_detection_data("2025-01-01", "2025-12-31", "TestStation")

        assert pool_calls == []  # serial — no executor created
        assert df is not None and len(df) == 2

    def test_parallel_2_uses_threadpool(self, monkeypatch):
        """MSD_ENGINE_PARALLEL=2 with multiple time-chunks → ThreadPoolExecutor(max_workers=2)."""
        import mes_dashboard.services.mid_section_defect_service as msd_svc

        pool_calls = []
        monkeypatch.setattr(msd_svc, "_MSD_ENGINE_PARALLEL", 2)
        self._make_detection_env(monkeypatch, pool_calls=pool_calls)

        # 12-month range → Step A decomposes into multiple chunks → parallel.
        df, _pf = msd_svc._fetch_station_detection_data("2025-01-01", "2025-12-31", "TestStation")

        assert pool_calls, "ThreadPoolExecutor should be created for parallel Step A"
        assert all(mw == 2 for mw in pool_calls)
        assert df is not None and len(df) == 2


# ============================================================
# Task 10.9: MSD partial failure warning test
# ============================================================

class TestMsdPartialFailure:
    """MSD detection partial failure logs a warning and propagates to _meta."""

    def _setup_partial_failure_mocks(self, monkeypatch):
        """Common mock setup: Step A CID resolution raises for every time-chunk."""
        import mes_dashboard.services.mid_section_defect_service as msd_svc
        import mes_dashboard.core.query_spool_store as spool_mod

        monkeypatch.setattr(spool_mod, "load_spooled_df", lambda *a, **kw: None)
        monkeypatch.setattr(spool_mod, "store_spooled_df", lambda *a, **kw: True)
        monkeypatch.setattr(msd_svc, "cache_get", lambda *a: None)
        monkeypatch.setattr(msd_svc, "cache_set", lambda *a, **kw: None)
        monkeypatch.setattr(msd_svc, "_build_station_filter", lambda station, alias: ("1=1", {}))
        monkeypatch.setattr(msd_svc, "_MSD_ENGINE_PARALLEL", 1)

        def fail_read_sql(sql, params=None, **kw):
            raise RuntimeError("simulated chunk failure")

        monkeypatch.setattr(msd_svc, "read_sql_df", fail_read_sql)
        return msd_svc

    def test_partial_failure_warning_logged(self, monkeypatch, caplog):
        """Step A chunk failure → logger.warning is emitted."""
        import logging
        msd_svc = self._setup_partial_failure_mocks(monkeypatch)

        with caplog.at_level(logging.WARNING, logger="mes_dashboard.mid_section_defect"):
            msd_svc._fetch_station_detection_data("2025-01-01", "2025-12-31", "TestStation")

        assert any("partial failure" in r.message.lower() for r in caplog.records)

    def test_partial_failure_returned_in_meta(self, monkeypatch):
        """Step A chunk failures → returned tuple[1] flags partial failure with ranges."""
        msd_svc = self._setup_partial_failure_mocks(monkeypatch)

        # 12-month range decomposes into multiple chunks; all read_sql_df calls raise.
        df, pf_meta = msd_svc._fetch_station_detection_data("2025-01-01", "2025-12-31", "TestStation")

        assert pf_meta.get("has_partial_failure") is True
        assert pf_meta.get("failed_chunk_count", 0) >= 1
        assert "~" in (pf_meta.get("failed_ranges") or "")
        # No CIDs resolved → empty detection frame, but no crash.
        assert df is not None and df.empty

    def test_partial_failure_propagated_to_query_analysis(self, monkeypatch):
        """partial_failure_meta from detection propagates to query_analysis() result _meta."""
        import mes_dashboard.services.mid_section_defect_service as msd_svc

        pf = {"has_partial_failure": True, "failed_ranges": "2025-01-01~2025-01-31"}

        # Simulate resolve_analysis_trace_context returning partial_failure_meta
        monkeypatch.setattr(
            msd_svc,
            "resolve_analysis_trace_context",
            lambda **kw: {
                "trace_query_id": "abc123",
                "seed_container_ids": [],
                "seed_container_names": {},
                "available_loss_reasons": [],
                "detection_df": __import__("pandas").DataFrame(),
                "partial_failure_meta": pf,
            },
        )
        monkeypatch.setattr(msd_svc, "cache_get", lambda *a: None)

        result = msd_svc.query_analysis("2025-01-01", "2025-12-31")

        assert result is not None
        assert "_meta" in result
        assert result["_meta"]["partial_failure"]["has_partial_failure"] is True


# ─── pj_types / packages filter tests ────────────────────────────────────────

def _make_detection_df_with_types():
    """Seed DataFrame with PJ_TYPE and PRODUCTLINENAME columns."""
    return pd.DataFrame([
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


@patch('mes_dashboard.services.mid_section_defect_service.cache_set')
@patch('mes_dashboard.services.mid_section_defect_service.cache_get', return_value=None)
@patch('mes_dashboard.services.mid_section_defect_service._load_analysis_from_spool', return_value=None)
@patch('mes_dashboard.services.mid_section_defect_service.ensure_analysis_background_job', return_value=None)
@patch('mes_dashboard.services.mid_section_defect_service._fetch_station_detection_data')
def test_query_analysis_pj_type_does_not_reduce_available_reasons(
    mock_fetch,
    _mock_ensure,
    mock_spool,
    _mock_cache_get,
    _mock_cache_set,
):
    """pj_types is a read-time mask, NOT a seed filter: available_loss_reasons stays
    population-based (full), and pj_types is forwarded to the mask layer."""
    mock_fetch.return_value = (_make_detection_df_with_types(), {})

    result = query_analysis('2025-01-01', '2025-01-31', pj_types=['TYPE-A'])

    assert result is not None
    assert 'error' not in result
    # Population-based: both reasons remain regardless of pj_types
    available = result.get('available_loss_reasons', [])
    assert 'R1' in available
    assert 'R2' in available
    # pj_types forwarded to the spool/mask layer
    assert mock_spool.called
    assert mock_spool.call_args.kwargs.get('pj_types') == ['TYPE-A']


@patch('mes_dashboard.services.mid_section_defect_service.cache_set')
@patch('mes_dashboard.services.mid_section_defect_service.cache_get', return_value=None)
@patch('mes_dashboard.services.mid_section_defect_service._load_analysis_from_spool', return_value=None)
@patch('mes_dashboard.services.mid_section_defect_service.ensure_analysis_background_job', return_value=None)
@patch('mes_dashboard.services.mid_section_defect_service._fetch_station_detection_data')
def test_query_analysis_package_does_not_reduce_available_reasons(
    mock_fetch,
    _mock_ensure,
    mock_spool,
    _mock_cache_get,
    _mock_cache_set,
):
    """packages is a read-time mask, NOT a seed filter: available_loss_reasons stays
    population-based, and packages is forwarded to the mask layer."""
    mock_fetch.return_value = (_make_detection_df_with_types(), {})

    result = query_analysis('2025-01-01', '2025-01-31', packages=['PKG-B'])

    assert result is not None
    assert 'error' not in result
    available = result.get('available_loss_reasons', [])
    assert 'R1' in available
    assert 'R2' in available
    assert mock_spool.called
    assert mock_spool.call_args.kwargs.get('packages') == ['PKG-B']


@patch('mes_dashboard.services.mid_section_defect_service.cache_set')
@patch('mes_dashboard.services.mid_section_defect_service.cache_get', return_value=None)
@patch('mes_dashboard.services.mid_section_defect_service._load_analysis_from_spool', return_value=None)
@patch('mes_dashboard.services.mid_section_defect_service.ensure_analysis_background_job', return_value=None)
@patch('mes_dashboard.services.mid_section_defect_service._fetch_station_detection_data')
def test_query_analysis_pj_type_and_package_both_forwarded(
    mock_fetch,
    _mock_ensure,
    mock_spool,
    _mock_cache_get,
    _mock_cache_set,
):
    """Both pj_types and packages are forwarded to the read-time mask layer; seeds /
    available_loss_reasons remain population-based (no seed-level AND-empty)."""
    mock_fetch.return_value = (_make_detection_df_with_types(), {})

    result = query_analysis(
        '2025-01-01', '2025-01-31',
        pj_types=['TYPE-A'],
        packages=['PKG-B'],
    )

    assert result is not None
    assert 'error' not in result
    # No seed-level AND-empty anymore: population reasons remain
    available = result.get('available_loss_reasons', [])
    assert 'R1' in available and 'R2' in available
    assert mock_spool.call_args.kwargs.get('pj_types') == ['TYPE-A']
    assert mock_spool.call_args.kwargs.get('packages') == ['PKG-B']


@patch('mes_dashboard.services.mid_section_defect_service.cache_set')
@patch('mes_dashboard.services.mid_section_defect_service.cache_get', return_value=None)
@patch('mes_dashboard.services.mid_section_defect_service._load_analysis_from_spool', return_value=None)
@patch('mes_dashboard.services.mid_section_defect_service.ensure_analysis_background_job', return_value=None)
@patch('mes_dashboard.services.mid_section_defect_service._fetch_station_detection_data')
def test_query_analysis_no_pj_types_packages_output_unchanged(
    mock_fetch,
    _mock_ensure,
    _mock_spool,
    _mock_cache_get,
    _mock_cache_set,
):
    """Empty pj_types=[] and packages=[] → no restriction; all rows returned (AC-5)."""
    mock_fetch.return_value = (_make_detection_df_with_types(), {})

    result = query_analysis('2025-01-01', '2025-01-31', pj_types=[], packages=[])

    assert result is not None
    assert 'error' not in result
    available = result.get('available_loss_reasons', [])
    assert 'R1' in available
    assert 'R2' in available


@patch('mes_dashboard.services.mid_section_defect_service.cache_set')
@patch('mes_dashboard.services.mid_section_defect_service.cache_get', return_value=None)
@patch('mes_dashboard.services.mid_section_defect_service._load_analysis_from_spool', return_value=None)
@patch('mes_dashboard.services.mid_section_defect_service.ensure_analysis_background_job', return_value=None)
@patch('mes_dashboard.services.mid_section_defect_service._fetch_station_detection_data')
def test_query_analysis_unknown_pj_type_does_not_empty_population(
    mock_fetch,
    _mock_ensure,
    mock_spool,
    _mock_cache_get,
    _mock_cache_set,
):
    """Unknown pj_types no longer empties the result at seed level; it is forwarded as
    a mask (the DuckDB layer yields empty aggregates, not the seed resolver)."""
    mock_fetch.return_value = (_make_detection_df_with_types(), {})

    result = query_analysis('2025-01-01', '2025-01-31', pj_types=['NONEXISTENT'])

    assert result is not None
    assert 'error' not in result
    # Population reasons unchanged; mask forwarded
    available = result.get('available_loss_reasons', [])
    assert 'R1' in available and 'R2' in available
    assert mock_spool.call_args.kwargs.get('pj_types') == ['NONEXISTENT']


@patch('mes_dashboard.services.mid_section_defect_service.cache_set')
@patch('mes_dashboard.services.mid_section_defect_service.cache_get', return_value=None)
@patch('mes_dashboard.services.mid_section_defect_service._load_analysis_from_spool', return_value=None)
@patch('mes_dashboard.services.mid_section_defect_service.ensure_analysis_background_job', return_value=None)
@patch('mes_dashboard.services.mid_section_defect_service._fetch_station_detection_data')
def test_query_analysis_empty_pj_types_list_no_filter(
    mock_fetch,
    _mock_ensure,
    _mock_spool,
    _mock_cache_get,
    _mock_cache_set,
):
    """pj_types=None (absent) → same as no filter; both rows returned."""
    mock_fetch.return_value = (_make_detection_df_with_types(), {})

    result = query_analysis('2025-01-01', '2025-01-31')

    assert result is not None
    assert 'error' not in result
    available = result.get('available_loss_reasons', [])
    assert 'R1' in available
    assert 'R2' in available


@patch('mes_dashboard.services.mid_section_defect_service.cache_set')
@patch('mes_dashboard.services.mid_section_defect_service.cache_get', return_value=None)
@patch('mes_dashboard.services.mid_section_defect_service._load_analysis_from_spool', return_value=None)
@patch('mes_dashboard.services.mid_section_defect_service.ensure_analysis_background_job', return_value=None)
@patch('mes_dashboard.services.mid_section_defect_service._fetch_station_detection_data')
def test_query_analysis_null_pj_type_column_no_crash(
    mock_fetch,
    _mock_ensure,
    mock_spool,
    _mock_cache_get,
    _mock_cache_set,
):
    """NULL PJ_TYPE values in the population do not crash seed resolution (mask at read)."""
    df_with_nulls = pd.DataFrame([
        {
            'CONTAINERID': 'CID-001',
            'CONTAINERNAME': 'LOT-001',
            'TRACKINQTY': 100,
            'REJECTQTY': 5,
            'LOSSREASONNAME': 'R1',
            'WORKFLOW': 'WF-A',
            'PRODUCTLINENAME': 'PKG-A',
            'PJ_TYPE': None,  # NULL
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
    mock_fetch.return_value = (df_with_nulls, {})

    # NULL PJ_TYPE in the population must not crash; seeds stay package-independent.
    result = query_analysis('2025-01-01', '2025-01-31', pj_types=['TYPE-B'])

    assert result is not None
    assert 'error' not in result
    available = result.get('available_loss_reasons', [])
    assert 'R1' in available  # population-based, includes the NULL-pj_type lot's reason
    assert 'R2' in available
    assert mock_spool.call_args.kwargs.get('pj_types') == ['TYPE-B']


# ---------------------------------------------------------------------------
# resolve_trace_seed_lots: pj_types / packages are NOT seed filters anymore.
# They are population masks applied at DuckDB read time, so the seed set (and
# therefore trace_query_id) is package-independent — one trace serves every
# Type/Package selection.  See msd second-query fix.
# ---------------------------------------------------------------------------

@patch('mes_dashboard.services.mid_section_defect_service._fetch_station_detection_data')
def test_resolve_trace_seed_lots_pj_type_does_not_filter_seeds(mock_fetch):
    """pj_types must NOT shrink the seed set — seeds stay package-independent."""
    mock_fetch.return_value = (_make_detection_df_with_types(), {})

    result = resolve_trace_seed_lots('2025-01-01', '2025-01-31', pj_types=['TYPE-A'])

    assert result is not None
    assert 'error' not in result
    cids = [s['container_id'] for s in result['seeds']]
    assert 'CID-001' in cids
    assert 'CID-002' in cids  # full population regardless of pj_types
    assert result['seed_count'] == 2


@patch('mes_dashboard.services.mid_section_defect_service._fetch_station_detection_data')
def test_resolve_trace_seed_lots_package_does_not_filter_seeds(mock_fetch):
    """packages must NOT shrink the seed set — seeds stay package-independent."""
    mock_fetch.return_value = (_make_detection_df_with_types(), {})

    result = resolve_trace_seed_lots('2025-01-01', '2025-01-31', packages=['PKG-B'])

    assert result is not None
    assert 'error' not in result
    cids = [s['container_id'] for s in result['seeds']]
    assert 'CID-001' in cids
    assert 'CID-002' in cids  # full population regardless of packages
    assert result['seed_count'] == 2


@patch('mes_dashboard.services.mid_section_defect_service._fetch_station_detection_data')
def test_resolve_trace_seed_lots_no_filter_returns_all(mock_fetch):
    """Empty pj_types/packages means no restriction — all seeds returned."""
    mock_fetch.return_value = (_make_detection_df_with_types(), {})

    result = resolve_trace_seed_lots('2025-01-01', '2025-01-31')

    assert result is not None
    assert result['seed_count'] == 2


@patch('mes_dashboard.services.mid_section_defect_service._fetch_station_detection_data')
def test_resolve_trace_seed_lots_unknown_pj_type_still_returns_all_seeds(mock_fetch):
    """An unknown pj_types value no longer empties the seed set (mask happens later)."""
    mock_fetch.return_value = (_make_detection_df_with_types(), {})

    result = resolve_trace_seed_lots('2025-01-01', '2025-01-31', pj_types=['NONEXISTENT'])

    assert result is not None
    assert 'error' not in result
    assert result['seed_count'] == 2  # seeds package-independent; mask applied at read time


# ===========================================================================
# AC-4: Forward attribution lineage re-keying (TDD)
# ===========================================================================

@pytest.mark.xfail(
    strict=True,
    reason="AC-4 permanent regression guard: _attribute_forward_defects WITHOUT "
           "lineage_spool_df still drops split descendants (per-CONTAINERID behavior). "
           "This is intentional — callers MUST pass lineage_spool_df to get re-keying. "
           "Tripwire: if this xfail unexpectedly passes, the no-lineage code path was "
           "changed in a way that may break the known fallback contract.",
)
def test_attribute_forward_defects_drops_split_descendant_FAILING():
    """AC-4 TDD tripwire: per-CONTAINERID attribution drops split-descendant rejects.

    Scenario: LOT-A is detected as defect at the front station (order=4, 成型).
    LOT-A splits into LOT-A-1 downstream at 測試 (order=11).
    LOT-A-1 has a downstream reject, but it is NOT in defect_cids (only LOT-A is).

    Without lineage_spool_df: `cid not in defect_set` filters out LOT-A-1 → drop.
    With lineage_spool_df: see test_attribute_forward_defects_lineage_rekeying_passes.
    """
    from mes_dashboard.services.mid_section_defect_service import _attribute_forward_defects

    detection_data = {
        'LOT-A': {
            'trackinqty': 100,
            'rejectqty_by_reason': {'BondWire': 5},
            'workflow': 'WF1',
            'productlinename': 'PKG-1',
            'pj_type': 'GA',
            'detection_equipmentname': 'MOLD-01',
            'detection_station_order': 4,
        },
    }
    defect_cids = ['LOT-A']  # only seed is a defect CID
    wip_by_cid = {
        'LOT-A-1': [  # split descendant — reaches downstream station
            {'workcenter_group': '測試', 'equipment_name': 'TEST-01', 'trackinqty': 80},
        ],
    }
    downstream_rejects = {
        'LOT-A-1': [  # split descendant has downstream reject
            {
                'workcenter_group': '測試',
                'lossreasonname': 'OpenCircuit',
                'equipment_name': 'TEST-01',
                'reject_total_qty': 8,
            },
        ],
    }
    station_order = 4  # 成型

    # Without lineage re-keying, LOT-A-1 is dropped (not in defect_set → empty result)
    result = _attribute_forward_defects(
        detection_data, defect_cids, wip_by_cid, downstream_rejects, station_order,
    )

    # The test expects to find 測試 station aggregation with LOT-A-1's reject
    # (this will FAIL with current code because LOT-A-1 is not in defect_set)
    assert '測試' in result, (
        "Split descendant LOT-A-1 must contribute its downstream reject to 測試 "
        "after lineage re-keying. Current per-CONTAINERID filtering drops it."
    )
    assert result['測試']['total_reject'] == 8


def test_attribute_forward_defects_lineage_rekeying_passes():
    """AC-4 regression: after lineage re-keying fix, split descendants are attributed.

    Uses the lineage_spool_df argument to map LOT-A-1 → SEED_ID=LOT-A.
    """
    from mes_dashboard.services.mid_section_defect_service import _attribute_forward_defects
    import pandas as pd

    detection_data = {
        'LOT-A': {
            'trackinqty': 100,
            'rejectqty_by_reason': {'BondWire': 5},
            'workflow': 'WF1',
            'productlinename': 'PKG-1',
            'pj_type': 'GA',
            'detection_equipmentname': 'MOLD-01',
            'detection_station_order': 4,
        },
    }
    defect_cids = ['LOT-A']
    wip_by_cid = {
        'LOT-A-1': [
            {'workcenter_group': '測試', 'equipment_name': 'TEST-01', 'trackinqty': 80},
        ],
    }
    downstream_rejects = {
        'LOT-A-1': [
            {
                'workcenter_group': '測試',
                'lossreasonname': 'OpenCircuit',
                'equipment_name': 'TEST-01',
                'reject_total_qty': 8,
            },
        ],
    }
    station_order = 4

    # Lineage spool: LOT-A-1 → SEED_ID=LOT-A (self-edge LOT-A → LOT-A also present)
    lineage_spool_df = pd.DataFrame([
        {'SEED_ID': 'LOT-A', 'DESCENDANT_ID': 'LOT-A'},
        {'SEED_ID': 'LOT-A', 'DESCENDANT_ID': 'LOT-A-1'},
    ])

    result = _attribute_forward_defects(
        detection_data, defect_cids, wip_by_cid, downstream_rejects, station_order,
        lineage_spool_df=lineage_spool_df,
    )

    assert '測試' in result, "Lineage re-keying must include LOT-A-1's downstream reject"
    assert result['測試']['total_reject'] == 8
    assert result['測試']['lots_reached'] >= 1


# ===========================================================================
# AC-1: by_detection_loss_reason aggregation
# ===========================================================================

def test_by_detection_loss_reason_aggregation():
    """AC-1: _build_by_detection_loss_reason returns per-reason reject_qty and reject_rate."""
    from mes_dashboard.services.mid_section_defect_service import _build_by_detection_loss_reason

    detection_data = {
        'LOT-A': {
            'trackinqty': 200,
            'rejectqty_by_reason': {'BondWire': 10, 'OpenCircuit': 5},
        },
        'LOT-B': {
            'trackinqty': 100,
            'rejectqty_by_reason': {'BondWire': 3},
        },
    }

    result = _build_by_detection_loss_reason(detection_data)

    assert isinstance(result, list)
    reasons = {r['loss_reason']: r for r in result}
    assert 'BondWire' in reasons
    assert reasons['BondWire']['reject_qty'] == 13  # 10 + 3
    assert 'OpenCircuit' in reasons
    assert reasons['OpenCircuit']['reject_qty'] == 5
    # input_qty / lot_count are per-reason membership cohorts:
    # BondWire is on LOT-A(200) + LOT-B(100) -> input 300, 2 lots
    # OpenCircuit is only on LOT-A(200) -> input 200, 1 lot
    assert reasons['BondWire']['input_qty'] == 300
    assert reasons['BondWire']['lot_count'] == 2
    assert reasons['OpenCircuit']['input_qty'] == 200
    assert reasons['OpenCircuit']['lot_count'] == 1
    # reject_rate = reject_qty / per-reason input_qty (NOT whole-cohort total)
    assert abs(reasons['BondWire']['reject_rate'] - 13 / 300) < 1e-6
    assert abs(reasons['OpenCircuit']['reject_rate'] - 5 / 200) < 1e-6


def test_by_detection_loss_reason_top_n_truncation():
    """AC-1: reasons beyond TOP_N are collapsed into '其他'."""
    from mes_dashboard.services.mid_section_defect_service import (
        _build_by_detection_loss_reason, TOP_N,
    )

    # Create TOP_N + 2 distinct reasons
    reasons = {f"Reason-{i:02d}": i + 1 for i in range(TOP_N + 2)}
    detection_data = {
        'LOT-X': {
            'trackinqty': 1000,
            'rejectqty_by_reason': reasons,
        },
    }

    result = _build_by_detection_loss_reason(detection_data)

    named = [r for r in result if r['loss_reason'] != '其他']
    other = [r for r in result if r['loss_reason'] == '其他']
    assert len(named) == TOP_N
    assert len(other) == 1
    # '其他' must aggregate the bottom 2 reasons
    assert other[0]['reject_qty'] == (1 + 2)  # smallest two


# ===========================================================================
# AC-2: loss_reason × workcenter_group cross-tab
# ===========================================================================

def test_loss_reason_workcenter_crosstab_builder():
    """AC-2: crosstab has loss_reasons[], workcenter_groups[], and cells[]."""
    from mes_dashboard.services.mid_section_defect_service import _build_loss_reason_workcenter_crosstab

    detection_data = {
        'LOT-A': {'trackinqty': 100, 'rejectqty_by_reason': {'BondWire': 10}},
    }
    forward_attr = {
        '測試': {
            'total_input': 100,
            'total_reject': 8,
            'loss_reasons': {'BondWire': 8},
            'lots_reached': 1,
            'machines': {},
            'reject_rate': 8.0,
        },
    }

    result = _build_loss_reason_workcenter_crosstab(detection_data, forward_attr)

    assert 'loss_reasons' in result
    assert 'workcenter_groups' in result
    assert 'cells' in result
    assert 'BondWire' in result['loss_reasons']
    assert '測試' in result['workcenter_groups']
    # One non-zero cell
    cells_dict = {
        (c['loss_reason'], c['workcenter_group']): c for c in result['cells']
    }
    assert ('BondWire', '測試') in cells_dict
    cell = cells_dict[('BondWire', '測試')]
    assert cell['reject_qty'] == 8


def test_crosstab_top_n_folds_remainder_to_other():
    """AC-2: axes beyond TOP_N on each dimension are collapsed to '其他'."""
    from mes_dashboard.services.mid_section_defect_service import (
        _build_loss_reason_workcenter_crosstab, TOP_N,
    )

    # Create TOP_N + 2 detection reasons and TOP_N + 1 downstream stations
    n_reasons = TOP_N + 2
    n_stations = TOP_N + 1
    detection_data = {
        f'LOT-{i}': {
            'trackinqty': 100,
            'rejectqty_by_reason': {f'Reason-{i:02d}': 5},
        }
        for i in range(n_reasons)
    }
    forward_attr = {
        f'Station-{j:02d}': {
            'total_input': 100,
            'total_reject': 2,
            'loss_reasons': {f'Reason-{j % n_reasons:02d}': 2},
            'lots_reached': 1,
            'machines': {},
            'reject_rate': 2.0,
        }
        for j in range(n_stations)
    }

    result = _build_loss_reason_workcenter_crosstab(detection_data, forward_attr)

    named_reasons = [r for r in result['loss_reasons'] if r != '其他']
    named_stations = [s for s in result['workcenter_groups'] if s != '其他']
    assert len(named_reasons) == TOP_N
    assert len(named_stations) == TOP_N


# ===========================================================================
# AC-3: downstream_trend (no control cohort)
# ===========================================================================

def test_downstream_reject_trend_no_control_cohort():
    """AC-3: downstream trend has date/reject_qty/reject_rate but no cohort baseline."""
    from mes_dashboard.services.mid_section_defect_service import _build_downstream_trend

    downstream_rejects = {
        'LOT-A': [
            {
                'workcenter_group': '測試',
                'lossreasonname': 'OpenCircuit',
                'reject_total_qty': 3,
                'txndate': '2025-03-01',
            },
        ],
        'LOT-B': [
            {
                'workcenter_group': '測試',
                'lossreasonname': 'BondWire',
                'reject_total_qty': 5,
                'txndate': '2025-03-02',
            },
        ],
    }
    wip_by_cid = {
        'LOT-A': [{'workcenter_group': '測試', 'trackinqty': 100}],
        'LOT-B': [{'workcenter_group': '測試', 'trackinqty': 200}],
    }
    defect_cids = ['LOT-A', 'LOT-B']
    station_order = 4  # 成型

    result = _build_downstream_trend(defect_cids, wip_by_cid, downstream_rejects, station_order)

    assert isinstance(result, list)
    assert len(result) >= 1
    for item in result:
        assert 'date' in item
        assert 'reject_qty' in item
        assert 'reject_rate' in item
        # AC-3: no cohort/baseline fields
        assert 'baseline_reject_rate' not in item
        assert 'control_reject_rate' not in item


# ===========================================================================
# AC-7: Amplification KPI divide-by-zero semantics
# ===========================================================================

def test_amplification_kpi_detection_rate_zero_emits_null():
    """AC-7: when detection_reject_rate=0, amplification is None."""
    from mes_dashboard.services.mid_section_defect_service import _compute_amplification_kpi

    result = _compute_amplification_kpi(
        detection_total_reject=0,
        detection_total_input=200,
        downstream_total_reject=5,
        downstream_total_input=200,
    )
    assert result is None


def test_amplification_kpi_downstream_rate_zero_emits_zero_float():
    """AC-7: when downstream=0 and detection>0, amplification is 0.0 (real zero)."""
    from mes_dashboard.services.mid_section_defect_service import _compute_amplification_kpi

    result = _compute_amplification_kpi(
        detection_total_reject=10,
        detection_total_input=100,
        downstream_total_reject=0,
        downstream_total_input=200,
    )
    assert result == 0.0
    assert isinstance(result, float)


def test_amplification_kpi_both_rates_nonzero_correct_ratio():
    """AC-7: amplification = downstream_rate / detection_rate."""
    from mes_dashboard.services.mid_section_defect_service import _compute_amplification_kpi

    # detection_rate = 10/100 = 0.10; downstream_rate = 20/200 = 0.10 → ratio = 1.0
    result = _compute_amplification_kpi(
        detection_total_reject=10,
        detection_total_input=100,
        downstream_total_reject=20,
        downstream_total_input=200,
    )
    assert result is not None
    assert abs(result - 1.0) < 1e-6

    # detection_rate = 5/100 = 0.05; downstream_rate = 20/200 = 0.10 → ratio = 2.0
    result2 = _compute_amplification_kpi(
        detection_total_reject=5,
        detection_total_input=100,
        downstream_total_reject=20,
        downstream_total_input=200,
    )
    assert result2 is not None
    assert abs(result2 - 2.0) < 1e-6


class TestDetectionInputPartialAggregation:
    """Regression: detection input qty must be the original load of a track-in
    session (MAX(TRACKINQTY)), not the last partial's remaining qty.

    MES records TRACKINQTY as the qty REMAINING at each partial's start, so it
    decreases across partials of the same upload (business-rule PH-06). The old
    ``station_detection_by_ids.sql`` picked rn=1 (the last partial) and returned
    its TRACKINQTY, under-counting the input (e.g. 43200 -> 3600) and inflating
    downstream/defect rates past 100%. This guards against silent revert.
    """

    def _render(self):
        from mes_dashboard.sql import SQLLoader

        return SQLLoader.load_with_params(
            "mid_section_defect/station_detection_by_ids",
            CONTAINER_IDS="'x'",
            STATION_FILTER="1=1",
            STATION_FILTER_REJECTS="1=1",
            DETECTION_TIME_FILTER="",
            REJECT_TIME_FILTER="",
        )

    def test_detection_input_uses_session_scoped_max_window(self):
        sql = self._render().upper()
        # session = same container + track-in timestamp + equipment
        assert "MAX(H.TRACKINQTY) OVER" in sql
        assert "PARTITION BY H.CONTAINERID, H.TRACKINTIMESTAMP, H.EQUIPMENTID" in sql

    def test_detection_output_column_is_corrected_value(self):
        sql = self._render().upper()
        # the projected TRACKINQTY column must be the corrected ORIG value,
        # never the raw last-partial t.TRACKINQTY
        assert "T.ORIG_TRACKINQTY AS TRACKINQTY" in sql
        assert "\n    T.TRACKINQTY,\n" not in self._render()


class TestFrontDownstreamReasonMatrix:
    """MSD-09: 前段報廢原因 × 下游報廢原因 關聯矩陣 (cohort-membership semantics)."""

    def _matrix(self, **kw):
        from mes_dashboard.services.mid_section_defect_service import (
            _build_front_downstream_reason_matrix,
        )
        return _build_front_downstream_reason_matrix(**kw)

    def test_basic_single_front_reason(self):
        m = self._matrix(
            detection_data={'S1': {'rejectqty_by_reason': {'NSOP': 10}}},
            defect_cids=['S1'],
            downstream_rejects={'S1': [
                {'workcenter_group': '測試', 'lossreasonname': 'OPEN', 'reject_total_qty': 100},
            ]},
            station_order=4,
        )
        assert m['rows'] == [{'name': 'NSOP', 'total': 100}]
        assert m['cols'] == [{'name': 'OPEN', 'total': 100}]
        assert m['cells'] == [[100]]
        assert m['row_pct'] == [[100.0]]

    def test_multi_front_reason_is_membership_double_counted(self):
        # A lot scrapped for BOTH NSOP and NSOL contributes its downstream
        # rejects to BOTH rows — sum of cells (200) exceeds physical reject (100).
        m = self._matrix(
            detection_data={'S1': {'rejectqty_by_reason': {'NSOP': 10, 'NSOL': 5}}},
            defect_cids=['S1'],
            downstream_rejects={'S1': [
                {'workcenter_group': '測試', 'lossreasonname': 'OPEN', 'reject_total_qty': 100},
            ]},
            station_order=4,
        )
        totals = {r['name']: r['total'] for r in m['rows']}
        assert totals == {'NSOP': 100, 'NSOL': 100}
        assert sum(sum(row) for row in m['cells']) == 200
        # each row is 100% OPEN
        assert all(pct == [100.0] for pct in m['row_pct'])

    def test_station_order_filters_non_downstream(self):
        # 成型 order(4) == station_order(4) -> excluded; 測試 order(11) -> kept
        m = self._matrix(
            detection_data={'S1': {'rejectqty_by_reason': {'NSOP': 10}}},
            defect_cids=['S1'],
            downstream_rejects={'S1': [
                {'workcenter_group': '成型', 'lossreasonname': 'X', 'reject_total_qty': 999},
                {'workcenter_group': '測試', 'lossreasonname': 'OPEN', 'reject_total_qty': 100},
            ]},
            station_order=4,
        )
        assert m['cols'] == [{'name': 'OPEN', 'total': 100}]
        assert m['cells'] == [[100]]

    def test_lineage_rekeys_descendant_to_seed(self):
        import pandas as pd
        det = {'SEED': {'rejectqty_by_reason': {'NSOP': 10}}}
        ds = {'DESC': [
            {'workcenter_group': '測試', 'lossreasonname': 'OPEN', 'reject_total_qty': 50},
        ]}
        lineage = pd.DataFrame([{'SEED_ID': 'SEED', 'DESCENDANT_ID': 'DESC'}])
        m = self._matrix(detection_data=det, defect_cids=['SEED'],
                         downstream_rejects=ds, station_order=4,
                         lineage_spool_df=lineage)
        assert m['rows'] == [{'name': 'NSOP', 'total': 50}]
        # without lineage, DESC is not a defect cid -> empty
        m2 = self._matrix(detection_data=det, defect_cids=['SEED'],
                          downstream_rejects=ds, station_order=4)
        assert m2 == {'rows': [], 'cols': [], 'cells': [], 'row_pct': []}

    def test_row_pct_normalization(self):
        m = self._matrix(
            detection_data={'S1': {'rejectqty_by_reason': {'NSOP': 10}}},
            defect_cids=['S1'],
            downstream_rejects={'S1': [
                {'workcenter_group': '測試', 'lossreasonname': 'OPEN', 'reject_total_qty': 75},
                {'workcenter_group': '測試', 'lossreasonname': '短路', 'reject_total_qty': 25},
            ]},
            station_order=4,
        )
        cols = [c['name'] for c in m['cols']]
        pct = dict(zip(cols, m['row_pct'][0]))
        assert pct == {'OPEN': 75.0, '短路': 25.0}

    def test_empty_inputs_return_empty_shape(self):
        assert self._matrix(detection_data={}, defect_cids=[],
                            downstream_rejects={}, station_order=4) == {
            'rows': [], 'cols': [], 'cells': [], 'row_pct': []}
