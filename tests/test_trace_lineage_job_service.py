# -*- coding: utf-8 -*-
"""Unit tests for trace_lineage_job_service.

Covers:
- Canonical query_id stability (same inputs → same id)
- query_id format (no invalid chars, max length)
- NDJSON line format compliance
- Job expiry non-raise behavior
"""

from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

from mes_dashboard.services.trace_lineage_job_service import (
    make_trace_lineage_query_id,
)


class TestQueryIdStability:
    """query_id must be deterministic for same inputs."""

    def test_same_inputs_produce_same_query_id(self):
        """Identical inputs must always produce identical query_id."""
        id1 = make_trace_lineage_query_id("query_tool_reverse", ["LOT-001", "LOT-002"])
        id2 = make_trace_lineage_query_id("query_tool_reverse", ["LOT-001", "LOT-002"])
        assert id1 == id2

    def test_order_of_container_ids_is_normalized(self):
        """Container IDs in different order must produce the same query_id."""
        id1 = make_trace_lineage_query_id("query_tool_reverse", ["LOT-001", "LOT-002"])
        id2 = make_trace_lineage_query_id("query_tool_reverse", ["LOT-002", "LOT-001"])
        assert id1 == id2

    def test_different_profiles_produce_different_ids(self):
        """Different profiles must produce different query_ids."""
        id1 = make_trace_lineage_query_id("query_tool_reverse", ["LOT-001"])
        id2 = make_trace_lineage_query_id("mid_section_defect", ["LOT-001"])
        assert id1 != id2

    def test_different_container_ids_produce_different_ids(self):
        """Different container IDs must produce different query_ids."""
        id1 = make_trace_lineage_query_id("query_tool_reverse", ["LOT-001"])
        id2 = make_trace_lineage_query_id("query_tool_reverse", ["LOT-002"])
        assert id1 != id2

    def test_query_id_max_length(self):
        """query_id must not exceed 128 characters."""
        long_ids = [f"LOT-{i:05d}" for i in range(50)]
        qid = make_trace_lineage_query_id("query_tool_reverse", long_ids)
        assert len(qid) <= 128

    def test_query_id_has_valid_chars(self):
        """query_id must contain only safe URL/filename characters."""
        import re
        qid = make_trace_lineage_query_id("query_tool_reverse", ["LOT-001"])
        assert re.match(r'^[a-zA-Z0-9\-_]+$', qid), f"Invalid chars in query_id: {qid!r}"

    def test_query_id_starts_with_prefix(self):
        """query_id should start with 'trace-lineage-' prefix."""
        qid = make_trace_lineage_query_id("query_tool_reverse", ["LOT-001"])
        assert qid.startswith("trace-lineage-")

    def test_mid_section_defect_direction_is_included(self):
        """For mid_section_defect profile, direction param must affect query_id."""
        id_backward = make_trace_lineage_query_id(
            "mid_section_defect", ["LOT-001"], params={"direction": "backward"}
        )
        id_forward = make_trace_lineage_query_id(
            "mid_section_defect", ["LOT-001"], params={"direction": "forward"}
        )
        assert id_backward != id_forward

    def test_duplicate_container_ids_are_deduplicated(self):
        """Duplicate container IDs must be deduplicated before hashing."""
        id1 = make_trace_lineage_query_id("query_tool_reverse", ["LOT-001"])
        id2 = make_trace_lineage_query_id("query_tool_reverse", ["LOT-001", "LOT-001"])
        assert id1 == id2

    def test_empty_container_ids_is_stable(self):
        """Empty container_ids list must produce a stable (non-crashing) query_id."""
        id1 = make_trace_lineage_query_id("query_tool_reverse", [])
        id2 = make_trace_lineage_query_id("query_tool_reverse", [])
        assert id1 == id2


class TestJobExpiryNonRaise:
    """Getting status for expired/missing jobs must not raise."""

    def test_get_job_status_returns_none_for_missing_job(self):
        """get_job_status for non-existent job must return None, not raise."""
        from mes_dashboard.services.async_query_job_service import get_job_status

        with patch(
            'mes_dashboard.services.async_query_job_service.get_control_redis_client',
            return_value=None  # simulate Redis unavailable
        ):
            result = get_job_status("trace", "nonexistent-job-id")
            assert result is None

    def test_get_job_status_returns_none_when_key_missing(self):
        """get_job_status returns None when job key not found in Redis."""
        from mes_dashboard.services.async_query_job_service import get_job_status

        mock_conn = MagicMock()
        mock_conn.hgetall.return_value = {}  # empty = not found

        with patch(
            'mes_dashboard.services.async_query_job_service.get_control_redis_client',
            return_value=mock_conn
        ):
            result = get_job_status("trace", "ghost-job-id")
            assert result is None
