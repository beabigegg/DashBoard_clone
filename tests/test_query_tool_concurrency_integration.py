# -*- coding: utf-8 -*-
"""Integration-style concurrency tests for query-tool routes.

Focus areas:
- multi-query payload handling under concurrent traffic
- mixed endpoint interaction stability
- oversized batch request rejection under burst load
- sustained repeated querying without process-level failures
"""

from __future__ import annotations

import concurrent.futures
import time
from typing import Any
from unittest.mock import patch

import pytest

from mes_dashboard import create_app
from mes_dashboard.core.cache import NoOpCache


@pytest.fixture
def app():
    """Create isolated Flask app for concurrency integration tests."""
    app = create_app("testing")
    app.config["TESTING"] = True
    app.extensions["cache"] = NoOpCache()
    return app


class TestQueryToolConcurrencyIntegration:
    """Concurrency-focused tests for query-tool route behavior."""

    @patch("mes_dashboard.core.rate_limit.check_and_record", return_value=(False, 0))
    @patch("mes_dashboard.routes.query_tool_routes.resolve_lots")
    def test_resolve_concurrent_multi_query_payloads_no_5xx(
        self,
        mock_resolve,
        _mock_rate_limit,
        app,
    ):
        """Concurrent resolve requests with 50-item payloads should stay stable."""

        def fake_resolve(input_type: str, values: list[str]) -> dict[str, Any]:
            # Simulate a slightly expensive resolve path.
            time.sleep(0.01)
            resolved = [
                {
                    "container_id": f"CID-{idx:03d}",
                    "input_value": value,
                    "input_type": input_type,
                }
                for idx, value in enumerate(values, start=1)
            ]
            return {
                "data": resolved,
                "total": len(resolved),
                "input_count": len(values),
                "not_found": [],
            }

        mock_resolve.side_effect = fake_resolve

        request_count = 36
        workers = 12

        def run_request(seed: int) -> tuple[int, dict[str, Any]]:
            payload = {
                "input_type": "lot_id",
                "values": [f"LOT-{seed:03d}-{idx:02d}" for idx in range(50)],
            }
            with app.test_client() as client:
                response = client.post("/api/query-tool/resolve", json=payload)
                return response.status_code, response.get_json() or {}

        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(run_request, idx) for idx in range(request_count)]
            results = [future.result() for future in concurrent.futures.as_completed(futures)]

        statuses = [status for status, _payload in results]
        payloads = [payload for _status, payload in results]

        assert all(status == 200 for status in statuses), f"Unexpected statuses: {statuses}"
        assert all("data" in payload for payload in payloads)
        assert all(payload.get("total") == 50 for payload in payloads)
        assert all(len(payload.get("not_found", [])) == 0 for payload in payloads)

    @patch("mes_dashboard.core.rate_limit.check_and_record", return_value=(False, 0))
    @patch("mes_dashboard.routes.query_tool_routes.get_lot_associations_batch")
    @patch("mes_dashboard.routes.query_tool_routes.get_lot_history_batch")
    def test_mixed_batch_history_and_association_queries_under_concurrency(
        self,
        mock_history_batch,
        mock_assoc_batch,
        _mock_rate_limit,
        app,
    ):
        """Concurrent mixed batch endpoints should preserve response contract."""
        mock_history_batch.side_effect = lambda cids, workcenter_groups=None: {
            "data": [
                {
                    "CONTAINERID": cid,
                    "WORKCENTER_GROUPS": workcenter_groups or [],
                }
                for cid in cids
            ],
            "total": len(cids),
        }
        mock_assoc_batch.side_effect = lambda cids, assoc_type: {
            "data": [
                {"CONTAINERID": cid, "TYPE": assoc_type}
                for cid in cids
            ],
            "total": len(cids),
        }

        request_count = 60
        workers = 16

        def run_request(index: int) -> tuple[int, dict[str, Any]]:
            with app.test_client() as client:
                if index % 3 == 0:
                    response = client.get(
                        "/api/query-tool/lot-history?"
                        "container_ids=CID-001,CID-002,CID-003&workcenter_groups=WB,FA"
                    )
                else:
                    assoc_type = "materials" if index % 2 == 0 else "rejects"
                    response = client.get(
                        "/api/query-tool/lot-associations?"
                        f"container_ids=CID-001,CID-002&type={assoc_type}"
                    )
                return response.status_code, response.get_json() or {}

        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(run_request, idx) for idx in range(request_count)]
            results = [future.result() for future in concurrent.futures.as_completed(futures)]

        statuses = [status for status, _payload in results]
        payloads = [payload for _status, payload in results]

        assert all(status == 200 for status in statuses), f"Unexpected statuses: {statuses}"
        assert all("data" in payload for payload in payloads)
        assert all("total" in payload for payload in payloads)
        assert mock_history_batch.called
        assert mock_assoc_batch.called

    @patch("mes_dashboard.core.rate_limit.check_and_record", return_value=(False, 0))
    @patch("mes_dashboard.routes.query_tool_routes.get_lot_history_batch")
    def test_oversized_batch_burst_is_rejected_without_service_execution(
        self,
        mock_history_batch,
        _mock_rate_limit,
        app,
    ):
        """Burst oversized batch requests should short-circuit to 413 safely."""
        app.config["QUERY_TOOL_MAX_CONTAINER_IDS"] = 10
        huge_ids = ",".join([f"CID-{idx:03d}" for idx in range(80)])

        request_count = 30
        workers = 12

        def run_request() -> tuple[int, float]:
            with app.test_client() as client:
                start = time.time()
                response = client.get(f"/api/query-tool/lot-history?container_ids={huge_ids}")
                return response.status_code, time.time() - start

        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(run_request) for _ in range(request_count)]
            results = [future.result() for future in concurrent.futures.as_completed(futures)]

        statuses = [status for status, _duration in results]
        durations = [duration for _status, duration in results]

        assert all(status == 413 for status in statuses), f"Unexpected statuses: {statuses}"
        # Fast-fail guard: this should reject quickly, not run heavy logic.
        assert max(durations) < 1.0, f"Oversized requests were unexpectedly slow: {max(durations):.3f}s"
        mock_history_batch.assert_not_called()

    @patch("mes_dashboard.core.rate_limit.check_and_record", return_value=(False, 0))
    @patch("mes_dashboard.routes.query_tool_routes.resolve_lots")
    def test_sustained_resolve_sequence_remains_stable(
        self,
        mock_resolve,
        _mock_rate_limit,
        app,
    ):
        """Repeated resolve requests over time should not degrade to 5xx."""
        mock_resolve.side_effect = lambda input_type, values: {
            "data": [
                {"container_id": f"{input_type}-{idx}", "input_value": value}
                for idx, value in enumerate(values)
            ],
            "total": len(values),
            "input_count": len(values),
            "not_found": [],
        }

        failures: list[int] = []
        with app.test_client() as client:
            for round_idx in range(120):
                response = client.post(
                    "/api/query-tool/resolve",
                    json={
                        "input_type": "lot_id",
                        "values": [f"GA2601{round_idx:03d}-A00-{idx:03d}" for idx in range(20)],
                    },
                )
                if response.status_code != 200:
                    failures.append(response.status_code)

        assert not failures, f"Sustained resolve produced failures: {failures[:10]}"
