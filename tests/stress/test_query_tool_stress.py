# -*- coding: utf-8 -*-
"""Query-tool specific stress coverage.

Focus:
- mixed multi-query soak behavior under concurrent traffic
- high-concurrency large payload handling (50 values per query)
- browser-side rapid interactions without JS crashes
"""

from __future__ import annotations

import concurrent.futures
import json
import os
import time
from typing import Any

import pytest
import requests
from playwright.sync_api import Page, expect


QUERY_TOOL_BASE = "/portal-shell/query-tool"


def _extract_container_id(payload: dict[str, Any]) -> str:
    rows = payload.get("data") or []
    if not rows:
        return ""
    row = rows[0] if isinstance(rows[0], dict) else {}
    return str(
        row.get("container_id")
        or row.get("CONTAINERID")
        or row.get("containerId")
        or ""
    )


def _probe_health_recoverability(base_url: str, attempts: int = 5, timeout: float = 5.0) -> tuple[int, list[str]]:
    """Probe health multiple times to allow brief post-burst recovery windows."""
    healthy_probes = 0
    errors: list[str] = []

    for _ in range(attempts):
        probe_start = time.time()
        try:
            response = requests.get(f"{base_url}/health", timeout=timeout)
            if response.status_code in (200, 503):
                payload = response.json()
                if payload.get("status") in {"healthy", "degraded", "unhealthy"}:
                    healthy_probes += 1
                else:
                    errors.append(f"unexpected health payload: {payload}")
            else:
                errors.append(f"unexpected health status: {response.status_code}")
        except Exception as exc:  # pragma: no cover - runtime dependent
            errors.append(str(exc)[:120])
        elapsed = time.time() - probe_start
        if healthy_probes >= 3:
            break
        time.sleep(max(0.5, min(2.0, elapsed + 0.2)))

    return healthy_probes, errors


def _intercept_navigation_as_admin(page: Page):
    """Inject auth + navigation so query-tool can render inside portal shell."""

    def handle_auth_me(route):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "success": True,
                    "data": {
                        "username": "92367",
                        "displayName": "Stress Admin",
                        "mail": "ymirliu@panjit.com.tw",
                        "department": "E2E",
                        "telephoneNumber": "1234",
                        "domain": "PANJIT",
                        "is_admin": True,
                    },
                },
                ensure_ascii=False,
            ),
        )

    def handle_heartbeat(route):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"success": True, "data": {"online_count": 1}}),
        )

    def handle_route(route):
        response = route.fetch()
        body = response.json()
        body["is_admin"] = True

        query_tool_entry = {
            "name": "批次追蹤工具",
            "order": 4,
            "route": "/query-tool",
            "status": "dev",
        }

        drawers = body.get("drawers", [])
        has_query_tool = any(
            page_item.get("route") == "/query-tool"
            for drawer in drawers
            for page_item in drawer.get("pages", [])
        )
        if not has_query_tool:
            for drawer in drawers:
                if not drawer.get("admin_only"):
                    drawer.setdefault("pages", []).append(query_tool_entry)
                    break
            else:
                drawers.append(
                    {
                        "id": "stress-test",
                        "name": "Stress Test",
                        "order": 999,
                        "admin_only": False,
                        "pages": [query_tool_entry],
                    }
                )

        body["drawers"] = drawers
        route.fulfill(
            status=response.status,
            headers={**response.headers, "content-type": "application/json"},
            body=json.dumps(body),
        )

    page.route("**/api/auth/me", handle_auth_me)
    page.route("**/api/auth/heartbeat", handle_heartbeat)
    page.route("**/api/portal/navigation", handle_route)


@pytest.mark.stress
@pytest.mark.load
class TestQueryToolApiStress:
    """High-concurrency and soak tests for query-tool APIs."""

    @staticmethod
    def _request(
        method: str,
        url: str,
        *,
        timeout: float,
        json_body: dict[str, Any] | None = None,
        allowed_statuses: set[int] | None = None,
    ) -> tuple[bool, float, str]:
        start = time.time()
        try:
            response = requests.request(method, url, json=json_body, timeout=timeout)
            duration = time.time() - start
            statuses = allowed_statuses or {200}
            if response.status_code in statuses:
                return True, duration, ""
            return False, duration, f"HTTP {response.status_code}"
        except Exception as exc:  # pragma: no cover - network/runtime dependent
            duration = time.time() - start
            return False, duration, str(exc)[:120]

    @staticmethod
    def _discover_targets(base_url: str, timeout: float) -> dict[str, str]:
        discovered = {
            "equipment_id": "",
            "equipment_name": "",
            "container_id": "",
        }

        try:
            equipment_resp = requests.get(f"{base_url}/api/query-tool/equipment-list", timeout=timeout)
            if equipment_resp.status_code == 200:
                items = (equipment_resp.json() or {}).get("data") or []
                if items:
                    discovered["equipment_id"] = str(items[0].get("RESOURCEID") or "")
                    discovered["equipment_name"] = str(items[0].get("RESOURCENAME") or "")
        except Exception:
            pass

        try:
            resolve_resp = requests.post(
                f"{base_url}/api/query-tool/resolve",
                json={
                    "input_type": "work_order",
                    "values": ["GA26010001"],
                },
                timeout=timeout,
            )
            if resolve_resp.status_code == 200:
                discovered["container_id"] = _extract_container_id(resolve_resp.json() or {})
        except Exception:
            pass

        return discovered

    def test_mixed_query_tool_soak_no_5xx_or_crash(
        self,
        base_url: str,
        stress_config: dict[str, Any],
        stress_result,
    ):
        """Run mixed query workload for a sustained period and verify recoverability."""
        result = stress_result("Query Tool Mixed Soak")
        timeout = stress_config["timeout"]
        concurrent_users = max(4, min(stress_config["concurrent_users"], 20))
        soak_seconds = int(os.environ.get("STRESS_QUERY_TOOL_SOAK_SECONDS", "45"))

        targets = self._discover_targets(base_url, timeout)
        equipment_id = targets["equipment_id"]
        equipment_name = targets["equipment_name"]
        container_id = targets["container_id"]

        workload: list[dict[str, Any]] = [
            {
                "method": "GET",
                "url": f"{base_url}/api/query-tool/equipment-list",
                "allowed_statuses": {200},
            },
            {
                "method": "GET",
                "url": f"{base_url}/api/query-tool/workcenter-groups",
                "allowed_statuses": {200},
            },
            {
                "method": "POST",
                "url": f"{base_url}/api/query-tool/resolve",
                "json_body": {
                    "input_type": "lot_id",
                    "values": [f"STRESS-LOT-{idx:03d}" for idx in range(10)],
                },
                # 429 is acceptable (protection triggered, not process crash).
                "allowed_statuses": {200, 429},
            },
        ]

        if equipment_id:
            workload.extend(
                [
                    {
                        "method": "POST",
                        "url": f"{base_url}/api/query-tool/equipment-period",
                        "json_body": {
                            "equipment_ids": [equipment_id],
                            "equipment_names": [equipment_name] if equipment_name else [],
                            "start_date": "2026-01-01",
                            "end_date": "2026-01-31",
                            "query_type": "status_hours",
                        },
                        "allowed_statuses": {200, 429},
                    },
                    {
                        "method": "POST",
                        "url": f"{base_url}/api/query-tool/equipment-period",
                        "json_body": {
                            "equipment_ids": [equipment_id],
                            "equipment_names": [equipment_name] if equipment_name else [],
                            "start_date": "2026-01-01",
                            "end_date": "2026-01-31",
                            "query_type": "lots",
                        },
                        "allowed_statuses": {200, 429},
                    },
                ]
            )

        if container_id:
            workload.extend(
                [
                    {
                        "method": "GET",
                        "url": f"{base_url}/api/query-tool/lot-history?container_id={container_id}",
                        "allowed_statuses": {200, 429},
                    },
                    {
                        "method": "GET",
                        "url": f"{base_url}/api/query-tool/lot-associations?container_id={container_id}&type=materials",
                        "allowed_statuses": {200, 429},
                    },
                ]
            )

        stop_at = time.time() + soak_seconds

        def worker(worker_idx: int):
            idx = worker_idx
            while time.time() < stop_at:
                spec = workload[idx % len(workload)]
                ok, duration, error = self._request(
                    spec["method"],
                    spec["url"],
                    timeout=timeout,
                    json_body=spec.get("json_body"),
                    allowed_statuses=spec.get("allowed_statuses"),
                )
                if ok:
                    result.add_success(duration)
                else:
                    result.add_failure(f"{error} @ {spec['url']}", duration)
                idx += 1
                time.sleep(0.02)

        start = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrent_users) as executor:
            futures = [executor.submit(worker, idx) for idx in range(concurrent_users)]
            for future in concurrent.futures.as_completed(futures):
                future.result()
        result.total_duration = time.time() - start

        print(result.report())

        # Process-level stability threshold (accepting 429 guardrails).
        assert result.total_requests >= concurrent_users * 10
        assert result.success_rate >= 85.0, f"Success rate too low: {result.success_rate:.2f}%"

        # Under gunicorn worker autorestart windows, `/workcenter-groups` can briefly
        # return 500 before filter-cache warm-up completes. Keep this tolerance tight
        # while still failing on any other 5xx regression.
        five_xx_errors = [err for err in result.errors if "HTTP 5" in err]
        unexpected_five_xx = [
            err for err in five_xx_errors
            if "/api/query-tool/workcenter-groups" not in err
        ]
        allowed_transient_five_xx = max(5, int(result.total_requests * 0.002))

        assert not unexpected_five_xx, f"Unexpected 5xx endpoints detected: {unexpected_five_xx[:5]}"
        assert len(five_xx_errors) <= allowed_transient_five_xx, (
            f"Too many 5xx responses ({len(five_xx_errors)} > {allowed_transient_five_xx}): "
            f"{five_xx_errors[:5]}"
        )

        healthy_probes, health_errors = _probe_health_recoverability(base_url)
        assert healthy_probes >= 3, (
            f"Health endpoint recoverability too low: {healthy_probes}/5 "
            f"({health_errors[:3]})"
        )

    def test_large_multi_value_resolve_high_concurrency_stability(
        self,
        base_url: str,
        stress_config: dict[str, Any],
        stress_result,
    ):
        """50-value resolve payloads under concurrency should avoid 5xx and stay recoverable."""
        result = stress_result("Query Tool Large Resolve Concurrency")
        timeout = stress_config["timeout"]
        concurrent_users = max(6, min(stress_config["concurrent_users"] * 2, 24))
        total_requests = max(30, concurrent_users * 3)

        def run_request(seed: int):
            payload = {
                "input_type": "lot_id",
                "values": [f"BULK-{seed:03d}-{idx:02d}" for idx in range(50)],
            }
            ok, duration, error = self._request(
                "POST",
                f"{base_url}/api/query-tool/resolve",
                timeout=timeout,
                json_body=payload,
                allowed_statuses={200, 429},
            )
            if ok:
                result.add_success(duration)
            else:
                result.add_failure(error, duration)

        start = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrent_users) as executor:
            futures = [executor.submit(run_request, idx) for idx in range(total_requests)]
            for future in concurrent.futures.as_completed(futures):
                future.result()
        result.total_duration = time.time() - start

        print(result.report())

        assert result.success_rate >= 95.0, f"Large resolve success rate too low: {result.success_rate:.2f}%"
        assert all("HTTP 5" not in err for err in result.errors), f"5xx detected: {result.errors[:5]}"

        # Post-burst recoverability probe.
        healthy_probes, health_errors = _probe_health_recoverability(base_url)
        assert healthy_probes >= 3, (
            f"Health endpoint recoverability too low: {healthy_probes}/5 "
            f"({health_errors[:3]})"
        )


@pytest.mark.stress
class TestQueryToolBrowserStress:
    """Browser interaction stress focused on query-tool UI flow resilience."""

    def test_rapid_lot_reverse_switching_stays_responsive(self, page: Page, base_url: str):
        """Rapid resolve + tab switch cycles should not crash frontend runtime."""
        _intercept_navigation_as_admin(page)
        page.goto(f"{base_url}{QUERY_TOOL_BASE}?tab=lot", wait_until="domcontentloaded", timeout=60000)
        expect(page.locator("textarea.query-tool-textarea").first).to_be_visible(timeout=60000)

        js_errors = []
        page.on("pageerror", lambda error: js_errors.append(str(error)))

        page.locator("select.query-tool-select:visible").first.select_option("work_order")
        page.locator("textarea.query-tool-textarea:visible").first.fill("GA26010001")

        for idx in range(8):
            with page.expect_response(
                lambda resp: "/api/query-tool/resolve" in resp.url and resp.status < 500,
                timeout=90000,
            ):
                page.locator("button:has-text('解析'):visible").first.click()
            page.wait_for_timeout(250)

            page.locator("button", has_text="流水批反查(反向)").click()
            page.wait_for_timeout(200)
            page.locator("select.query-tool-select:visible").first.select_option("serial_number")
            page.locator("textarea.query-tool-textarea:visible").first.fill(f"GMSN-{idx:05d}")
            with page.expect_response(
                lambda resp: "/api/query-tool/resolve" in resp.url and resp.status < 500,
                timeout=90000,
            ):
                page.locator("button:has-text('解析'):visible").first.click()
            page.wait_for_timeout(250)

            page.locator("button", has_text="批次追蹤(正向)").click()
            page.wait_for_timeout(200)

        expect(page.locator("body")).to_be_visible()
        assert len(js_errors) == 0, f"Detected JS errors under rapid interaction: {js_errors[:3]}"
