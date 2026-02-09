# -*- coding: utf-8 -*-
"""Unit tests for TMTT Defect Analysis Service."""

import unittest
from unittest.mock import patch, MagicMock

import pandas as pd

from mes_dashboard.services.tmtt_defect_service import (
    _build_kpi,
    _build_chart_data,
    _build_all_charts,
    _build_detail_table,
    _validate_date_range,
    query_tmtt_defect_analysis,
    PRINT_DEFECT,
    LEAD_DEFECT,
)


def _make_df(rows):
    """Helper to create test DataFrame from list of dicts."""
    cols = [
        'CONTAINERID', 'CONTAINERNAME', 'PJ_TYPE', 'PRODUCTLINENAME',
        'WORKFLOW', 'FINISHEDRUNCARD', 'TMTT_EQUIPMENTID',
        'TMTT_EQUIPMENTNAME', 'TRACKINQTY', 'TRACKINTIMESTAMP',
        'MOLD_EQUIPMENTID', 'MOLD_EQUIPMENTNAME',
        'LOSSREASONNAME', 'REJECTQTY',
    ]
    if not rows:
        return pd.DataFrame(columns=cols)
    df = pd.DataFrame(rows)
    for c in cols:
        if c not in df.columns:
            df[c] = None
    return df


class TestValidateDateRange(unittest.TestCase):
    """Test date range validation."""

    def test_valid_range(self):
        self.assertIsNone(_validate_date_range('2025-01-01', '2025-01-31'))

    def test_invalid_format(self):
        result = _validate_date_range('2025/01/01', '2025-01-31')
        self.assertIn('格式', result)

    def test_start_after_end(self):
        result = _validate_date_range('2025-02-01', '2025-01-01')
        self.assertIn('不能晚於', result)

    def test_exceeds_max_days(self):
        result = _validate_date_range('2025-01-01', '2025-12-31')
        self.assertIn('180', result)

    def test_exactly_max_days(self):
        self.assertIsNone(_validate_date_range('2025-01-01', '2025-06-30'))


class TestBuildKpi(unittest.TestCase):
    """Test KPI calculation with separate defect rates."""

    def test_empty_dataframe(self):
        df = _make_df([])
        kpi = _build_kpi(df)
        self.assertEqual(kpi['total_input'], 0)
        self.assertEqual(kpi['lot_count'], 0)
        self.assertEqual(kpi['print_defect_qty'], 0)
        self.assertEqual(kpi['lead_defect_qty'], 0)
        self.assertEqual(kpi['print_defect_rate'], 0.0)
        self.assertEqual(kpi['lead_defect_rate'], 0.0)

    def test_single_lot_no_defects(self):
        df = _make_df([{
            'CONTAINERID': 'A001', 'TRACKINQTY': 100,
            'LOSSREASONNAME': None, 'REJECTQTY': 0,
        }])
        kpi = _build_kpi(df)
        self.assertEqual(kpi['total_input'], 100)
        self.assertEqual(kpi['lot_count'], 1)
        self.assertEqual(kpi['print_defect_qty'], 0)
        self.assertEqual(kpi['lead_defect_qty'], 0)

    def test_separate_defect_rates(self):
        """A LOT with both print and lead defects - rates calculated separately."""
        df = _make_df([
            {'CONTAINERID': 'A001', 'TRACKINQTY': 10000,
             'LOSSREASONNAME': PRINT_DEFECT, 'REJECTQTY': 50},
            {'CONTAINERID': 'A001', 'TRACKINQTY': 10000,
             'LOSSREASONNAME': LEAD_DEFECT, 'REJECTQTY': 30},
        ])
        kpi = _build_kpi(df)
        # INPUT should be deduplicated (10000, not 20000)
        self.assertEqual(kpi['total_input'], 10000)
        self.assertEqual(kpi['lot_count'], 1)
        self.assertEqual(kpi['print_defect_qty'], 50)
        self.assertEqual(kpi['lead_defect_qty'], 30)
        self.assertAlmostEqual(kpi['print_defect_rate'], 0.5, places=4)
        self.assertAlmostEqual(kpi['lead_defect_rate'], 0.3, places=4)

    def test_multiple_lots(self):
        df = _make_df([
            {'CONTAINERID': 'A001', 'TRACKINQTY': 100,
             'LOSSREASONNAME': PRINT_DEFECT, 'REJECTQTY': 2},
            {'CONTAINERID': 'A002', 'TRACKINQTY': 200,
             'LOSSREASONNAME': LEAD_DEFECT, 'REJECTQTY': 1},
            {'CONTAINERID': 'A003', 'TRACKINQTY': 300,
             'LOSSREASONNAME': None, 'REJECTQTY': 0},
        ])
        kpi = _build_kpi(df)
        self.assertEqual(kpi['total_input'], 600)
        self.assertEqual(kpi['lot_count'], 3)
        self.assertEqual(kpi['print_defect_qty'], 2)
        self.assertEqual(kpi['lead_defect_qty'], 1)


class TestBuildChartData(unittest.TestCase):
    """Test Pareto chart data aggregation."""

    def test_empty_dataframe(self):
        df = _make_df([])
        result = _build_chart_data(df, 'PJ_TYPE')
        self.assertEqual(result, [])

    def test_single_dimension_value(self):
        df = _make_df([
            {'CONTAINERID': 'A001', 'TRACKINQTY': 100, 'PJ_TYPE': 'TypeA',
             'LOSSREASONNAME': PRINT_DEFECT, 'REJECTQTY': 5},
            {'CONTAINERID': 'A001', 'TRACKINQTY': 100, 'PJ_TYPE': 'TypeA',
             'LOSSREASONNAME': LEAD_DEFECT, 'REJECTQTY': 3},
        ])
        result = _build_chart_data(df, 'PJ_TYPE')
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['name'], 'TypeA')
        self.assertEqual(result[0]['print_defect_qty'], 5)
        self.assertEqual(result[0]['lead_defect_qty'], 3)
        self.assertEqual(result[0]['total_defect_qty'], 8)
        self.assertAlmostEqual(result[0]['cumulative_pct'], 100.0)

    def test_null_dimension_grouped_as_unknown(self):
        df = _make_df([
            {'CONTAINERID': 'A001', 'TRACKINQTY': 100, 'MOLD_EQUIPMENTNAME': None,
             'LOSSREASONNAME': PRINT_DEFECT, 'REJECTQTY': 2},
        ])
        result = _build_chart_data(df, 'MOLD_EQUIPMENTNAME')
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['name'], '(未知)')

    def test_sorted_by_total_defect_desc(self):
        df = _make_df([
            {'CONTAINERID': 'A001', 'TRACKINQTY': 100, 'PJ_TYPE': 'TypeA',
             'LOSSREASONNAME': PRINT_DEFECT, 'REJECTQTY': 1},
            {'CONTAINERID': 'A002', 'TRACKINQTY': 100, 'PJ_TYPE': 'TypeB',
             'LOSSREASONNAME': PRINT_DEFECT, 'REJECTQTY': 10},
        ])
        result = _build_chart_data(df, 'PJ_TYPE')
        self.assertEqual(result[0]['name'], 'TypeB')
        self.assertEqual(result[1]['name'], 'TypeA')

    def test_cumulative_percentage(self):
        df = _make_df([
            {'CONTAINERID': 'A001', 'TRACKINQTY': 100, 'PJ_TYPE': 'TypeA',
             'LOSSREASONNAME': PRINT_DEFECT, 'REJECTQTY': 6},
            {'CONTAINERID': 'A002', 'TRACKINQTY': 100, 'PJ_TYPE': 'TypeB',
             'LOSSREASONNAME': PRINT_DEFECT, 'REJECTQTY': 4},
        ])
        result = _build_chart_data(df, 'PJ_TYPE')
        # TypeA: 6/10 = 60%, TypeB: cumulative 10/10 = 100%
        self.assertAlmostEqual(result[0]['cumulative_pct'], 60.0)
        self.assertAlmostEqual(result[1]['cumulative_pct'], 100.0)


class TestBuildAllCharts(unittest.TestCase):
    """Test all 5 chart dimensions are built."""

    def test_returns_all_dimensions(self):
        df = _make_df([{
            'CONTAINERID': 'A001', 'TRACKINQTY': 100,
            'WORKFLOW': 'WF1', 'PRODUCTLINENAME': 'PKG1',
            'PJ_TYPE': 'T1', 'TMTT_EQUIPMENTNAME': 'TMTT-1',
            'MOLD_EQUIPMENTNAME': 'MOLD-1',
            'LOSSREASONNAME': PRINT_DEFECT, 'REJECTQTY': 1,
        }])
        charts = _build_all_charts(df)
        self.assertIn('by_workflow', charts)
        self.assertIn('by_package', charts)
        self.assertIn('by_type', charts)
        self.assertIn('by_tmtt_machine', charts)
        self.assertIn('by_mold_machine', charts)


class TestBuildDetailTable(unittest.TestCase):
    """Test detail table building."""

    def test_empty_dataframe(self):
        df = _make_df([])
        result = _build_detail_table(df)
        self.assertEqual(result, [])

    def test_single_lot_aggregated(self):
        """LOT with both defect types should produce one row."""
        df = _make_df([
            {'CONTAINERID': 'A001', 'CONTAINERNAME': 'LOT-001',
             'TRACKINQTY': 100, 'PJ_TYPE': 'T1', 'PRODUCTLINENAME': 'P1',
             'WORKFLOW': 'WF1', 'FINISHEDRUNCARD': 'RC001',
             'TMTT_EQUIPMENTNAME': 'TMTT-1', 'MOLD_EQUIPMENTNAME': 'MOLD-1',
             'LOSSREASONNAME': PRINT_DEFECT, 'REJECTQTY': 5},
            {'CONTAINERID': 'A001', 'CONTAINERNAME': 'LOT-001',
             'TRACKINQTY': 100, 'PJ_TYPE': 'T1', 'PRODUCTLINENAME': 'P1',
             'WORKFLOW': 'WF1', 'FINISHEDRUNCARD': 'RC001',
             'TMTT_EQUIPMENTNAME': 'TMTT-1', 'MOLD_EQUIPMENTNAME': 'MOLD-1',
             'LOSSREASONNAME': LEAD_DEFECT, 'REJECTQTY': 3},
        ])
        result = _build_detail_table(df)
        self.assertEqual(len(result), 1)
        row = result[0]
        self.assertEqual(row['CONTAINERNAME'], 'LOT-001')
        self.assertEqual(row['INPUT_QTY'], 100)
        self.assertEqual(row['PRINT_DEFECT_QTY'], 5)
        self.assertEqual(row['LEAD_DEFECT_QTY'], 3)
        self.assertAlmostEqual(row['PRINT_DEFECT_RATE'], 5.0, places=4)
        self.assertAlmostEqual(row['LEAD_DEFECT_RATE'], 3.0, places=4)

    def test_lot_with_no_defects(self):
        df = _make_df([{
            'CONTAINERID': 'A001', 'CONTAINERNAME': 'LOT-001',
            'TRACKINQTY': 100, 'PJ_TYPE': 'T1',
            'LOSSREASONNAME': None, 'REJECTQTY': 0,
        }])
        result = _build_detail_table(df)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['PRINT_DEFECT_QTY'], 0)
        self.assertEqual(result[0]['LEAD_DEFECT_QTY'], 0)


class TestQueryTmttDefectAnalysis(unittest.TestCase):
    """Test the main entry point function."""

    def setUp(self):
        from mes_dashboard.core import database as db
        db._ENGINE = None

    @patch('mes_dashboard.services.tmtt_defect_service.cache_get', return_value=None)
    @patch('mes_dashboard.services.tmtt_defect_service.cache_set')
    @patch('mes_dashboard.services.tmtt_defect_service._fetch_base_data')
    def test_valid_query(self, mock_fetch, mock_cache_set, mock_cache_get):
        mock_fetch.return_value = _make_df([{
            'CONTAINERID': 'A001', 'CONTAINERNAME': 'LOT-001',
            'TRACKINQTY': 100, 'PJ_TYPE': 'T1', 'PRODUCTLINENAME': 'P1',
            'WORKFLOW': 'WF1', 'FINISHEDRUNCARD': 'RC001',
            'TMTT_EQUIPMENTNAME': 'TMTT-1', 'MOLD_EQUIPMENTNAME': 'MOLD-1',
            'LOSSREASONNAME': PRINT_DEFECT, 'REJECTQTY': 2,
        }])

        result = query_tmtt_defect_analysis('2025-01-01', '2025-01-31')
        self.assertIn('kpi', result)
        self.assertIn('charts', result)
        self.assertIn('detail', result)
        self.assertNotIn('error', result)
        mock_cache_set.assert_called_once()

    def test_invalid_dates(self):
        result = query_tmtt_defect_analysis('invalid', '2025-01-31')
        self.assertIn('error', result)

    def test_exceeds_max_days(self):
        result = query_tmtt_defect_analysis('2025-01-01', '2025-12-31')
        self.assertIn('error', result)
        self.assertIn('180', result['error'])

    @patch('mes_dashboard.services.tmtt_defect_service.cache_get')
    def test_cache_hit(self, mock_cache_get):
        cached_data = {'kpi': {}, 'charts': {}, 'detail': []}
        mock_cache_get.return_value = cached_data
        result = query_tmtt_defect_analysis('2025-01-01', '2025-01-31')
        self.assertEqual(result, cached_data)

    @patch('mes_dashboard.services.tmtt_defect_service.cache_get', return_value=None)
    @patch('mes_dashboard.services.tmtt_defect_service._fetch_base_data', return_value=None)
    def test_query_failure(self, mock_fetch, mock_cache_get):
        result = query_tmtt_defect_analysis('2025-01-01', '2025-01-31')
        self.assertIsNone(result)


if __name__ == '__main__':
    unittest.main()
