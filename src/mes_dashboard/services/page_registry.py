# -*- coding: utf-8 -*-
"""Page registry service for managing page access status."""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from pathlib import Path
from threading import Lock

logger = logging.getLogger(__name__)

# Data file path (relative to project root)
# Path: src/mes_dashboard/services/page_registry.py -> project root/data/
DATA_FILE = Path(__file__).parent.parent.parent.parent / "data" / "page_status.json"
_lock = Lock()
_cache: dict | None = None
_cache_mtime: float = 0.0
_UNSET = object()

DEFAULT_DRAWERS = [
    {"id": "reports", "name": "報表類", "order": 1, "admin_only": False},
    {"id": "queries", "name": "查詢類", "order": 2, "admin_only": False},
    {"id": "dev-tools", "name": "開發工具", "order": 3, "admin_only": True},
]

LEGACY_NAV_ASSIGNMENTS = {
    "/wip-overview": {"drawer_id": "reports", "order": 1},
    "/resource": {"drawer_id": "reports", "order": 2},
    "/resource-history": {"drawer_id": "reports", "order": 3},
    "/tables": {"drawer_id": "queries", "order": 1},
    "/excel-query": {"drawer_id": "queries", "order": 2},
    "/job-query": {"drawer_id": "queries", "order": 3},
    "/query-tool": {"drawer_id": "queries", "order": 4},
    "/admin/pages": {
        "drawer_id": "dev-tools",
        "order": 1,
        "status": "dev",
        "name": "頁面管理",
    },
    "/admin/dashboard": {
        "drawer_id": "dev-tools",
        "order": 2,
        "status": "dev",
        "name": "管理儀表板",
    },
}


class DrawerError(Exception):
    """Base drawer management error."""


class DrawerNotFoundError(DrawerError):
    """Raised when drawer cannot be found."""


class DrawerConflictError(DrawerError):
    """Raised when drawer operation conflicts with existing data."""


def _load() -> dict:
    """Load page status configuration.

    Detects file changes across gunicorn workers by comparing mtime,
    so writes from one worker are visible to reads in another.
    """
    global _cache, _cache_mtime

    # Check if another worker has written a newer version to disk.
    if _cache is not None:
        try:
            disk_mtime = DATA_FILE.stat().st_mtime
        except OSError:
            disk_mtime = 0.0
        if disk_mtime > _cache_mtime:
            _cache = None  # Invalidate so we re-read below.

    if _cache is None:
        if DATA_FILE.exists():
            try:
                _cache = json.loads(DATA_FILE.read_text(encoding="utf-8"))
                _cache_mtime = DATA_FILE.stat().st_mtime
                logger.debug("Loaded page status from %s", DATA_FILE)
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("Failed to load page status: %s", e)
                _cache = {"pages": [], "api_public": False}
                _cache_mtime = 0.0
        else:
            logger.info("Page status file not found, using defaults")
            _cache = {"pages": [], "api_public": False}
            _cache_mtime = 0.0

        if _migrate_navigation_schema(_cache):
            _save(_cache)
            logger.info("Migrated page status config to drawers schema")
    return _cache


def _save(data: dict) -> None:
    """Save page status configuration."""
    global _cache, _cache_mtime
    tmp_path: Path | None = None
    try:
        DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(data, ensure_ascii=False, indent=2)

        # Atomic write: write to sibling temp file, then replace target.
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=str(DATA_FILE.parent),
            prefix=f".{DATA_FILE.name}.",
            suffix=".tmp",
            delete=False,
        ) as tmp:
            tmp.write(payload)
            tmp.flush()
            os.fsync(tmp.fileno())
            tmp_path = Path(tmp.name)
        os.replace(tmp_path, DATA_FILE)
        _cache = data
        try:
            _cache_mtime = DATA_FILE.stat().st_mtime
        except OSError:
            _cache_mtime = 0.0
        logger.debug("Saved page status to %s", DATA_FILE)
    except OSError as e:
        if tmp_path is not None:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass
        logger.error("Failed to save page status: %s", e)
        raise


def _migrate_navigation_schema(data: dict) -> bool:
    """Migrate legacy schema to drawers schema when needed."""
    if "drawers" in data:
        return False

    data["drawers"] = [drawer.copy() for drawer in DEFAULT_DRAWERS]
    pages = data.setdefault("pages", [])
    pages_by_route = {page.get("route"): page for page in pages if page.get("route")}

    for route, assignment in LEGACY_NAV_ASSIGNMENTS.items():
        page = pages_by_route.get(route)
        if page is None and route.startswith("/admin/"):
            page = {
                "route": route,
                "name": assignment.get("name", route),
                "status": assignment.get("status", "dev"),
            }
            pages.append(page)
            pages_by_route[route] = page

        if page is None:
            continue

        page.setdefault("drawer_id", assignment["drawer_id"])
        page.setdefault("order", assignment["order"])
        if assignment.get("name"):
            page.setdefault("name", assignment["name"])
        if assignment.get("status"):
            page.setdefault("status", assignment["status"])

    return True


def _safe_int(value: object, default: int) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _as_positive_int(value: object, *, field: str) -> int:
    try:
        parsed = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be an integer") from exc

    if parsed < 1:
        raise ValueError(f"{field} must be >= 1")
    return parsed


def _drawer_exists(data: dict, drawer_id: str) -> bool:
    return any(drawer.get("id") == drawer_id for drawer in data.get("drawers", []))


def _apply_page_drawer(data: dict, page: dict, drawer_id: str | None) -> None:
    if drawer_id in (None, ""):
        page.pop("drawer_id", None)
        return

    drawer_id = str(drawer_id)
    if not _drawer_exists(data, drawer_id):
        raise ValueError(f"Drawer not found: {drawer_id}")
    page["drawer_id"] = drawer_id


def _apply_page_order(page: dict, order: object) -> None:
    if order in (None, ""):
        page.pop("order", None)
        return
    page["order"] = _as_positive_int(order, field="order")


def _slugify_drawer_id(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "drawer"


def _generate_drawer_id(name: str, existing_ids: set[str]) -> str:
    base = _slugify_drawer_id(name)
    candidate = base
    suffix = 2
    while candidate in existing_ids:
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


def _sorted_drawers(drawers: list[dict]) -> list[dict]:
    return sorted(
        drawers,
        key=lambda drawer: (
            _safe_int(drawer.get("order"), 9999),
            str(drawer.get("name", "")),
        ),
    )


def _sorted_pages(pages: list[dict]) -> list[dict]:
    return sorted(
        pages,
        key=lambda page: (
            _safe_int(page.get("order"), 9999),
            str(page.get("name") or page.get("route", "")),
        ),
    )


def get_page_status(route: str) -> str | None:
    """Get page status ('released' or 'dev').

    Args:
        route: Page route path (e.g., '/wip-overview')

    Returns:
        'released', 'dev', or None if page is not registered.
    """
    with _lock:
        data = _load()
        for page in data.get("pages", []):
            if page["route"] == route:
                return page.get("status", "dev")
        return None  # Not registered - let Flask handle it


def is_page_registered(route: str) -> bool:
    """Check if a page is registered in the page registry.

    Args:
        route: Page route path (e.g., '/wip-overview')

    Returns:
        True if page is registered, False otherwise.
    """
    return get_page_status(route) is not None


def set_page_status(
    route: str,
    status: str,
    name: str | None = None,
    drawer_id: str | None | object = _UNSET,
    order: int | None | object = _UNSET,
) -> None:
    """Set page status.

    Args:
        route: Page route path
        status: 'released' or 'dev'
        name: Optional page display name
        drawer_id: Optional drawer assignment (None/'': clear assignment)
        order: Optional page order within drawer (None/'': clear order)
    """
    if status not in ("released", "dev"):
        raise ValueError(f"Invalid status: {status}")

    with _lock:
        data = _load()
        pages = data.setdefault("pages", [])

        # Update existing page
        for page in pages:
            if page["route"] == route:
                page["status"] = status
                if name:
                    page["name"] = name
                if drawer_id is not _UNSET:
                    _apply_page_drawer(data, page, drawer_id)
                if order is not _UNSET:
                    _apply_page_order(page, order)
                _save(data)
                logger.info("Updated page status: %s -> %s", route, status)
                return

        # Add new page
        new_page = {
            "route": route,
            "name": name or route,
            "status": status,
        }
        if drawer_id is not _UNSET:
            _apply_page_drawer(data, new_page, drawer_id)
        if order is not _UNSET:
            _apply_page_order(new_page, order)

        pages.append(new_page)
        _save(data)
        logger.info("Added new page: %s (%s)", route, status)


def get_all_pages() -> list[dict]:
    """Get all page configurations.

    Returns:
        List of page dicts: [{route, name, status, drawer_id?, order?}, ...]
    """
    with _lock:
        return _load().get("pages", [])


def get_all_drawers() -> list[dict]:
    """Get all drawer configurations sorted by order."""
    with _lock:
        data = _load()
        drawers = data.setdefault("drawers", [drawer.copy() for drawer in DEFAULT_DRAWERS])
        return [dict(drawer) for drawer in _sorted_drawers(drawers)]


def create_drawer(name: str, order: int | None = None, admin_only: bool = False) -> dict:
    """Create a new drawer and persist it."""
    normalized_name = (name or "").strip()
    if not normalized_name:
        raise ValueError("Drawer name is required")

    with _lock:
        data = _load()
        drawers = data.setdefault("drawers", [drawer.copy() for drawer in DEFAULT_DRAWERS])
        lower_names = {str(drawer.get("name", "")).strip().casefold() for drawer in drawers}
        if normalized_name.casefold() in lower_names:
            raise DrawerConflictError(f"Drawer name already exists: {normalized_name}")

        existing_ids = {str(drawer.get("id", "")) for drawer in drawers}
        drawer_id = _generate_drawer_id(normalized_name, existing_ids)
        if order is None:
            order = max((_safe_int(drawer.get("order"), 0) for drawer in drawers), default=0) + 1
        else:
            order = _as_positive_int(order, field="order")

        created = {
            "id": drawer_id,
            "name": normalized_name,
            "order": order,
            "admin_only": bool(admin_only),
        }
        drawers.append(created)
        _save(data)
        logger.info("Created drawer: %s", drawer_id)
        return dict(created)


def update_drawer(
    drawer_id: str,
    *,
    name: str | None = None,
    order: int | None = None,
    admin_only: bool | None = None,
) -> dict:
    """Update drawer fields and persist it."""
    with _lock:
        data = _load()
        drawers = data.setdefault("drawers", [drawer.copy() for drawer in DEFAULT_DRAWERS])
        target = next((drawer for drawer in drawers if drawer.get("id") == drawer_id), None)
        if target is None:
            raise DrawerNotFoundError(f"Drawer not found: {drawer_id}")

        if name is not None:
            normalized_name = name.strip()
            if not normalized_name:
                raise ValueError("Drawer name is required")
            for drawer in drawers:
                if drawer is target:
                    continue
                if str(drawer.get("name", "")).strip().casefold() == normalized_name.casefold():
                    raise DrawerConflictError(f"Drawer name already exists: {normalized_name}")
            target["name"] = normalized_name

        if order is not None:
            target["order"] = _as_positive_int(order, field="order")

        if admin_only is not None:
            target["admin_only"] = bool(admin_only)

        _save(data)
        logger.info("Updated drawer: %s", drawer_id)
        return dict(target)


def delete_drawer(drawer_id: str) -> None:
    """Delete a drawer when no pages are assigned to it."""
    with _lock:
        data = _load()
        drawers = data.setdefault("drawers", [drawer.copy() for drawer in DEFAULT_DRAWERS])
        target = next((drawer for drawer in drawers if drawer.get("id") == drawer_id), None)
        if target is None:
            raise DrawerNotFoundError(f"Drawer not found: {drawer_id}")

        assigned_pages = [
            page.get("route")
            for page in data.get("pages", [])
            if page.get("drawer_id") == drawer_id
        ]
        if assigned_pages:
            assigned = ", ".join(str(route) for route in assigned_pages if route)
            raise DrawerConflictError(f"Drawer has assigned pages: {assigned}")

        data["drawers"] = [drawer for drawer in drawers if drawer.get("id") != drawer_id]
        _save(data)
        logger.info("Deleted drawer: %s", drawer_id)


def get_navigation_config() -> list[dict]:
    """Get drawers with nested pages sorted for portal sidebar rendering."""
    with _lock:
        data = _load()
        drawers = _sorted_drawers(data.get("drawers", []))
        grouped: dict[str, dict] = {}
        ordered_drawers: list[dict] = []

        for drawer in drawers:
            normalized_drawer = {
                "id": str(drawer.get("id")),
                "name": drawer.get("name") or str(drawer.get("id")),
                "order": _safe_int(drawer.get("order"), 9999),
                "admin_only": bool(drawer.get("admin_only", False)),
                "pages": [],
            }
            grouped[normalized_drawer["id"]] = normalized_drawer
            ordered_drawers.append(normalized_drawer)

        for page in data.get("pages", []):
            route = page.get("route")
            drawer_id = page.get("drawer_id")
            if not route or not drawer_id or drawer_id not in grouped:
                continue

            drawer = grouped[drawer_id]
            drawer["pages"].append(
                {
                    "route": route,
                    "name": page.get("name") or route,
                    "status": page.get("status", "dev"),
                    "order": _safe_int(page.get("order"), 9999),
                }
            )

        for drawer in ordered_drawers:
            drawer["pages"] = _sorted_pages(drawer["pages"])

        return ordered_drawers


def is_api_public() -> bool:
    """Check if API endpoints are publicly accessible.

    Returns:
        True if API endpoints bypass permission checks
    """
    with _lock:
        value = _load().get("api_public", False)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        if isinstance(value, (int, float)):
            return bool(value)
        return False


def reload_cache() -> None:
    """Force reload of page status from disk."""
    global _cache, _cache_mtime
    with _lock:
        _cache = None
        _cache_mtime = 0.0
        _load()
        logger.info("Reloaded page status cache")
