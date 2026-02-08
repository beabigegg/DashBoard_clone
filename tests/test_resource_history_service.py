# -*- coding: utf-8 -*-
"""Unit tests for resource_history_service.py.

Tests the service layer functions for resource history analysis.
"""

import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta

import pandas as pd

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from mes_dashboard.services.resource_history_service import (
    get_filter_options,
    query_summary,
    query_detail,
    export_csv,
    _validate_date_range,
    _get_date_trunc,
    _calc_ou_pct,
    _calc_availability_pct,
    _build_kpi_from_df,
    _build_detail_from_raw_df,
    MAX_QUERY_DAYS,
)


class TestValidateDateRange(unittest.TestCase):
    """Test date range validation."""

    def test_valid_date_range(self):
        """Valid date range should return None."""
        result = _validate_date_range('2024-01-01', '2024-01-31')
        self.assertIsNone(result)

    def test_date_range_exceeds_max(self):
        """Date range exceeding MAX_QUERY_DAYS should return error message."""
        result = _validate_date_range('2024-01-01', '2026-01-02')
        self.assertIsNotNone(result)
        self.assertIn('730', result)

    def test_end_date_before_start_date(self):
        """End date before start date should return error message."""
        result = _validate_date_range('2024-01-31', '2024-01-01')
        self.assertIsNotNone(result)
        self.assertIn('起始日期', result)

    def test_invalid_date_format(self):
        """Invalid date format should return error message."""
        result = _validate_date_range('invalid', '2024-01-01')
        self.assertIsNotNone(result)
        self.assertIn('日期格式錯誤', result)


class TestGetDateTrunc(unittest.TestCase):
    """Test date truncation SQL generation."""

    def test_day_granularity(self):
        """Day granularity should use TRUNC without format."""
        result = _get_date_trunc('day')
        self.assertIn('TRUNC(TXNDATE)', result)
        self.assertNotIn('IW', result)

    def test_week_granularity(self):
        """Week granularity should use TRUNC with IW format."""
        result = _get_date_trunc('week')
        self.assertIn("'IW'", result)

    def test_month_granularity(self):
        """Month granularity should use TRUNC with MM format."""
        result = _get_date_trunc('month')
        self.assertIn("'MM'", result)

    def test_year_granularity(self):
        """Year granularity should use TRUNC with YYYY format."""
        result = _get_date_trunc('year')
        self.assertIn("'YYYY'", result)

    def test_unknown_granularity(self):
        """Unknown granularity should default to day."""
        result = _get_date_trunc('unknown')
        self.assertIn('TRUNC(TXNDATE)', result)
        self.assertNotIn("'IW'", result)


class TestCalcOuPct(unittest.TestCase):
    """Test OU% calculation."""

    def test_normal_calculation(self):
        """OU% should be calculated correctly."""
        # PRD=800, SBY=100, UDT=50, SDT=30, EGT=20
        # OU% = 800 / (800+100+50+30+20) * 100 = 80%
        result = _calc_ou_pct(800, 100, 50, 30, 20)
        self.assertEqual(result, 80.0)

    def test_zero_denominator(self):
        """Zero denominator should return 0, not error."""
        result = _calc_ou_pct(0, 0, 0, 0, 0)
        self.assertEqual(result, 0)

    def test_all_prd(self):
        """100% PRD should result in 100% OU."""
        result = _calc_ou_pct(100, 0, 0, 0, 0)
        self.assertEqual(result, 100.0)

    def test_no_prd(self):
        """No PRD should result in 0% OU."""
        result = _calc_ou_pct(0, 100, 50, 30, 20)
        self.assertEqual(result, 0)


class TestCalcAvailabilityPct(unittest.TestCase):
    """Test Availability% calculation."""

    def test_normal_calculation(self):
        """Availability% should be calculated correctly."""
        # PRD=800, SBY=100, UDT=50, SDT=30, EGT=20, NST=100
        # Availability% = (800+100+20) / (800+100+20+30+50+100) * 100 = 920 / 1100 * 100 = 83.6%
        result = _calc_availability_pct(800, 100, 50, 30, 20, 100)
        self.assertEqual(result, 83.6)

    def test_zero_denominator(self):
        """Zero denominator should return 0, not error."""
        result = _calc_availability_pct(0, 0, 0, 0, 0, 0)
        self.assertEqual(result, 0)

    def test_all_available(self):
        """100% available (no SDT, UDT, NST) should result in 100%."""
        # PRD=100, SBY=50, EGT=50, no SDT/UDT/NST
        # Availability% = (100+50+50) / (100+50+50+0+0+0) * 100 = 100%
        result = _calc_availability_pct(100, 50, 0, 0, 50, 0)
        self.assertEqual(result, 100.0)

    def test_no_available_time(self):
        """No available time (all SDT/UDT/NST) should result in 0%."""
        # PRD=0, SBY=0, EGT=0, SDT=50, UDT=30, NST=20
        # Availability% = 0 / (0+0+0+50+30+20) * 100 = 0%
        result = _calc_availability_pct(0, 0, 50, 30, 0, 20)
        self.assertEqual(result, 0)

    def test_mixed_scenario(self):
        """Mixed scenario with partial availability."""
        # PRD=500, SBY=200, UDT=100, SDT=100, EGT=50, NST=50
        # Numerator = PRD + SBY + EGT = 500 + 200 + 50 = 750
        # Denominator = 500 + 200 + 50 + 100 + 100 + 50 = 1000
        # Availability% = 750 / 1000 * 100 = 75%
        result = _calc_availability_pct(500, 200, 100, 100, 50, 50)
        self.assertEqual(result, 75.0)


class TestBuildKpiFromDf(unittest.TestCase):
    """Test KPI building from DataFrame."""

    def test_empty_dataframe(self):
        """Empty DataFrame should return default KPI values."""
        df = pd.DataFrame()
        result = _build_kpi_from_df(df)

        self.assertEqual(result['ou_pct'], 0)
        self.assertEqual(result['availability_pct'], 0)
        self.assertEqual(result['prd_hours'], 0)
        self.assertEqual(result['machine_count'], 0)

    def test_normal_dataframe(self):
        """Normal DataFrame should build correct KPI."""
        df = pd.DataFrame([{
            'PRD_HOURS': 800,
            'SBY_HOURS': 100,
            'UDT_HOURS': 50,
            'SDT_HOURS': 30,
            'EGT_HOURS': 20,
            'NST_HOURS': 100,
            'MACHINE_COUNT': 10
        }])
        result = _build_kpi_from_df(df)

        self.assertEqual(result['ou_pct'], 80.0)
        # Availability% = (800+100+20) / (800+100+20+30+50+100) * 100 = 920/1100 = 83.6%
        self.assertEqual(result['availability_pct'], 83.6)
        self.assertEqual(result['prd_hours'], 800)
        self.assertEqual(result['machine_count'], 10)

    def test_none_values_in_dataframe(self):
        """None values should be treated as 0."""
        df = pd.DataFrame([{
            'PRD_HOURS': None,
            'SBY_HOURS': None,
            'UDT_HOURS': None,
            'SDT_HOURS': None,
            'EGT_HOURS': None,
            'NST_HOURS': None,
            'MACHINE_COUNT': None
        }])
        result = _build_kpi_from_df(df)

        self.assertEqual(result['ou_pct'], 0)
        self.assertEqual(result['availability_pct'], 0)
        self.assertEqual(result['prd_hours'], 0)
        self.assertEqual(result['machine_count'], 0)


class TestBuildDetailFromDf(unittest.TestCase):
    """Test detail data building from DataFrame."""

    def test_empty_dataframe(self):
        """Empty DataFrame should return empty list."""
        df = pd.DataFrame()
        resource_lookup = {}
        result = _build_detail_from_raw_df(df, resource_lookup)
        self.assertEqual(result, [])

    @patch('mes_dashboard.services.filter_cache.get_workcenter_mapping')
    def test_normal_dataframe(self, mock_wc_mapping):
        """Normal DataFrame should build correct detail data."""
        mock_wc_mapping.return_value = {
            'WC01': {'group': 'Group01', 'sequence': 1}
        }
        df = pd.DataFrame([{
            'HISTORYID': 'RES01',
            'PRD_HOURS': 80,
            'SBY_HOURS': 10,
            'UDT_HOURS': 5,
            'SDT_HOURS': 3,
            'EGT_HOURS': 2,
            'NST_HOURS': 10,
            'TOTAL_HOURS': 110
        }])
        resource_lookup = {
            'RES01': {
                'RESOURCEID': 'RES01',
                'WORKCENTERNAME': 'WC01',
                'RESOURCEFAMILYNAME': 'FAM01',
                'RESOURCENAME': 'RES01'
            }
        }
        result = _build_detail_from_raw_df(df, resource_lookup)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['workcenter'], 'Group01')
        self.assertEqual(result[0]['family'], 'FAM01')
        self.assertEqual(result[0]['resource'], 'RES01')
        self.assertEqual(result[0]['machine_count'], 1)
        # OU% = 80 / (80+10+5+3+2) * 100 = 80%
        self.assertEqual(result[0]['ou_pct'], 80.0)


class TestGetFilterOptions(unittest.TestCase):
    """Test filter options retrieval."""

    @patch('mes_dashboard.services.filter_cache.get_workcenter_groups')
    @patch('mes_dashboard.services.resource_cache.get_resource_families')
    def test_cache_failure(self, mock_families, mock_groups):
        """Cache failure should return None."""
        mock_groups.return_value = None
        mock_families.return_value = None
        result = get_filter_options()
        self.assertIsNone(result)

    @patch('mes_dashboard.services.filter_cache.get_workcenter_groups')
    @patch('mes_dashboard.services.resource_cache.get_resource_families')
    def test_successful_query(self, mock_families, mock_groups):
        """Successful query should return workcenter groups and families."""
        mock_groups.return_value = [
            {'name': '焊接_DB', 'sequence': 1},
            {'name': '成型', 'sequence': 4},
        ]
        mock_families.return_value = ['FAM01', 'FAM02']

        result = get_filter_options()

        self.assertIsNotNone(result)
        self.assertEqual(len(result['workcenter_groups']), 2)
        self.assertEqual(result['workcenter_groups'][0]['name'], '焊接_DB')
        self.assertEqual(result['families'], ['FAM01', 'FAM02'])


class TestQuerySummary(unittest.TestCase):
    """Test summary query function."""

    def test_invalid_date_range(self):
        """Invalid date range should return error."""
        result = query_summary(
            start_date='2024-01-01',
            end_date='2026-01-02',  # More than 730 days
            granularity='day'
        )
        self.assertIsNotNone(result)
        self.assertIn('error', result)

    @patch('mes_dashboard.services.resource_history_service.read_sql_df')
    def test_successful_query(self, mock_read_sql):
        """Successful query should return all sections."""
        # Mock data for all queries
        kpi_df = pd.DataFrame([{
            'PRD_HOURS': 800, 'SBY_HOURS': 100, 'UDT_HOURS': 50,
            'SDT_HOURS': 30, 'EGT_HOURS': 20, 'NST_HOURS': 100,
            'MACHINE_COUNT': 10
        }])

        trend_df = pd.DataFrame([{
            'DATA_DATE': datetime(2024, 1, 1),
            'PRD_HOURS': 100, 'SBY_HOURS': 10, 'UDT_HOURS': 5,
            'SDT_HOURS': 3, 'EGT_HOURS': 2, 'NST_HOURS': 10,
            'MACHINE_COUNT': 5
        }])

        heatmap_df = pd.DataFrame([{
            'WORKCENTERNAME': 'WC01', 'DATA_DATE': datetime(2024, 1, 1),
            'PRD_HOURS': 80, 'SBY_HOURS': 10, 'UDT_HOURS': 5,
            'SDT_HOURS': 3, 'EGT_HOURS': 2
        }])

        comparison_df = pd.DataFrame([{
            'WORKCENTERNAME': 'WC01',
            'PRD_HOURS': 800, 'SBY_HOURS': 100, 'UDT_HOURS': 50,
            'SDT_HOURS': 30, 'EGT_HOURS': 20, 'MACHINE_COUNT': 10
        }])

        # Use a function to return appropriate mock based on SQL content
        # (ThreadPoolExecutor runs queries in parallel, so side_effect list is unreliable)
        def mock_sql(sql):
            sql_upper = sql.upper()
            if 'DATA_DATE' in sql_upper and 'WORKCENTERNAME' in sql_upper:
                return heatmap_df  # heatmap has both DATA_DATE and WORKCENTERNAME
            elif 'DATA_DATE' in sql_upper:
                return trend_df  # trend has DATA_DATE but no WORKCENTERNAME
            elif 'WORKCENTERNAME' in sql_upper:
                return comparison_df  # comparison has WORKCENTERNAME but no DATA_DATE
            else:
                return kpi_df  # kpi has neither

        mock_read_sql.side_effect = mock_sql

        result = query_summary(
            start_date='2024-01-01',
            end_date='2024-01-07',
            granularity='day'
        )

        self.assertIsNotNone(result)
        self.assertIn('kpi', result)
        self.assertIn('trend', result)
        self.assertIn('heatmap', result)
        self.assertIn('workcenter_comparison', result)


class TestQueryDetail(unittest.TestCase):
    """Test detail query function."""

    def test_invalid_date_range(self):
        """Invalid date range should return error."""
        result = query_detail(
            start_date='2024-01-01',
            end_date='2026-01-02',  # More than 730 days
            granularity='day'
        )
        self.assertIsNotNone(result)
        self.assertIn('error', result)

    @patch('mes_dashboard.services.filter_cache.get_workcenter_mapping')
    @patch('mes_dashboard.services.resource_history_service._get_filtered_resources')
    @patch('mes_dashboard.services.resource_history_service.read_sql_df')
    def test_successful_query(self, mock_read_sql, mock_get_resources, mock_wc_mapping):
        """Successful query should return data with total count."""
        # Mock filtered resources
        mock_get_resources.return_value = [
            {'RESOURCEID': 'RES01', 'WORKCENTERNAME': 'WC01',
             'RESOURCEFAMILYNAME': 'FAM01', 'RESOURCENAME': 'RES01'}
        ]
        mock_wc_mapping.return_value = {
            'WC01': {'group': 'Group01', 'sequence': 1}
        }

        # Mock detail query with HISTORYID column
        detail_df = pd.DataFrame([{
            'HISTORYID': 'RES01',
            'PRD_HOURS': 80, 'SBY_HOURS': 10, 'UDT_HOURS': 5,
            'SDT_HOURS': 3, 'EGT_HOURS': 2, 'NST_HOURS': 10,
            'TOTAL_HOURS': 110
        }])

        mock_read_sql.return_value = detail_df

        result = query_detail(
            start_date='2024-01-01',
            end_date='2024-01-07',
            granularity='day',
        )

        self.assertIsNotNone(result)
        self.assertIn('data', result)
        self.assertIn('total', result)
        self.assertIn('truncated', result)
        self.assertEqual(result['total'], 1)
        self.assertFalse(result['truncated'])


class TestExportCsv(unittest.TestCase):
    """Test CSV export function."""

    def test_invalid_date_range(self):
        """Invalid date range should yield error."""
        result = list(export_csv(
            start_date='2024-01-01',
            end_date='2026-01-02',  # More than 730 days
        ))
        self.assertTrue(any('Error' in r for r in result))

    @patch('mes_dashboard.services.filter_cache.get_workcenter_mapping')
    @patch('mes_dashboard.services.resource_history_service._get_filtered_resources')
    @patch('mes_dashboard.services.resource_history_service.read_sql_df')
    def test_successful_export(self, mock_read_sql, mock_get_filtered_resources, mock_wc_mapping):
        """Successful export should yield CSV rows."""
        mock_get_filtered_resources.return_value = [{
            'RESOURCEID': 'RES01',
            'WORKCENTERNAME': 'WC01',
            'RESOURCEFAMILYNAME': 'FAM01',
            'RESOURCENAME': 'RES01',
        }]
        mock_wc_mapping.return_value = {'WC01': {'group': 'WC01', 'sequence': 1}}

        mock_read_sql.return_value = pd.DataFrame([{
            'HISTORYID': 'RES01',
            'PRD_HOURS': 80, 'SBY_HOURS': 10, 'UDT_HOURS': 5,
            'SDT_HOURS': 3, 'EGT_HOURS': 2, 'NST_HOURS': 10,
            'TOTAL_HOURS': 110
        }])

        result = list(export_csv(
            start_date='2024-01-01',
            end_date='2024-01-07',
        ))

        # Should have header row + data row
        self.assertGreaterEqual(len(result), 2)
        # Header should contain column names
        self.assertIn('站點', result[0])
        self.assertIn('OU%', result[0])


if __name__ == '__main__':
    unittest.main()
