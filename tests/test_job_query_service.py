# -*- coding: utf-8 -*-
"""Unit tests for Job Query service functions.

Tests the core service functions without database dependencies.
"""

import pytest
from unittest.mock import patch
from mes_dashboard.services.job_query_service import (
    validate_date_range,
    _build_resource_filter,
    _build_resource_filter_sql,
    get_jobs_by_resources,
    export_jobs_with_history,
    BATCH_SIZE,
    MAX_DATE_RANGE_DAYS,
    QUERY_ERROR_MESSAGE,
    EXPORT_ERROR_MESSAGE,
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
        # 365 days from 2024-01-01 is 2024-12-31
        result = validate_date_range('2024-01-01', '2024-12-31')
        assert result is None

    def test_one_day_over_max_range(self):
        """Should reject one day over max range."""
        # 366 days
        result = validate_date_range('2024-01-01', '2025-01-01')
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


class TestBuildResourceFilter:
    """Tests for _build_resource_filter function."""

    def test_empty_list(self):
        """Should return empty list for empty input."""
        result = _build_resource_filter([])
        assert result == []

    def test_single_id(self):
        """Should return single chunk for single ID."""
        result = _build_resource_filter(['RES001'])
        assert len(result) == 1
        assert result[0] == ['RES001']

    def test_multiple_ids(self):
        """Should join multiple IDs with comma."""
        result = _build_resource_filter(['RES001', 'RES002', 'RES003'])
        assert len(result) == 1
        assert result[0] == ['RES001', 'RES002', 'RES003']

    def test_chunking(self):
        """Should chunk when exceeding batch size."""
        # Create more than BATCH_SIZE IDs
        ids = [f'RES{i:05d}' for i in range(BATCH_SIZE + 10)]
        result = _build_resource_filter(ids)
        assert len(result) == 2
        # First chunk should have BATCH_SIZE items
        assert len(result[0]) == BATCH_SIZE

    def test_preserve_id_value_without_sql_interpolation(self):
        """Should keep raw value and defer safety to bind variables."""
        result = _build_resource_filter(["RES'001"])
        assert len(result) == 1
        assert result[0] == ["RES'001"]

    def test_custom_chunk_size(self):
        """Should respect custom chunk size."""
        ids = ['RES001', 'RES002', 'RES003', 'RES004', 'RES005']
        result = _build_resource_filter(ids, max_chunk_size=2)
        assert len(result) == 3  # 2+2+1


class TestBuildResourceFilterSql:
    """Tests for _build_resource_filter_sql function."""

    def test_empty_list(self):
        """Should return 1=0 for empty input (no results)."""
        result = _build_resource_filter_sql([])
        assert result == "1=0"

    def test_single_id(self):
        """Should build IN clause with bind variable for single ID."""
        result, params = _build_resource_filter_sql(['RES001'], return_params=True)
        assert "j.RESOURCEID IN" in result
        assert ":p0" in result
        assert params["p0"] == "RES001"
        assert "RES001" not in result

    def test_multiple_ids(self):
        """Should build IN clause with multiple bind variables."""
        result, params = _build_resource_filter_sql(['RES001', 'RES002'], return_params=True)
        assert "j.RESOURCEID IN" in result
        assert ":p0" in result
        assert ":p1" in result
        assert params["p0"] == "RES001"
        assert params["p1"] == "RES002"

    def test_custom_column(self):
        """Should use custom column name."""
        result = _build_resource_filter_sql(['RES001'], column='r.ID')
        assert "r.ID IN" in result

    def test_large_list_uses_or(self):
        """Should use OR for chunked results."""
        # Create more than BATCH_SIZE IDs
        ids = [f'RES{i:05d}' for i in range(BATCH_SIZE + 10)]
        result = _build_resource_filter_sql(ids)
        assert " OR " in result
        # Should have parentheses wrapping the OR conditions
        assert result.startswith("(")
        assert result.endswith(")")

    def test_sql_injection_payload_stays_in_params(self):
        """Injection payload should never be interpolated into SQL text."""
        payload = "RES001' OR '1'='1"
        sql, params = _build_resource_filter_sql([payload], return_params=True)
        assert payload in params.values()
        assert payload not in sql


class TestServiceConstants:
    """Tests for service constants."""

    def test_batch_size_is_reasonable(self):
        """Batch size should be <= 1000 (Oracle limit)."""
        assert BATCH_SIZE <= 1000

    def test_max_date_range_is_year(self):
        """Max date range should be 365 days."""
        assert MAX_DATE_RANGE_DAYS == 365


class TestErrorLeakageProtection:
    """Tests for exception detail masking in job-query service."""

    @patch("mes_dashboard.services.job_query_service.read_sql_df")
    def test_query_error_masks_internal_details(self, mock_read):
        mock_read.side_effect = RuntimeError("ORA-00942: table or view does not exist")

        result = get_jobs_by_resources(["RES001"], "2024-01-01", "2024-01-31")

        assert result["error"] == QUERY_ERROR_MESSAGE
        assert "ORA-00942" not in result["error"]

    @patch("mes_dashboard.services.job_query_service.read_sql_df")
    def test_export_stream_error_masks_internal_details(self, mock_read):
        mock_read.side_effect = RuntimeError("sensitive sql context")

        output = "".join(export_jobs_with_history(["RES001"], "2024-01-01", "2024-01-31"))

        assert EXPORT_ERROR_MESSAGE in output
        assert "sensitive sql context" not in output
