# -*- coding: utf-8 -*-
"""Service tests for mid-section defect analysis."""

from __future__ import annotations

from unittest.mock import patch

import pandas as pd

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


# ============================================================
# Task 9.5: MSD engine parallel env var tests
# ============================================================

class TestMsdEngineParallel:
    """MSD_ENGINE_PARALLEL env var controls execute_plan parallel for MSD detection."""

    def _make_detection_env(self, monkeypatch, *, engine_calls, progress=None):
        import mes_dashboard.services.batch_query_engine as engine_mod
        import mes_dashboard.services.mid_section_defect_service as msd_svc
        import mes_dashboard.core.query_spool_store as spool_mod
        import mes_dashboard.sql as sql_mod

        def fake_execute_plan(chunks, query_fn, **kwargs):
            engine_calls.append(kwargs.get("parallel"))
            return kwargs.get("query_hash", "fake_hash")

        # Patch engine_mod (these are imported fresh inside the function)
        monkeypatch.setattr(engine_mod, "execute_plan", fake_execute_plan)
        monkeypatch.setattr(engine_mod, "merge_chunks_to_spool", lambda *a, **kw: ("/tmp/f.parquet", 1))
        monkeypatch.setattr(engine_mod, "get_batch_progress", lambda *a: progress or {})
        monkeypatch.setattr(engine_mod, "should_decompose_by_time", lambda *a: True)
        monkeypatch.setattr(engine_mod, "decompose_by_time_range", lambda *a, **kw: [
            {"chunk_start": "2025-01-01", "chunk_end": "2025-01-31"},
        ])
        monkeypatch.setattr(spool_mod, "register_spool_file", lambda *a, **kw: None)
        monkeypatch.setattr(spool_mod, "load_spooled_df", lambda *a: None)
        monkeypatch.setattr(sql_mod.SQLLoader, "load_with_params", lambda *a, **kw: "SELECT 1")
        monkeypatch.setattr(msd_svc, "read_sql_df", lambda *a, **kw: __import__('pandas').DataFrame())
        # Bypass cache_get so it goes to Oracle path
        monkeypatch.setattr(msd_svc, "cache_get", lambda *a: None)
        # Mock _build_station_filter to return simple values
        monkeypatch.setattr(msd_svc, "_build_station_filter", lambda station, alias: ("1=1", {}))

    def test_default_parallel_is_1(self, monkeypatch):
        """Without MSD_ENGINE_PARALLEL → execute_plan gets parallel=1."""
        import mes_dashboard.services.mid_section_defect_service as msd_svc

        engine_calls = []
        monkeypatch.setattr(msd_svc, "_MSD_ENGINE_PARALLEL", 1)
        self._make_detection_env(monkeypatch, engine_calls=engine_calls)

        msd_svc._fetch_station_detection_data("2025-01-01", "2025-12-31", "TestStation")

        assert len(engine_calls) == 1
        assert engine_calls[0] == 1

    def test_parallel_2_passed_to_execute_plan(self, monkeypatch):
        """MSD_ENGINE_PARALLEL=2 → execute_plan gets parallel=2."""
        import mes_dashboard.services.mid_section_defect_service as msd_svc

        engine_calls = []
        monkeypatch.setattr(msd_svc, "_MSD_ENGINE_PARALLEL", 2)
        self._make_detection_env(monkeypatch, engine_calls=engine_calls)

        msd_svc._fetch_station_detection_data("2025-01-01", "2025-12-31", "TestStation")

        assert len(engine_calls) == 1
        assert engine_calls[0] == 2


# ============================================================
# Task 10.9: MSD partial failure warning test
# ============================================================

class TestMsdPartialFailure:
    """MSD detection partial failure logs a warning and propagates to _meta."""

    def _setup_partial_failure_mocks(self, monkeypatch):
        """Common mock setup for partial failure tests."""
        import mes_dashboard.services.mid_section_defect_service as msd_svc
        import mes_dashboard.services.batch_query_engine as engine_mod
        import mes_dashboard.core.query_spool_store as spool_mod
        import mes_dashboard.sql as sql_mod
        import pandas as pd

        monkeypatch.setattr(engine_mod, "execute_plan", lambda *a, **kw: kw.get("query_hash", "fake"))
        monkeypatch.setattr(engine_mod, "merge_chunks_to_spool", lambda *a, **kw: ("/tmp/f.parquet", 1))
        monkeypatch.setattr(
            engine_mod,
            "get_batch_progress",
            lambda *a: {"has_partial_failure": "True", "failed_ranges": "2025-01-01~2025-01-31"},
        )
        monkeypatch.setattr(engine_mod, "should_decompose_by_time", lambda *a: True)
        monkeypatch.setattr(engine_mod, "decompose_by_time_range", lambda *a, **kw: [
            {"chunk_start": "2025-01-01", "chunk_end": "2025-01-31"},
        ])
        monkeypatch.setattr(spool_mod, "register_spool_file", lambda *a, **kw: None)
        monkeypatch.setattr(spool_mod, "load_spooled_df", lambda *a: None)
        monkeypatch.setattr(sql_mod.SQLLoader, "load_with_params", lambda *a, **kw: "SELECT 1")
        monkeypatch.setattr(msd_svc, "read_sql_df", lambda *a, **kw: pd.DataFrame())
        monkeypatch.setattr(msd_svc, "cache_get", lambda *a: None)
        monkeypatch.setattr(msd_svc, "_build_station_filter", lambda station, alias: ("1=1", {}))
        return msd_svc

    def test_partial_failure_warning_logged(self, monkeypatch, caplog):
        """Chunk partial failure → logger.warning is emitted."""
        import logging
        msd_svc = self._setup_partial_failure_mocks(monkeypatch)

        with caplog.at_level(logging.WARNING, logger="mes_dashboard.mid_section_defect"):
            msd_svc._fetch_station_detection_data("2025-01-01", "2025-12-31", "TestStation")

        assert any("partial failure" in r.message.lower() for r in caplog.records)

    def test_partial_failure_returned_in_meta(self, monkeypatch):
        """Chunk partial failure → returned tuple[1] contains partial failure info."""
        msd_svc = self._setup_partial_failure_mocks(monkeypatch)

        df, pf_meta = msd_svc._fetch_station_detection_data("2025-01-01", "2025-12-31", "TestStation")

        assert pf_meta.get("has_partial_failure") is True
        assert pf_meta.get("failed_ranges") == "2025-01-01~2025-01-31"

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
def test_query_analysis_filter_by_pj_type_reduces_rows(
    mock_fetch,
    _mock_ensure,
    _mock_spool,
    _mock_cache_get,
    _mock_cache_set,
):
    """Passing pj_types=['TYPE-A'] should exclude TYPE-B rows from detection_df."""
    mock_fetch.return_value = (_make_detection_df_with_types(), {})

    result = query_analysis('2025-01-01', '2025-01-31', pj_types=['TYPE-A'])

    assert result is not None
    assert 'error' not in result
    # Only TYPE-A container (CID-001/R1) should remain
    available = result.get('available_loss_reasons', [])
    assert 'R1' in available
    assert 'R2' not in available


@patch('mes_dashboard.services.mid_section_defect_service.cache_set')
@patch('mes_dashboard.services.mid_section_defect_service.cache_get', return_value=None)
@patch('mes_dashboard.services.mid_section_defect_service._load_analysis_from_spool', return_value=None)
@patch('mes_dashboard.services.mid_section_defect_service.ensure_analysis_background_job', return_value=None)
@patch('mes_dashboard.services.mid_section_defect_service._fetch_station_detection_data')
def test_query_analysis_filter_by_package_reduces_rows(
    mock_fetch,
    _mock_ensure,
    _mock_spool,
    _mock_cache_get,
    _mock_cache_set,
):
    """Passing packages=['PKG-B'] should exclude PKG-A rows from detection_df."""
    mock_fetch.return_value = (_make_detection_df_with_types(), {})

    result = query_analysis('2025-01-01', '2025-01-31', packages=['PKG-B'])

    assert result is not None
    assert 'error' not in result
    available = result.get('available_loss_reasons', [])
    assert 'R2' in available
    assert 'R1' not in available


@patch('mes_dashboard.services.mid_section_defect_service.cache_set')
@patch('mes_dashboard.services.mid_section_defect_service.cache_get', return_value=None)
@patch('mes_dashboard.services.mid_section_defect_service._load_analysis_from_spool', return_value=None)
@patch('mes_dashboard.services.mid_section_defect_service.ensure_analysis_background_job', return_value=None)
@patch('mes_dashboard.services.mid_section_defect_service._fetch_station_detection_data')
def test_query_analysis_filter_pj_type_and_package_and_semantics(
    mock_fetch,
    _mock_ensure,
    _mock_spool,
    _mock_cache_get,
    _mock_cache_set,
):
    """AND-semantics: both pj_types and packages applied; no co-occurrence → empty."""
    mock_fetch.return_value = (_make_detection_df_with_types(), {})

    # TYPE-A is in CID-001/PKG-A, TYPE-B in CID-002/PKG-B
    # Asking for TYPE-A AND PKG-B → no rows match
    result = query_analysis(
        '2025-01-01', '2025-01-31',
        pj_types=['TYPE-A'],
        packages=['PKG-B'],
    )

    assert result is not None
    assert 'error' not in result
    assert result.get('available_loss_reasons', []) == []


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
def test_query_analysis_unknown_pj_type_returns_empty_detection(
    mock_fetch,
    _mock_ensure,
    _mock_spool,
    _mock_cache_get,
    _mock_cache_set,
):
    """Unknown pj_types value → empty df after filter; response shape unchanged; no 5xx."""
    mock_fetch.return_value = (_make_detection_df_with_types(), {})

    result = query_analysis('2025-01-01', '2025-01-31', pj_types=['NONEXISTENT'])

    assert result is not None
    assert 'error' not in result
    assert result.get('available_loss_reasons', []) == []


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
    _mock_spool,
    _mock_cache_get,
    _mock_cache_set,
):
    """NULL PJ_TYPE values are excluded from isin match; no crash (AC-7 #8)."""
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

    # NULL row must be excluded; TYPE-B row should pass
    result = query_analysis('2025-01-01', '2025-01-31', pj_types=['TYPE-B'])

    assert result is not None
    assert 'error' not in result
    available = result.get('available_loss_reasons', [])
    assert 'R2' in available
    assert 'R1' not in available


# ---------------------------------------------------------------------------
# resolve_trace_seed_lots: pj_types / packages filter (trace path)
# ---------------------------------------------------------------------------

@patch('mes_dashboard.services.mid_section_defect_service._fetch_station_detection_data')
def test_resolve_trace_seed_lots_filter_by_pj_type(mock_fetch):
    """pj_types filter must exclude non-matching seeds from the trace seed set."""
    mock_fetch.return_value = (_make_detection_df_with_types(), {})

    result = resolve_trace_seed_lots('2025-01-01', '2025-01-31', pj_types=['TYPE-A'])

    assert result is not None
    assert 'error' not in result
    cids = [s['container_id'] for s in result['seeds']]
    assert 'CID-001' in cids
    assert 'CID-002' not in cids
    assert result['seed_count'] == 1


@patch('mes_dashboard.services.mid_section_defect_service._fetch_station_detection_data')
def test_resolve_trace_seed_lots_filter_by_package(mock_fetch):
    """packages filter must exclude non-matching seeds from the trace seed set."""
    mock_fetch.return_value = (_make_detection_df_with_types(), {})

    result = resolve_trace_seed_lots('2025-01-01', '2025-01-31', packages=['PKG-B'])

    assert result is not None
    assert 'error' not in result
    cids = [s['container_id'] for s in result['seeds']]
    assert 'CID-002' in cids
    assert 'CID-001' not in cids
    assert result['seed_count'] == 1


@patch('mes_dashboard.services.mid_section_defect_service._fetch_station_detection_data')
def test_resolve_trace_seed_lots_no_filter_returns_all(mock_fetch):
    """Empty pj_types/packages means no restriction — all seeds returned."""
    mock_fetch.return_value = (_make_detection_df_with_types(), {})

    result = resolve_trace_seed_lots('2025-01-01', '2025-01-31')

    assert result is not None
    assert result['seed_count'] == 2


@patch('mes_dashboard.services.mid_section_defect_service._fetch_station_detection_data')
def test_resolve_trace_seed_lots_filter_all_excluded_returns_empty(mock_fetch):
    """Filter that excludes all rows must return seed_count=0, not error."""
    mock_fetch.return_value = (_make_detection_df_with_types(), {})

    result = resolve_trace_seed_lots('2025-01-01', '2025-01-31', pj_types=['NONEXISTENT'])

    assert result is not None
    assert 'error' not in result
    assert result['seed_count'] == 0
    assert result['seeds'] == []
