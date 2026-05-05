# -*- coding: utf-8 -*-
"""Unit tests for Job Query service functions.

Tests the core service functions without database dependencies.
"""

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

    def test_max_date_range_is_two_years(self):
        """Max date range should be 730 days (2 years)."""
        assert MAX_DATE_RANGE_DAYS == 730


class TestErrorLeakageProtection:
    """Tests for exception detail masking in job-query service."""

    @patch("mes_dashboard.services.job_query_service.read_sql_df")
    def test_query_error_masks_internal_details(self, mock_read):
        mock_read.side_effect = RuntimeError("ORA-00942: table or view does not exist")

        result = get_jobs_by_resources(["RES001"], "2024-01-01", "2024-01-05")

        assert result["error"] == QUERY_ERROR_MESSAGE
        assert "ORA-00942" not in result["error"]

    @patch("mes_dashboard.services.job_query_service.read_sql_df")
    def test_export_stream_error_masks_internal_details(self, mock_read):
        mock_read.side_effect = RuntimeError("sensitive sql context")

        output = "".join(export_jobs_with_history(["RES001"], "2024-01-01", "2024-01-31"))

        assert EXPORT_ERROR_MESSAGE in output
        assert "sensitive sql context" not in output


# ============================================================
# Task 9.3: Job engine parallel env var tests
# ============================================================

class TestJobEngineParallel:
    """JOB_ENGINE_PARALLEL env var controls execute_plan parallel for job query."""

    def _make_engine_env(self, monkeypatch, *, engine_calls):
        import mes_dashboard.services.batch_query_engine as engine_mod

        def fake_execute_plan(chunks, query_fn, **kwargs):
            engine_calls.append(kwargs.get("parallel"))
            return kwargs.get("query_hash", "fake_hash")

        monkeypatch.setattr(engine_mod, "execute_plan", fake_execute_plan)
        monkeypatch.setattr(engine_mod, "merge_chunks_to_spool", lambda *a, **kw: ("/tmp/f.parquet", 1))
        monkeypatch.setattr(engine_mod, "get_batch_progress", lambda *a: {})
        # Patch spool read to return empty list
        import mes_dashboard.core.query_spool_store as spool_mod
        monkeypatch.setattr(spool_mod, "get_spool_file_path", lambda *a: None)
        monkeypatch.setattr(spool_mod, "read_spool_records", lambda *a: None)
        monkeypatch.setattr(spool_mod, "register_spool_file", lambda *a, **kw: None)

    def test_default_parallel_is_1(self, monkeypatch):
        """Without JOB_ENGINE_PARALLEL → execute_plan gets parallel=1."""
        import mes_dashboard.services.job_query_service as job_svc
        engine_calls = []
        monkeypatch.setattr(job_svc, "_JOB_ENGINE_PARALLEL", 1)
        self._make_engine_env(monkeypatch, engine_calls=engine_calls)

        job_svc.get_jobs_by_resources(["R1"], "2025-01-01", "2025-03-31")

        assert len(engine_calls) == 1
        assert engine_calls[0] == 1

    def test_parallel_2_passed_to_execute_plan(self, monkeypatch):
        """JOB_ENGINE_PARALLEL=2 → execute_plan gets parallel=2."""
        import mes_dashboard.services.job_query_service as job_svc
        engine_calls = []
        monkeypatch.setattr(job_svc, "_JOB_ENGINE_PARALLEL", 2)
        self._make_engine_env(monkeypatch, engine_calls=engine_calls)

        job_svc.get_jobs_by_resources(["R1"], "2025-01-01", "2025-03-31")

        assert len(engine_calls) == 1
        assert engine_calls[0] == 2


# ============================================================
# Task 10.7: Job partial failure propagation tests
# ============================================================

class TestJobPartialFailure:
    """Job partial failure propagates to result['_meta']['partial_failure']."""

    def _make_engine_env(self, monkeypatch, *, progress=None):
        import mes_dashboard.services.batch_query_engine as engine_mod
        import mes_dashboard.core.query_spool_store as spool_mod

        monkeypatch.setattr(engine_mod, "execute_plan", lambda *a, **kw: kw.get("query_hash", "fake"))
        monkeypatch.setattr(engine_mod, "merge_chunks_to_spool", lambda *a, **kw: ("/tmp/f.parquet", 1))
        monkeypatch.setattr(engine_mod, "get_batch_progress", lambda *a: progress or {})
        monkeypatch.setattr(spool_mod, "get_spool_file_path", lambda *a: None)
        monkeypatch.setattr(spool_mod, "read_spool_records", lambda *a: None)
        monkeypatch.setattr(spool_mod, "register_spool_file", lambda *a, **kw: None)

    def test_partial_failure_in_meta(self, monkeypatch):
        """Chunk partial failure → result._meta.partial_failure.has_partial_failure == True."""
        import mes_dashboard.services.job_query_service as job_svc
        self._make_engine_env(
            monkeypatch,
            progress={"has_partial_failure": "True", "failed_chunk_count": "1", "failed_ranges": "2025-01-01~2025-01-31"},
        )

        result = job_svc.get_jobs_by_resources(["R1"], "2025-01-01", "2025-03-31")

        assert result["_meta"]["partial_failure"]["has_partial_failure"] is True

    def test_no_partial_failure_no_meta_key(self, monkeypatch):
        """All chunks succeed → no _meta in result."""
        import mes_dashboard.services.job_query_service as job_svc
        self._make_engine_env(monkeypatch)

        result = job_svc.get_jobs_by_resources(["R1"], "2025-01-01", "2025-03-31")

        assert "_meta" not in result
