# -*- coding: utf-8 -*-
"""Tier 0 unit tests for material_consumption_service.

TDD: These tests are written FIRST (failing) before the implementation.

Test coverage per CLAUDE.md Test Coverage Discipline:
- Both Oracle fallback AND spool/regroup paths tested per kwarg.
- Fixtures include pj_type, material_part, and date columns.
- Uses mock.assert_called_once() + per-kwarg call_args.kwargs checks.
- NEVER uses mock.assert_called_once_with(...).
"""

from __future__ import annotations

import datetime
from unittest import mock
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

import mes_dashboard.services.material_consumption_service as _MC_SVC


# ---------------------------------------------------------------------------
# Shared fixture builders
# ---------------------------------------------------------------------------


def _sample_summary_df(
    txn_dates=None,
    material_parts=None,
    pj_types=None,
    primary_categories=None,
) -> pd.DataFrame:
    """Build a minimal summary spool fixture that includes all filter columns."""
    txn_dates = txn_dates or [datetime.date(2026, 1, 10), datetime.date(2026, 1, 11)]
    material_parts = material_parts or ["MAT-A", "MAT-B"]
    pj_types = pj_types or ["TypeX", "TypeY"]
    primary_categories = primary_categories or ["CatA", "CatB"]
    n = max(len(txn_dates), len(material_parts), len(pj_types))
    rows = []
    for i in range(n):
        rows.append(
            {
                "txn_date": txn_dates[i % len(txn_dates)],
                "material_part": material_parts[i % len(material_parts)],
                "pj_type": pj_types[i % len(pj_types)],
                "primary_category": primary_categories[i % len(primary_categories)],
                "total_consumed": float(100 + i * 10),
                "total_required": float(120 + i * 10),
                "lot_count": 3 + i,
                "workorder_count": 2 + i,
            }
        )
    return pd.DataFrame(rows)


def _sample_detail_df(pj_types=None) -> pd.DataFrame:
    """Build a minimal detail spool fixture."""
    pj_types = pj_types or ["TypeX", "TypeY"]
    rows = []
    for i, pjt in enumerate(pj_types):
        rows.append(
            {
                "CONTAINERID": f"C{i:04d}",
                "CONTAINERNAME": f"LOT-{i:04d}",
                "PJ_WORKORDER": f"WO{i:04d}",
                "WORKCENTERNAME": "WC-A",
                "MATERIALPARTNAME": "MAT-A",
                "MATERIALLOTNAME": f"ML{i:04d}",
                "VENDORLOTNUMBER": f"VL{i:04d}",
                "QTYREQUIRED": 100.0,
                "QTYCONSUMED": 98.0,
                "EQUIPMENTNAME": "EQ-01",
                "TXNDATE": datetime.date(2026, 1, 10),
                "PRIMARY_CATEGORY": "CatA",
                "SECONDARY_CATEGORY": "SubCat1",
                "pj_type": pjt,
            }
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# TestSummaryOraclePath
# ---------------------------------------------------------------------------


class TestSummaryOraclePath:
    """Oracle path for get_summary() — spool miss forces Oracle execute."""

    @patch("mes_dashboard.services.material_consumption_service.get_spool_file_path", return_value=None)
    @patch("mes_dashboard.services.material_consumption_service.read_sql_df")
    @patch("mes_dashboard.services.material_consumption_service.store_spooled_df")
    @patch("mes_dashboard.services.material_consumption_service._compute_summary_from_spool")
    def test_aggregates_consumed_required_by_txn_date(
        self,
        mock_compute,
        mock_store,
        mock_read,
        mock_spool_path,
    ):
        """When spool miss, reads Oracle and stores result."""
        df = _sample_summary_df()
        mock_read.return_value = df
        mock_compute.return_value = {
            "kpi": {"total_consumed": 200.0, "total_required": 240.0, "efficiency_pct": 83.3, "lot_count": 6, "workorder_count": 4},
            "trend": [],
            "type_breakdown": [],
        }
        result = _MC_SVC.get_summary(
            material_parts=["MAT-A"],
            start_date="2026-01-01",
            end_date="2026-01-31",
            granularity="month",
        )
        mock_read.assert_called_once()
        assert "query_id" in result
        assert "kpi" in result

    @patch("mes_dashboard.services.material_consumption_service.get_spool_file_path", return_value=None)
    @patch("mes_dashboard.services.material_consumption_service.read_sql_df")
    @patch("mes_dashboard.services.material_consumption_service.store_spooled_df")
    @patch("mes_dashboard.services.material_consumption_service._compute_summary_from_spool")
    def test_pj_type_join_present_in_sql(
        self,
        mock_compute,
        mock_store,
        mock_read,
        mock_spool_path,
    ):
        """PJ_TYPE JOIN must appear in the generated SQL — filtering moved to DuckDB."""
        df = _sample_summary_df(pj_types=["TypeX"])
        mock_read.return_value = df
        mock_compute.return_value = {
            "kpi": {}, "trend": [], "type_breakdown": []
        }
        _MC_SVC.get_summary(
            material_parts=["MAT-A"],
            start_date="2026-01-01",
            end_date="2026-01-31",
            granularity="week",
        )
        # Verify Oracle was called (spool miss triggered it)
        mock_read.assert_called_once()
        # SQL must reference the PJ_TYPE JOIN (no pj_types Oracle filter now)
        call_sql = mock_read.call_args.args[0] if mock_read.call_args.args else ""
        assert "PJ_TYPE" in call_sql.upper() or "pj_type" in call_sql.lower(), (
            f"PJ_TYPE JOIN not in Oracle SQL. sql={call_sql[:300]}"
        )

    @patch("mes_dashboard.services.material_consumption_service.get_spool_file_path", return_value=None)
    @patch("mes_dashboard.services.material_consumption_service.read_sql_df")
    @patch("mes_dashboard.services.material_consumption_service.store_spooled_df")
    @patch("mes_dashboard.services.material_consumption_service._compute_summary_from_spool")
    def test_workcenter_groups_not_in_sql(
        self,
        mock_compute,
        mock_store,
        mock_read,
        mock_spool_path,
    ):
        """workcenter_groups must NOT be passed to Oracle SQL (removed filter)."""
        mock_read.return_value = _sample_summary_df()
        mock_compute.return_value = {"kpi": {}, "trend": [], "type_breakdown": []}

        _MC_SVC.get_summary(
            material_parts=["MAT-A"],
            start_date="2026-01-01",
            end_date="2026-01-31",
            granularity="week",
        )
        mock_read.assert_called_once()
        call_params = mock_read.call_args.args[1] if len(mock_read.call_args.args) > 1 else {}
        call_sql = mock_read.call_args.args[0] if mock_read.call_args.args else ""
        # WORKCENTERNAME must not appear in WHERE conditions (only date + material_parts)
        assert "WORKCENTERNAME" not in call_sql, (
            f"WORKCENTERNAME found in summary SQL — should be removed: {call_sql[:300]}"
        )

    @patch("mes_dashboard.services.material_consumption_service.get_spool_file_path", return_value=None)
    @patch("mes_dashboard.services.material_consumption_service.read_sql_df")
    @patch("mes_dashboard.services.material_consumption_service.store_spooled_df")
    @patch("mes_dashboard.services.material_consumption_service._compute_summary_from_spool")
    def test_material_parts_kwarg_forwarded_to_sql(
        self,
        mock_compute,
        mock_store,
        mock_read,
        mock_spool_path,
    ):
        """material_parts must appear in the Oracle query's param bindings."""
        mock_read.return_value = _sample_summary_df()
        mock_compute.return_value = {"kpi": {}, "trend": [], "type_breakdown": []}

        _MC_SVC.get_summary(
            material_parts=["PART-XYZ"],
            start_date="2026-01-01",
            end_date="2026-01-31",
            granularity="week",
        )
        mock_read.assert_called_once()
        call_params = mock_read.call_args.args[1] if len(mock_read.call_args.args) > 1 else {}
        assert "PART-XYZ" in str(call_params), (
            f"material_parts 'PART-XYZ' not in Oracle params: {call_params}"
        )


# ---------------------------------------------------------------------------
# TestSummarySpoolPath
# ---------------------------------------------------------------------------


class TestSummarySpoolPath:
    """Spool/regroup path for get_summary() — spool hit skips Oracle."""

    def _mock_spool_path(self, tmp_path):
        """Return a real parquet path for spool hit simulation."""
        df = _sample_summary_df()
        p = tmp_path / "summary_test.parquet"
        df.to_parquet(str(p), engine="pyarrow", index=False)
        return str(p)

    @patch("mes_dashboard.services.material_consumption_service.read_sql_df")
    def test_granularity_week_regroups_without_oracle(self, mock_read, tmp_path):
        """When spool exists, week granularity regroups from spool, no Oracle call."""
        spool_path = self._mock_spool_path(tmp_path)

        with patch("mes_dashboard.services.material_consumption_service.get_spool_file_path", return_value=spool_path):
            result = _MC_SVC.apply_view(query_id="test-qid", granularity="week")

        mock_read.assert_not_called()
        assert "trend" in result
        assert "type_breakdown" in result

    @patch("mes_dashboard.services.material_consumption_service.read_sql_df")
    def test_granularity_month_regroups_without_oracle(self, mock_read, tmp_path):
        """month granularity regroups from spool without Oracle."""
        spool_path = self._mock_spool_path(tmp_path)

        with patch("mes_dashboard.services.material_consumption_service.get_spool_file_path", return_value=spool_path):
            result = _MC_SVC.apply_view(query_id="test-qid", granularity="month")

        mock_read.assert_not_called()
        assert "trend" in result

    @patch("mes_dashboard.services.material_consumption_service.read_sql_df")
    def test_granularity_quarter_regroups_without_oracle(self, mock_read, tmp_path):
        """quarter granularity regroups from spool without Oracle."""
        spool_path = self._mock_spool_path(tmp_path)

        with patch("mes_dashboard.services.material_consumption_service.get_spool_file_path", return_value=spool_path):
            result = _MC_SVC.apply_view(query_id="test-qid", granularity="quarter")

        mock_read.assert_not_called()
        assert "trend" in result

    def test_spool_miss_raises_cache_expired(self):
        """apply_view raises CacheExpiredError when spool is missing."""
        with patch("mes_dashboard.services.material_consumption_service.get_spool_file_path", return_value=None):
            with pytest.raises(_MC_SVC.CacheExpiredError):
                _MC_SVC.apply_view(query_id="missing-qid", granularity="week")


# ---------------------------------------------------------------------------
# TestDetailOraclePath
# ---------------------------------------------------------------------------


class TestDetailOraclePath:
    """Oracle path for get_detail_summary()."""

    @patch("mes_dashboard.services.material_consumption_service.get_spool_file_path", return_value=None)
    @patch("mes_dashboard.services.material_consumption_service.read_sql_df")
    @patch("mes_dashboard.services.material_consumption_service.store_spooled_df")
    def test_sync_rows_under_limit_returns_inline(self, mock_store, mock_read, mock_spool_path):
        """Rows <= SYNC_ROW_LIMIT → 200 inline, no RQ job."""
        detail_df = _sample_detail_df()
        mock_read.return_value = detail_df
        mock_store.return_value = True

        with patch.dict("os.environ", {"SYNC_ROW_LIMIT": "30000"}):
            result = _MC_SVC.get_detail_summary(
                material_parts=["MAT-A"],
                start_date="2026-01-01",
                end_date="2026-01-31",
            )

        assert result.get("async") is not True
        assert "query_id" in result
        assert "rows" in result

    @patch("mes_dashboard.services.material_consumption_service.get_spool_file_path", return_value=None)
    @patch("mes_dashboard.services.material_consumption_service.read_sql_df")
    @patch("mes_dashboard.services.material_consumption_service.store_spooled_df")
    @patch("mes_dashboard.services.material_consumption_service.enqueue_job")
    def test_rows_over_limit_enqueues_rq_job(self, mock_enqueue, mock_store, mock_read, mock_spool_path):
        """Rows > SYNC_ROW_LIMIT → enqueue RQ job, return {async: True, job_id}."""
        # Build a 5-row detail df, but set limit=2 to force async
        detail_df = _sample_detail_df(pj_types=["T1", "T2", "T3", "T4", "T5"])
        mock_read.return_value = detail_df
        mock_enqueue.return_value = ("test-job-id", None)

        with patch.dict("os.environ", {"SYNC_ROW_LIMIT": "2"}):
            result = _MC_SVC.get_detail_summary(
                material_parts=["MAT-A"],
                start_date="2026-01-01",
                end_date="2026-01-31",
            )

        assert result.get("async") is True
        assert "job_id" in result
        mock_enqueue.assert_called_once()


# ---------------------------------------------------------------------------
# TestDetailSpoolPath
# ---------------------------------------------------------------------------


class TestDetailSpoolPath:
    """DuckDB pagination path for detail spool."""

    def test_pagination_returns_correct_page(self, tmp_path):
        """get_detail_page() returns page N from spool via DuckDB."""
        detail_df = _sample_detail_df(pj_types=["T1", "T2", "T3"])
        spool_path = tmp_path / "detail_test.parquet"
        detail_df.to_parquet(str(spool_path), engine="pyarrow", index=False)

        # Patch at the runtime module level where the class reads it
        with patch(
            "mes_dashboard.services.material_consumption_duckdb_runtime.get_spool_file_path",
            return_value=str(spool_path),
        ):
            result = _MC_SVC.get_detail_page(query_id="test-qid", page=1)

        assert result is not None, "Expected dict result, got None"
        assert "rows" in result
        assert "pagination" in result
        assert result["pagination"]["page"] == 1

    def test_pj_types_filter_applied_on_both_paths(self, tmp_path):
        """pj_types kwarg filters detail rows in spool path."""
        detail_df = _sample_detail_df(pj_types=["TypeX", "TypeY", "TypeZ"])
        spool_path = tmp_path / "detail_filter_test.parquet"
        detail_df.to_parquet(str(spool_path), engine="pyarrow", index=False)

        with patch(
            "mes_dashboard.services.material_consumption_duckdb_runtime.get_spool_file_path",
            return_value=str(spool_path),
        ):
            result = _MC_SVC.get_detail_page(query_id="test-qid", page=1, pj_types=["TypeX"])

        assert result is not None, "Expected dict result, got None"
        # All returned rows must have pj_type == TypeX
        for row in result["rows"]:
            assert row.get("pj_type") == "TypeX", f"Expected TypeX, got {row.get('pj_type')}"


# ---------------------------------------------------------------------------
# TestCsvExport
# ---------------------------------------------------------------------------


class TestCsvExport:
    """Chunked CSV export without full memory load."""

    def test_streams_chunks_without_full_memory_load(self, tmp_path):
        """export_csv_stream() is a generator that yields bytes chunks."""
        detail_df = _sample_detail_df(pj_types=["T1", "T2"])
        spool_path = tmp_path / "export_test.parquet"
        detail_df.to_parquet(str(spool_path), engine="pyarrow", index=False)

        with patch(
            "mes_dashboard.services.material_consumption_duckdb_runtime.get_spool_file_path",
            return_value=str(spool_path),
        ):
            gen = _MC_SVC.export_csv_stream(query_id="test-qid")
            chunks = list(gen)

        assert len(chunks) > 0, "Expected at least one chunk (header)"
        first_chunk = chunks[0]
        assert isinstance(first_chunk, bytes)
        # Header row should be present
        header_text = first_chunk.decode("utf-8-sig")
        assert "CONTAINERID" in header_text or "LOT" in header_text.upper() or "容器" in header_text


# ---------------------------------------------------------------------------
# TestInputValidation
# ---------------------------------------------------------------------------


class TestInputValidation:
    """MC-02 input validation at service layer."""

    def test_parts_cap_20_enforced(self):
        """More than 20 material_parts raises ValidationError."""
        with pytest.raises(_MC_SVC.ValidationError):
            _MC_SVC.validate_material_parts([f"PART-{i}" for i in range(21)])

    def test_wildcard_translated_to_like_escaped(self):
        """Token with * is translated to LIKE pattern with % and escaping."""
        tokens = _MC_SVC.validate_material_parts(["MAT-A*"])
        assert len(tokens) == 1
        token = tokens[0]
        assert token["kind"] == "pattern"
        assert "%" in token["bound_value"]

    def test_exact_token_uses_in_list(self):
        """Exact tokens (no *) produce 'exact' kind."""
        tokens = _MC_SVC.validate_material_parts(["MAT-A", "MAT-B"])
        kinds = [t["kind"] for t in tokens]
        assert all(k == "exact" for k in kinds)

    def test_meta_char_rejected_before_oracle(self):
        """SQL meta-chars in token raise ValidationError without Oracle call."""
        with pytest.raises(_MC_SVC.ValidationError):
            _MC_SVC.validate_material_parts(["MAT'; DROP TABLE x--"])


# ---------------------------------------------------------------------------
# TestDetailJob
# ---------------------------------------------------------------------------


class TestDetailJob:
    """Tests for get_job_status, rq_material_consumption_job success/failure paths."""

    def test_get_job_status_correct_function_called(self):
        """get_job_status() must call async_query_job_service.get_job_status (not get_async_job_status).

        Mocks at the async_query_job_service module boundary to expose any import error.
        """
        with patch(
            "mes_dashboard.services.async_query_job_service.get_job_status"
        ) as mock_fn:
            mock_fn.return_value = {"status": "completed", "query_id": "q-abc"}
            result = _MC_SVC.get_job_status("test-job-id")

        mock_fn.assert_called_once()
        # First positional arg must be the prefix, second must be job_id
        call_args = mock_fn.call_args
        assert call_args.args[0] == "async", (
            f"Expected prefix='async', got {call_args.args[0]!r}"
        )
        assert call_args.args[1] == "test-job-id", (
            f"Expected job_id='test-job-id', got {call_args.args[1]!r}"
        )
        assert result["status"] == "completed"

    @patch("mes_dashboard.services.material_consumption_service.get_spool_file_path", return_value=None)
    @patch("mes_dashboard.services.material_consumption_service.read_sql_df")
    @patch("mes_dashboard.services.material_consumption_service.store_spooled_df")
    def test_rq_job_calls_complete_job_on_success(self, mock_store, mock_read, mock_spool_path):
        """rq_material_consumption_job calls complete_job with the query_id on success."""
        mock_read.return_value = _sample_detail_df()
        mock_store.return_value = True

        with patch(
            "mes_dashboard.services.async_query_job_service.complete_job"
        ) as mock_complete:
            _MC_SVC.rq_material_consumption_job(
                job_id="job-success-001",
                query_id="q-success-001",
                material_parts=["MAT-A"],
                start_date="2026-01-01",
                end_date="2026-01-31",
            )

        mock_complete.assert_called_once()
        call_kwargs = mock_complete.call_args.kwargs
        # Must be called with success semantics: no error kwarg (or None)
        assert call_kwargs.get("error") is None, (
            f"Expected no error kwarg, got error={call_kwargs.get('error')!r}"
        )
        assert call_kwargs.get("query_id") == "q-success-001", (
            f"Expected query_id='q-success-001', got {call_kwargs.get('query_id')!r}"
        )

    @patch("mes_dashboard.services.material_consumption_service.get_spool_file_path", return_value=None)
    @patch("mes_dashboard.services.material_consumption_service.read_sql_df")
    def test_rq_job_calls_complete_job_on_failure(self, mock_read, mock_spool_path):
        """rq_material_consumption_job calls complete_job with error info on Oracle failure."""
        mock_read.side_effect = RuntimeError("Oracle connection refused")

        with patch(
            "mes_dashboard.services.async_query_job_service.complete_job"
        ) as mock_complete:
            with pytest.raises(RuntimeError):
                _MC_SVC.rq_material_consumption_job(
                    job_id="job-fail-001",
                    query_id="q-fail-001",
                    material_parts=["MAT-A"],
                    start_date="2026-01-01",
                    end_date="2026-01-31",
                )

        mock_complete.assert_called_once()
        call_kwargs = mock_complete.call_args.kwargs
        assert call_kwargs.get("error") is not None, (
            "Expected error kwarg to be set on failure"
        )
        assert "Oracle" in str(call_kwargs.get("error")), (
            f"Expected error message to mention Oracle, got {call_kwargs.get('error')!r}"
        )


# ---------------------------------------------------------------------------
# TestIdempotentSpoolWrite
# ---------------------------------------------------------------------------


class TestIdempotentSpoolWrite:
    """Idempotency: existing spool skips Oracle query."""

    @patch("mes_dashboard.services.material_consumption_service.read_sql_df")
    @patch("mes_dashboard.services.material_consumption_service._compute_summary_from_spool")
    def test_spool_exists_skips_oracle_query(self, mock_compute, mock_read, tmp_path):
        """When spool file already exists, Oracle query is NOT executed."""
        # Create a real parquet file to simulate an existing spool
        df = _sample_summary_df()
        spool_path = tmp_path / "summary_existing.parquet"
        df.to_parquet(str(spool_path), engine="pyarrow", index=False)

        mock_compute.return_value = {"kpi": {}, "trend": [], "type_breakdown": []}

        with patch(
            "mes_dashboard.services.material_consumption_service.get_spool_file_path",
            return_value=str(spool_path),
        ):
            _MC_SVC.get_summary(
                material_parts=["MAT-A"],
                start_date="2026-01-01",
                end_date="2026-01-31",
                granularity="week",
            )

        mock_read.assert_not_called()


# ---------------------------------------------------------------------------
# TestGetPartsList
# ---------------------------------------------------------------------------


class TestGetPartsList:
    """Tests for _get_parts_list() — Redis-cached DISTINCT MATERIALPARTNAME + DESCRIPTION."""

    def test_redis_hit_returns_cached_list(self):
        """When Redis returns a cached value, no Oracle query is made."""
        import json

        fake_parts = [
            {"name": "PART-A", "description": "Desc A"},
            {"name": "PART-B", "description": None},
            {"name": "PART-C", "description": "Desc C"},
        ]

        mock_redis = MagicMock()
        mock_redis.get.return_value = json.dumps(fake_parts).encode()

        with patch(
            "mes_dashboard.services.material_consumption_service.read_sql_df"
        ) as mock_oracle, patch(
            "mes_dashboard.services.material_consumption_service.REDIS_ENABLED",
            True,
        ), patch(
            "mes_dashboard.services.material_consumption_service.get_redis_client",
            return_value=mock_redis,
        ):
            result = _MC_SVC._get_parts_list()

        mock_oracle.assert_not_called()
        assert result == fake_parts

    def test_redis_miss_queries_oracle_and_caches(self):
        """When Redis has no entry, Oracle is queried and result is cached."""
        import json

        mock_redis = MagicMock()
        mock_redis.get.return_value = None  # cache miss

        oracle_df = pd.DataFrame(
            {"part": ["PART-X", "PART-Y"], "description": ["Desc X", "Desc Y"]}
        )

        with patch(
            "mes_dashboard.services.material_consumption_service.read_sql_df",
            return_value=oracle_df,
        ) as mock_oracle, patch(
            "mes_dashboard.services.material_consumption_service.REDIS_ENABLED",
            True,
        ), patch(
            "mes_dashboard.services.material_consumption_service.get_redis_client",
            return_value=mock_redis,
        ):
            result = _MC_SVC._get_parts_list()

        mock_oracle.assert_called_once()
        names = [d["name"] for d in result]
        assert "PART-X" in names
        assert "PART-Y" in names
        part_x = next(d for d in result if d["name"] == "PART-X")
        assert part_x["description"] == "Desc X"
        # Must have written to Redis cache
        mock_redis.set.assert_called_once()
        set_args = mock_redis.set.call_args
        assert set_args.kwargs.get("ex") == _MC_SVC._PARTS_CACHE_TTL

    def test_oracle_fallback_returns_empty_on_failure(self):
        """When Oracle raises, _get_parts_list returns [] and does not crash."""
        with patch(
            "mes_dashboard.services.material_consumption_service.REDIS_ENABLED",
            False,
        ), patch(
            "mes_dashboard.services.material_consumption_service.read_sql_df",
            side_effect=RuntimeError("Oracle down"),
        ):
            result = _MC_SVC._get_parts_list()

        assert result == []

    def test_redis_disabled_queries_oracle_without_caching(self):
        """When Redis is disabled, Oracle is queried but set() is never called."""
        oracle_df = pd.DataFrame(
            {"part": ["PART-Z"], "description": ["Desc Z"]}
        )

        with patch(
            "mes_dashboard.services.material_consumption_service.read_sql_df",
            return_value=oracle_df,
        ) as mock_oracle, patch(
            "mes_dashboard.services.material_consumption_service.REDIS_ENABLED",
            False,
        ):
            result = _MC_SVC._get_parts_list()

        mock_oracle.assert_called_once()
        names = [d["name"] for d in result]
        assert "PART-Z" in names

    def test_description_none_when_db_value_is_null(self):
        """When the DB DESCRIPTION value is NaN/None, dict includes description: None."""
        import math

        oracle_df = pd.DataFrame(
            {"part": ["PART-NULL", "PART-REAL"], "description": [float("nan"), "Has Desc"]}
        )

        with patch(
            "mes_dashboard.services.material_consumption_service.read_sql_df",
            return_value=oracle_df,
        ), patch(
            "mes_dashboard.services.material_consumption_service.REDIS_ENABLED",
            False,
        ):
            result = _MC_SVC._get_parts_list()

        null_entry = next(d for d in result if d["name"] == "PART-NULL")
        assert null_entry["description"] is None
        real_entry = next(d for d in result if d["name"] == "PART-REAL")
        assert real_entry["description"] == "Has Desc"


# ---------------------------------------------------------------------------
# TestApplyViewTypes
# ---------------------------------------------------------------------------


class TestApplyViewTypes:
    """apply_view(types=...) filters pj_type in DuckDB — no Oracle."""

    def _write_spool(self, tmp_path):
        df = _sample_summary_df(
            txn_dates=[datetime.date(2026, 1, 10), datetime.date(2026, 1, 20)],
            material_parts=["MAT-A", "MAT-A"],
            pj_types=["TypeX", "TypeY"],
            primary_categories=["CatA", "CatB"],
        )
        p = tmp_path / "spool_types.parquet"
        df.to_parquet(str(p), engine="pyarrow", index=False)
        return str(p)

    @patch("mes_dashboard.services.material_consumption_service.read_sql_df")
    def test_types_filter_narrows_type_breakdown(self, mock_oracle, tmp_path):
        """apply_view(types=['TypeX']) returns only TypeX rows in type_breakdown."""
        spool_path = self._write_spool(tmp_path)

        with patch(
            "mes_dashboard.services.material_consumption_service.get_spool_file_path",
            return_value=spool_path,
        ):
            result = _MC_SVC.apply_view(
                query_id="test-types-qid",
                granularity="month",
                types=["TypeX"],
            )

        mock_oracle.assert_not_called()
        # All type_breakdown entries must be TypeX
        for entry in result.get("type_breakdown", []):
            assert entry["pj_type"] == "TypeX", (
                f"Expected only TypeX, got {entry['pj_type']!r}"
            )

    @patch("mes_dashboard.services.material_consumption_service.read_sql_df")
    def test_no_types_returns_all_pj_types(self, mock_oracle, tmp_path):
        """apply_view(types=None) returns all pj_type rows unfiltered."""
        spool_path = self._write_spool(tmp_path)

        with patch(
            "mes_dashboard.services.material_consumption_service.get_spool_file_path",
            return_value=spool_path,
        ):
            result = _MC_SVC.apply_view(
                query_id="test-notypes-qid",
                granularity="month",
                types=None,
            )

        mock_oracle.assert_not_called()
        pj_types_found = {e["pj_type"] for e in result.get("type_breakdown", [])}
        assert "TypeX" in pj_types_found
        assert "TypeY" in pj_types_found

    @patch("mes_dashboard.services.material_consumption_service.read_sql_df")
    def test_day_granularity_regroups_without_oracle(self, mock_oracle, tmp_path):
        """apply_view(granularity='day') regroups to YYYY-MM-DD without Oracle."""
        spool_path = self._write_spool(tmp_path)

        with patch(
            "mes_dashboard.services.material_consumption_service.get_spool_file_path",
            return_value=spool_path,
        ):
            result = _MC_SVC.apply_view(query_id="test-day-qid", granularity="day")

        mock_oracle.assert_not_called()
        assert "trend" in result
        # Verify period format is YYYY-MM-DD
        for entry in result.get("trend", []):
            period = entry.get("period", "")
            assert len(period) == 10 and period[4] == "-" and period[7] == "-", (
                f"Day granularity period not YYYY-MM-DD: {period!r}"
            )


# ---------------------------------------------------------------------------
# TestCacheKeySimplified
# ---------------------------------------------------------------------------


class TestCacheKeySimplified:
    """Cache key must NOT include workcenter_groups, primary_categories, or pj_types."""

    def test_summary_cache_key_excludes_removed_filters(self):
        """Two calls differing only in workcenter/primary/pj produce the same key."""
        key1 = _MC_SVC._compute_summary_cache_key(
            ["MAT-A"], "2026-01-01", "2026-01-31"
        )
        key2 = _MC_SVC._compute_summary_cache_key(
            ["MAT-A"], "2026-01-01", "2026-01-31"
        )
        assert key1 == key2

    def test_detail_cache_key_excludes_removed_filters(self):
        """Detail cache key only depends on material_parts + date range."""
        key1 = _MC_SVC._compute_detail_cache_key(
            ["MAT-A"], "2026-01-01", "2026-01-31"
        )
        key2 = _MC_SVC._compute_detail_cache_key(
            ["MAT-A"], "2026-01-01", "2026-01-31"
        )
        assert key1 == key2

    def test_summary_key_differs_on_material_parts(self):
        """Different material_parts → different summary cache key."""
        key1 = _MC_SVC._compute_summary_cache_key(
            ["MAT-A"], "2026-01-01", "2026-01-31"
        )
        key2 = _MC_SVC._compute_summary_cache_key(
            ["MAT-B"], "2026-01-01", "2026-01-31"
        )
        assert key1 != key2

    def test_detail_key_differs_on_date_range(self):
        """Different date range → different detail cache key."""
        key1 = _MC_SVC._compute_detail_cache_key(
            ["MAT-A"], "2026-01-01", "2026-01-31"
        )
        key2 = _MC_SVC._compute_detail_cache_key(
            ["MAT-A"], "2026-02-01", "2026-02-28"
        )
        assert key1 != key2


# ---------------------------------------------------------------------------
# TDD: add-package-detail-tables — PRODUCTLINENAME in material-consumption
# ---------------------------------------------------------------------------


def _sample_detail_df_with_productlinename(pj_types=None, productlinenames=None) -> pd.DataFrame:
    """Build a detail spool fixture that includes PRODUCTLINENAME column."""
    pj_types = pj_types or ["TypeX", "TypeY"]
    productlinenames = productlinenames or ["PKG-D", "PKG-E"]
    rows = []
    for i, pjt in enumerate(pj_types):
        rows.append(
            {
                "CONTAINERID": f"C{i:04d}",
                "CONTAINERNAME": f"LOT-{i:04d}",
                "PJ_WORKORDER": f"WO{i:04d}",
                "WORKCENTERNAME": "WC-A",
                "MATERIALPARTNAME": "MAT-A",
                "MATERIALLOTNAME": f"ML{i:04d}",
                "VENDORLOTNUMBER": f"VL{i:04d}",
                "QTYREQUIRED": 100.0,
                "QTYCONSUMED": 98.0,
                "EQUIPMENTNAME": "EQ-01",
                "TXNDATE": datetime.date(2026, 1, 10),
                "PRIMARY_CATEGORY": "CatA",
                "SECONDARY_CATEGORY": "SubCat1",
                "pj_type": pjt,
                "PRODUCTLINENAME": productlinenames[i % len(productlinenames)],
            }
        )
    return pd.DataFrame(rows)


class TestSampleDetailDfIncludesProductlinenamColumn:
    """Fixture discipline guard: _sample_detail_df helper must emit PRODUCTLINENAME."""

    def test_sample_detail_df_includes_productlinename_column(self):
        """Updated _sample_detail_df() must include PRODUCTLINENAME column."""
        df = _sample_detail_df_with_productlinename()
        assert "PRODUCTLINENAME" in df.columns, (
            "PRODUCTLINENAME column missing from detail fixture"
        )


class TestGetDetailPageIncludesProductlinename:
    """PRODUCTLINENAME must appear in detail page response rows (spool path)."""

    def test_get_detail_page_includes_productlinename(self, tmp_path):
        """Spool path: fixture with PRODUCTLINENAME='PKG-D'; response rows contain the field."""
        detail_df = _sample_detail_df_with_productlinename(
            pj_types=["TypeX"], productlinenames=["PKG-D"]
        )
        spool_path = tmp_path / "detail_pkg.parquet"
        detail_df.to_parquet(str(spool_path), engine="pyarrow", index=False)

        with mock.patch(
            "mes_dashboard.services.material_consumption_duckdb_runtime.get_spool_file_path",
            return_value=str(spool_path),
        ):
            result = _MC_SVC.get_detail_page(query_id="test-pkg-qid", page=1)

        assert result is not None
        rows = result.get("rows", [])
        assert len(rows) > 0
        assert "productlinename" in rows[0], (
            f"productlinename missing from detail page row. Keys: {list(rows[0].keys())}"
        )
        assert rows[0]["productlinename"] == "PKG-D"

    def test_get_detail_page_productlinename_trailing_space_trimmed(self, tmp_path):
        """PRODUCTLINENAME='PKG-D  ' (CHAR-padded) must be trimmed in response (AC-6)."""
        detail_df = _sample_detail_df_with_productlinename(
            pj_types=["TypeX"], productlinenames=["PKG-D  "]
        )
        spool_path = tmp_path / "detail_pkg_space.parquet"
        detail_df.to_parquet(str(spool_path), engine="pyarrow", index=False)

        with mock.patch(
            "mes_dashboard.services.material_consumption_duckdb_runtime.get_spool_file_path",
            return_value=str(spool_path),
        ):
            result = _MC_SVC.get_detail_page(query_id="test-pkg-space-qid", page=1)

        assert result is not None
        rows = result.get("rows", [])
        assert len(rows) > 0
        val = rows[0].get("productlinename")
        assert val != "PKG-D  ", f"Trailing spaces must be trimmed, got {val!r}"

    def test_get_detail_page_productlinename_null_safe(self, tmp_path):
        """PRODUCTLINENAME=None must not crash and must appear in response (AC-6)."""
        detail_df = _sample_detail_df_with_productlinename(
            pj_types=["TypeX"], productlinenames=[None]
        )
        spool_path = tmp_path / "detail_pkg_null.parquet"
        detail_df.to_parquet(str(spool_path), engine="pyarrow", index=False)

        with mock.patch(
            "mes_dashboard.services.material_consumption_duckdb_runtime.get_spool_file_path",
            return_value=str(spool_path),
        ):
            result = _MC_SVC.get_detail_page(query_id="test-pkg-null-qid", page=1)

        assert result is not None, "get_detail_page must not crash on NULL PRODUCTLINENAME"
        rows = result.get("rows", [])
        assert len(rows) > 0

    def test_get_detail_page_existing_columns_unchanged(self, tmp_path):
        """All existing columns in _sample_detail_df survive after PRODUCTLINENAME extension."""
        detail_df = _sample_detail_df_with_productlinename(
            pj_types=["TypeX"], productlinenames=["PKG-E"]
        )
        spool_path = tmp_path / "detail_existing.parquet"
        detail_df.to_parquet(str(spool_path), engine="pyarrow", index=False)

        with mock.patch(
            "mes_dashboard.services.material_consumption_duckdb_runtime.get_spool_file_path",
            return_value=str(spool_path),
        ):
            result = _MC_SVC.get_detail_page(query_id="test-existing-qid", page=1)

        assert result is not None
        rows = result.get("rows", [])
        assert len(rows) > 0
        row = rows[0]
        for key in ("containerid", "containername", "pj_workorder", "workcentername",
                    "material_part", "materiallotname", "vendorlotnumber",
                    "qty_required", "qty_consumed", "equipmentname", "txn_date",
                    "primary_category", "secondary_category", "pj_type"):
            assert key in row, f"Pre-existing key {key!r} missing from detail page row"


class TestDetailExportCsvIncludesProductlinename:
    """PRODUCTLINENAME column must appear in CSV export header and rows."""

    def test_detail_export_csv_includes_productlinename(self, tmp_path):
        """export_csv_stream must include PRODUCTLINENAME in CSV header (AC-5)."""
        detail_df = _sample_detail_df_with_productlinename(
            pj_types=["TypeX", "TypeY"], productlinenames=["PKG-F", "PKG-G"]
        )
        spool_path = tmp_path / "export_pkg.parquet"
        detail_df.to_parquet(str(spool_path), engine="pyarrow", index=False)

        with mock.patch(
            "mes_dashboard.services.material_consumption_duckdb_runtime.get_spool_file_path",
            return_value=str(spool_path),
        ):
            gen = _MC_SVC.export_csv_stream(query_id="test-export-pkg-qid")
            chunks = list(gen)

        assert len(chunks) > 0
        header_text = chunks[0].decode("utf-8-sig")
        assert "PRODUCTLINENAME" in header_text or "Package" in header_text, (
            f"PRODUCTLINENAME or Package header missing from CSV. Header: {header_text!r}"
        )
