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
    _build_in_clause,
    _build_in_filter,
    BATCH_SIZE,
    MAX_LOT_IDS,
    MAX_SERIAL_NUMBERS,
    MAX_WORK_ORDERS,
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
        # 90 days from 2024-01-01 is 2024-03-31
        result = validate_date_range('2024-01-01', '2024-03-31')
        assert result is None

    def test_one_day_over_max_range(self):
        """Should reject one day over max range."""
        # 91 days
        result = validate_date_range('2024-01-01', '2024-04-02')
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


class TestBuildInClause:
    """Tests for _build_in_clause function."""

    def test_empty_list(self):
        """Should return empty list for empty input."""
        result = _build_in_clause([])
        assert result == []

    def test_single_value(self):
        """Should return single chunk for single value."""
        result = _build_in_clause(['VAL001'])
        assert len(result) == 1
        assert result[0] == "'VAL001'"

    def test_multiple_values(self):
        """Should join multiple values with comma."""
        result = _build_in_clause(['VAL001', 'VAL002', 'VAL003'])
        assert len(result) == 1
        assert "'VAL001'" in result[0]
        assert "'VAL002'" in result[0]
        assert "'VAL003'" in result[0]
        assert result[0] == "'VAL001', 'VAL002', 'VAL003'"

    def test_chunking(self):
        """Should chunk when exceeding batch size."""
        # Create more than BATCH_SIZE values
        values = [f'VAL{i:06d}' for i in range(BATCH_SIZE + 10)]
        result = _build_in_clause(values)
        assert len(result) == 2
        # First chunk should have BATCH_SIZE items
        assert result[0].count("'") == BATCH_SIZE * 2  # 2 quotes per value

    def test_escape_single_quotes(self):
        """Should escape single quotes in values."""
        result = _build_in_clause(["VAL'001"])
        assert len(result) == 1
        assert "VAL''001" in result[0]  # Escaped

    def test_custom_chunk_size(self):
        """Should respect custom chunk size."""
        values = ['V1', 'V2', 'V3', 'V4', 'V5']
        result = _build_in_clause(values, max_chunk_size=2)
        assert len(result) == 3  # 2+2+1


class TestBuildInFilter:
    """Tests for _build_in_filter function."""

    def test_empty_list(self):
        """Should return 1=0 for empty input (no results)."""
        result = _build_in_filter([], 'COL')
        assert result == "1=0"

    def test_single_value(self):
        """Should build simple IN clause for single value."""
        result = _build_in_filter(['VAL001'], 'COL')
        assert "COL IN" in result
        assert "'VAL001'" in result

    def test_multiple_values(self):
        """Should build IN clause with multiple values."""
        result = _build_in_filter(['VAL001', 'VAL002'], 'COL')
        assert "COL IN" in result
        assert "'VAL001'" in result
        assert "'VAL002'" in result

    def test_custom_column(self):
        """Should use custom column name."""
        result = _build_in_filter(['VAL001'], 't.MYCOL')
        assert "t.MYCOL IN" in result

    def test_large_list_uses_or(self):
        """Should use OR for chunked results."""
        # Create more than BATCH_SIZE values
        values = [f'VAL{i:06d}' for i in range(BATCH_SIZE + 10)]
        result = _build_in_filter(values, 'COL')
        assert " OR " in result
        # Should have parentheses wrapping the OR conditions
        assert result.startswith("(")
        assert result.endswith(")")


class TestServiceConstants:
    """Tests for service constants."""

    def test_batch_size_is_reasonable(self):
        """Batch size should be <= 1000 (Oracle limit)."""
        assert BATCH_SIZE <= 1000

    def test_max_date_range_is_reasonable(self):
        """Max date range should be 90 days."""
        assert MAX_DATE_RANGE_DAYS == 90

    def test_max_lot_ids_is_reasonable(self):
        """Max LOT IDs should be sensible."""
        assert 10 <= MAX_LOT_IDS <= 100

    def test_max_serial_numbers_is_reasonable(self):
        """Max serial numbers should be sensible."""
        assert 10 <= MAX_SERIAL_NUMBERS <= 100

    def test_max_work_orders_is_reasonable(self):
        """Max work orders should be low due to expansion."""
        assert MAX_WORK_ORDERS <= 20  # Work orders can expand to many LOTs

    def test_max_equipments_is_reasonable(self):
        """Max equipments should be sensible."""
        assert 5 <= MAX_EQUIPMENTS <= 50
