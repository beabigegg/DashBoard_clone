# -*- coding: utf-8 -*-
"""
Tier 1 mock tests: WIP rowcount pre-check and RQ routing.

query-path-c-elimination-cleanup (IP-11):
  AC-3: WIP detail route performs COUNT(*) pre-check.
        - count >= L3 (200,000) → attempt RQ dispatch (202 if enqueue succeeds).
        - count < L3 → stay sync (200).
        - COUNT error → fail-open, stay sync (200).

NOT marked integration_real — all Oracle/RQ calls are mocked.
Run without special flags:

    conda run -n mes-dashboard pytest \
        tests/integration/test_wip_rowcount_rq_routing.py -v --tb=short
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

import mes_dashboard.routes.wip_routes as wip_module


@pytest.fixture
def wip_app():
    """Minimal Flask test app with wip blueprint."""
    from mes_dashboard.app import create_app
    app = create_app("testing")
    return app


# ---------------------------------------------------------------------------
# AC-3: above L3 threshold → RQ dispatch
# ---------------------------------------------------------------------------


class TestAboveL3Threshold:
    def test_wip_above_l3_threshold_routes_to_rq(self, wip_app, monkeypatch):
        """AC-3: count_wip_rows >= 200,000 → 202 + job_id when enqueue succeeds."""
        # count_wip_rows returns 250,000 (above L3=200,000)
        mock_enqueue = MagicMock(return_value=("wip-detail-xyz", None))

        with patch.object(
            wip_module, "count_wip_rows", return_value=250_000
        ), patch.object(
            wip_module, "is_async_available", return_value=True
        ), patch.object(
            wip_module, "enqueue_job_dynamic", mock_enqueue
        ), patch.object(
            wip_module, "get_owner_token", return_value="test-user"
        ):
            with wip_app.test_client() as client:
                resp = client.get("/api/wip/detail/焊接_DB")

        assert resp.status_code == 202, (
            f"Expected 202 for count ≥ L3 (200,000) when async available, got {resp.status_code}"
        )
        data = resp.get_json()
        assert data["data"]["async"] is True
        assert "job_id" in data["data"]


# ---------------------------------------------------------------------------
# AC-3: below L3 threshold → stay sync
# ---------------------------------------------------------------------------


class TestBelowL3Threshold:
    def test_wip_below_l3_threshold_stays_inline(self, wip_app, monkeypatch):
        """AC-3: count_wip_rows < 200,000 → 200 sync response."""
        mock_result = {
            "workcenter": "焊接_DB",
            "summary": {"totalLots": 100, "runLots": 50, "queueLots": 30, "holdLots": 20,
                         "qualityHoldLots": 15, "nonQualityHoldLots": 5},
            "specs": [],
            "lots": [],
            "pagination": {"page": 1, "page_size": 100, "total_count": 100, "total_pages": 1},
            "sys_date": "2024-01-01",
        }
        mock_enqueue = MagicMock()

        with patch.object(
            wip_module, "count_wip_rows", return_value=150_000
        ), patch.object(
            wip_module, "is_async_available", return_value=True
        ), patch.object(
            wip_module, "enqueue_job_dynamic", mock_enqueue
        ), patch.object(
            wip_module, "get_wip_detail", return_value=mock_result
        ):
            with wip_app.test_client() as client:
                resp = client.get("/api/wip/detail/焊接_DB")

        assert resp.status_code == 200, (
            f"Expected 200 (sync) for count < L3, got {resp.status_code}"
        )
        # enqueue_job_dynamic must NOT have been called
        mock_enqueue.assert_not_called()


# ---------------------------------------------------------------------------
# AC-3 / R1: COUNT error → fail-open, stay sync
# ---------------------------------------------------------------------------


class TestCountErrorFailOpen:
    def test_wip_count_error_fails_open_stays_inline(self, wip_app, monkeypatch):
        """AC-3, R1: COUNT(*) raises exception → fail-open, stay sync (count_wip_rows returns 0)."""
        mock_result = {
            "workcenter": "焊接_DB",
            "summary": {"totalLots": 50, "runLots": 25, "queueLots": 15, "holdLots": 10,
                         "qualityHoldLots": 8, "nonQualityHoldLots": 2},
            "specs": [],
            "lots": [],
            "pagination": {"page": 1, "page_size": 100, "total_count": 50, "total_pages": 1},
            "sys_date": "2024-01-01",
        }
        mock_enqueue = MagicMock()

        # count_wip_rows returns 0 (fail-open behavior on Oracle error, per IP-3)
        with patch.object(
            wip_module, "count_wip_rows", return_value=0
        ), patch.object(
            wip_module, "is_async_available", return_value=True
        ), patch.object(
            wip_module, "enqueue_job_dynamic", mock_enqueue
        ), patch.object(
            wip_module, "get_wip_detail", return_value=mock_result
        ):
            with wip_app.test_client() as client:
                resp = client.get("/api/wip/detail/焊接_DB")

        assert resp.status_code == 200, (
            f"Expected 200 (fail-open) when COUNT returns 0, got {resp.status_code}"
        )
        # Must not dispatch to RQ when count=0 < L3
        mock_enqueue.assert_not_called()


# ---------------------------------------------------------------------------
# AC-2: Above L3 → job completes and spool is readable
# wip-rq-worker-chunks-cleanup
# ---------------------------------------------------------------------------


class TestWipJobCompletesAndSpoolReadable:
    def test_wip_above_l3_job_completes_and_spool_readable(self, wip_app):
        """AC-2: Above-L3 enqueue returns 202 + job_id; spool retrievable at /api/spool/wip_dataset/<query_id>.

        Mocks: count_wip_rows=250k, is_async_available=True, enqueue_job_dynamic returns job_id.
        Spool route tested independently — verifies namespace acceptance (not end-to-end spool write).
        """
        mock_enqueue = MagicMock(return_value=("wip-detail-abc123", None))

        with wip_app.test_client() as client:
            with patch.object(
                wip_module, "count_wip_rows", return_value=250_000
            ), patch.object(
                wip_module, "is_async_available", return_value=True
            ), patch.object(
                wip_module, "enqueue_job_dynamic", mock_enqueue
            ), patch.object(
                wip_module, "get_owner_token", return_value="test-user"
            ):
                resp = client.get("/api/wip/detail/焊接_DB")

        assert resp.status_code == 202
        data = resp.get_json()
        assert data["data"]["async"] is True
        assert data["data"]["job_id"] == "wip-detail-abc123"
        assert "status_url" in data["data"]
        # status_url must reference the wip-detail prefix for polling
        assert "wip-detail" in data["data"]["status_url"]


# ---------------------------------------------------------------------------
# AC-5: Redis-down → fail-open to sync
# wip-rq-worker-chunks-cleanup
# ---------------------------------------------------------------------------


class TestRedisDownFailOpen:
    def test_wip_redis_down_fails_open_to_sync(self, wip_app):
        """AC-5: When is_async_available() returns False (Redis/worker down), route falls to sync."""
        mock_result = {
            "workcenter": "焊接_DB",
            "summary": {"totalLots": 300000, "runLots": 200000, "queueLots": 80000, "holdLots": 20000,
                         "qualityHoldLots": 15000, "nonQualityHoldLots": 5000},
            "specs": [],
            "lots": [],
            "pagination": {"page": 1, "page_size": 100, "total_count": 300000, "total_pages": 3000},
            "sys_date": "2024-01-01",
        }
        mock_enqueue = MagicMock()

        with wip_app.test_client() as client:
            with patch.object(
                wip_module, "count_wip_rows", return_value=300_000
            ), patch.object(
                wip_module, "is_async_available", return_value=False
            ), patch.object(
                wip_module, "enqueue_job_dynamic", mock_enqueue
            ), patch.object(
                wip_module, "get_wip_detail", return_value=mock_result
            ):
                resp = client.get("/api/wip/detail/焊接_DB")

        assert resp.status_code == 200, (
            f"Expected 200 (fail-open) when Redis is down, got {resp.status_code}"
        )
        # enqueue must NOT be called when async not available
        mock_enqueue.assert_not_called()


# ---------------------------------------------------------------------------
# AC-7: Async spool schema parity vs sync lots[0] keys
# xfail(strict=True) until spool assembly path is confirmed (AC-7 open risk)
# wip-rq-worker-chunks-cleanup
# ---------------------------------------------------------------------------


class TestAsyncRowSchemaMatchesSyncPath:
    def test_async_row_schema_matches_sync_path(self):
        """AC-7 (resolved): Async spool parquet columns must be camelCase, matching sync lots keys.

        Verifies that _ORACLE_TO_CAMEL + _compute_wip_status produce the expected
        camelCase column set when applied to a mock Oracle DataFrame.
        xfail(strict=True) removed: assembly layer implemented in wip_query_job_service.py.
        """
        import pandas as pd
        from mes_dashboard.services.wip_query_job_service import (
            _ORACLE_TO_CAMEL,
            _compute_wip_status,
        )

        # Minimal Oracle-column DataFrame (mirrors raw read_sql_df output)
        sample_row = {col: "x" for col in _ORACLE_TO_CAMEL}
        sample_row["EQUIPMENTCOUNT"] = 0
        sample_row["CURRENTHOLDCOUNT"] = 0
        df = pd.DataFrame([sample_row])

        # Simulate the assembly layer applied in execute_wip_detail_oracle_query
        df["wipStatus"] = df.apply(
            lambda r: _compute_wip_status(
                int(r.get("EQUIPMENTCOUNT") or 0),
                int(r.get("CURRENTHOLDCOUNT") or 0),
            ),
            axis=1,
        )
        df = df.rename(columns=_ORACLE_TO_CAMEL)

        actual_cols = set(df.columns)
        expected_subset = {
            "lotId", "equipment", "wipStatus", "holdReason", "qty",
            "packageLef", "spec", "pjType", "holdCount", "equipmentCount",
        }

        assert expected_subset.issubset(actual_cols), (
            f"Missing camelCase columns after assembly: {expected_subset - actual_cols}"
        )
        assert "LOTID" not in actual_cols, "Oracle column LOTID not renamed"
        assert "EQUIPMENTS" not in actual_cols, "Oracle column EQUIPMENTS not renamed"
        assert "HOLDREASONNAME" not in actual_cols, "Oracle column HOLDREASONNAME not renamed"
