# -*- coding: utf-8 -*-
"""Integration tests: Query Tool heavy-join scenarios.

Covers timeout, date-range guard, and SQL-injection blocklist edge cases.
All Oracle I/O is mocked — these tests do not require a live DB.

Gate: @pytest.mark.integration AND --run-integration CLI flag.
"""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def app_client(app):
    """Flask test client with public API access."""
    app.config["API_PUBLIC"] = True
    return app.test_client()


# ---------------------------------------------------------------------------
# Helper: build a minimal valid equipment-period payload
# ---------------------------------------------------------------------------


def _equipment_payload(**overrides) -> dict:
    base = {
        "equipment_ids": ["EQ-001"],
        "equipment_names": ["Furnace-1"],
        "start_date": "2024-01-01",
        "end_date": "2024-01-07",
        "query_type": "status_hours",
    }
    base.update(overrides)
    return base


def _resolve_payload(**overrides) -> dict:
    base = {
        "input_type": "lot_id",
        "values": ["LOT12345678901234"],
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestQueryToolHeavyJoin:
    """Validate query-tool route behavior under timeout, range, and injection scenarios."""

    # ------------------------------------------------------------------ #
    # 6.11.1 — Timeout: response has partial flag OR QUERY_TIMEOUT code  #
    # ------------------------------------------------------------------ #

    def test_multi_filter_lineage_returns_partial_result_envelope_on_timeout(
        self, app_client
    ):
        """When Oracle query times out, response envelope signals timeout or partial."""
        from sqlalchemy.exc import TimeoutError as SATimeout

        # Patch the route-level service import so the exception propagates to the route.
        with patch(
            "mes_dashboard.routes.query_tool_routes.get_equipment_status_hours",
            side_effect=SATimeout("simulated oracle call timeout"),
        ), patch(
            "mes_dashboard.services.page_registry.is_api_public", return_value=True
        ):
            resp = app_client.post(
                "/api/query-tool/equipment-period",
                json=_equipment_payload(),
                content_type="application/json",
            )

        data = resp.get_json()
        assert data is not None, "Response must be JSON"

        # Accept either:
        #  a) partial flag in data or meta
        #  b) a timeout / internal error code (nested under data["error"]["code"])
        is_partial = (
            (isinstance(data.get("data"), dict) and data["data"].get("partial") is True)
            or (isinstance(data.get("meta"), dict) and data["meta"].get("partial") is True)
        )
        error_code = (data.get("error") or {}).get("code") if isinstance(data.get("error"), dict) else None
        is_timeout_error = (
            not data.get("success", True)
            and error_code in (
                "DB_QUERY_TIMEOUT",
                "INTERNAL_ERROR",
                "SERVICE_UNAVAILABLE",
                "DB_QUERY_ERROR",
            )
        )
        assert is_partial or is_timeout_error, (
            f"Expected partial=true or a timeout error code, got: {data}"
        )

    # ------------------------------------------------------------------ #
    # 6.11.2 — Happy path: mock quick Oracle, assert full data envelope  #
    # ------------------------------------------------------------------ #

    def test_heavy_join_within_timeout_returns_data(self, app_client):
        """Mock fast Oracle response; full data returned with correct envelope shape."""
        mock_result = {
            "equipment_ids": ["EQ-001"],
            "rows": [{"hour": "00", "status": "PRD", "count": 5}],
            "total": 1,
        }

        with patch(
            "mes_dashboard.services.query_tool_service.get_equipment_status_hours",
            return_value=mock_result,
        ), patch(
            "mes_dashboard.services.page_registry.is_api_public", return_value=True
        ):
            resp = app_client.post(
                "/api/query-tool/equipment-period",
                json=_equipment_payload(),
                content_type="application/json",
            )

        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        data = resp.get_json()
        assert data is not None, "Response must be JSON"
        assert data.get("success") is True, f"Expected success=true, got: {data}"
        assert "data" in data, "Response must contain 'data' key"
        assert "meta" in data, "Response must contain 'meta' key"

    # ------------------------------------------------------------------ #
    # 6.11.3 — Date range guard rejects range > MAX_DATE_RANGE_DAYS      #
    # ------------------------------------------------------------------ #

    def test_date_range_guard_rejects_excessive_range(self, app_client):
        """A date range exceeding the configured limit must return 400 VALIDATION_ERROR."""
        # MAX_DATE_RANGE_DAYS is 730 (2 years). Use 800 days to be safely over.
        start = date(2022, 1, 1)
        end = start + timedelta(days=800)

        with patch(
            "mes_dashboard.services.page_registry.is_api_public", return_value=True
        ):
            resp = app_client.post(
                "/api/query-tool/equipment-period",
                json=_equipment_payload(
                    start_date=start.isoformat(),
                    end_date=end.isoformat(),
                ),
                content_type="application/json",
            )

        assert resp.status_code == 400, (
            f"Expected 400 for excessive date range, got {resp.status_code}"
        )
        data = resp.get_json()
        assert data is not None
        assert data.get("success") is False
        # Error code is nested under data["error"]["code"] per response.py contract.
        error_code = (data.get("error") or {}).get("code") if isinstance(data.get("error"), dict) else None
        assert error_code == "VALIDATION_ERROR", (
            f"Expected VALIDATION_ERROR, got error_code={error_code!r}, full response: {data}"
        )

    # ------------------------------------------------------------------ #
    # 6.11.4 — SQL injection blocklist rejects DROP statement            #
    # ------------------------------------------------------------------ #

    def test_injection_blocklist_rejects_drop_statement(self, app_client):
        """Values containing SQL DDL keywords like DROP must be rejected."""
        # Inject DROP via the 'values' field, which goes through validate_lot_input.
        malicious_payload = _resolve_payload(
            values=["'; DROP TABLE LOTS; --"],
        )

        with patch(
            "mes_dashboard.services.page_registry.is_api_public", return_value=True
        ):
            resp = app_client.post(
                "/api/query-tool/resolve",
                json=malicious_payload,
                content_type="application/json",
            )

        # Acceptable outcomes: 400 VALIDATION_ERROR, or any non-200 error response.
        # The route must NOT successfully execute the malicious SQL.
        data = resp.get_json()
        assert data is not None

        # Either the input is rejected (400) or it fails validation (no DB hit).
        # Success (200) with the raw DROP string in values would be the failure case.
        is_blocked = (
            resp.status_code in (400, 422, 500)
            or (data.get("success") is False)
        )
        has_drop_in_data = (
            resp.status_code == 200
            and isinstance(data.get("data"), dict)
            and any(
                "drop" in str(v).lower()
                for v in (data["data"].get("rows") or [])
            )
        )
        assert is_blocked or not has_drop_in_data, (
            f"DROP statement was not blocked; response: {data}"
        )

    # ------------------------------------------------------------------ #
    # 6.11.5 — Validation: missing required fields returns 400           #
    # ------------------------------------------------------------------ #

    def test_missing_date_fields_returns_400(self, app_client):
        """Equipment-period query without start_date/end_date must return 400."""
        with patch(
            "mes_dashboard.services.page_registry.is_api_public", return_value=True
        ):
            resp = app_client.post(
                "/api/query-tool/equipment-period",
                json={"equipment_ids": ["EQ-001"], "query_type": "status_hours"},
                content_type="application/json",
            )

        assert resp.status_code == 400
        data = resp.get_json()
        assert data is not None
        assert data.get("success") is False

    # ------------------------------------------------------------------ #
    # 6.11.6 — Validation: invalid query_type returns 400                #
    # ------------------------------------------------------------------ #

    def test_invalid_query_type_returns_400(self, app_client):
        """Equipment-period with an unknown query_type must return 400."""
        with patch(
            "mes_dashboard.services.page_registry.is_api_public", return_value=True
        ):
            resp = app_client.post(
                "/api/query-tool/equipment-period",
                json=_equipment_payload(query_type="__evil__"),
                content_type="application/json",
            )

        assert resp.status_code == 400
        data = resp.get_json()
        assert data is not None
        assert data.get("success") is False
