# -*- coding: utf-8 -*-
"""Unit tests for Excel query service functions.

Tests the core service functions without database dependencies.
"""

import pytest
from unittest.mock import MagicMock, patch
from mes_dashboard.services.excel_query_service import (
    parse_excel,
    get_column_unique_values,
    execute_batch_query,
    execute_advanced_batch_query,
    detect_excel_column_type,
    escape_like_pattern,
    build_like_condition,
    build_date_range_condition,
    validate_like_keywords,
    sanitize_column_name,
    validate_table_name,
    LIKE_KEYWORD_LIMIT,
    PARSE_ERROR_MESSAGE,
    COLUMN_READ_ERROR_MESSAGE,
    QUERY_ERROR_MESSAGE,
)


class TestDetectExcelColumnType:
    """Tests for detect_excel_column_type function."""

    def test_empty_values_returns_text(self):
        """Empty list should return text type."""
        result = detect_excel_column_type([])
        assert result['detected_type'] == 'text'
        assert result['type_label'] == '文字'

    def test_detect_date_type(self):
        """Should detect date format YYYY-MM-DD."""
        values = ['2024-01-15', '2024-02-20', '2024-03-25', '2024-04-30']
        result = detect_excel_column_type(values)
        assert result['detected_type'] == 'date'
        assert result['type_label'] == '日期'

    def test_detect_date_with_slash(self):
        """Should detect date format YYYY/MM/DD."""
        values = ['2024/01/15', '2024/02/20', '2024/03/25', '2024/04/30']
        result = detect_excel_column_type(values)
        assert result['detected_type'] == 'date'
        assert result['type_label'] == '日期'

    def test_detect_datetime_type(self):
        """Should detect datetime format."""
        values = [
            '2024-01-15 10:30:00',
            '2024-02-20 14:45:30',
            '2024-03-25T08:00:00',
            '2024-04-30 23:59:59'
        ]
        result = detect_excel_column_type(values)
        assert result['detected_type'] == 'datetime'
        assert result['type_label'] == '日期時間'

    def test_detect_number_type(self):
        """Should detect numeric values."""
        values = ['123', '456.78', '-99', '0', '1000000']
        result = detect_excel_column_type(values)
        assert result['detected_type'] == 'number'
        assert result['type_label'] == '數值'

    def test_detect_id_type(self):
        """Should detect ID pattern (uppercase alphanumeric)."""
        values = ['LOT001', 'WIP-2024-001', 'ABC_123', 'PROD001', 'TEST_ID']
        result = detect_excel_column_type(values)
        assert result['detected_type'] == 'id'
        assert result['type_label'] == '識別碼'

    def test_mixed_values_returns_text(self):
        """Mixed values should return text type."""
        values = ['abc', '123', '2024-01-01', 'xyz', 'test']
        result = detect_excel_column_type(values)
        assert result['detected_type'] == 'text'
        assert result['type_label'] == '文字'

    def test_sample_values_included(self):
        """Should include sample values in result."""
        values = ['A', 'B', 'C', 'D', 'E', 'F']
        result = detect_excel_column_type(values)
        assert 'sample_values' in result
        assert len(result['sample_values']) <= 5


class TestEscapeLikePattern:
    """Tests for escape_like_pattern function."""

    def test_escape_percent(self):
        """Should escape percent sign."""
        assert escape_like_pattern('100%') == '100\\%'

    def test_escape_underscore(self):
        """Should escape underscore."""
        assert escape_like_pattern('test_value') == 'test\\_value'

    def test_escape_backslash(self):
        """Should escape backslash."""
        assert escape_like_pattern('path\\file') == 'path\\\\file'

    def test_escape_multiple_specials(self):
        """Should escape multiple special characters."""
        assert escape_like_pattern('50%_off') == '50\\%\\_off'

    def test_no_escape_needed(self):
        """Should return unchanged if no special chars."""
        assert escape_like_pattern('normalvalue') == 'normalvalue'


class TestBuildLikeCondition:
    """Tests for build_like_condition function."""

    def test_contains_mode(self):
        """Should build LIKE %...% pattern."""
        condition, params = build_like_condition('COL', ['abc'], 'contains')
        assert 'LIKE :like_0' in condition
        assert params['like_0'] == '%abc%'

    def test_prefix_mode(self):
        """Should build LIKE ...% pattern."""
        condition, params = build_like_condition('COL', ['abc'], 'prefix')
        assert 'LIKE :like_0' in condition
        assert params['like_0'] == 'abc%'

    def test_suffix_mode(self):
        """Should build LIKE %... pattern."""
        condition, params = build_like_condition('COL', ['abc'], 'suffix')
        assert 'LIKE :like_0' in condition
        assert params['like_0'] == '%abc'

    def test_multiple_values(self):
        """Should build OR conditions for multiple values."""
        condition, params = build_like_condition('COL', ['a', 'b', 'c'], 'contains')
        assert 'OR' in condition
        assert len(params) == 3
        assert params['like_0'] == '%a%'
        assert params['like_1'] == '%b%'
        assert params['like_2'] == '%c%'

    def test_empty_values(self):
        """Should return empty for empty values."""
        condition, params = build_like_condition('COL', [], 'contains')
        assert condition == ''
        assert params == {}

    def test_escape_clause_included(self):
        """Should include ESCAPE clause."""
        condition, params = build_like_condition('COL', ['test'], 'contains')
        assert "ESCAPE '\\')" in condition


class TestBuildDateRangeCondition:
    """Tests for build_date_range_condition function."""

    def test_both_dates(self):
        """Should build condition with both dates."""
        condition, params = build_date_range_condition(
            'TXNDATE', '2024-01-01', '2024-12-31'
        )
        assert 'TO_DATE(:date_from' in condition
        assert 'TO_DATE(:date_to' in condition
        assert params['date_from'] == '2024-01-01'
        assert params['date_to'] == '2024-12-31'

    def test_only_from_date(self):
        """Should build condition with only start date."""
        condition, params = build_date_range_condition(
            'TXNDATE', date_from='2024-01-01'
        )
        assert '>=' in condition
        assert 'date_from' in params
        assert 'date_to' not in params

    def test_only_to_date(self):
        """Should build condition with only end date."""
        condition, params = build_date_range_condition(
            'TXNDATE', date_to='2024-12-31'
        )
        assert '<' in condition
        assert 'date_to' in params
        assert 'date_from' not in params

    def test_no_dates(self):
        """Should return empty for no dates."""
        condition, params = build_date_range_condition('TXNDATE')
        assert condition == ''
        assert params == {}

    def test_end_date_includes_full_day(self):
        """End date condition should include +1 for full day."""
        condition, params = build_date_range_condition(
            'TXNDATE', date_to='2024-12-31'
        )
        assert '+ 1' in condition


class TestValidateLikeKeywords:
    """Tests for validate_like_keywords function."""

    def test_within_limit(self):
        """Should pass validation for values within limit."""
        values = ['a'] * 50
        result = validate_like_keywords(values)
        assert result['valid'] is True

    def test_at_limit(self):
        """Should pass validation at exact limit."""
        values = ['a'] * LIKE_KEYWORD_LIMIT
        result = validate_like_keywords(values)
        assert result['valid'] is True

    def test_exceeds_limit(self):
        """Should fail validation when exceeding limit."""
        values = ['a'] * (LIKE_KEYWORD_LIMIT + 1)
        result = validate_like_keywords(values)
        assert result['valid'] is False
        assert 'error' in result


class TestSanitizeColumnName:
    """Tests for sanitize_column_name function."""

    def test_valid_name(self):
        """Should keep valid column name."""
        assert sanitize_column_name('LOT_ID') == 'LOT_ID'

    def test_removes_special_chars(self):
        """Should remove special characters."""
        assert sanitize_column_name('LOT-ID') == 'LOTID'
        assert sanitize_column_name('LOT ID') == 'LOTID'

    def test_allows_underscore(self):
        """Should allow underscore."""
        assert sanitize_column_name('MY_COLUMN_NAME') == 'MY_COLUMN_NAME'

    def test_prevents_sql_injection(self):
        """Should prevent SQL injection attempts."""
        assert sanitize_column_name("COL; DROP TABLE--") == 'COLDROPTABLE'


class TestValidateTableName:
    """Tests for validate_table_name function."""

    def test_simple_name(self):
        """Should validate simple table name."""
        assert validate_table_name('MY_TABLE') is True

    def test_schema_qualified(self):
        """Should validate schema.table format."""
        assert validate_table_name('DWH.DW_MES_WIP') is True

    def test_invalid_starts_with_number(self):
        """Should reject names starting with number."""
        assert validate_table_name('123TABLE') is False

    def test_invalid_special_chars(self):
        """Should reject names with special characters."""
        assert validate_table_name('TABLE-NAME') is False
        assert validate_table_name('TABLE NAME') is False

    def test_sql_injection_prevention(self):
        """Should reject SQL injection attempts."""
        assert validate_table_name('TABLE; DROP--') is False


class TestErrorLeakageProtection:
    """Tests for exception detail masking in excel-query service."""

    @patch("mes_dashboard.services.excel_query_service.pd.read_excel")
    def test_parse_excel_masks_internal_error_details(self, mock_read_excel):
        mock_read_excel.side_effect = RuntimeError("openpyxl stack trace detail")

        result = parse_excel(MagicMock())

        assert result["error"] == PARSE_ERROR_MESSAGE
        assert "openpyxl" not in result["error"]

    @patch("mes_dashboard.services.excel_query_service.pd.read_excel")
    def test_get_column_unique_values_masks_internal_error_details(self, mock_read_excel):
        mock_read_excel.side_effect = RuntimeError("internal parser detail")

        result = get_column_unique_values(MagicMock(), "LOT_ID")

        assert result["error"] == COLUMN_READ_ERROR_MESSAGE
        assert "internal parser detail" not in result["error"]

    @patch("mes_dashboard.services.excel_query_service.get_db_connection")
    def test_execute_batch_query_masks_internal_error_details(self, mock_get_db):
        mock_cursor = MagicMock()
        mock_cursor.execute.side_effect = RuntimeError("ORA-00942: table missing")
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_get_db.return_value = mock_conn

        result = execute_batch_query(
            table_name="DWH.DW_MES_WIP",
            search_column="LOT_ID",
            return_columns=["LOT_ID"],
            search_values=["LOT001"],
        )

        assert result["error"] == QUERY_ERROR_MESSAGE
        assert "ORA-00942" not in result["error"]

    @patch("mes_dashboard.services.excel_query_service.get_db_connection")
    def test_execute_advanced_batch_query_masks_internal_error_details(self, mock_get_db):
        mock_cursor = MagicMock()
        mock_cursor.execute.side_effect = RuntimeError("sensitive sql context")
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_get_db.return_value = mock_conn

        result = execute_advanced_batch_query(
            table_name="DWH.DW_MES_WIP",
            search_column="LOT_ID",
            return_columns=["LOT_ID"],
            search_values=["LOT001"],
            query_type="in",
        )

        assert result["error"] == QUERY_ERROR_MESSAGE
        assert "sensitive sql context" not in result["error"]
