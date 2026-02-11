# -*- coding: utf-8 -*-
"""Navigation contract helpers for portal migration safety checks."""

from __future__ import annotations

from typing import Any


VALID_PAGE_STATUS = {"released", "dev"}


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
