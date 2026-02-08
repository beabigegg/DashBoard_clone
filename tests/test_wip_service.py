# -*- coding: utf-8 -*-
"""Unit tests for WIP service layer.

Tests the WIP query functions that use DW_MES_LOT_V view.
"""

import unittest
from unittest.mock import patch, MagicMock
from functools import wraps
import pandas as pd

from mes_dashboard.services.wip_service import (
    WIP_VIEW,
    get_wip_summary,
    get_wip_matrix,
    get_wip_hold_summary,
    get_wip_detail,
    get_workcenters,
    get_packages,
    search_workorders,
    search_lot_ids,
)


def disable_cache(func):
    """Decorator to disable Redis cache for Oracle fallback tests."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        with patch('mes_dashboard.services.wip_service.get_cached_wip_data', return_value=None):
            with patch('mes_dashboard.services.wip_service.get_cached_sys_date', return_value=None):
                return func(*args, **kwargs)
    return wrapper


class TestWipServiceConfig(unittest.TestCase):
    """Test WIP service configuration."""

    def test_wip_view_configured(self):
        """WIP_VIEW should be configured correctly."""
        self.assertEqual(WIP_VIEW, "DWH.DW_MES_LOT_V")


class TestGetWipSummary(unittest.TestCase):
    """Test get_wip_summary function."""

    @disable_cache
    @patch('mes_dashboard.services.wip_service.read_sql_df')
    def test_returns_none_on_empty_result(self, mock_read_sql):
        """Should return None when query returns empty DataFrame."""
        mock_read_sql.return_value = pd.DataFrame()

        result = get_wip_summary()

        self.assertIsNone(result)

    @disable_cache
    @patch('mes_dashboard.services.wip_service.read_sql_df')
    def test_returns_none_on_exception(self, mock_read_sql):
        """Should return None when query raises exception."""
        mock_read_sql.side_effect = Exception("Database error")

        result = get_wip_summary()

        self.assertIsNone(result)



class TestGetWipMatrix(unittest.TestCase):
    """Test get_wip_matrix function."""

    @disable_cache
    @patch('mes_dashboard.services.wip_service.read_sql_df')
    def test_returns_matrix_structure(self, mock_read_sql):
        """Should return dict with matrix structure."""
        mock_df = pd.DataFrame({
            'WORKCENTER_GROUP': ['切割', '切割', '焊接_DB'],
            'WORKCENTERSEQUENCE_GROUP': [1, 1, 2],
            'PACKAGE_LEF': ['SOT-23', 'SOD-323', 'SOT-23'],
            'QTY': [50000000, 30000000, 40000000]
        })
        mock_read_sql.return_value = mock_df

        result = get_wip_matrix()

        self.assertIsNotNone(result)
        self.assertIn('workcenters', result)
        self.assertIn('packages', result)
        self.assertIn('matrix', result)
        self.assertIn('workcenter_totals', result)
        self.assertIn('package_totals', result)
        self.assertIn('grand_total', result)

    @disable_cache
    @patch('mes_dashboard.services.wip_service.read_sql_df')
    def test_workcenters_sorted_by_sequence(self, mock_read_sql):
        """Workcenters should be sorted by WORKCENTERSEQUENCE_GROUP."""
        mock_df = pd.DataFrame({
            'WORKCENTER_GROUP': ['焊接_DB', '切割'],
            'WORKCENTERSEQUENCE_GROUP': [2, 1],
            'PACKAGE_LEF': ['SOT-23', 'SOT-23'],
            'QTY': [40000000, 50000000]
        })
        mock_read_sql.return_value = mock_df

        result = get_wip_matrix()

        self.assertEqual(result['workcenters'], ['切割', '焊接_DB'])

    @disable_cache
    @patch('mes_dashboard.services.wip_service.read_sql_df')
    def test_packages_sorted_by_qty_desc(self, mock_read_sql):
        """Packages should be sorted by total QTY descending."""
        mock_df = pd.DataFrame({
            'WORKCENTER_GROUP': ['切割', '切割'],
            'WORKCENTERSEQUENCE_GROUP': [1, 1],
            'PACKAGE_LEF': ['SOD-323', 'SOT-23'],
            'QTY': [30000000, 50000000]
        })
        mock_read_sql.return_value = mock_df

        result = get_wip_matrix()

        self.assertEqual(result['packages'][0], 'SOT-23')  # Higher QTY first

    @disable_cache
    @patch('mes_dashboard.services.wip_service.read_sql_df')
    def test_returns_empty_structure_on_empty_result(self, mock_read_sql):
        """Should return empty structure when no data."""
        mock_read_sql.return_value = pd.DataFrame()

        result = get_wip_matrix()

        self.assertIsNotNone(result)
        self.assertEqual(result['workcenters'], [])
        self.assertEqual(result['packages'], [])
        self.assertEqual(result['grand_total'], 0)

    @disable_cache
    @patch('mes_dashboard.services.wip_service.read_sql_df')
    def test_calculates_totals_correctly(self, mock_read_sql):
        """Should calculate workcenter and package totals correctly."""
        mock_df = pd.DataFrame({
            'WORKCENTER_GROUP': ['切割', '切割'],
            'WORKCENTERSEQUENCE_GROUP': [1, 1],
            'PACKAGE_LEF': ['SOT-23', 'SOD-323'],
            'QTY': [50000000, 30000000]
        })
        mock_read_sql.return_value = mock_df

        result = get_wip_matrix()

        self.assertEqual(result['workcenter_totals']['切割'], 80000000)
        self.assertEqual(result['package_totals']['SOT-23'], 50000000)
        self.assertEqual(result['grand_total'], 80000000)


class TestGetWipHoldSummary(unittest.TestCase):
    """Test get_wip_hold_summary function."""

    @disable_cache
    @patch('mes_dashboard.services.wip_service.read_sql_df')
    def test_returns_hold_items(self, mock_read_sql):
        """Should return list of hold items."""
        mock_df = pd.DataFrame({
            'REASON': ['YieldLimit', '特殊需求管控'],
            'LOTS': [21, 44],
            'QTY': [1084443, 4235060]
        })
        mock_read_sql.return_value = mock_df

        result = get_wip_hold_summary()

        self.assertIsNotNone(result)
        self.assertIn('items', result)
        self.assertEqual(len(result['items']), 2)
        self.assertEqual(result['items'][0]['reason'], 'YieldLimit')
        self.assertEqual(result['items'][0]['lots'], 21)

    @disable_cache
    @patch('mes_dashboard.services.wip_service.read_sql_df')
    def test_returns_empty_items_on_no_holds(self, mock_read_sql):
        """Should return empty items list when no holds."""
        mock_read_sql.return_value = pd.DataFrame()

        result = get_wip_hold_summary()

        self.assertIsNotNone(result)
        self.assertEqual(result['items'], [])


class TestGetWipDetail(unittest.TestCase):
    """Test get_wip_detail function."""

    @disable_cache
    @patch('mes_dashboard.services.wip_service.read_sql_df')
    def test_returns_none_on_empty_summary(self, mock_read_sql):
        """Should return None when summary query returns empty."""
        mock_read_sql.return_value = pd.DataFrame()

        result = get_wip_detail('不存在的工站')

        self.assertIsNone(result)


class TestGetWorkcenters(unittest.TestCase):
    """Test get_workcenters function."""

    @disable_cache
    @patch('mes_dashboard.services.wip_service.read_sql_df')
    def test_returns_workcenter_list(self, mock_read_sql):
        """Should return list of workcenters with lot counts."""
        mock_df = pd.DataFrame({
            'WORKCENTER_GROUP': ['切割', '焊接_DB'],
            'WORKCENTERSEQUENCE_GROUP': [1, 2],
            'LOT_COUNT': [1377, 859]
        })
        mock_read_sql.return_value = mock_df

        result = get_workcenters()

        self.assertIsNotNone(result)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['name'], '切割')
        self.assertEqual(result[0]['lot_count'], 1377)

    @disable_cache
    @patch('mes_dashboard.services.wip_service.read_sql_df')
    def test_returns_empty_list_on_no_data(self, mock_read_sql):
        """Should return empty list when no workcenters."""
        mock_read_sql.return_value = pd.DataFrame()

        result = get_workcenters()

        self.assertEqual(result, [])

    @disable_cache
    @patch('mes_dashboard.services.wip_service.read_sql_df')
    def test_returns_none_on_exception(self, mock_read_sql):
        """Should return None on exception."""
        mock_read_sql.side_effect = Exception("Database error")

        result = get_workcenters()

        self.assertIsNone(result)


class TestGetPackages(unittest.TestCase):
    """Test get_packages function."""

    @disable_cache
    @patch('mes_dashboard.services.wip_service.read_sql_df')
    def test_returns_package_list(self, mock_read_sql):
        """Should return list of packages with lot counts."""
        mock_df = pd.DataFrame({
            'PACKAGE_LEF': ['SOT-23', 'SOD-323'],
            'LOT_COUNT': [2234, 1392]
        })
        mock_read_sql.return_value = mock_df

        result = get_packages()

        self.assertIsNotNone(result)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['name'], 'SOT-23')
        self.assertEqual(result[0]['lot_count'], 2234)

    @disable_cache
    @patch('mes_dashboard.services.wip_service.read_sql_df')
    def test_returns_empty_list_on_no_data(self, mock_read_sql):
        """Should return empty list when no packages."""
        mock_read_sql.return_value = pd.DataFrame()

        result = get_packages()

        self.assertEqual(result, [])


class TestSearchWorkorders(unittest.TestCase):
    """Test search_workorders function."""

    @disable_cache
    @patch('mes_dashboard.services.wip_service.read_sql_df')
    def test_returns_matching_workorders(self, mock_read_sql):
        """Should return list of matching WORKORDER values."""
        mock_df = pd.DataFrame({
            'WORKORDER': ['GA26012001', 'GA26012002', 'GA26012003']
        })
        mock_read_sql.return_value = mock_df

        result = search_workorders('GA26')

        self.assertIsNotNone(result)
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0], 'GA26012001')

    @disable_cache
    @patch('mes_dashboard.services.wip_service.read_sql_df')
    def test_returns_empty_list_for_short_query(self, mock_read_sql):
        """Should return empty list for query < 2 characters."""
        result = search_workorders('G')

        self.assertEqual(result, [])
        mock_read_sql.assert_not_called()

    @disable_cache
    @patch('mes_dashboard.services.wip_service.read_sql_df')
    def test_returns_empty_list_for_empty_query(self, mock_read_sql):
        """Should return empty list for empty query."""
        result = search_workorders('')

        self.assertEqual(result, [])
        mock_read_sql.assert_not_called()

    @disable_cache
    @patch('mes_dashboard.services.wip_service.read_sql_df')
    def test_returns_empty_list_on_no_matches(self, mock_read_sql):
        """Should return empty list when no matches found."""
        mock_read_sql.return_value = pd.DataFrame()

        result = search_workorders('NONEXISTENT')

        self.assertEqual(result, [])

    @disable_cache
    @patch('mes_dashboard.services.wip_service.read_sql_df')
    def test_respects_limit_parameter(self, mock_read_sql):
        """Should respect the limit parameter."""
        mock_df = pd.DataFrame({
            'WORKORDER': ['GA26012001', 'GA26012002']
        })
        mock_read_sql.return_value = mock_df

        result = search_workorders('GA26', limit=2)

        self.assertEqual(len(result), 2)

    @disable_cache
    @patch('mes_dashboard.services.wip_service.read_sql_df')
    def test_caps_limit_at_50(self, mock_read_sql):
        """Should cap limit at 50."""
        mock_df = pd.DataFrame({'WORKORDER': ['GA26012001']})
        mock_read_sql.return_value = mock_df

        search_workorders('GA26', limit=100)

        # Verify params contain row_limit=50 (capped from 100)
        call_args = mock_read_sql.call_args
        params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get('params', {})
        self.assertEqual(params.get('row_limit'), 50)

    @disable_cache
    @patch('mes_dashboard.services.wip_service.read_sql_df')
    def test_returns_none_on_exception(self, mock_read_sql):
        """Should return None on exception."""
        mock_read_sql.side_effect = Exception("Database error")

        result = search_workorders('GA26')

        self.assertIsNone(result)

    @disable_cache
    @patch('mes_dashboard.services.wip_service.read_sql_df')
    def test_excludes_dummy_by_default(self, mock_read_sql):
        """Should exclude DUMMY lots by default."""
        mock_df = pd.DataFrame({'WORKORDER': []})
        mock_read_sql.return_value = mock_df

        search_workorders('GA26')

        call_args = mock_read_sql.call_args[0][0]
        self.assertIn("LOTID NOT LIKE '%DUMMY%'", call_args)

    @disable_cache
    @patch('mes_dashboard.services.wip_service.read_sql_df')
    def test_includes_dummy_when_specified(self, mock_read_sql):
        """Should include DUMMY lots when include_dummy=True."""
        mock_df = pd.DataFrame({'WORKORDER': []})
        mock_read_sql.return_value = mock_df

        search_workorders('GA26', include_dummy=True)

        call_args = mock_read_sql.call_args[0][0]
        self.assertNotIn("LOTID NOT LIKE '%DUMMY%'", call_args)


class TestSearchLotIds(unittest.TestCase):
    """Test search_lot_ids function."""

    @disable_cache
    @patch('mes_dashboard.services.wip_service.read_sql_df')
    def test_returns_matching_lotids(self, mock_read_sql):
        """Should return list of matching LOTID values."""
        mock_df = pd.DataFrame({
            'LOTID': ['GA26012345-A00-001', 'GA26012345-A00-002']
        })
        mock_read_sql.return_value = mock_df

        result = search_lot_ids('GA26012345')

        self.assertIsNotNone(result)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0], 'GA26012345-A00-001')

    @disable_cache
    @patch('mes_dashboard.services.wip_service.read_sql_df')
    def test_returns_empty_list_for_short_query(self, mock_read_sql):
        """Should return empty list for query < 2 characters."""
        result = search_lot_ids('G')

        self.assertEqual(result, [])
        mock_read_sql.assert_not_called()

    @disable_cache
    @patch('mes_dashboard.services.wip_service.read_sql_df')
    def test_returns_empty_list_on_no_matches(self, mock_read_sql):
        """Should return empty list when no matches found."""
        mock_read_sql.return_value = pd.DataFrame()

        result = search_lot_ids('NONEXISTENT')

        self.assertEqual(result, [])

    @disable_cache
    @patch('mes_dashboard.services.wip_service.read_sql_df')
    def test_returns_none_on_exception(self, mock_read_sql):
        """Should return None on exception."""
        mock_read_sql.side_effect = Exception("Database error")

        result = search_lot_ids('GA26')

        self.assertIsNone(result)

    @disable_cache
    @patch('mes_dashboard.services.wip_service.read_sql_df')
    def test_excludes_dummy_by_default(self, mock_read_sql):
        """Should exclude DUMMY lots by default."""
        mock_df = pd.DataFrame({'LOTID': []})
        mock_read_sql.return_value = mock_df

        search_lot_ids('GA26')

        call_args = mock_read_sql.call_args[0][0]
        self.assertIn("LOTID NOT LIKE '%DUMMY%'", call_args)


class TestWipSearchIndexShortcut(unittest.TestCase):
    """Test derived search index fast-path behavior."""

    @patch('mes_dashboard.services.wip_service._search_workorders_from_oracle')
    @patch('mes_dashboard.services.wip_service._get_wip_search_index')
    def test_workorder_search_uses_index_without_cross_filters(self, mock_index, mock_oracle):
        mock_index.return_value = {
            "workorders": ["GA26012001", "GA26012002", "GB00000001"]
        }

        result = search_workorders("GA26", limit=10)

        self.assertEqual(result, ["GA26012001", "GA26012002"])
        mock_oracle.assert_not_called()

    @patch('mes_dashboard.services.wip_service._search_workorders_from_oracle')
    @patch('mes_dashboard.services.wip_service._get_wip_search_index')
    def test_workorder_search_with_cross_filters_falls_back(self, mock_index, mock_oracle):
        mock_index.return_value = {
            "workorders": ["GA26012001", "GA26012002"]
        }
        mock_oracle.return_value = ["GA26012001"]

        result = search_workorders("GA26", package="SOT-23")

        self.assertEqual(result, ["GA26012001"])
        mock_oracle.assert_called_once()


class TestDummyExclusionInAllFunctions(unittest.TestCase):
    """Test DUMMY exclusion is applied in all WIP functions."""

    @disable_cache
    @patch('mes_dashboard.services.wip_service.read_sql_df')
    def test_get_wip_summary_excludes_dummy_by_default(self, mock_read_sql):
        """get_wip_summary should exclude DUMMY by default."""
        mock_df = pd.DataFrame({
            'TOTAL_LOTS': [100],
            'TOTAL_QTY_PCS': [1000],
            'RUN_LOTS': [80],
            'RUN_QTY_PCS': [800],
            'QUEUE_LOTS': [10],
            'QUEUE_QTY_PCS': [100],
            'HOLD_LOTS': [10],
            'HOLD_QTY_PCS': [100],
            'DATA_UPDATE_DATE': ['2026-01-26']
        })
        mock_read_sql.return_value = mock_df

        get_wip_summary()

        call_args = mock_read_sql.call_args[0][0]
        self.assertIn("LOTID NOT LIKE '%DUMMY%'", call_args)

    @disable_cache
    @patch('mes_dashboard.services.wip_service.read_sql_df')
    def test_get_wip_summary_includes_dummy_when_specified(self, mock_read_sql):
        """get_wip_summary should include DUMMY when specified."""
        mock_df = pd.DataFrame({
            'TOTAL_LOTS': [100],
            'TOTAL_QTY_PCS': [1000],
            'RUN_LOTS': [80],
            'RUN_QTY_PCS': [800],
            'QUEUE_LOTS': [10],
            'QUEUE_QTY_PCS': [100],
            'HOLD_LOTS': [10],
            'HOLD_QTY_PCS': [100],
            'DATA_UPDATE_DATE': ['2026-01-26']
        })
        mock_read_sql.return_value = mock_df

        get_wip_summary(include_dummy=True)

        call_args = mock_read_sql.call_args[0][0]
        self.assertNotIn("LOTID NOT LIKE '%DUMMY%'", call_args)

    @disable_cache
    @patch('mes_dashboard.services.wip_service.read_sql_df')
    def test_get_wip_matrix_excludes_dummy_by_default(self, mock_read_sql):
        """get_wip_matrix should exclude DUMMY by default."""
        mock_df = pd.DataFrame({
            'WORKCENTER_GROUP': ['切割'],
            'WORKCENTERSEQUENCE_GROUP': [1],
            'PACKAGE_LEF': ['SOT-23'],
            'QTY': [1000]
        })
        mock_read_sql.return_value = mock_df

        get_wip_matrix()

        call_args = mock_read_sql.call_args[0][0]
        self.assertIn("LOTID NOT LIKE '%DUMMY%'", call_args)

    @disable_cache
    @patch('mes_dashboard.services.wip_service.read_sql_df')
    def test_get_wip_hold_summary_excludes_dummy_by_default(self, mock_read_sql):
        """get_wip_hold_summary should exclude DUMMY by default."""
        mock_df = pd.DataFrame({
            'REASON': ['YieldLimit'], 'LOTS': [10], 'QTY': [1000]
        })
        mock_read_sql.return_value = mock_df

        get_wip_hold_summary()

        call_args = mock_read_sql.call_args[0][0]
        self.assertIn("LOTID NOT LIKE '%DUMMY%'", call_args)

    @disable_cache
    @patch('mes_dashboard.services.wip_service.read_sql_df')
    def test_get_workcenters_excludes_dummy_by_default(self, mock_read_sql):
        """get_workcenters should exclude DUMMY by default."""
        mock_df = pd.DataFrame({
            'WORKCENTER_GROUP': ['切割'],
            'WORKCENTERSEQUENCE_GROUP': [1],
            'LOT_COUNT': [100]
        })
        mock_read_sql.return_value = mock_df

        get_workcenters()

        call_args = mock_read_sql.call_args[0][0]
        self.assertIn("LOTID NOT LIKE '%DUMMY%'", call_args)

    @disable_cache
    @patch('mes_dashboard.services.wip_service.read_sql_df')
    def test_get_packages_excludes_dummy_by_default(self, mock_read_sql):
        """get_packages should exclude DUMMY by default."""
        mock_df = pd.DataFrame({
            'PACKAGE_LEF': ['SOT-23'], 'LOT_COUNT': [100]
        })
        mock_read_sql.return_value = mock_df

        get_packages()

        call_args = mock_read_sql.call_args[0][0]
        self.assertIn("LOTID NOT LIKE '%DUMMY%'", call_args)


class TestMultipleFilterConditions(unittest.TestCase):
    """Test multiple filter conditions work together."""

    @disable_cache
    @patch('mes_dashboard.services.wip_service.read_sql_df')
    def test_get_wip_summary_with_all_filters(self, mock_read_sql):
        """get_wip_summary should combine all filter conditions via parameterized queries."""
        mock_df = pd.DataFrame({
            'TOTAL_LOTS': [50],
            'TOTAL_QTY_PCS': [500],
            'RUN_LOTS': [40],
            'RUN_QTY_PCS': [400],
            'QUEUE_LOTS': [5],
            'QUEUE_QTY_PCS': [50],
            'HOLD_LOTS': [5],
            'HOLD_QTY_PCS': [50],
            'QUALITY_HOLD_LOTS': [3],
            'QUALITY_HOLD_QTY_PCS': [30],
            'NON_QUALITY_HOLD_LOTS': [2],
            'NON_QUALITY_HOLD_QTY_PCS': [20],
            'DATA_UPDATE_DATE': ['2026-01-26']
        })
        mock_read_sql.return_value = mock_df

        get_wip_summary(workorder='GA26', lotid='A00')

        # Check SQL contains parameterized LIKE conditions
        call_args = mock_read_sql.call_args
        sql = call_args[0][0]
        params = call_args[0][1] if len(call_args[0]) > 1 else {}

        self.assertIn("WORKORDER LIKE", sql)
        self.assertIn("LOTID LIKE", sql)
        self.assertIn("LOTID NOT LIKE '%DUMMY%'", sql)
        # Verify params contain the search patterns
        self.assertTrue(any('%GA26%' in str(v) for v in params.values()))
        self.assertTrue(any('%A00%' in str(v) for v in params.values()))

    @disable_cache
    @patch('mes_dashboard.services.wip_service.read_sql_df')
    def test_get_wip_matrix_with_all_filters(self, mock_read_sql):
        """get_wip_matrix should combine all filter conditions via parameterized queries."""
        mock_df = pd.DataFrame({
            'WORKCENTER_GROUP': ['切割'],
            'WORKCENTERSEQUENCE_GROUP': [1],
            'PACKAGE_LEF': ['SOT-23'],
            'QTY': [500]
        })
        mock_read_sql.return_value = mock_df

        get_wip_matrix(workorder='GA26', lotid='A00', include_dummy=True)

        # Check SQL contains parameterized LIKE conditions
        call_args = mock_read_sql.call_args
        sql = call_args[0][0]
        params = call_args[0][1] if len(call_args[0]) > 1 else {}

        self.assertIn("WORKORDER LIKE", sql)
        self.assertIn("LOTID LIKE", sql)
        # Should NOT contain DUMMY exclusion since include_dummy=True
        self.assertNotIn("LOTID NOT LIKE '%DUMMY%'", sql)
        # Verify params contain the search patterns
        self.assertTrue(any('%GA26%' in str(v) for v in params.values()))
        self.assertTrue(any('%A00%' in str(v) for v in params.values()))



import pytest


class TestWipServiceIntegration:
    """Integration tests that hit the actual database.

    These tests are skipped by default. Run with:
        python -m pytest tests/test_wip_service.py -k Integration --run-integration
    """

    @pytest.mark.integration
    def test_get_wip_summary_integration(self):
        """Integration test for get_wip_summary."""
        result = get_wip_summary()
        assert result is not None
        assert result['totalLots'] > 0
        assert 'dataUpdateDate' in result

    @pytest.mark.integration
    def test_get_wip_matrix_integration(self):
        """Integration test for get_wip_matrix."""
        result = get_wip_matrix()
        assert result is not None
        assert len(result['workcenters']) > 0
        assert result['grand_total'] > 0

    @pytest.mark.integration
    def test_get_wip_hold_summary_integration(self):
        """Integration test for get_wip_hold_summary."""
        result = get_wip_hold_summary()
        assert result is not None
        assert 'items' in result

    @pytest.mark.integration
    def test_get_wip_detail_integration(self):
        """Integration test for get_wip_detail."""
        # First get a valid workcenter
        workcenters = get_workcenters()
        assert workcenters is not None and len(workcenters) > 0

        wc_name = workcenters[0]['name']
        result = get_wip_detail(wc_name, page=1, page_size=10)

        assert result is not None
        assert result['workcenter'] == wc_name
        assert 'summary' in result
        assert 'lots' in result
        assert 'pagination' in result

    @pytest.mark.integration
    def test_get_workcenters_integration(self):
        """Integration test for get_workcenters."""
        result = get_workcenters()
        assert result is not None
        assert len(result) > 0
        assert 'name' in result[0]
        assert 'lot_count' in result[0]

    @pytest.mark.integration
    def test_get_packages_integration(self):
        """Integration test for get_packages."""
        result = get_packages()
        assert result is not None
        assert len(result) > 0
        assert 'name' in result[0]
        assert 'lot_count' in result[0]

    @pytest.mark.integration
    def test_search_workorders_integration(self):
        """Integration test for search_workorders."""
        # Use a common prefix that likely exists
        result = search_workorders('GA')
        assert result is not None
        # Should return a list (possibly empty if no GA* workorders)
        assert isinstance(result, list)

    @pytest.mark.integration
    def test_search_lot_ids_integration(self):
        """Integration test for search_lot_ids."""
        # Use a common prefix that likely exists
        result = search_lot_ids('GA')
        assert result is not None
        assert isinstance(result, list)

    @pytest.mark.integration
    def test_dummy_exclusion_integration(self):
        """Integration test to verify DUMMY exclusion works."""
        # Get summary with and without DUMMY
        result_without_dummy = get_wip_summary(include_dummy=False)
        result_with_dummy = get_wip_summary(include_dummy=True)

        assert result_without_dummy is not None
        assert result_with_dummy is not None

        # If there are DUMMY lots, with_dummy should have more
        # (or equal if no DUMMY lots exist)
        assert result_with_dummy['totalLots'] >= result_without_dummy['totalLots']

    @pytest.mark.integration
    def test_workorder_filter_integration(self):
        """Integration test for workorder filter."""
        # Get all data first
        all_result = get_wip_summary()
        assert all_result is not None

        # Search for a workorder that exists
        workorders = search_workorders('GA', limit=1)
        if workorders and len(workorders) > 0:
            # Filter by that workorder
            filtered_result = get_wip_summary(workorder=workorders[0])
            assert filtered_result is not None
            # Filtered count should be less than or equal to total
            assert filtered_result['totalLots'] <= all_result['totalLots']


if __name__ == "__main__":
    unittest.main()
