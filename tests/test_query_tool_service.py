# -*- coding: utf-8 -*-
"""Unit tests for Query Tool service functions.

Tests the core service functions without database dependencies:
- Input validation (LOT, equipment, date range)
- IN clause building helpers
- Constants validation
"""

import pytest

from mes_dashboard.services.query_tool_service import (
    validate_date_range,
    validate_lot_input,
    validate_equipment_input,
    _resolve_by_lot_id,
    _resolve_by_wafer_lot,
    _resolve_by_serial_number,
    _resolve_by_work_order,
    get_lot_split_merge_history,
    get_equipment_rejects,
    BATCH_SIZE,
    MAX_DATE_RANGE_DAYS,
)


class TestValidateDateRange:
    """Tests for validate_date_range function."""

    def test_valid_range(self):
        """Should return None for valid date range."""
        result = validate_date_range('2024-01-01', '2024-01-31')
        assert result is None

    def test_same_day(self):
        """Should allow same day as start and end."""
        result = validate_date_range('2024-01-01', '2024-01-01')
        assert result is None

    def test_end_before_start(self):
        """Should reject end date before start date."""
        result = validate_date_range('2024-12-31', '2024-01-01')
        assert result is not None
        assert '結束日期' in result or '早於' in result

    def test_exceeds_max_range(self):
        """Should reject date range exceeding 730-day limit."""
        # 2023-01-01 to 2025-02-28 = 789 days > 730
        result = validate_date_range('2023-01-01', '2025-02-28')
        assert result is not None
        assert str(MAX_DATE_RANGE_DAYS) in result

    def test_exactly_max_range(self):
        """Should allow exactly max range days (730)."""
        # 2023-01-01 to 2024-12-31 = 730 days
        result = validate_date_range('2023-01-01', '2024-12-31')
        assert result is None

    def test_one_day_over_max_range(self):
        """Should reject one day over max range."""
        # 731 days
        result = validate_date_range('2023-01-01', '2025-01-01')
        assert result is not None
        assert str(MAX_DATE_RANGE_DAYS) in result

    def test_invalid_date_format(self):
        """Should reject invalid date format."""
        result = validate_date_range('01-01-2024', '12-31-2024')
        assert result is not None
        assert '格式' in result or 'format' in result.lower()

    def test_invalid_start_date(self):
        """Should reject invalid start date."""
        result = validate_date_range('2024-13-01', '2024-12-31')
        assert result is not None
        assert '格式' in result or 'format' in result.lower()

    def test_invalid_end_date(self):
        """Should reject invalid end date."""
        result = validate_date_range('2024-01-01', '2024-02-30')
        assert result is not None
        assert '格式' in result or 'format' in result.lower()

    def test_non_date_string(self):
        """Should reject non-date strings."""
        result = validate_date_range('abc', 'def')
        assert result is not None
        assert '格式' in result or 'format' in result.lower()


class TestValidateLotInput:
    """Tests for validate_lot_input function."""

    def test_valid_lot_ids(self):
        """Should accept valid LOT IDs within limit."""
        values = ['GA23100020-A00-001', 'GA23100020-A00-002']
        result = validate_lot_input('lot_id', values)
        assert result is None

    def test_valid_serial_numbers(self):
        """Should accept valid serial numbers within limit."""
        values = ['SN001', 'SN002', 'SN003']
        result = validate_lot_input('serial_number', values)
        assert result is None

    def test_valid_work_orders(self):
        """Should accept valid work orders within limit."""
        values = ['GA231000001']
        result = validate_lot_input('work_order', values)
        assert result is None

    def test_empty_values(self):
        """Should reject empty values list."""
        result = validate_lot_input('lot_id', [])
        assert result is not None
        assert '至少一個' in result

    def test_large_input_list_allowed_when_no_count_cap(self, monkeypatch):
        """Should allow large lists when count cap is disabled."""
        monkeypatch.setenv("CONTAINER_RESOLVE_INPUT_MAX_VALUES", "0")
        values = [f'GA{i:09d}' for i in range(150)]
        result = validate_lot_input('lot_id', values)
        assert result is None

    def test_rejects_too_broad_wildcard_pattern(self, monkeypatch):
        """Should reject broad wildcard like '%' to prevent full scan."""
        monkeypatch.setenv("CONTAINER_RESOLVE_PATTERN_MIN_PREFIX_LEN", "2")
        result = validate_lot_input('lot_id', ['%'])
        assert result is not None
        assert '萬用字元條件過於寬鬆' in result

    def test_accepts_wildcard_with_prefix(self, monkeypatch):
        monkeypatch.setenv("CONTAINER_RESOLVE_PATTERN_MIN_PREFIX_LEN", "2")
        result = validate_lot_input('lot_id', ['GA25%'])
        assert result is None


class TestValidateEquipmentInput:
    """Tests for validate_equipment_input function."""

    def test_valid_equipment_ids(self):
        """Should accept valid equipment IDs within limit."""
        values = ['EQ001', 'EQ002', 'EQ003']
        result = validate_equipment_input(values)
        assert result is None

    def test_empty_equipment_ids(self):
        """Should reject empty equipment list."""
        result = validate_equipment_input([])
        assert result is not None
        assert '至少一台' in result



class TestResolveQueriesUseBindParams:
    """Queries with user input should always use bind params."""

    def test_resolve_by_lot_id_uses_query_builder_params(self):
        from unittest.mock import patch
        import pandas as pd

        with patch('mes_dashboard.services.query_tool_service.SQLLoader.load_with_params') as mock_load:
            with patch('mes_dashboard.services.query_tool_service.read_sql_df_slow') as mock_read:
                mock_load.return_value = "SELECT * FROM DUAL"
                mock_read.return_value = pd.DataFrame([
                    {
                        'CONTAINERID': 'CID-1',
                        'CONTAINERNAME': 'LOT-1',
                        'SPECNAME': 'SPEC-1',
                        'QTY': 100,
                    }
                ])

                result = _resolve_by_lot_id(['LOT-1'])

                assert result['total'] == 1
                mock_load.assert_called_once()
                sql_params = mock_load.call_args.kwargs
                assert 'CONTAINER_FILTER' in sql_params
                assert ':p0' in sql_params['CONTAINER_FILTER']
                _, query_params = mock_read.call_args.args
                assert query_params == {'p0': 'LOT-1'}

    def test_resolve_by_lot_id_supports_wildcard_pattern(self):
        from unittest.mock import patch
        import pandas as pd

        with patch('mes_dashboard.services.query_tool_service.SQLLoader.load_with_params') as mock_load:
            with patch('mes_dashboard.services.query_tool_service.read_sql_df_slow') as mock_read:
                mock_load.return_value = "SELECT * FROM DUAL"
                mock_read.return_value = pd.DataFrame([
                    {
                        'CONTAINERID': 'CID-1',
                        'CONTAINERNAME': 'GA25123401',
                        'SPECNAME': 'SPEC-1',
                        'QTY': 100,
                    },
                    {
                        'CONTAINERID': 'CID-2',
                        'CONTAINERNAME': 'GA24123401',
                        'SPECNAME': 'SPEC-2',
                        'QTY': 200,
                    },
                ])

                result = _resolve_by_lot_id(['GA25%01'])

                assert result['total'] == 1
                assert result['data'][0]['lot_id'] == 'GA25123401'
                assert result['data'][0]['input_value'] == 'GA25%01'
                sql_params = mock_load.call_args.kwargs
                assert "LIKE" in sql_params['CONTAINER_FILTER']
                _, query_params = mock_read.call_args.args
                assert query_params == {'p0': 'GA25%01'}

    def test_resolve_by_wafer_lot_supports_wildcard_pattern(self):
        from unittest.mock import patch
        import pandas as pd

        with patch('mes_dashboard.services.query_tool_service.SQLLoader.load_with_params') as mock_load:
            with patch('mes_dashboard.services.query_tool_service.read_sql_df_slow') as mock_read:
                mock_load.return_value = "SELECT * FROM DUAL"
                mock_read.return_value = pd.DataFrame([
                    {
                        'CONTAINERID': 'CID-1',
                        'CONTAINERNAME': 'GA25123401-A00-001',
                        'SPECNAME': 'SPEC-1',
                        'QTY': 100,
                        'FIRSTNAME': 'GMSN-1173#A',
                    },
                    {
                        'CONTAINERID': 'CID-2',
                        'CONTAINERNAME': 'GA25123402-A00-001',
                        'SPECNAME': 'SPEC-2',
                        'QTY': 100,
                        'FIRSTNAME': 'GMSN-9999#B',
                    },
                ])

                result = _resolve_by_wafer_lot(['GMSN-1173%'])

                assert result['total'] == 1
                assert result['data'][0]['input_value'] == 'GMSN-1173%'
                sql_params = mock_load.call_args.kwargs
                assert "LIKE" in sql_params['WAFER_FILTER']
                assert "OBJECTTYPE = 'LOT'" in sql_params['WAFER_FILTER']

    def test_resolve_by_serial_number_uses_query_builder_params(self):
        from unittest.mock import patch
        import pandas as pd

        with patch('mes_dashboard.services.query_tool_service.SQLLoader.load_with_params') as mock_load:
            with patch('mes_dashboard.services.query_tool_service.read_sql_df_slow') as mock_read:
                mock_load.side_effect = [
                    "SELECT * FROM COMBINE",
                    "SELECT * FROM CONTAINER_NAME",
                    "SELECT * FROM FIRSTNAME",
                ]
                mock_read.side_effect = [
                    pd.DataFrame([
                        {
                            'CONTAINERID': 'CID-FIN',
                            'FINISHEDNAME': 'SN-1',
                            'CONTAINERNAME': 'LOT-FIN',
                            'SPECNAME': 'SPEC-1',
                        }
                    ]),
                    pd.DataFrame([
                        {
                            'CONTAINERID': 'CID-NAME',
                            'CONTAINERNAME': 'SN-1',
                            'SPECNAME': 'SPEC-2',
                            'MFGORDERNAME': None,
                            'QTY': 1,
                        }
                    ]),
                    pd.DataFrame([
                        {
                            'CONTAINERID': 'CID-FIRST',
                            'CONTAINERNAME': 'GD25000001-A01',
                            'FIRSTNAME': 'SN-1',
                            'SPECNAME': 'SPEC-3',
                            'QTY': 1,
                        }
                    ]),
                ]

                result = _resolve_by_serial_number(['SN-1'])

                assert result['total'] == 3
                assert {row['match_source'] for row in result['data']} == {
                    'finished_name',
                    'container_name',
                    'first_name',
                }

                assert [call.args[0] for call in mock_load.call_args_list] == [
                    'query_tool/lot_resolve_serial',
                    'query_tool/lot_resolve_id',
                    'query_tool/lot_resolve_wafer_lot',
                ]
                assert ':p0' in mock_load.call_args_list[0].kwargs['SERIAL_FILTER']
                assert ':p0' in mock_load.call_args_list[1].kwargs['CONTAINER_FILTER']
                assert ':p0' in mock_load.call_args_list[2].kwargs['WAFER_FILTER']
                assert "OBJECTTYPE = 'LOT'" in mock_load.call_args_list[1].kwargs['CONTAINER_FILTER']
                assert "OBJECTTYPE = 'LOT'" in mock_load.call_args_list[2].kwargs['WAFER_FILTER']

                assert mock_read.call_args_list[0].args[1] == {'p0': 'SN-1'}
                assert mock_read.call_args_list[1].args[1] == {'p0': 'SN-1'}
                assert mock_read.call_args_list[2].args[1] == {'p0': 'SN-1'}

    def test_resolve_by_work_order_uses_query_builder_params(self):
        from unittest.mock import patch
        import pandas as pd

        with patch('mes_dashboard.services.query_tool_service.SQLLoader.load_with_params') as mock_load:
            with patch('mes_dashboard.services.query_tool_service.read_sql_df_slow') as mock_read:
                mock_load.return_value = "SELECT * FROM DUAL"
                mock_read.return_value = pd.DataFrame([
                    {
                        'CONTAINERID': 'CID-1',
                        'MFGORDERNAME': 'WO-1',
                        'CONTAINERNAME': 'LOT-1',
                        'SPECNAME': 'SPEC-1',
                    }
                ])

                result = _resolve_by_work_order(['WO-1'])

                assert result['total'] == 1
                sql_params = mock_load.call_args.kwargs
                assert ':p0' in sql_params['WORK_ORDER_FILTER']
                _, query_params = mock_read.call_args.args
                assert query_params == {'p0': 'WO-1'}

    def test_resolve_by_work_order_supports_wildcard_pattern(self):
        from unittest.mock import patch
        import pandas as pd

        with patch('mes_dashboard.services.query_tool_service.SQLLoader.load_with_params') as mock_load:
            with patch('mes_dashboard.services.query_tool_service.read_sql_df_slow') as mock_read:
                mock_load.return_value = "SELECT * FROM DUAL"
                mock_read.return_value = pd.DataFrame([
                    {
                        'CONTAINERID': 'CID-1',
                        'MFGORDERNAME': 'GA25120018',
                        'CONTAINERNAME': 'GA25120018-A00-001',
                        'SPECNAME': 'SPEC-1',
                    },
                    {
                        'CONTAINERID': 'CID-2',
                        'MFGORDERNAME': 'GA24120018',
                        'CONTAINERNAME': 'GA24120018-A00-001',
                        'SPECNAME': 'SPEC-2',
                    },
                ])

                result = _resolve_by_work_order(['ga25%'])

                assert result['total'] == 1
                assert result['data'][0]['input_value'] == 'ga25%'
                assert result['data'][0]['lot_id'] == 'GA25120018-A00-001'
                sql_params = mock_load.call_args.kwargs
                assert "LIKE" in sql_params['WORK_ORDER_FILTER']
                assert "UPPER(NVL(MFGORDERNAME, ''))" in sql_params['WORK_ORDER_FILTER']
                _, query_params = mock_read.call_args.args
                assert query_params == {'p0': 'GA25%'}


class TestSplitMergeHistoryMode:
    """Both modes use read_sql_df_slow for timeout protection."""

    def test_fast_mode_uses_time_window_and_row_limit(self):
        from unittest.mock import patch
        import pandas as pd

        with patch('mes_dashboard.services.query_tool_service.SQLLoader.load_with_params') as mock_load:
            with patch('mes_dashboard.services.query_tool_service.read_sql_df_slow') as mock_slow:
                mock_load.return_value = "SELECT * FROM DUAL"
                mock_slow.return_value = pd.DataFrame([])

                result = get_lot_split_merge_history('WO-1', full_history=False)

                assert result['mode'] == 'fast'
                kwargs = mock_load.call_args.kwargs
                assert "ADD_MONTHS(SYSDATE, -6)" in kwargs['TIME_WINDOW']
                assert "FETCH FIRST 500 ROWS ONLY" == kwargs['ROW_LIMIT']
                mock_slow.assert_called_once()

    def test_full_mode_uses_slow_query_without_limits(self):
        from unittest.mock import patch
        import pandas as pd

        with patch('mes_dashboard.services.query_tool_service.SQLLoader.load_with_params') as mock_load:
            with patch('mes_dashboard.services.query_tool_service.read_sql_df') as mock_fast:
                with patch('mes_dashboard.services.query_tool_service.read_sql_df_slow') as mock_slow:
                    mock_load.return_value = "SELECT * FROM DUAL"
                    mock_slow.return_value = pd.DataFrame([])

                    result = get_lot_split_merge_history('WO-1', full_history=True)

                    assert result['mode'] == 'full'
                    kwargs = mock_load.call_args.kwargs
                    assert kwargs['TIME_WINDOW'] == ''
                    assert kwargs['ROW_LIMIT'] == ''
                    mock_fast.assert_not_called()
                    mock_slow.assert_called_once()


class TestServiceConstants:
    """Tests for service constants."""

    def test_batch_size_is_reasonable(self):
        """Batch size should be <= 1000 (Oracle limit)."""
        assert BATCH_SIZE <= 1000

    def test_max_date_range_is_two_years(self):
        """Max date range should be 730 days (2 years)."""
        assert MAX_DATE_RANGE_DAYS == 730



class TestGetWorkcenterForGroups:
    """Tests for _get_workcenters_for_groups helper function."""

    def test_calls_filter_cache(self):
        """Should call filter_cache.get_workcenters_for_groups."""
        from unittest.mock import patch

        with patch('mes_dashboard.services.filter_cache.get_workcenters_for_groups') as mock_get:
            from mes_dashboard.services.query_tool_service import _get_workcenters_for_groups
            mock_get.return_value = ['DB_1', 'DB_2']

            result = _get_workcenters_for_groups(['DB'])

            mock_get.assert_called_once_with(['DB'])
            assert result == ['DB_1', 'DB_2']

    def test_returns_empty_list_for_unknown_group(self):
        """Should return empty list for unknown group."""
        from unittest.mock import patch

        with patch('mes_dashboard.services.filter_cache.get_workcenters_for_groups') as mock_get:
            from mes_dashboard.services.query_tool_service import _get_workcenters_for_groups
            mock_get.return_value = []

            result = _get_workcenters_for_groups(['UNKNOWN'])

            assert result == []


class TestGetLotHistoryWithWorkcenterFilter:
    """Tests for get_lot_history with workcenter_groups filter."""

    def test_no_filter_returns_all(self):
        """When no workcenter_groups, should not add filter to SQL."""
        from unittest.mock import patch
        from mes_dashboard.services.query_tool_service import get_lot_history

        with patch('mes_dashboard.services.query_tool_service.EventFetcher.fetch_events') as mock_fetch:
            mock_fetch.return_value = {
                'abc123': [
                    {'CONTAINERID': 'abc123', 'WORKCENTERNAME': 'DB_1'},
                    {'CONTAINERID': 'abc123', 'WORKCENTERNAME': 'WB_1'},
                ]
            }

            result = get_lot_history('abc123', workcenter_groups=None)

            assert 'error' not in result
            assert result['filtered_by_groups'] == []
            assert result['total'] == 2

    def test_with_filter_adds_condition(self):
        """When workcenter_groups provided, should filter by workcenters."""
        from unittest.mock import patch
        from mes_dashboard.services.query_tool_service import get_lot_history

        with patch('mes_dashboard.services.query_tool_service.EventFetcher.fetch_events') as mock_fetch:
            with patch('mes_dashboard.services.filter_cache.get_workcenters_for_groups') as mock_get_wc:
                mock_fetch.return_value = {
                    'abc123': [
                        {'CONTAINERID': 'abc123', 'WORKCENTERNAME': 'DB_1'},
                        {'CONTAINERID': 'abc123', 'WORKCENTERNAME': 'WB_1'},
                    ]
                }
                mock_get_wc.return_value = ['DB_1']

                result = get_lot_history('abc123', workcenter_groups=['DB'])

                mock_get_wc.assert_called_once_with(['DB'])
                assert result['filtered_by_groups'] == ['DB']
                assert result['total'] == 1
                assert result['data'][0]['WORKCENTERNAME'] == 'DB_1'

    def test_empty_groups_list_no_filter(self):
        """Empty groups list should return all (no filter)."""
        from unittest.mock import patch
        from mes_dashboard.services.query_tool_service import get_lot_history

        with patch('mes_dashboard.services.query_tool_service.EventFetcher.fetch_events') as mock_fetch:
            mock_fetch.return_value = {
                'abc123': [{'CONTAINERID': 'abc123', 'WORKCENTERNAME': 'DB_1'}]
            }

            result = get_lot_history('abc123', workcenter_groups=[])

            assert result['filtered_by_groups'] == []
            assert result['total'] == 1

    def test_filter_with_empty_workcenters_result(self):
        """When group has no workcenters, should not add filter."""
        from unittest.mock import patch
        from mes_dashboard.services.query_tool_service import get_lot_history

        with patch('mes_dashboard.services.query_tool_service.EventFetcher.fetch_events') as mock_fetch:
            with patch('mes_dashboard.services.filter_cache.get_workcenters_for_groups') as mock_get_wc:
                mock_fetch.return_value = {
                    'abc123': [{'CONTAINERID': 'abc123', 'WORKCENTERNAME': 'DB_1'}]
                }
                mock_get_wc.return_value = []

                result = get_lot_history('abc123', workcenter_groups=['UNKNOWN'])

                assert 'error' not in result
                assert result['total'] == 1


class TestGetEquipmentRejects:
    """TDD tests for get_equipment_rejects() — must fail before IP-1/IP-2 land.

    These tests guard the core AC requirements of the equipment-rejects-by-lots
    change:
      - AC-1: cross-station reject join (CONTAINERID-based, not EQUIPMENTNAME-based)
      - AC-2: detail row shape — no aggregate fields
      - AC-4: empty-WIP short-circuit (LOTREJECTHISTORY not queried when WIP empty)
    """

    def test_get_equipment_rejects_cross_station_lot(self):
        """AC-1: A lot processed on EQP-A but with reject logged under EQP-B must appear.

        WHY: The old equipment_rejects.sql filtered LOTREJECTHISTORY by EQUIPMENTNAME,
        which meant that if a lot was processed on Furnace-A but the reject event
        was recorded under Furnace-B's name, the row was silently missing.
        The new design resolves via LOTWIPHISTORY(EQUIPMENTID) → CONTAINERID, then
        JOINs LOTREJECTHISTORY on CONTAINERID — so the cross-station row IS returned
        regardless of which EQUIPMENTNAME appears in the reject event.
        """
        from unittest.mock import patch
        import pandas as pd

        # Fixture: lot LOT-CROSS was processed on EQP-A (EQUIPMENTID='EQP-A'),
        # but the reject event was logged with EQUIPMENTNAME='Furnace-B' (cross-station).
        reject_rows = pd.DataFrame([{
            'CONTAINERID': 'CID-CROSS',
            'CONTAINERNAME': 'LOT-CROSS',
            'WORKCENTERNAME': 'DB',
            'WORKCENTER_GROUP': 'DB',
            'WORKCENTERSEQUENCE_GROUP': 1,
            'PRODUCTLINENAME': 'PROD-LINE',
            'PJ_FUNCTION': 'FUNC-A',
            'PJ_TYPE': 'TYPE-A',
            'PRODUCTNAME': 'PROD-A',
            'SPECNAME': 'SPEC-A',
            'LOSSREASONNAME': 'CRACK',
            'EQUIPMENTNAME': 'Furnace-B',  # differs from queried EQP-A — cross-station
            'REJECTCOMMENT': '',
            'REJECT_QTY': 5,
            'STANDBY_QTY': 0,
            'QTYTOPROCESS_QTY': 0,
            'INPROCESS_QTY': 0,
            'PROCESSED_QTY': 0,
            'REJECT_TOTAL_QTY': 5,
            'DEFECT_QTY': 5,
            'TXN_TIME': '2024-01-15 10:00:00',
            'TXNDATE': '2024-01-15',
            'TXN_DAY': '2024-01-15',
        }])

        with patch('mes_dashboard.services.query_tool_service.SQLLoader.load_with_params') as mock_load:
            with patch('mes_dashboard.services.query_tool_service.read_sql_df_slow') as mock_read:
                mock_load.return_value = "SELECT * FROM DUAL"
                mock_read.return_value = reject_rows

                result = get_equipment_rejects(
                    equipment_ids=['EQP-A'],
                    start_date='2024-01-01',
                    end_date='2024-01-31',
                )

        assert result['total'] == 1
        row = result['data'][0]
        # Cross-station: EQUIPMENTNAME in result row is 'Furnace-B', not 'EQP-A'
        assert row['EQUIPMENTNAME'] == 'Furnace-B', (
            "Cross-station reject must appear with the reject event's EQUIPMENTNAME, "
            "not the queried EQUIPMENTID"
        )
        assert row['CONTAINERNAME'] == 'LOT-CROSS'

    def test_get_equipment_rejects_no_aggregate_columns(self):
        """AC-2: Response rows must NOT contain TOTAL_REJECT_QTY, TOTAL_DEFECT_QTY,
        or AFFECTED_LOT_COUNT — these are aggregate fields from the old SQL.

        WHY: The new design returns one row per reject event (detail view), not
        aggregate rows grouped by EQUIPMENTNAME+LOSSREASONNAME. Any row that still
        carries the aggregate-shape fields indicates the wrong SQL was loaded.
        """
        from unittest.mock import patch
        import pandas as pd

        detail_rows = pd.DataFrame([{
            'CONTAINERID': 'CID-1',
            'CONTAINERNAME': 'LOT-1',
            'WORKCENTERNAME': 'WB',
            'WORKCENTER_GROUP': 'WB',
            'WORKCENTERSEQUENCE_GROUP': 2,
            'PRODUCTLINENAME': 'PL-1',
            'PJ_FUNCTION': 'F1',
            'PJ_TYPE': 'T1',
            'PRODUCTNAME': 'PROD-1',
            'SPECNAME': 'SPEC-1',
            'LOSSREASONNAME': 'PARTICLE',
            'EQUIPMENTNAME': 'Furnace-A',
            'REJECTCOMMENT': None,
            'REJECT_QTY': 3,
            'STANDBY_QTY': 0,
            'QTYTOPROCESS_QTY': 0,
            'INPROCESS_QTY': 0,
            'PROCESSED_QTY': 0,
            'REJECT_TOTAL_QTY': 3,
            'DEFECT_QTY': 3,
            'TXN_TIME': '2024-01-10 08:00:00',
            'TXNDATE': '2024-01-10',
            'TXN_DAY': '2024-01-10',
        }])

        with patch('mes_dashboard.services.query_tool_service.SQLLoader.load_with_params') as mock_load:
            with patch('mes_dashboard.services.query_tool_service.read_sql_df_slow') as mock_read:
                mock_load.return_value = "SELECT * FROM DUAL"
                mock_read.return_value = detail_rows

                result = get_equipment_rejects(
                    equipment_ids=['EQP-A'],
                    start_date='2024-01-01',
                    end_date='2024-01-31',
                )

        assert result['total'] == 1
        for row in result['data']:
            assert 'TOTAL_REJECT_QTY' not in row, (
                "Aggregate field TOTAL_REJECT_QTY must not appear in detail rows"
            )
            assert 'TOTAL_DEFECT_QTY' not in row, (
                "Aggregate field TOTAL_DEFECT_QTY must not appear in detail rows"
            )
            assert 'AFFECTED_LOT_COUNT' not in row, (
                "Aggregate field AFFECTED_LOT_COUNT must not appear in detail rows"
            )
        # Detail fields must be present
        assert 'REJECT_TOTAL_QTY' in result['data'][0]
        assert 'DEFECT_QTY' in result['data'][0]
        assert 'CONTAINERNAME' in result['data'][0]

    def test_get_equipment_rejects_empty_short_circuit(self):
        """AC-4: When no equipment_ids are provided, raise UserInputError immediately.
        The LOTREJECTHISTORY query (read_sql_df_slow) must NOT be invoked at all.

        WHY: The new service validates equipment_ids first. An empty list means
        no WIP can be resolved, so there is nothing to join against LOTREJECTHISTORY.
        The short-circuit prevents a full-scan query on LOTREJECTHISTORY.
        """
        from unittest.mock import patch
        import pandas as pd
        from mes_dashboard.core.exceptions import UserInputError

        with patch('mes_dashboard.services.query_tool_service.SQLLoader.load_with_params') as mock_load:
            with patch('mes_dashboard.services.query_tool_service.read_sql_df_slow') as mock_read:
                mock_read.return_value = pd.DataFrame([])

                with pytest.raises(UserInputError):
                    get_equipment_rejects(
                        equipment_ids=[],
                        start_date='2024-01-01',
                        end_date='2024-01-31',
                    )

                # LOTREJECTHISTORY query must NOT have been invoked
                mock_read.assert_not_called()
                mock_load.assert_not_called()
