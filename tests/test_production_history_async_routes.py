# -*- coding: utf-8 -*-
"""Route tests for production-history async query feature.

Covers:
- POST /api/production-history/query — spool hit (200), spool miss async (202),
  enqueue failure (503), sync fallback when RQ unavailable
- GET  /api/production-history/job/<job_id> — found (200), not-found (404)
"""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch

import mes_dashboard.core.database as db
from mes_dashboard.app import create_app


def _parse(response) -> dict:
    return json.loads(response.data)


_VALID_QUERY_BODY = {
    "start_date": "2024-01-01",
    "end_date": "2024-02-01",
    "pj_types": ["PJ"],
}

_SYNC_RESULT = {
    "dataset_id": "ph-sync-001",
    "detail": {"rows": [], "pagination": {}},
    "matrix": {"tree": [], "month_columns": []},
    "meta": {},
}


class TestProductionHistoryQueryRoute(unittest.TestCase):

    def setUp(self):
        db._ENGINE = None
        self.app = create_app("testing")
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    # ------------------------------------------------------------------
    # 1. Spool miss → async 202
    # ------------------------------------------------------------------

    def test_spool_miss_returns_async_202(self):
        """Spool miss with RQ available should return 202 with job_id."""
        fake_job_id = "prod-hist-0001"

        with patch(
            "mes_dashboard.routes.production_history_routes.make_canonical_spool_id",
            return_value="ph-test-001",
        ), patch(
            "mes_dashboard.routes.production_history_routes.get_spool_file_path",
            return_value=None,  # spool miss
        ), patch(
            "mes_dashboard.services.async_query_job_service.is_async_available",
            return_value=True,
        ), patch(
            "mes_dashboard.services.production_history_job_service.PRODUCTION_HISTORY_ASYNC_ENABLED",
            True,
        ), patch(
            "mes_dashboard.services.production_history_job_service.enqueue_production_history_query",
            return_value=(fake_job_id, None),
        ):
            response = self.client.post(
                "/api/production-history/query", json=_VALID_QUERY_BODY
            )

        payload = _parse(response)
        self.assertEqual(response.status_code, 202)
        self.assertTrue(payload["success"])
        data = payload["data"]
        self.assertIs(data.get("async"), True)
        self.assertEqual(data["job_id"], fake_job_id)
        self.assertIn("status_url", data)
        self.assertIn(fake_job_id, data["status_url"])
        self.assertIn("dataset_id", data)

    # ------------------------------------------------------------------
    # 2. Spool hit → sync 200
    # ------------------------------------------------------------------

    def test_spool_hit_returns_sync_200(self):
        """Spool hit should bypass async and return 200 immediately."""
        with patch(
            "mes_dashboard.routes.production_history_routes.make_canonical_spool_id",
            return_value="ph-hit-001",
        ), patch(
            "mes_dashboard.routes.production_history_routes.get_spool_file_path",
            return_value="/some/path.parquet",  # spool hit
        ), patch(
            "mes_dashboard.routes.production_history_routes.query_production_history",
            return_value=dict(_SYNC_RESULT),
        ):
            response = self.client.post(
                "/api/production-history/query", json=_VALID_QUERY_BODY
            )

        payload = _parse(response)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["success"])
        self.assertEqual(payload["data"]["dataset_id"], "ph-sync-001")

    # ------------------------------------------------------------------
    # 3. Enqueue failure → 503
    # ------------------------------------------------------------------

    def test_async_enqueue_failure_returns_503(self):
        """enqueue failure should return 503."""
        with patch(
            "mes_dashboard.routes.production_history_routes.make_canonical_spool_id",
            return_value="ph-test-002",
        ), patch(
            "mes_dashboard.routes.production_history_routes.get_spool_file_path",
            return_value=None,
        ), patch(
            "mes_dashboard.services.async_query_job_service.is_async_available",
            return_value=True,
        ), patch(
            "mes_dashboard.services.production_history_job_service.PRODUCTION_HISTORY_ASYNC_ENABLED",
            True,
        ), patch(
            "mes_dashboard.services.production_history_job_service.enqueue_production_history_query",
            return_value=(None, "Redis unavailable"),
        ):
            response = self.client.post(
                "/api/production-history/query", json=_VALID_QUERY_BODY
            )

        self.assertEqual(response.status_code, 503)

    # ------------------------------------------------------------------
    # 4. RQ unavailable → 503 (sync fallback removed by AC-5)
    # ------------------------------------------------------------------

    def test_rq_unavailable_returns_503(self):
        """AC-5: sync fallback removed; RQ unavailable + legacy path → 503 degraded."""
        with patch(
            "mes_dashboard.routes.production_history_routes.make_canonical_spool_id",
            return_value="ph-test-003",
        ), patch(
            "mes_dashboard.routes.production_history_routes.get_spool_file_path",
            return_value=None,
        ), patch(
            "mes_dashboard.services.async_query_job_service.is_async_available",
            return_value=False,
        ), patch(
            "mes_dashboard.routes.production_history_routes._PRODUCTION_HISTORY_USE_UNIFIED_JOB",
            False,
        ):
            response = self.client.post(
                "/api/production-history/query", json=_VALID_QUERY_BODY
            )

        self.assertEqual(response.status_code, 503)
        payload = _parse(response)
        self.assertFalse(payload["success"])


class TestProductionHistoryJobStatusRoute(unittest.TestCase):

    def setUp(self):
        db._ENGINE = None
        self.app = create_app("testing")
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def test_job_found_returns_200_with_status(self):
        """GET /api/production-history/job/<job_id> should return status when job exists."""
        fake_status = {"status": "running", "progress": "querying Oracle", "pct": 50}

        with patch(
            "mes_dashboard.services.async_query_job_service.get_job_status",
            return_value=fake_status,
        ):
            response = self.client.get("/api/production-history/job/prod-hist-0001")

        payload = _parse(response)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["success"])
        self.assertEqual(payload["data"]["status"], "running")

    def test_job_not_found_returns_404(self):
        """GET /api/production-history/job/<job_id> should return 404 when job does not exist."""
        with patch(
            "mes_dashboard.services.async_query_job_service.get_job_status",
            return_value=None,
        ):
            response = self.client.get("/api/production-history/job/nonexistent-job")

        self.assertEqual(response.status_code, 404)

    def test_completed_job_returns_query_id(self):
        """GET /api/production-history/job/<job_id> returns query_id when completed."""
        fake_status = {
            "status": "completed",
            "query_id": "ph-result-001",
            "pct": 100,
        }

        with patch(
            "mes_dashboard.services.async_query_job_service.get_job_status",
            return_value=fake_status,
        ):
            response = self.client.get("/api/production-history/job/prod-hist-done")

        payload = _parse(response)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["data"]["query_id"], "ph-result-001")
        self.assertEqual(payload["data"]["status"], "completed")
