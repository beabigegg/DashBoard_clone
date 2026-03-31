# -*- coding: utf-8 -*-
"""Route tests for yield-alert async query feature.

Covers:
- POST /api/yield-alert/query — cache hit (200), cache miss async (202),
  enqueue failure (503), sync fallback when RQ unavailable
- GET  /api/yield-alert/job/<job_id> — found (200), not-found (404)
"""

from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock, patch

import mes_dashboard.core.database as db
from mes_dashboard.app import create_app


def _parse(response) -> dict:
    return json.loads(response.data)


_VALID_QUERY_BODY = {
    "start_date": "2024-01-01",
    "end_date": "2024-02-01",
}

_SYNC_RESULT = {
    "query_id": "ya-sync-001",
    "meta": {"cache_hit": False},
}

_MOCK_CACHE_MODULE = "mes_dashboard.services.yield_alert_dataset_cache"


def _patch_cache(cache_hit: bool):
    """Return patchers for yield_alert_dataset_cache internals."""
    mock = MagicMock()
    mock._CACHE_SCHEMA_VERSION = 4
    mock._make_query_id.return_value = "ya-test-qid-001"
    mock._get_cached_payload.return_value = {"query_id": "ya-test-qid-001"} if cache_hit else None
    return mock


class TestYieldAlertQueryRoute(unittest.TestCase):

    def setUp(self):
        db._ENGINE = None
        self.app = create_app("testing")
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    # ------------------------------------------------------------------
    # 1. Cache miss → async 202
    # ------------------------------------------------------------------

    def test_cache_miss_returns_async_202(self):
        """Cache miss with RQ available should return 202 with job_id."""
        fake_job_id = "yield-alert-0001"

        with patch(
            "mes_dashboard.routes.yield_alert_routes.execute_primary_query",
        ), patch(
            f"{_MOCK_CACHE_MODULE}._CACHE_SCHEMA_VERSION", 4,
        ), patch(
            f"{_MOCK_CACHE_MODULE}._make_query_id",
            return_value="ya-test-qid-001",
        ), patch(
            f"{_MOCK_CACHE_MODULE}._get_cached_payload",
            return_value=None,  # cache miss
        ), patch(
            "mes_dashboard.services.async_query_job_service.is_async_available",
            return_value=True,
        ), patch(
            "mes_dashboard.services.yield_alert_job_service.YIELD_ALERT_ASYNC_ENABLED",
            True,
        ), patch(
            "mes_dashboard.services.yield_alert_job_service.enqueue_yield_alert_query",
            return_value=(fake_job_id, None),
        ):
            response = self.client.post(
                "/api/yield-alert/query", json=_VALID_QUERY_BODY
            )

        payload = _parse(response)
        self.assertEqual(response.status_code, 202)
        self.assertTrue(payload["success"])
        data = payload["data"]
        self.assertIs(data.get("async"), True)
        self.assertEqual(data["job_id"], fake_job_id)
        self.assertIn("status_url", data)
        self.assertIn(fake_job_id, data["status_url"])
        self.assertIn("query_id", data)

    # ------------------------------------------------------------------
    # 2. Cache hit → sync 200
    # ------------------------------------------------------------------

    def test_cache_hit_returns_sync_200(self):
        """Cache hit should bypass async and return 200 immediately."""
        with patch(
            f"{_MOCK_CACHE_MODULE}._CACHE_SCHEMA_VERSION", 4,
        ), patch(
            f"{_MOCK_CACHE_MODULE}._make_query_id",
            return_value="ya-hit-qid-001",
        ), patch(
            f"{_MOCK_CACHE_MODULE}._get_cached_payload",
            return_value={"query_id": "ya-hit-qid-001"},  # cache hit
        ), patch(
            "mes_dashboard.routes.yield_alert_routes.execute_primary_query",
            return_value=dict(_SYNC_RESULT),
        ):
            response = self.client.post(
                "/api/yield-alert/query", json=_VALID_QUERY_BODY
            )

        payload = _parse(response)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["success"])
        self.assertEqual(payload["data"]["query_id"], "ya-sync-001")

    # ------------------------------------------------------------------
    # 3. Enqueue failure → 503
    # ------------------------------------------------------------------

    def test_async_enqueue_failure_returns_503(self):
        """enqueue failure should return 503."""
        with patch(
            f"{_MOCK_CACHE_MODULE}._CACHE_SCHEMA_VERSION", 4,
        ), patch(
            f"{_MOCK_CACHE_MODULE}._make_query_id",
            return_value="ya-test-qid-002",
        ), patch(
            f"{_MOCK_CACHE_MODULE}._get_cached_payload",
            return_value=None,
        ), patch(
            "mes_dashboard.services.async_query_job_service.is_async_available",
            return_value=True,
        ), patch(
            "mes_dashboard.services.yield_alert_job_service.YIELD_ALERT_ASYNC_ENABLED",
            True,
        ), patch(
            "mes_dashboard.services.yield_alert_job_service.enqueue_yield_alert_query",
            return_value=(None, "Redis unavailable"),
        ):
            response = self.client.post(
                "/api/yield-alert/query", json=_VALID_QUERY_BODY
            )

        self.assertEqual(response.status_code, 503)

    # ------------------------------------------------------------------
    # 4. RQ unavailable → sync fallback
    # ------------------------------------------------------------------

    def test_rq_unavailable_falls_back_to_sync(self):
        """When RQ is unavailable, should fall back to sync execution."""
        with patch(
            f"{_MOCK_CACHE_MODULE}._CACHE_SCHEMA_VERSION", 4,
        ), patch(
            f"{_MOCK_CACHE_MODULE}._make_query_id",
            return_value="ya-test-qid-003",
        ), patch(
            f"{_MOCK_CACHE_MODULE}._get_cached_payload",
            return_value=None,
        ), patch(
            "mes_dashboard.services.async_query_job_service.is_async_available",
            return_value=False,
        ), patch(
            "mes_dashboard.routes.yield_alert_routes.execute_primary_query",
            return_value=dict(_SYNC_RESULT),
        ):
            response = self.client.post(
                "/api/yield-alert/query", json=_VALID_QUERY_BODY
            )

        payload = _parse(response)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["success"])


class TestYieldAlertJobStatusRoute(unittest.TestCase):

    def setUp(self):
        db._ENGINE = None
        self.app = create_app("testing")
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def test_job_found_returns_200_with_status(self):
        """GET /api/yield-alert/job/<job_id> should return status when job exists."""
        fake_status = {"status": "running", "progress": "querying Oracle", "pct": 40}

        with patch(
            "mes_dashboard.services.async_query_job_service.get_job_status",
            return_value=fake_status,
        ):
            response = self.client.get("/api/yield-alert/job/yield-alert-0001")

        payload = _parse(response)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["success"])
        self.assertEqual(payload["data"]["status"], "running")

    def test_job_not_found_returns_404(self):
        """GET /api/yield-alert/job/<job_id> should return 404 when job does not exist."""
        with patch(
            "mes_dashboard.services.async_query_job_service.get_job_status",
            return_value=None,
        ):
            response = self.client.get("/api/yield-alert/job/nonexistent-job")

        self.assertEqual(response.status_code, 404)

    def test_completed_job_returns_query_id(self):
        """GET /api/yield-alert/job/<job_id> returns query_id when completed."""
        fake_status = {
            "status": "completed",
            "query_id": "ya-result-001",
            "pct": 100,
        }

        with patch(
            "mes_dashboard.services.async_query_job_service.get_job_status",
            return_value=fake_status,
        ):
            response = self.client.get("/api/yield-alert/job/yield-alert-done")

        payload = _parse(response)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["data"]["query_id"], "ya-result-001")
        self.assertEqual(payload["data"]["status"], "completed")
