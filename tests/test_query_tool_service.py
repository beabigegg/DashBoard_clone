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
    BATCH_SIZE,
    MAX_LOT_IDS,
    MAX_SERIAL_NUMBERS,
    MAX_WORK_ORDERS,
    MAX_GD_WORK_ORDERS,
    MAX_EQUIPMENTS,
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
        """Should reject date range exceeding limit."""
        result = validate_date_range('2023-01-01', '2024-12-31')
        assert result is not None
        assert str(MAX_DATE_RANGE_DAYS) in result

    def test_exactly_max_range(self):
        """Should allow exactly max range days."""
        # 365 days from 2025-01-01 is 2026-01-01
        result = validate_date_range('2025-01-01', '2026-01-01')
        assert result is None

    def test_one_day_over_max_range(self):
        """Should reject one day over max range."""
        # 366 days
        result = validate_date_range('2025-01-01', '2026-01-02')
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

    def test_exceeds_lot_id_limit(self):
        """Should reject LOT IDs exceeding limit."""
        values = [f'GA{i:09d}' for i in range(MAX_LOT_IDS + 1)]
        result = validate_lot_input('lot_id', values)
        assert result is not None
        assert '超過上限' in result
        assert str(MAX_LOT_IDS) in result

    def test_exceeds_serial_number_limit(self):
        """Should reject serial numbers exceeding limit."""
        values = [f'SN{i:06d}' for i in range(MAX_SERIAL_NUMBERS + 1)]
        result = validate_lot_input('serial_number', values)
        assert result is not None
        assert '超過上限' in result
        assert str(MAX_SERIAL_NUMBERS) in result

    def test_exceeds_work_order_limit(self):
        """Should reject work orders exceeding limit."""
        values = [f'WO{i:06d}' for i in range(MAX_WORK_ORDERS + 1)]
        result = validate_lot_input('work_order', values)
        assert result is not None
        assert '超過上限' in result
        assert str(MAX_WORK_ORDERS) in result

    def test_exceeds_gd_work_order_limit(self):
        """Should reject GD work orders exceeding limit."""
        values = [f'GD{i:06d}' for i in range(MAX_GD_WORK_ORDERS + 1)]
        result = validate_lot_input('gd_work_order', values)
        assert result is not None
        assert '超過上限' in result
        assert str(MAX_GD_WORK_ORDERS) in result

    def test_exactly_at_limit(self):
        """Should accept values exactly at limit."""
        values = [f'GA{i:09d}' for i in range(MAX_LOT_IDS)]
        result = validate_lot_input('lot_id', values)
        assert result is None

    def test_unknown_input_type_uses_default_limit(self):
        """Should use default limit for unknown input types."""
        values = [f'X{i}' for i in range(MAX_LOT_IDS)]
        result = validate_lot_input('unknown_type', values)
        assert result is None

        values_over = [f'X{i}' for i in range(MAX_LOT_IDS + 1)]
        result = validate_lot_input('unknown_type', values_over)
        assert result is not None


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

    def test_exceeds_equipment_limit(self):
        """Should reject equipment IDs exceeding limit."""
        values = [f'EQ{i:05d}' for i in range(MAX_EQUIPMENTS + 1)]
        result = validate_equipment_input(values)
        assert result is not None
        assert '不得超過' in result
        assert str(MAX_EQUIPMENTS) in result

    def test_exactly_at_limit(self):
        """Should accept equipment IDs exactly at limit."""
        values = [f'EQ{i:05d}' for i in range(MAX_EQUIPMENTS)]
        result = validate_equipment_input(values)
        assert result is None


class TestResolveQueriesUseBindParams:
    """Queries with user input should always use bind params."""

    def test_resolve_by_lot_id_uses_query_builder_params(self):
        from unittest.mock import patch
        import pandas as pd

        with patch('mes_dashboard.services.query_tool_service.SQLLoader.load_with_params') as mock_load:
            with patch('mes_dashboard.services.query_tool_service.read_sql_df') as mock_read:
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
            with patch('mes_dashboard.services.query_tool_service.read_sql_df') as mock_read:
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
            with patch('mes_dashboard.services.query_tool_service.read_sql_df') as mock_read:
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
            with patch('mes_dashboard.services.query_tool_service.read_sql_df') as mock_read:
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
            with patch('mes_dashboard.services.query_tool_service.read_sql_df') as mock_read:
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
            with patch('mes_dashboard.services.query_tool_service.read_sql_df') as mock_read:
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
    """Fast mode should use read_sql_df, full mode should use read_sql_df_slow."""

    def test_fast_mode_uses_time_window_and_row_limit(self):
        from unittest.mock import patch
        import pandas as pd

        with patch('mes_dashboard.services.query_tool_service.SQLLoader.load_with_params') as mock_load:
            with patch('mes_dashboard.services.query_tool_service.read_sql_df') as mock_fast:
                with patch('mes_dashboard.services.query_tool_service.read_sql_df_slow') as mock_slow:
                    mock_load.return_value = "SELECT * FROM DUAL"
                    mock_fast.return_value = pd.DataFrame([])

                    result = get_lot_split_merge_history('WO-1', full_history=False)

                    assert result['mode'] == 'fast'
                    kwargs = mock_load.call_args.kwargs
                    assert "ADD_MONTHS(SYSDATE, -6)" in kwargs['TIME_WINDOW']
                    assert "FETCH FIRST 500 ROWS ONLY" == kwargs['ROW_LIMIT']
                    mock_fast.assert_called_once()
                    mock_slow.assert_not_called()

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

    def test_max_date_range_is_reasonable(self):
        """Max date range should be 365 days."""
        assert MAX_DATE_RANGE_DAYS == 365

    def test_max_lot_ids_is_reasonable(self):
        """Max LOT IDs should be sensible."""
        assert 10 <= MAX_LOT_IDS <= 100

    def test_max_serial_numbers_is_reasonable(self):
        """Max serial numbers should be sensible."""
        assert 10 <= MAX_SERIAL_NUMBERS <= 100

    def test_max_work_orders_is_reasonable(self):
        """Max work orders should match API contract."""
        assert MAX_WORK_ORDERS == 50

    def test_max_gd_work_orders_is_reasonable(self):
        """Max GD work orders should match API contract."""
        assert MAX_GD_WORK_ORDERS == 100

    def test_max_equipments_is_reasonable(self):
        """Max equipments should be sensible."""
        assert 5 <= MAX_EQUIPMENTS <= 50


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
