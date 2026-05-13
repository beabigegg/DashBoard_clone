# -*- coding: utf-8 -*-
"""Tests for resource-history pre-warm job (resource-history-perf).

Tests cover:
  - AC-2: correct date-chunk generation for N months
  - AC-4: Oracle unreachable → logs warning, no exception
  - AC-8: skip_cached=True → cached chunks are not re-fetched
"""

import logging
import sys
import os
from datetime import date, timedelta
from typing import List, Dict
from unittest.mock import MagicMock, patch, call

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


# ============================================================
# Helpers
# ============================================================

def _build_expected_chunks(months: int) -> List[Dict[str, str]]:
    """Reproduce the same date-range logic as prewarm_last_n_months."""
    from mes_dashboard.services.batch_query_engine import decompose_by_time_range
    end = date.today()
    start = end - timedelta(days=months * 31)
    return decompose_by_time_range(start.isoformat(), end.isoformat())


# ============================================================
# TestResourceHistoryPrewarm
# ============================================================

class TestResourceHistoryPrewarm:
    """Unit tests for _warmup_resource_history_job and prewarm_last_n_months."""

    def test_prewarm_generates_correct_date_chunks(self):
        """N months → approximately N 31-day chunks (one per month)."""
        from mes_dashboard.services.resource_history_service import prewarm_last_n_months

        months = 3
        expected_chunks = _build_expected_chunks(months)

        executed_chunks = []

        def _fake_execute_plan(chunks, query_fn, *, skip_cached, cache_prefix, chunk_ttl, **kwargs):
            executed_chunks.extend(chunks)
            return "fakehash"

        with (
            patch(
                'mes_dashboard.services.resource_history_service._execute_prewarm_plan',
                side_effect=_fake_execute_plan,
            ),
            patch(
                'mes_dashboard.services.resource_history_service._get_filtered_resources',
                return_value=[{'RESOURCEID': 'R1', 'WORKCENTERNAME': 'WC1',
                               'RESOURCEFAMILYNAME': 'FAM1', 'RESOURCENAME': 'R1'}],
            ),
        ):
            prewarm_last_n_months(months=months)

        # Should have generated chunks that cover ~3 months of 31-day windows
        assert len(executed_chunks) >= months, (
            f"Expected at least {months} chunks, got {len(executed_chunks)}"
        )
        # All chunks must have chunk_start and chunk_end
        for chunk in executed_chunks:
            assert 'chunk_start' in chunk
            assert 'chunk_end' in chunk

    def test_prewarm_skips_cached_keys(self):
        """When skip_cached=True, chunks with existing Redis keys are not re-fetched."""
        from mes_dashboard.services.resource_history_service import prewarm_last_n_months

        call_log = []

        def _fake_execute_plan(chunks, query_fn, *, skip_cached, cache_prefix, chunk_ttl, **kwargs):
            call_log.append({'skip_cached': skip_cached, 'chunk_count': len(chunks)})
            return "fakehash"

        with (
            patch(
                'mes_dashboard.services.resource_history_service._execute_prewarm_plan',
                side_effect=_fake_execute_plan,
            ),
            patch(
                'mes_dashboard.services.resource_history_service._get_filtered_resources',
                return_value=[{'RESOURCEID': 'R1', 'WORKCENTERNAME': 'WC1',
                               'RESOURCEFAMILYNAME': 'FAM1', 'RESOURCENAME': 'R1'}],
            ),
        ):
            prewarm_last_n_months(months=2)

        # Every execute_plan call must have skip_cached=True
        assert len(call_log) > 0, "Expected at least one execute_plan call"
        for entry in call_log:
            assert entry['skip_cached'] is True, (
                "prewarm_last_n_months must always pass skip_cached=True"
            )

    def test_prewarm_survives_oracle_failure(self, caplog):
        """OracleDB error → logs warning, does NOT raise."""
        from mes_dashboard.services.resource_history_service import prewarm_last_n_months

        class FakeOracleError(Exception):
            pass

        def _raise_oracle(*args, **kwargs):
            raise FakeOracleError("ORA-12541: TNS:no listener")

        with (
            patch(
                'mes_dashboard.services.resource_history_service._execute_prewarm_plan',
                side_effect=_raise_oracle,
            ),
            patch(
                'mes_dashboard.services.resource_history_service._get_filtered_resources',
                return_value=[{'RESOURCEID': 'R1', 'WORKCENTERNAME': 'WC1',
                               'RESOURCEFAMILYNAME': 'FAM1', 'RESOURCENAME': 'R1'}],
            ),
            caplog.at_level(logging.WARNING, logger='mes_dashboard.resource_history'),
        ):
            # Must not raise
            prewarm_last_n_months(months=1)

        # Must have logged a warning
        assert any('prewarm' in r.message.lower() or 'ORA' in r.message or 'failed' in r.message.lower()
                   for r in caplog.records), (
            "Expected a warning log entry on Oracle failure"
        )


# ============================================================
# Integration-style: warmup scheduler job function
# ============================================================

class TestWarmupSchedulerJobFunction:
    """Verify _warmup_resource_history_job is registered in _WARMUP_JOBS."""

    def test_warmup_resource_history_job_in_warmup_jobs(self):
        """_warmup_resource_history_job must appear in _WARMUP_JOBS registry."""
        from mes_dashboard.core.spool_warmup_scheduler import _WARMUP_JOBS
        job_ids = [job_id for job_id, _ in _WARMUP_JOBS]
        assert 'warmup-resource-history' in job_ids, (
            f"'warmup-resource-history' not found in _WARMUP_JOBS. "
            f"Found: {job_ids}"
        )

    def test_warmup_resource_history_job_function_does_not_raise_on_oracle_error(self, caplog):
        """_warmup_resource_history_job must catch Oracle errors and log a warning."""
        from mes_dashboard.core.spool_warmup_scheduler import _warmup_resource_history_job

        class FakeOracleError(Exception):
            pass

        with (
            patch(
                'mes_dashboard.services.resource_history_service.prewarm_last_n_months',
                side_effect=FakeOracleError("ORA-12541"),
            ),
            caplog.at_level(logging.WARNING, logger='mes_dashboard.spool_warmup_scheduler'),
        ):
            # Must not raise
            _warmup_resource_history_job()

        assert any('resource_history' in r.message for r in caplog.records), (
            "Expected a warning log mentioning resource_history warmup failure"
        )
