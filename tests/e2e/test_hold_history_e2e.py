# -*- coding: utf-8 -*-
"""E2E tests for Hold History module.

Tests the two-phase query/view pattern:
  POST /api/hold-history/query → execute Oracle, cache result
  GET  /api/hold-history/view  → read cache, apply filters

Run with: pytest tests/e2e/test_hold_history_e2e.py -v -s
"""

import pytest
import requests


@pytest.mark.e2e
class TestHoldHistoryQuery:
    """E2E tests for Hold History primary query endpoint."""

    def test_query_requires_dates(self, api_base_url):
        """POST /query without dates returns 400."""
        resp = requests.post(f"{api_base_url}/hold-history/query", json={}, timeout=30)
        assert resp.status_code == 400
        payload = resp.json()
        assert payload["success"] is False

    def test_query_rejects_invalid_date_format(self, api_base_url):
        """POST /query with bad date format returns 400."""
        resp = requests.post(
            f"{api_base_url}/hold-history/query",
            json={"start_date": "03-01-2026", "end_date": "03-06-2026"},
            timeout=30,
        )
        assert resp.status_code == 400

    def test_query_rejects_inverted_dates(self, api_base_url):
        """POST /query with end_date < start_date returns 400."""
        resp = requests.post(
            f"{api_base_url}/hold-history/query",
            json={"start_date": "2026-03-10", "end_date": "2026-03-01"},
            timeout=30,
        )
        assert resp.status_code == 400

    def test_query_returns_query_id(self, api_base_url):
        """POST /query with valid dates returns query_id and meta."""
        resp = requests.post(
            f"{api_base_url}/hold-history/query",
            json={"start_date": "2026-03-01", "end_date": "2026-03-07"},
            timeout=120,
        )
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["success"] is True
        assert "query_id" in payload.get("data", {}) or "query_id" in payload.get("meta", {})

    def test_query_with_hold_type_filter(self, api_base_url):
        """POST /query with hold_type=quality succeeds."""
        resp = requests.post(
            f"{api_base_url}/hold-history/query",
            json={
                "start_date": "2026-03-01",
                "end_date": "2026-03-07",
                "hold_type": "quality",
            },
            timeout=120,
        )
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["success"] is True

    def test_long_range_returns_202_and_job_id(self, api_base_url):
        """Long-range query (≥ HOLD_ASYNC_DAY_THRESHOLD) returns 202 with job_id when async enabled.

        When HOLD_ASYNC_ENABLED=true and the date range meets the threshold, the endpoint
        must return 202 with {async: true, job_id, status_url}. Falls back to 200 sync if
        the worker is unavailable (is_async_available()=False). Either outcome is acceptable
        here; what must NOT happen is a 4xx/5xx.
        """
        import datetime

        end = datetime.date.today()
        start = end - datetime.timedelta(days=120)  # 120 days > default threshold of 90
        resp = requests.post(
            f"{api_base_url}/hold-history/query",
            json={"start_date": start.isoformat(), "end_date": end.isoformat()},
            timeout=30,
        )
        assert resp.status_code in (200, 202), (
            f"Expected 200 (sync fallback) or 202 (async), got {resp.status_code}"
        )
        payload = resp.json()
        assert payload["success"] is True
        if resp.status_code == 202:
            data = payload.get("data", {})
            assert "job_id" in data, "202 response must include job_id"
            assert "status_url" in data, "202 response must include status_url"
            assert "hold-history" in data["status_url"], (
                "status_url must include hold-history prefix"
            )


@pytest.mark.e2e
class TestHoldHistoryView:
    """E2E tests for Hold History cached view endpoint."""

    @pytest.fixture(scope="class")
    def query_id(self, api_base_url):
        """Execute a query and return the query_id for view tests."""
        resp = requests.post(
            f"{api_base_url}/hold-history/query",
            json={"start_date": "2026-03-01", "end_date": "2026-03-07"},
            timeout=120,
        )
        assert resp.status_code == 200
        payload = resp.json()
        data = payload.get("data", {})
        qid = data.get("query_id") or payload.get("meta", {}).get("query_id")
        assert qid, f"No query_id in response: {payload}"
        return qid

    def test_view_requires_query_id(self, api_base_url):
        """GET /view without query_id returns 400."""
        resp = requests.get(f"{api_base_url}/hold-history/view", timeout=30)
        assert resp.status_code == 400

    def test_view_returns_data(self, api_base_url, query_id):
        """GET /view with valid query_id returns hold data with actual records."""
        resp = requests.get(
            f"{api_base_url}/hold-history/view",
            params={"query_id": query_id},
            timeout=60,
        )
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["success"] is True
        data = payload["data"]
        assert isinstance(data, dict)
        assert data.get("total_row_count", 0) > 0, (
            "Hold history view returned 0 total_row_count — Oracle query may have failed silently "
            f"(data keys: {list(data.keys())})"
        )
        items = data.get("list", {}).get("items", [])
        assert len(items) > 0, "Hold history list.items is empty despite non-zero total_row_count"
        assert len(data.get("trend", [])) > 0, "Hold history trend data is empty"

    def test_view_pagination(self, api_base_url, query_id):
        """GET /view supports pagination and returns non-empty page."""
        resp = requests.get(
            f"{api_base_url}/hold-history/view",
            params={"query_id": query_id, "page": 1, "per_page": 10},
            timeout=60,
        )
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["success"] is True
        data = payload["data"]
        items = data.get("list", {}).get("items", [])
        assert len(items) > 0, "Hold history pagination returned empty items page"

    def test_view_with_hold_type_filter(self, api_base_url, query_id):
        """GET /view with hold_type filter returns filtered data."""
        resp = requests.get(
            f"{api_base_url}/hold-history/view",
            params={"query_id": query_id, "hold_type": "quality"},
            timeout=60,
        )
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["success"] is True

    def test_view_with_duration_range_filter(self, api_base_url, query_id):
        """GET /view with duration_range filter returns filtered data."""
        resp = requests.get(
            f"{api_base_url}/hold-history/view",
            params={"query_id": query_id, "duration_range": "<4h"},
            timeout=60,
        )
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["success"] is True

    def test_view_expired_query_id_returns_410(self, api_base_url):
        """GET /view with expired query_id returns 410 CACHE_EXPIRED."""
        resp = requests.get(
            f"{api_base_url}/hold-history/view",
            params={"query_id": "nonexistent-expired-id"},
            timeout=30,
        )
        assert resp.status_code == 410
        payload = resp.json()
        assert payload["success"] is False


@pytest.mark.e2e
class TestHoldHistoryDurationPayloadFields:
    """E2E tests verifying new duration payload fields are present (task 8.1)."""

    @pytest.fixture(autouse=True)
    def _query_id(self, api_base_url):
        self._api_base_url = api_base_url
        resp = requests.post(
            f"{api_base_url}/hold-history/query",
            json={"start_date": "2026-03-01", "end_date": "2026-03-07"},
            timeout=120,
        )
        assert resp.status_code == 200
        data = resp.json().get("data", {})
        self.query_id = data.get("query_id") or data.get("meta", {}).get("query_id")
        self.bootstrap_duration = data.get("duration", {})

    def test_duration_has_avg_released_hours(self):
        dur = self.bootstrap_duration
        assert "avgReleasedHours" in dur, "duration payload missing avgReleasedHours"
        assert dur["avgReleasedHours"] >= 0

    def test_duration_has_avg_on_hold_hours(self):
        dur = self.bootstrap_duration
        assert "avgOnHoldHours" in dur, "duration payload missing avgOnHoldHours"
        assert dur["avgOnHoldHours"] >= 0

    def test_duration_has_max_released_hours(self):
        dur = self.bootstrap_duration
        assert "maxReleasedHours" in dur, "duration payload missing maxReleasedHours"
        assert dur["maxReleasedHours"] >= 0

    def test_duration_has_max_on_hold_hours(self):
        dur = self.bootstrap_duration
        assert "maxOnHoldHours" in dur, "duration payload missing maxOnHoldHours"
        assert dur["maxOnHoldHours"] >= 0

    def test_duration_via_view_endpoint(self):
        if not self.query_id:
            pytest.skip("No query_id available")
        resp = requests.get(
            f"{self._api_base_url}/hold-history/view",
            params={"query_id": self.query_id, "hold_type": "quality"},
            timeout=60,
        )
        if resp.status_code == 410:
            pytest.skip("Cache expired")
        assert resp.status_code == 200
        dur = resp.json()["data"].get("duration", {})
        assert "avgReleasedHours" in dur
        assert "maxReleasedHours" in dur


@pytest.mark.e2e
class TestHoldHistoryTrendRepeatQualityField:
    """E2E tests verifying repeatQualityHoldQty is present in trend days (task 8.1)."""

    def test_query_trend_days_have_repeat_quality(self, api_base_url):
        resp = requests.post(
            f"{api_base_url}/hold-history/query",
            json={"start_date": "2026-03-01", "end_date": "2026-03-07"},
            timeout=120,
        )
        assert resp.status_code == 200
        data = resp.json().get("data", {})
        trend = data.get("trend", {})
        days = trend.get("days", [])
        assert len(days) > 0
        day = days[0]
        for section_key in ("quality", "non_quality", "all"):
            section = day.get(section_key, {})
            assert "repeatQualityHoldQty" in section, \
                f"trend day section '{section_key}' missing repeatQualityHoldQty"
            assert section["repeatQualityHoldQty"] >= 0


# ============================================================
# Today-mode E2E tests (hold-history-today-mode)
# ============================================================

_TODAY_SUMMARY_KEYS = {
    "onHoldLots",
    "onHoldQty",
    "todayNewQty",
    "todayReleaseQty",
    "todayFutureHoldQty",
    "onHoldAvgHours",
    "onHoldMaxHours",
}

_TODAY_RECORD_TYPES = ["on_hold", "new", "release"]


@pytest.mark.e2e
class TestHoldHistoryConfig:
    """E2E: GET /api/hold-history/config feature-flag endpoint."""

    def test_config_returns_200(self, api_base_url):
        resp = requests.get(f"{api_base_url}/hold-history/config", timeout=10)
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["success"] is True

    def test_config_has_today_mode_enabled(self, api_base_url):
        resp = requests.get(f"{api_base_url}/hold-history/config", timeout=10)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "today_mode_enabled" in data
        assert isinstance(data["today_mode_enabled"], bool)

    def test_config_has_auto_refresh_seconds(self, api_base_url):
        resp = requests.get(f"{api_base_url}/hold-history/config", timeout=10)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "auto_refresh_seconds" in data
        assert isinstance(data["auto_refresh_seconds"], int)
        assert data["auto_refresh_seconds"] > 0


@pytest.mark.e2e
class TestHoldHistoryTodaySnapshot:
    """E2E: POST /api/hold-history/today-snapshot endpoint."""

    def _post_snapshot(self, api_base_url, **kwargs):
        body = {"hold_type": "quality", "record_type": "on_hold", **kwargs}
        return requests.post(
            f"{api_base_url}/hold-history/today-snapshot",
            json=body,
            timeout=60,
        )

    def test_today_snapshot_returns_200_or_503(self, api_base_url):
        """Endpoint must respond with 200 (data) or 503 (DB unavailable), never 500."""
        resp = self._post_snapshot(api_base_url)
        assert resp.status_code in (200, 503), (
            f"Expected 200 or 503, got {resp.status_code}. "
            "A 500 indicates an unhandled exception in the route."
        )
        payload = resp.json()
        assert "success" in payload

    def test_today_snapshot_envelope_structure(self, api_base_url):
        """On 200, response must have success=True and a data dict."""
        resp = self._post_snapshot(api_base_url)
        if resp.status_code == 503:
            pytest.skip("DB unavailable in this environment")
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["success"] is True
        assert isinstance(payload.get("data"), dict)

    def test_today_snapshot_summary_keys(self, api_base_url):
        """On 200, summary must contain all 7 expected keys."""
        resp = self._post_snapshot(api_base_url)
        if resp.status_code == 503:
            pytest.skip("DB unavailable in this environment")
        data = resp.json()["data"]
        summary = data.get("summary", {})
        missing = _TODAY_SUMMARY_KEYS - set(summary.keys())
        assert not missing, f"summary missing keys: {missing}"

    def test_today_snapshot_no_trend_key(self, api_base_url):
        """today-snapshot must NOT include a 'trend' key (trend is range-only)."""
        resp = self._post_snapshot(api_base_url)
        if resp.status_code == 503:
            pytest.skip("DB unavailable in this environment")
        data = resp.json()["data"]
        assert "trend" not in data, "today-snapshot should not expose 'trend'"

    def test_today_snapshot_has_list_and_pareto(self, api_base_url):
        """On 200, list and reason_pareto dicts must be present."""
        resp = self._post_snapshot(api_base_url)
        if resp.status_code == 503:
            pytest.skip("DB unavailable in this environment")
        data = resp.json()["data"]
        assert "list" in data
        assert "reason_pareto" in data

    def test_today_snapshot_rejects_bad_record_type(self, api_base_url):
        """Invalid record_type for today mode → 400."""
        resp = self._post_snapshot(api_base_url, record_type="new_wrong")
        assert resp.status_code == 400
        payload = resp.json()
        assert payload["success"] is False

    def test_today_snapshot_rejects_bad_duration_range(self, api_base_url):
        """Invalid duration_range → 400."""
        resp = self._post_snapshot(api_base_url, duration_range="bad")
        assert resp.status_code == 400

    @pytest.mark.parametrize("record_type", _TODAY_RECORD_TYPES)
    def test_today_snapshot_all_record_types_accepted(self, api_base_url, record_type):
        """Each valid record_type returns 200 or 503 (never 400)."""
        resp = self._post_snapshot(api_base_url, record_type=record_type)
        assert resp.status_code in (200, 503), (
            f"record_type={record_type!r} unexpectedly returned {resp.status_code}"
        )

    def test_today_snapshot_summary_numeric_values(self, api_base_url):
        """All summary values must be non-negative numbers."""
        resp = self._post_snapshot(api_base_url)
        if resp.status_code == 503:
            pytest.skip("DB unavailable in this environment")
        summary = resp.json()["data"]["summary"]
        for key in _TODAY_SUMMARY_KEYS:
            val = summary.get(key, -1)
            assert isinstance(val, (int, float)), f"summary.{key} is not a number: {val!r}"
            assert val >= 0, f"summary.{key} is negative: {val}"
