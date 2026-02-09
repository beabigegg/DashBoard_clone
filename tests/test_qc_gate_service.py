# -*- coding: utf-8 -*-
"""Unit tests for QC-GATE summary service."""

from __future__ import annotations

from unittest.mock import patch

import pandas as pd

from mes_dashboard.services.qc_gate_service import get_qc_gate_summary


@patch('mes_dashboard.services.qc_gate_service.get_spec_order_mapping')
@patch('mes_dashboard.services.qc_gate_service.get_cache_updated_at')
@patch('mes_dashboard.services.qc_gate_service.get_cached_sys_date')
@patch('mes_dashboard.services.qc_gate_service.get_cached_wip_data')
def test_get_qc_gate_summary_filters_classifies_and_orders(
    mock_get_wip,
    mock_get_sys_date,
    mock_get_cache_updated_at,
    mock_get_spec_order_mapping,
):
    mock_get_sys_date.return_value = '2026-02-09T12:00:00'
    mock_get_cache_updated_at.return_value = '2026-02-09T12:00:00'
    mock_get_spec_order_mapping.return_value = {
        'QC-GATE-A': 10,
        'QC-GATE-B': 20,
    }

    mock_get_wip.return_value = pd.DataFrame(
        [
            {
                'LOTID': 'L-001',
                'CONTAINERID': 'C-001',
                'SPECNAME': 'QC-GATE-B',
                'MOVEINTIMESTAMP': '2026-02-09T09:00:00',
                'QTY': 100,
                'WORKORDER': 'WO-1',
                'STATUS': 'QUEUE',
                'EQUIPMENTS': None,
            },
            {
                'LOTID': 'L-002',
                'CONTAINERID': 'C-002',
                'SPECNAME': 'QC-GATE-A',
                'MOVEINTIMESTAMP': '2026-02-09T11:00:00',
                'QTY': 200,
                'WORKORDER': 'WO-2',
                'STATUS': 'QUEUE',
                'EQUIPMENTS': None,
            },
            {
                'LOTID': 'L-003',
                'CONTAINERID': 'C-003',
                'SPECNAME': 'QC-GATE-A',
                'MOVEINTIMESTAMP': '2026-02-08T08:00:00',
                'QTY': 50,
                'WORKORDER': 'WO-3',
                'STATUS': 'HOLD',
                'EQUIPMENTS': None,
            },
            {
                'LOTID': 'L-004',
                'CONTAINERID': 'C-004',
                'SPECNAME': 'ASSEMBLY-STEP',
                'MOVEINTIMESTAMP': '2026-02-09T10:00:00',
                'QTY': 25,
                'WORKORDER': 'WO-4',
                'STATUS': 'QUEUE',
                'EQUIPMENTS': None,
            },
            {
                'LOTID': 'L-005',
                'CONTAINERID': 'C-005',
                'SPECNAME': 'QC-LATE-GATE',
                'MOVEINTIMESTAMP': '2026-02-07T06:00:00',
                'QTY': 75,
                'WORKORDER': 'WO-5',
                'STATUS': 'QUEUE',
                'EQUIPMENTS': None,
            },
        ]
    )

    result = get_qc_gate_summary()

    assert result is not None
    assert result['cache_time'] == '2026-02-09T12:00:00'

    stations = result['stations']
    assert [station['specname'] for station in stations] == [
        'QC-GATE-A',
        'QC-GATE-B',
        'QC-LATE-GATE',
    ]

    station_a = stations[0]
    assert station_a['buckets']['lt_6h'] == 1
    assert station_a['buckets']['gt_24h'] == 1
    assert station_a['total'] == 2

    station_b = stations[1]
    assert station_b['buckets']['lt_6h'] == 1
    assert station_b['total'] == 1

    unknown_station = stations[2]
    assert unknown_station['spec_order'] == 999999
    assert unknown_station['total'] == 1


@patch('mes_dashboard.services.qc_gate_service.get_spec_order_mapping', return_value={})
@patch('mes_dashboard.services.qc_gate_service.get_cache_updated_at', return_value='2026-02-09T12:00:00')
@patch('mes_dashboard.services.qc_gate_service.get_cached_sys_date', return_value=None)
@patch('mes_dashboard.services.qc_gate_service.get_cached_wip_data')
def test_get_qc_gate_summary_returns_empty_when_no_match(
    mock_get_wip,
    _mock_get_sys_date,
    _mock_get_cache_updated_at,
    _mock_get_spec_order_mapping,
):
    mock_get_wip.return_value = pd.DataFrame(
        [
            {
                'LOTID': 'L-100',
                'SPECNAME': 'ASSEMBLY-STEP',
                'MOVEINTIMESTAMP': '2026-02-09T10:00:00',
            }
        ]
    )

    result = get_qc_gate_summary()

    assert result is not None
    assert result['cache_time'] == '2026-02-09T12:00:00'
    assert result['stations'] == []


@patch('mes_dashboard.services.qc_gate_service.get_cache_updated_at', return_value='2026-02-09T12:00:00')
@patch('mes_dashboard.services.qc_gate_service.get_cached_sys_date', return_value=None)
@patch('mes_dashboard.services.qc_gate_service.get_cached_wip_data', return_value=None)
def test_get_qc_gate_summary_returns_empty_when_cache_missing(
    _mock_get_wip,
    _mock_get_sys_date,
    _mock_get_cache_updated_at,
):
    result = get_qc_gate_summary()

    assert result is not None
    assert result['cache_time'] == '2026-02-09T12:00:00'
    assert result['stations'] == []
