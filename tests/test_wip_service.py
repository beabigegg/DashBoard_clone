# -*- coding: utf-8 -*-
"""Unit tests for WIP service layer.

Tests the WIP query functions that use DWH.DW_PJ_LOT_V view.
"""

import unittest
from unittest.mock import patch, MagicMock
import pandas as pd

from mes_dashboard.services.wip_service import (
    WIP_VIEW,
    _escape_sql,
    _build_base_conditions,
    get_wip_summary,
    get_wip_matrix,
    get_wip_hold_summary,
    get_wip_detail,
    get_workcenters,
    get_packages,
    search_workorders,
    search_lot_ids,
)


class TestWipServiceConfig(unittest.TestCase):
    """Test WIP service configuration."""

    def test_wip_view_has_schema_prefix(self):
        """WIP_VIEW should include DWH schema prefix."""
        self.assertEqual(WIP_VIEW, "DWH.DW_PJ_LOT_V")
        self.assertTrue(WIP_VIEW.startswith("DWH."))


class TestEscapeSql(unittest.TestCase):
    """Test _escape_sql function for SQL injection prevention."""

    def test_escapes_single_quotes(self):
        """Should escape single quotes."""
        self.assertEqual(_escape_sql("O'Brien"), "O''Brien")

    def test_escapes_multiple_quotes(self):
        """Should escape multiple single quotes."""
        self.assertEqual(_escape_sql("It's Bob's"), "It''s Bob''s")

    def test_handles_none(self):
        """Should return None for None input."""
        self.assertIsNone(_escape_sql(None))

    def test_no_change_for_safe_string(self):
        """Should not modify strings without quotes."""
        self.assertEqual(_escape_sql("GA26012345"), "GA26012345")


class TestBuildBaseConditions(unittest.TestCase):
    """Test _build_base_conditions function."""

    def test_default_excludes_dummy(self):
        """Default behavior should exclude DUMMY lots."""
        conditions = _build_base_conditions()
        self.assertIn("LOTID NOT LIKE '%DUMMY%'", conditions)

    def test_include_dummy_true(self):
        """include_dummy=True should not add DUMMY exclusion."""
        conditions = _build_base_conditions(include_dummy=True)
        self.assertNotIn("LOTID NOT LIKE '%DUMMY%'", conditions)

    def test_workorder_filter(self):
        """Should add WORKORDER LIKE condition."""
        conditions = _build_base_conditions(workorder='GA26')
        self.assertTrue(any("WORKORDER LIKE '%GA26%'" in c for c in conditions))

    def test_lotid_filter(self):
        """Should add LOTID LIKE condition."""
        conditions = _build_base_conditions(lotid='12345')
        self.assertTrue(any("LOTID LIKE '%12345%'" in c for c in conditions))

    def test_multiple_conditions(self):
        """Should combine multiple conditions."""
        conditions = _build_base_conditions(
            include_dummy=False,
            workorder='GA26',
            lotid='A00'
        )
        # Should have 3 conditions: DUMMY exclusion, workorder, lotid
        self.assertEqual(len(conditions), 3)

    def test_escapes_sql_in_workorder(self):
        """Should escape SQL special characters in workorder."""
        conditions = _build_base_conditions(workorder="test'value")
        # Should have escaped the quote
        self.assertTrue(any("test''value" in c for c in conditions))

    def test_escapes_sql_in_lotid(self):
        """Should escape SQL special characters in lotid."""
        conditions = _build_base_conditions(lotid="lot'id")
        # Should have escaped the quote
        self.assertTrue(any("lot''id" in c for c in conditions))


class TestGetWipSummary(unittest.TestCase):
    """Test get_wip_summary function."""

    @patch('mes_dashboard.services.wip_service.read_sql_df')
    def test_returns_summary_dict_on_success(self, mock_read_sql):
        """Should return dict with summary fields when query succeeds."""
        mock_df = pd.DataFrame({
            'TOTAL_LOTS': [9073],
            'TOTAL_QTY': [858878718],
            'HOLD_LOTS': [120],
            'HOLD_QTY': [8213395],
            'SYS_DATE': ['2026-01-26 19:18:29']
        })
        mock_read_sql.return_value = mock_df

        result = get_wip_summary()

        self.assertIsNotNone(result)
        self.assertEqual(result['total_lots'], 9073)
        self.assertEqual(result['total_qty'], 858878718)
        self.assertEqual(result['hold_lots'], 120)
        self.assertEqual(result['hold_qty'], 8213395)
        self.assertIn('sys_date', result)

    @patch('mes_dashboard.services.wip_service.read_sql_df')
    def test_returns_none_on_empty_result(self, mock_read_sql):
        """Should return None when query returns empty DataFrame."""
        mock_read_sql.return_value = pd.DataFrame()

        result = get_wip_summary()

        self.assertIsNone(result)

    @patch('mes_dashboard.services.wip_service.read_sql_df')
    def test_returns_none_on_exception(self, mock_read_sql):
        """Should return None when query raises exception."""
        mock_read_sql.side_effect = Exception("Database error")

        result = get_wip_summary()

        self.assertIsNone(result)

    @patch('mes_dashboard.services.wip_service.read_sql_df')
    def test_handles_null_values(self, mock_read_sql):
        """Should handle NULL values gracefully."""
        mock_df = pd.DataFrame({
            'TOTAL_LOTS': [None],
            'TOTAL_QTY': [None],
            'HOLD_LOTS': [None],
            'HOLD_QTY': [None],
            'SYS_DATE': [None]
        })
        mock_read_sql.return_value = mock_df

        result = get_wip_summary()

        self.assertIsNotNone(result)
        self.assertEqual(result['total_lots'], 0)
        self.assertEqual(result['total_qty'], 0)
        self.assertEqual(result['hold_lots'], 0)
        self.assertEqual(result['hold_qty'], 0)


class TestGetWipMatrix(unittest.TestCase):
    """Test get_wip_matrix function."""

    @patch('mes_dashboard.services.wip_service.read_sql_df')
    def test_returns_matrix_structure(self, mock_read_sql):
        """Should return dict with matrix structure."""
        mock_df = pd.DataFrame({
            'WORKCENTER_GROUP': ['切割', '切割', '焊接_DB'],
            'WORKCENTERSEQUENCE_GROUP': [1, 1, 2],
            'PRODUCTLINENAME': ['SOT-23', 'SOD-323', 'SOT-23'],
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

    @patch('mes_dashboard.services.wip_service.read_sql_df')
    def test_workcenters_sorted_by_sequence(self, mock_read_sql):
        """Workcenters should be sorted by WORKCENTERSEQUENCE_GROUP."""
        mock_df = pd.DataFrame({
            'WORKCENTER_GROUP': ['焊接_DB', '切割'],
            'WORKCENTERSEQUENCE_GROUP': [2, 1],
            'PRODUCTLINENAME': ['SOT-23', 'SOT-23'],
            'QTY': [40000000, 50000000]
        })
        mock_read_sql.return_value = mock_df

        result = get_wip_matrix()

        self.assertEqual(result['workcenters'], ['切割', '焊接_DB'])

    @patch('mes_dashboard.services.wip_service.read_sql_df')
    def test_packages_sorted_by_qty_desc(self, mock_read_sql):
        """Packages should be sorted by total QTY descending."""
        mock_df = pd.DataFrame({
            'WORKCENTER_GROUP': ['切割', '切割'],
            'WORKCENTERSEQUENCE_GROUP': [1, 1],
            'PRODUCTLINENAME': ['SOD-323', 'SOT-23'],
            'QTY': [30000000, 50000000]
        })
        mock_read_sql.return_value = mock_df

        result = get_wip_matrix()

        self.assertEqual(result['packages'][0], 'SOT-23')  # Higher QTY first

    @patch('mes_dashboard.services.wip_service.read_sql_df')
    def test_returns_empty_structure_on_empty_result(self, mock_read_sql):
        """Should return empty structure when no data."""
        mock_read_sql.return_value = pd.DataFrame()

        result = get_wip_matrix()

        self.assertIsNotNone(result)
        self.assertEqual(result['workcenters'], [])
        self.assertEqual(result['packages'], [])
        self.assertEqual(result['grand_total'], 0)

    @patch('mes_dashboard.services.wip_service.read_sql_df')
    def test_calculates_totals_correctly(self, mock_read_sql):
        """Should calculate workcenter and package totals correctly."""
        mock_df = pd.DataFrame({
            'WORKCENTER_GROUP': ['切割', '切割'],
            'WORKCENTERSEQUENCE_GROUP': [1, 1],
            'PRODUCTLINENAME': ['SOT-23', 'SOD-323'],
            'QTY': [50000000, 30000000]
        })
        mock_read_sql.return_value = mock_df

        result = get_wip_matrix()

        self.assertEqual(result['workcenter_totals']['切割'], 80000000)
        self.assertEqual(result['package_totals']['SOT-23'], 50000000)
        self.assertEqual(result['grand_total'], 80000000)


class TestGetWipHoldSummary(unittest.TestCase):
    """Test get_wip_hold_summary function."""

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

    @patch('mes_dashboard.services.wip_service.read_sql_df')
    def test_returns_empty_items_on_no_holds(self, mock_read_sql):
        """Should return empty items list when no holds."""
        mock_read_sql.return_value = pd.DataFrame()

        result = get_wip_hold_summary()

        self.assertIsNotNone(result)
        self.assertEqual(result['items'], [])


class TestGetWipDetail(unittest.TestCase):
    """Test get_wip_detail function."""

    @patch('mes_dashboard.services.wip_service.read_sql_df')
    def test_returns_detail_structure(self, mock_read_sql):
        """Should return dict with detail structure."""
        # Mock for summary query
        summary_df = pd.DataFrame({
            'TOTAL_LOTS': [859],
            'ON_EQUIPMENT_LOTS': [312],
            'WAITING_LOTS': [547],
            'HOLD_LOTS': [15],
            'SYS_DATE': ['2026-01-26 19:18:29']
        })
        # Mock for specs query
        specs_df = pd.DataFrame({
            'SPECNAME': ['Spec1', 'Spec2'],
            'SPECSEQUENCE': [1, 2]
        })
        # Mock for lots query
        lots_df = pd.DataFrame({
            'LOTID': ['GA25102485-A00-004'],
            'EQUIPMENTNAME': ['GSMP-0054'],
            'STATUS': ['ACTIVE'],
            'HOLDREASONNAME': [None],
            'QTY': [750],
            'PRODUCTLINENAME': ['SOT-23'],
            'SPECNAME': ['Spec1']
        })

        mock_read_sql.side_effect = [summary_df, specs_df, lots_df]

        result = get_wip_detail('焊接_DB')

        self.assertIsNotNone(result)
        self.assertEqual(result['workcenter'], '焊接_DB')
        self.assertIn('summary', result)
        self.assertIn('specs', result)
        self.assertIn('lots', result)
        self.assertIn('pagination', result)
        self.assertIn('sys_date', result)

    @patch('mes_dashboard.services.wip_service.read_sql_df')
    def test_summary_contains_required_fields(self, mock_read_sql):
        """Summary should contain total/on_equipment/waiting/hold lots."""
        summary_df = pd.DataFrame({
            'TOTAL_LOTS': [100],
            'ON_EQUIPMENT_LOTS': [60],
            'WAITING_LOTS': [40],
            'HOLD_LOTS': [5],
            'SYS_DATE': ['2026-01-26']
        })
        specs_df = pd.DataFrame({'SPECNAME': [], 'SPECSEQUENCE': []})
        lots_df = pd.DataFrame()

        mock_read_sql.side_effect = [summary_df, specs_df, lots_df]

        result = get_wip_detail('切割')

        self.assertEqual(result['summary']['total_lots'], 100)
        self.assertEqual(result['summary']['on_equipment_lots'], 60)
        self.assertEqual(result['summary']['waiting_lots'], 40)
        self.assertEqual(result['summary']['hold_lots'], 5)

    @patch('mes_dashboard.services.wip_service.read_sql_df')
    def test_pagination_calculated_correctly(self, mock_read_sql):
        """Pagination should be calculated correctly."""
        summary_df = pd.DataFrame({
            'TOTAL_LOTS': [250],
            'ON_EQUIPMENT_LOTS': [100],
            'WAITING_LOTS': [150],
            'HOLD_LOTS': [0],
            'SYS_DATE': ['2026-01-26']
        })
        specs_df = pd.DataFrame({'SPECNAME': [], 'SPECSEQUENCE': []})
        lots_df = pd.DataFrame()

        mock_read_sql.side_effect = [summary_df, specs_df, lots_df]

        result = get_wip_detail('切割', page=2, page_size=100)

        self.assertEqual(result['pagination']['page'], 2)
        self.assertEqual(result['pagination']['page_size'], 100)
        self.assertEqual(result['pagination']['total_count'], 250)
        self.assertEqual(result['pagination']['total_pages'], 3)

    @patch('mes_dashboard.services.wip_service.read_sql_df')
    def test_returns_none_on_empty_summary(self, mock_read_sql):
        """Should return None when summary query returns empty."""
        mock_read_sql.return_value = pd.DataFrame()

        result = get_wip_detail('不存在的工站')

        self.assertIsNone(result)


class TestGetWorkcenters(unittest.TestCase):
    """Test get_workcenters function."""

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

    @patch('mes_dashboard.services.wip_service.read_sql_df')
    def test_returns_empty_list_on_no_data(self, mock_read_sql):
        """Should return empty list when no workcenters."""
        mock_read_sql.return_value = pd.DataFrame()

        result = get_workcenters()

        self.assertEqual(result, [])

    @patch('mes_dashboard.services.wip_service.read_sql_df')
    def test_returns_none_on_exception(self, mock_read_sql):
        """Should return None on exception."""
        mock_read_sql.side_effect = Exception("Database error")

        result = get_workcenters()

        self.assertIsNone(result)


class TestGetPackages(unittest.TestCase):
    """Test get_packages function."""

    @patch('mes_dashboard.services.wip_service.read_sql_df')
    def test_returns_package_list(self, mock_read_sql):
        """Should return list of packages with lot counts."""
        mock_df = pd.DataFrame({
            'PRODUCTLINENAME': ['SOT-23', 'SOD-323'],
            'LOT_COUNT': [2234, 1392]
        })
        mock_read_sql.return_value = mock_df

        result = get_packages()

        self.assertIsNotNone(result)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['name'], 'SOT-23')
        self.assertEqual(result[0]['lot_count'], 2234)

    @patch('mes_dashboard.services.wip_service.read_sql_df')
    def test_returns_empty_list_on_no_data(self, mock_read_sql):
        """Should return empty list when no packages."""
        mock_read_sql.return_value = pd.DataFrame()

        result = get_packages()

        self.assertEqual(result, [])


class TestSearchWorkorders(unittest.TestCase):
    """Test search_workorders function."""

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

    @patch('mes_dashboard.services.wip_service.read_sql_df')
    def test_returns_empty_list_for_short_query(self, mock_read_sql):
        """Should return empty list for query < 2 characters."""
        result = search_workorders('G')

        self.assertEqual(result, [])
        mock_read_sql.assert_not_called()

    @patch('mes_dashboard.services.wip_service.read_sql_df')
    def test_returns_empty_list_for_empty_query(self, mock_read_sql):
        """Should return empty list for empty query."""
        result = search_workorders('')

        self.assertEqual(result, [])
        mock_read_sql.assert_not_called()

    @patch('mes_dashboard.services.wip_service.read_sql_df')
    def test_returns_empty_list_on_no_matches(self, mock_read_sql):
        """Should return empty list when no matches found."""
        mock_read_sql.return_value = pd.DataFrame()

        result = search_workorders('NONEXISTENT')

        self.assertEqual(result, [])

    @patch('mes_dashboard.services.wip_service.read_sql_df')
    def test_respects_limit_parameter(self, mock_read_sql):
        """Should respect the limit parameter."""
        mock_df = pd.DataFrame({
            'WORKORDER': ['GA26012001', 'GA26012002']
        })
        mock_read_sql.return_value = mock_df

        result = search_workorders('GA26', limit=2)

        self.assertEqual(len(result), 2)

    @patch('mes_dashboard.services.wip_service.read_sql_df')
    def test_caps_limit_at_50(self, mock_read_sql):
        """Should cap limit at 50."""
        mock_df = pd.DataFrame({'WORKORDER': ['GA26012001']})
        mock_read_sql.return_value = mock_df

        search_workorders('GA26', limit=100)

        # Verify SQL contains FETCH FIRST 50
        call_args = mock_read_sql.call_args[0][0]
        self.assertIn('FETCH FIRST 50 ROWS ONLY', call_args)

    @patch('mes_dashboard.services.wip_service.read_sql_df')
    def test_returns_none_on_exception(self, mock_read_sql):
        """Should return None on exception."""
        mock_read_sql.side_effect = Exception("Database error")

        result = search_workorders('GA26')

        self.assertIsNone(result)

    @patch('mes_dashboard.services.wip_service.read_sql_df')
    def test_excludes_dummy_by_default(self, mock_read_sql):
        """Should exclude DUMMY lots by default."""
        mock_df = pd.DataFrame({'WORKORDER': []})
        mock_read_sql.return_value = mock_df

        search_workorders('GA26')

        call_args = mock_read_sql.call_args[0][0]
        self.assertIn("LOTID NOT LIKE '%DUMMY%'", call_args)

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

    @patch('mes_dashboard.services.wip_service.read_sql_df')
    def test_returns_empty_list_for_short_query(self, mock_read_sql):
        """Should return empty list for query < 2 characters."""
        result = search_lot_ids('G')

        self.assertEqual(result, [])
        mock_read_sql.assert_not_called()

    @patch('mes_dashboard.services.wip_service.read_sql_df')
    def test_returns_empty_list_on_no_matches(self, mock_read_sql):
        """Should return empty list when no matches found."""
        mock_read_sql.return_value = pd.DataFrame()

        result = search_lot_ids('NONEXISTENT')

        self.assertEqual(result, [])

    @patch('mes_dashboard.services.wip_service.read_sql_df')
    def test_returns_none_on_exception(self, mock_read_sql):
        """Should return None on exception."""
        mock_read_sql.side_effect = Exception("Database error")

        result = search_lot_ids('GA26')

        self.assertIsNone(result)

    @patch('mes_dashboard.services.wip_service.read_sql_df')
    def test_excludes_dummy_by_default(self, mock_read_sql):
        """Should exclude DUMMY lots by default."""
        mock_df = pd.DataFrame({'LOTID': []})
        mock_read_sql.return_value = mock_df

        search_lot_ids('GA26')

        call_args = mock_read_sql.call_args[0][0]
        self.assertIn("LOTID NOT LIKE '%DUMMY%'", call_args)


class TestDummyExclusionInAllFunctions(unittest.TestCase):
    """Test DUMMY exclusion is applied in all WIP functions."""

    @patch('mes_dashboard.services.wip_service.read_sql_df')
    def test_get_wip_summary_excludes_dummy_by_default(self, mock_read_sql):
        """get_wip_summary should exclude DUMMY by default."""
        mock_df = pd.DataFrame({
            'TOTAL_LOTS': [100], 'TOTAL_QTY': [1000],
            'HOLD_LOTS': [10], 'HOLD_QTY': [100],
            'SYS_DATE': ['2026-01-26']
        })
        mock_read_sql.return_value = mock_df

        get_wip_summary()

        call_args = mock_read_sql.call_args[0][0]
        self.assertIn("LOTID NOT LIKE '%DUMMY%'", call_args)

    @patch('mes_dashboard.services.wip_service.read_sql_df')
    def test_get_wip_summary_includes_dummy_when_specified(self, mock_read_sql):
        """get_wip_summary should include DUMMY when specified."""
        mock_df = pd.DataFrame({
            'TOTAL_LOTS': [100], 'TOTAL_QTY': [1000],
            'HOLD_LOTS': [10], 'HOLD_QTY': [100],
            'SYS_DATE': ['2026-01-26']
        })
        mock_read_sql.return_value = mock_df

        get_wip_summary(include_dummy=True)

        call_args = mock_read_sql.call_args[0][0]
        self.assertNotIn("LOTID NOT LIKE '%DUMMY%'", call_args)

    @patch('mes_dashboard.services.wip_service.read_sql_df')
    def test_get_wip_matrix_excludes_dummy_by_default(self, mock_read_sql):
        """get_wip_matrix should exclude DUMMY by default."""
        mock_df = pd.DataFrame({
            'WORKCENTER_GROUP': ['切割'],
            'WORKCENTERSEQUENCE_GROUP': [1],
            'PRODUCTLINENAME': ['SOT-23'],
            'QTY': [1000]
        })
        mock_read_sql.return_value = mock_df

        get_wip_matrix()

        call_args = mock_read_sql.call_args[0][0]
        self.assertIn("LOTID NOT LIKE '%DUMMY%'", call_args)

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

    @patch('mes_dashboard.services.wip_service.read_sql_df')
    def test_get_packages_excludes_dummy_by_default(self, mock_read_sql):
        """get_packages should exclude DUMMY by default."""
        mock_df = pd.DataFrame({
            'PRODUCTLINENAME': ['SOT-23'], 'LOT_COUNT': [100]
        })
        mock_read_sql.return_value = mock_df

        get_packages()

        call_args = mock_read_sql.call_args[0][0]
        self.assertIn("LOTID NOT LIKE '%DUMMY%'", call_args)


class TestMultipleFilterConditions(unittest.TestCase):
    """Test multiple filter conditions work together."""

    @patch('mes_dashboard.services.wip_service.read_sql_df')
    def test_get_wip_summary_with_all_filters(self, mock_read_sql):
        """get_wip_summary should combine all filter conditions."""
        mock_df = pd.DataFrame({
            'TOTAL_LOTS': [50], 'TOTAL_QTY': [500],
            'HOLD_LOTS': [5], 'HOLD_QTY': [50],
            'SYS_DATE': ['2026-01-26']
        })
        mock_read_sql.return_value = mock_df

        get_wip_summary(workorder='GA26', lotid='A00')

        call_args = mock_read_sql.call_args[0][0]
        self.assertIn("WORKORDER LIKE '%GA26%'", call_args)
        self.assertIn("LOTID LIKE '%A00%'", call_args)
        self.assertIn("LOTID NOT LIKE '%DUMMY%'", call_args)

    @patch('mes_dashboard.services.wip_service.read_sql_df')
    def test_get_wip_matrix_with_all_filters(self, mock_read_sql):
        """get_wip_matrix should combine all filter conditions."""
        mock_df = pd.DataFrame({
            'WORKCENTER_GROUP': ['切割'],
            'WORKCENTERSEQUENCE_GROUP': [1],
            'PRODUCTLINENAME': ['SOT-23'],
            'QTY': [500]
        })
        mock_read_sql.return_value = mock_df

        get_wip_matrix(workorder='GA26', lotid='A00', include_dummy=True)

        call_args = mock_read_sql.call_args[0][0]
        self.assertIn("WORKORDER LIKE '%GA26%'", call_args)
        self.assertIn("LOTID LIKE '%A00%'", call_args)
        # Should NOT contain DUMMY exclusion since include_dummy=True
        self.assertNotIn("LOTID NOT LIKE '%DUMMY%'", call_args)

    @patch('mes_dashboard.services.wip_service.read_sql_df')
    def test_get_wip_detail_with_all_filters(self, mock_read_sql):
        """get_wip_detail should combine all filter conditions."""
        summary_df = pd.DataFrame({
            'TOTAL_LOTS': [10], 'ON_EQUIPMENT_LOTS': [5],
            'WAITING_LOTS': [5], 'HOLD_LOTS': [1],
            'SYS_DATE': ['2026-01-26']
        })
        specs_df = pd.DataFrame({'SPECNAME': [], 'SPECSEQUENCE': []})
        lots_df = pd.DataFrame()

        mock_read_sql.side_effect = [summary_df, specs_df, lots_df]

        get_wip_detail(
            workcenter='切割',
            package='SOT-23',
            status='ACTIVE',
            workorder='GA26',
            lotid='A00'
        )

        # Check the first call (summary query) contains all conditions
        call_args = mock_read_sql.call_args_list[0][0][0]
        self.assertIn("WORKCENTER_GROUP = '切割'", call_args)
        self.assertIn("PRODUCTLINENAME = 'SOT-23'", call_args)
        self.assertIn("STATUS = 'ACTIVE'", call_args)
        self.assertIn("WORKORDER LIKE '%GA26%'", call_args)
        self.assertIn("LOTID LIKE '%A00%'", call_args)
        self.assertIn("LOTID NOT LIKE '%DUMMY%'", call_args)


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
        assert result['total_lots'] > 0
        assert 'sys_date' in result

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
        assert result_with_dummy['total_lots'] >= result_without_dummy['total_lots']

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
            assert filtered_result['total_lots'] <= all_result['total_lots']


if __name__ == "__main__":
    unittest.main()
