# -*- coding: utf-8 -*-
"""Route integration tests for the reject-history async query feature.

Covers:
- POST /api/reject-history/query  — cache-hit sync (200) and spool-miss async (202) paths,
  enqueue failure, container mode
- GET  /api/reject-history/job/<job_id> — found (200), not-found (404),
  completed status (200 with status/query_id fields)

All responses are verified against the standard JSON envelope:
  { success: bool, data: ..., error: { code, message }, meta: { timestamp } }
"""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch, MagicMock

import mes_dashboard.core.database as db
from mes_dashboard.app import create_app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse(response) -> dict:
    return json.loads(response.data)


# Short date range that stays within the 190-day limit but below the 10-day
# async threshold (so should_use_async returns False).
_SHORT_START = "2026-01-01"
_SHORT_END = "2026-01-05"      # 5-day span

# Long date range above the async threshold.
_LONG_START = "2026-01-01"
_LONG_END = "2026-01-31"       # 31-day span

_SYNC_RESULT = {
    "query_id": "qid-sync-001",
    "summary": {},
    "trend": [],
    "detail": {
        "items": [],
        "pagination": {"page": 1, "perPage": 50, "total": 0, "totalPages": 1},
    },
    "available_filters": {"workcenter_groups": [], "packages": [], "reasons": []},
    "meta": {},
}

_VALID_QUERY_BODY_SHORT = {
    "mode": "date_range",
    "start_date": _SHORT_START,
    "end_date": _SHORT_END,
    "include_excluded_scrap": False,
    "exclude_material_scrap": True,
    "exclude_pb_diode": True,
}

_VALID_QUERY_BODY_LONG = {
    "mode": "date_range",
    "start_date": _LONG_START,
    "end_date": _LONG_END,
    "include_excluded_scrap": False,
    "exclude_material_scrap": True,
    "exclude_pb_diode": True,
}


# ---------------------------------------------------------------------------
# TestRejectHistoryQueryRoute
# ---------------------------------------------------------------------------

class TestRejectHistoryQueryRoute(unittest.TestCase):

    def setUp(self):
        db._ENGINE = None
        self.app = create_app("testing")
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    # ------------------------------------------------------------------
    # Patch targets
    # ------------------------------------------------------------------
    _ENQUEUE = (
        "mes_dashboard.routes.reject_history_routes."
        "mes_dashboard.services.reject_query_job_service.enqueue_reject_query"
    )
    _EXECUTE = "mes_dashboard.routes.reject_history_routes.execute_primary_query"
    _GET_CACHED_DF = "mes_dashboard.routes.reject_history_routes._has_cached_df"
    _SLOW_QUERY_COUNT = (
        "mes_dashboard.routes.reject_history_routes.get_slow_query_active_count"
    )
    _MEMORY_GUARD = (
        "mes_dashboard.core.worker_memory_guard.get_memory_guard_telemetry"
    )

    # ------------------------------------------------------------------
    # 1. Short query — async 202 on spool miss
    # ------------------------------------------------------------------

    @patch("mes_dashboard.routes.reject_history_routes._has_cached_df", return_value=False)
    def test_short_query_returns_async_202_on_spool_miss(self, _mock_cache):
        """5-day date_range spool miss should enqueue async work."""
        fake_job_id = "reject-short-0001"
        with patch(
            "mes_dashboard.services.reject_query_job_service.enqueue_reject_query",
            return_value=(fake_job_id, None),
        ):
            response = self.client.post(
                "/api/reject-history/query", json=_VALID_QUERY_BODY_SHORT
            )
        payload = _parse(response)

        self.assertEqual(response.status_code, 202)
        self.assertTrue(payload["success"])
        self.assertEqual(payload["data"]["job_id"], fake_job_id)
        self.assertIn("query_id", payload["data"])

    # ------------------------------------------------------------------
    # 2. Long query — async 202
    # ------------------------------------------------------------------

    @patch("mes_dashboard.routes.reject_history_routes._has_cached_df", return_value=False)
    def test_long_query_returns_async_202(
        self, _mock_cache
    ):
        """31-day date_range spool miss should enqueue async work."""
        fake_job_id = "reject-deadbeef-0001"
        with patch(
            "mes_dashboard.services.reject_query_job_service.enqueue_reject_query",
            return_value=(fake_job_id, None),
        ):
            response = self.client.post(
                "/api/reject-history/query", json=_VALID_QUERY_BODY_LONG
            )

        payload = _parse(response)

        self.assertEqual(response.status_code, 202)
        self.assertTrue(payload["success"])
        self.assertIn("data", payload)
        self.assertIn("meta", payload)
        self.assertIn("timestamp", payload["meta"])

        data = payload["data"]
        self.assertIs(data.get("async"), True)
        self.assertEqual(data["job_id"], fake_job_id)
        self.assertIn("status_url", data)
        self.assertIn(fake_job_id, data["status_url"])
        self.assertIn("query_id", data)

    # ------------------------------------------------------------------
    # 3. Cache hit bypasses enqueue path
    # ------------------------------------------------------------------

    @patch("mes_dashboard.routes.reject_history_routes.execute_primary_query")
    def test_cache_hit_serves_sync_result(
        self, mock_execute
    ):
        """When _get_cached_df returns a DataFrame, route should reuse sync result."""
        import pandas as pd

        cached_df = pd.DataFrame({"col": [1, 2, 3]})
        mock_execute.return_value = _SYNC_RESULT

        with patch(
            "mes_dashboard.routes.reject_history_routes._has_cached_df",
            return_value=True,
        ):
            response = self.client.post(
                "/api/reject-history/query", json=_VALID_QUERY_BODY_SHORT
            )

        payload = _parse(response)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["success"])
        mock_execute.assert_called_once()

    # ------------------------------------------------------------------
    # 4. Async enqueue failure → 503
    # ------------------------------------------------------------------

    @patch("mes_dashboard.routes.reject_history_routes._has_cached_df", return_value=False)
    def test_async_enqueue_failure_returns_503(
        self, _mock_cache
    ):
        """enqueue failure should fail closed with 503 instead of falling back to sync."""
        with patch(
            "mes_dashboard.services.reject_query_job_service.enqueue_reject_query",
            return_value=(None, "Redis unavailable"),
        ):
            response = self.client.post(
                "/api/reject-history/query", json=_VALID_QUERY_BODY_LONG
            )
        payload = _parse(response)

        self.assertEqual(response.status_code, 503)
        self.assertFalse(payload["success"])
        self.assertIsInstance(payload["error"], dict)
        self.assertEqual(payload["error"]["code"], "SERVICE_UNAVAILABLE")
        self.assertIn("message", payload["error"])
        self.assertIn("Retry-After", response.headers)

    # ------------------------------------------------------------------
    # 5. Container mode — async 202 on spool miss
    # ------------------------------------------------------------------

    @patch("mes_dashboard.routes.reject_history_routes._has_cached_df", return_value=False)
    def test_container_mode_returns_async_202(self, _mock_cache):
        """container mode now also routes through the background spool pipeline."""
        fake_job_id = "reject-container-0001"
        with patch(
            "mes_dashboard.services.reject_query_job_service.enqueue_reject_query",
            return_value=(fake_job_id, None),
        ):
            response = self.client.post(
                "/api/reject-history/query",
                json={
                    "mode": "container",
                    "container_input_type": "lot",
                    "container_values": ["LOT-001", "LOT-002"],
                    "include_excluded_scrap": False,
                    "exclude_material_scrap": True,
                    "exclude_pb_diode": True,
                },
            )
        payload = _parse(response)

        self.assertEqual(response.status_code, 202)
        self.assertTrue(payload["success"])
        self.assertEqual(payload["data"]["job_id"], fake_job_id)


# ---------------------------------------------------------------------------
# TestRejectHistoryJobStatusRoute
# ---------------------------------------------------------------------------

class TestRejectHistoryJobStatusRoute(unittest.TestCase):

    def setUp(self):
        db._ENGINE = None
        self.app = create_app("testing")
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    _GET_JOB_STATUS = (
        "mes_dashboard.routes.reject_history_routes."
        "mes_dashboard.services.async_query_job_service.get_job_status"
    )

    # ------------------------------------------------------------------
    # 1. Job found → 200
    # ------------------------------------------------------------------

    def test_job_status_found(self):
        """get_job_status returns a dict → 200 with standard envelope."""
        fake_status = {
            "job_id": "reject-abc",
            "status": "running",
            "progress": 42,
        }
        with patch(
            "mes_dashboard.services.async_query_job_service.get_job_status",
            return_value=fake_status,
        ):
            response = self.client.get("/api/reject-history/job/reject-abc")

        payload = _parse(response)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["success"])
        self.assertIn("data", payload)
        self.assertIn("meta", payload)
        self.assertIn("timestamp", payload["meta"])
        self.assertEqual(payload["data"]["job_id"], "reject-abc")
        self.assertEqual(payload["data"]["status"], "running")

    # ------------------------------------------------------------------
    # 2. Job not found → 404
    # ------------------------------------------------------------------

    def test_job_status_not_found(self):
        """get_job_status returns None → 404 NOT_FOUND envelope."""
        with patch(
            "mes_dashboard.services.async_query_job_service.get_job_status",
            return_value=None,
        ):
            response = self.client.get("/api/reject-history/job/reject-missing-123")

        payload = _parse(response)

        self.assertEqual(response.status_code, 404)
        self.assertFalse(payload["success"])
        self.assertIsInstance(payload["error"], dict)
        self.assertEqual(payload["error"]["code"], "NOT_FOUND")
        self.assertIn("message", payload["error"])
        self.assertIn("meta", payload)
        self.assertIn("timestamp", payload["meta"])

    # ------------------------------------------------------------------
    # 3. Completed job — status and query_id present
    # ------------------------------------------------------------------

    def test_job_status_completed(self):
        """Completed job response includes status=completed and query_id."""
        fake_query_id = "qid-async-completed-001"
        fake_status = {
            "job_id": "reject-done-999",
            "status": "completed",
            "query_id": fake_query_id,
            "progress": 100,
        }
        with patch(
            "mes_dashboard.services.async_query_job_service.get_job_status",
            return_value=fake_status,
        ):
            response = self.client.get("/api/reject-history/job/reject-done-999")

        payload = _parse(response)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["success"])
        data = payload["data"]
        self.assertEqual(data["status"], "completed")
        self.assertEqual(data["query_id"], fake_query_id)


if __name__ == "__main__":
    unittest.main()
