# -*- coding: utf-8 -*-
"""Shared browser helpers for portal-shell E2E tests."""

from __future__ import annotations

import json
import time
from urllib.parse import urlencode

from playwright.sync_api import Page


def _admin_payload() -> dict:
    return {
        "success": True,
        "data": {
            "username": "92367",
            "displayName": "E2E Admin",
            "mail": "ymirliu@panjit.com.tw",
            "department": "E2E",
            "telephoneNumber": "1234",
            "domain": "PANJIT",
            "is_admin": True,
        },
    }


def ensure_shell_admin(page: Page, route_path: str | None = None, route_name: str | None = None):
    """Mock shell auth/navigation so in-scope portal routes render consistently."""
    routes = getattr(page, "_shell_e2e_routes", None)
    if routes is None:
        routes = []
        page._shell_e2e_routes = routes

        def handle_auth_me(route):
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(_admin_payload(), ensure_ascii=False),
            )

        def handle_heartbeat(route):
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({"success": True, "data": {"online_count": 1}}),
            )

        def handle_navigation(route):
            response = route.fetch()
            body = response.json()
            if not isinstance(body, dict):
                body = {}

            body["is_admin"] = True
            drawers = body.get("drawers")
            if not isinstance(drawers, list):
                drawers = []

            target_drawer = None
            for drawer in drawers:
                if not drawer.get("admin_only"):
                    target_drawer = drawer
                    break
            if target_drawer is None:
                target_drawer = {
                    "id": "e2e-test-drawer",
                    "name": "E2E Test",
                    "order": 999,
                    "admin_only": False,
                    "pages": [],
                }
                drawers.append(target_drawer)

            existing_routes = {
                page_entry.get("route")
                for drawer in drawers
                for page_entry in drawer.get("pages", [])
                if isinstance(page_entry, dict)
            }
            for registered_route, registered_name in getattr(page, "_shell_e2e_routes", []):
                if registered_route in existing_routes:
                    continue
                target_drawer.setdefault("pages", []).append(
                    {
                        "name": registered_name,
                        "order": 999,
                        "route": registered_route,
                        "status": "released",
                    }
                )

            body["drawers"] = drawers
            route.fulfill(
                status=response.status,
                headers={**response.headers, "content-type": "application/json"},
                body=json.dumps(body, ensure_ascii=False),
            )

        page.route("**/api/auth/me", handle_auth_me)
        page.route("**/api/auth/heartbeat", handle_heartbeat)
        page.route("**/api/portal/navigation", handle_navigation)

    if route_path:
        normalized_path = route_path if route_path.startswith("/") else f"/{route_path}"
        display_name = route_name or normalized_path.strip("/") or "home"
        entry = (normalized_path, display_name)
        if entry not in routes:
            routes.append(entry)


def goto_shell_route(page: Page, app_server: str, route_path: str, route_name: str | None = None, **params) -> str:
    """Navigate to a portal-shell route with shell auth mocked."""
    normalized_path = route_path if route_path.startswith("/") else f"/{route_path}"
    ensure_shell_admin(page, normalized_path, route_name)
    query = urlencode(
        [
            (key, item)
            for key, value in params.items()
            for item in (value if isinstance(value, list) else [value])
            if item not in (None, "")
        ],
        doseq=True,
    )
    url = f"{app_server}/portal-shell{normalized_path}"
    if query:
        url = f"{url}?{query}"
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(1500)
    return url


def wait_for_any_visible(page: Page, selectors: list[str], timeout_ms: int = 120000) -> str:
    """Return the first selector that becomes visible within timeout."""
    deadline = time.time() + (timeout_ms / 1000)
    while time.time() < deadline:
        for selector in selectors:
            locator = page.locator(selector)
            if locator.count() > 0 and locator.first.is_visible():
                return selector
        page.wait_for_timeout(250)
    raise AssertionError(f"None of the selectors became visible within {timeout_ms}ms: {selectors}")
