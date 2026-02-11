# -*- coding: utf-8 -*-
"""Navigation contract helpers for portal migration safety checks."""

from __future__ import annotations

from typing import Any


VALID_PAGE_STATUS = {"released", "dev"}
VALID_RENDER_MODES = {"native", "wrapper"}
VALID_REWRITE_EVIDENCE_STATUS = {"pending", "pass", "fail", "n/a"}


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _can_view(status: str | None, is_admin: bool) -> bool:
    if is_admin:
        return True
    return status == "released"


def compute_drawer_visibility(data: dict[str, Any], is_admin: bool) -> list[dict[str, Any]]:
    """Compute effective drawer visibility using current registry semantics."""
    drawers = sorted(
        [dict(d) for d in data.get("drawers", [])],
        key=lambda d: (_safe_int(d.get("order"), 9999), str(d.get("name", ""))),
    )
    pages = [dict(p) for p in data.get("pages", [])]

    pages_by_drawer: dict[str, list[dict[str, Any]]] = {}
    for page in pages:
        drawer_id = page.get("drawer_id")
        if not drawer_id:
            continue
        pages_by_drawer.setdefault(str(drawer_id), []).append(page)

    visible_drawers: list[dict[str, Any]] = []
    for drawer in drawers:
        if bool(drawer.get("admin_only", False)) and not is_admin:
            continue

        drawer_id = str(drawer.get("id"))
        drawer_pages = sorted(
            pages_by_drawer.get(drawer_id, []),
            key=lambda p: (_safe_int(p.get("order"), 9999), str(p.get("name") or p.get("route", ""))),
        )

        visible_pages = [
            {
                "route": page.get("route"),
                "name": page.get("name"),
                "status": page.get("status"),
                "order": page.get("order"),
            }
            for page in drawer_pages
            if _can_view(page.get("status"), is_admin)
        ]

        if not visible_pages:
            continue

        visible_drawers.append(
            {
                "id": drawer_id,
                "name": drawer.get("name"),
                "order": drawer.get("order"),
                "admin_only": bool(drawer.get("admin_only", False)),
                "pages": visible_pages,
            }
        )
    return visible_drawers


def validate_drawer_page_contract(data: dict[str, Any]) -> list[str]:
    """Validate drawer/page assignments and ordering constraints."""
    errors: list[str] = []
    drawers = data.get("drawers", [])
    pages = data.get("pages", [])

    seen_drawers: set[str] = set()
    for drawer in drawers:
        drawer_id = str(drawer.get("id", "")).strip()
        if not drawer_id:
            errors.append("drawer.id is required")
            continue
        if drawer_id in seen_drawers:
            errors.append(f"duplicate drawer id: {drawer_id}")
        seen_drawers.add(drawer_id)

        order = drawer.get("order")
        if order is not None and _safe_int(order, 0) < 1:
            errors.append(f"drawer.order must be >= 1: {drawer_id}")

    seen_routes: set[str] = set()
    for page in pages:
        route = str(page.get("route", "")).strip()
        if not route:
            errors.append("page.route is required")
            continue
        if route in seen_routes:
            errors.append(f"duplicate page route: {route}")
        seen_routes.add(route)

        status = str(page.get("status", "dev"))
        if status not in VALID_PAGE_STATUS:
            errors.append(f"invalid page status for {route}: {status}")

        drawer_id = page.get("drawer_id")
        if drawer_id is not None and str(drawer_id) not in seen_drawers:
            errors.append(f"page references missing drawer: route={route}, drawer_id={drawer_id}")

        order = page.get("order")
        if order is not None and _safe_int(order, 0) < 1:
            errors.append(f"page.order must be >= 1: {route}")

    return sorted(set(errors))


def validate_route_migration_contract(
    data: dict[str, Any],
    *,
    required_routes: set[str] | None = None,
) -> list[str]:
    """Validate route migration contract for shell route-view cutover.

    Expected shape:
    {
      "routes": [
        {
          "route": "/wip-overview",
          "render_mode": "native" | "wrapper",
          "required_query_keys": [...],
          "owner": "...",
          "rollback_strategy": "..."
        }
      ]
    }
    """
    errors: list[str] = []

    routes = data.get("routes")
    if not isinstance(routes, list):
        return ["routes must be a list"]

    seen_routes: set[str] = set()
    for idx, item in enumerate(routes):
        if not isinstance(item, dict):
            errors.append(f"routes[{idx}] must be an object")
            continue

        route = str(item.get("route", "")).strip()
        if not route:
            errors.append(f"routes[{idx}].route is required")
            continue
        if not route.startswith("/"):
            errors.append(f"routes[{idx}].route must start with '/': {route}")
        if route in seen_routes:
            errors.append(f"duplicate route definition: {route}")
        seen_routes.add(route)

        render_mode = str(item.get("render_mode", "")).strip()
        if render_mode not in VALID_RENDER_MODES:
            errors.append(f"invalid render_mode for {route}: {render_mode}")

        owner = str(item.get("owner", "")).strip()
        if not owner:
            errors.append(f"owner is required for {route}")

        rollback_strategy = str(item.get("rollback_strategy", "")).strip()
        if not rollback_strategy:
            errors.append(f"rollback_strategy is required for {route}")

        query_keys = item.get("required_query_keys", [])
        if not isinstance(query_keys, list):
            errors.append(f"required_query_keys must be a list for {route}")
        else:
            normalized_keys: list[str] = []
            for key in query_keys:
                if not isinstance(key, str) or not key.strip():
                    errors.append(f"required_query_keys contains invalid key for {route}")
                    continue
                normalized_keys.append(key.strip())
            if len(normalized_keys) != len(set(normalized_keys)):
                errors.append(f"required_query_keys contains duplicates for {route}")

    if required_routes is not None:
        missing = sorted(required_routes - seen_routes)
        if missing:
            errors.append("missing route definitions: " + ", ".join(missing))

    return sorted(set(errors))


def validate_wave_b_rewrite_entry_criteria(
    route_contract_data: dict[str, Any],
    rewrite_criteria_data: dict[str, Any],
) -> list[str]:
    """Validate Wave B rewrite entry criteria and native cutover gate rules.

    Gate rule:
    - For Wave B routes (rollback strategy retain_wrapper_until_rewrite_is_green),
      native cutover is blocked unless criteria and evidence are complete.
    """
    errors: list[str] = []

    routes = route_contract_data.get("routes")
    if not isinstance(routes, list):
        return ["route contract routes must be a list"]

    pages = rewrite_criteria_data.get("pages")
    if not isinstance(pages, dict):
        return ["rewrite criteria pages must be an object"]

    tracked_routes: dict[str, str] = {}
    for idx, item in enumerate(routes):
        if not isinstance(item, dict):
            errors.append(f"routes[{idx}] must be an object")
            continue

        route = str(item.get("route", "")).strip()
        if not route.startswith("/"):
            continue

        render_mode = str(item.get("render_mode", "")).strip()
        if route in pages:
            tracked_routes[route] = render_mode

    for route in sorted(tracked_routes):
        criteria = pages.get(route)
        if not isinstance(criteria, dict):
            errors.append(f"missing rewrite entry criteria for {route}")
            continue

        smoke_checks = criteria.get("required_smoke_checks")
        if not isinstance(smoke_checks, list) or not smoke_checks:
            errors.append(f"required_smoke_checks must be non-empty for {route}")
        elif any(not isinstance(item, str) or not item.strip() for item in smoke_checks):
            errors.append(f"required_smoke_checks contains invalid item for {route}")

        parity_checks = criteria.get("required_parity_checks")
        if not isinstance(parity_checks, list) or not parity_checks:
            errors.append(f"required_parity_checks must be non-empty for {route}")
        elif any(not isinstance(item, str) or not item.strip() for item in parity_checks):
            errors.append(f"required_parity_checks contains invalid item for {route}")

        evidence = criteria.get("evidence")
        if not isinstance(evidence, dict):
            errors.append(f"evidence must be an object for {route}")
            continue

        smoke_status = str(evidence.get("smoke", "")).strip()
        parity_status = str(evidence.get("parity", "")).strip()
        telemetry_status = str(evidence.get("telemetry", "")).strip()

        for key, status in (
            ("smoke", smoke_status),
            ("parity", parity_status),
            ("telemetry", telemetry_status),
        ):
            if status not in VALID_REWRITE_EVIDENCE_STATUS:
                errors.append(f"invalid evidence status for {route}: {key}={status}")

        native_cutover_ready = bool(criteria.get("native_cutover_ready", False))
        criteria_complete = (
            native_cutover_ready
            and smoke_status == "pass"
            and parity_status == "pass"
            and telemetry_status in {"pass", "n/a"}
        )

        if tracked_routes[route] == "native" and not criteria_complete:
            errors.append(f"native cutover blocked for {route}: rewrite criteria incomplete")

    return sorted(set(errors))
