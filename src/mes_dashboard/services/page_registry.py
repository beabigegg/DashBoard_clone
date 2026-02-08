# -*- coding: utf-8 -*-
"""Page registry service for managing page access status."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from threading import Lock

logger = logging.getLogger(__name__)

# Data file path (relative to project root)
# Path: src/mes_dashboard/services/page_registry.py -> project root/data/
DATA_FILE = Path(__file__).parent.parent.parent.parent / "data" / "page_status.json"
_lock = Lock()
_cache: dict | None = None


def _load() -> dict:
    """Load page status configuration."""
    global _cache
    if _cache is None:
        if DATA_FILE.exists():
            try:
                _cache = json.loads(DATA_FILE.read_text(encoding="utf-8"))
                logger.debug("Loaded page status from %s", DATA_FILE)
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("Failed to load page status: %s", e)
                _cache = {"pages": [], "api_public": True}
        else:
            logger.info("Page status file not found, using defaults")
            _cache = {"pages": [], "api_public": True}
    return _cache


def _save(data: dict) -> None:
    """Save page status configuration."""
    global _cache
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
        logger.debug("Saved page status to %s", DATA_FILE)
    except OSError as e:
        if tmp_path is not None:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass
        logger.error("Failed to save page status: %s", e)
        raise


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


def set_page_status(route: str, status: str, name: str | None = None) -> None:
    """Set page status.

    Args:
        route: Page route path
        status: 'released' or 'dev'
        name: Optional page display name
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
                _save(data)
                logger.info("Updated page status: %s -> %s", route, status)
                return

        # Add new page
        pages.append({
            "route": route,
            "name": name or route,
            "status": status
        })
        _save(data)
        logger.info("Added new page: %s (%s)", route, status)


def get_all_pages() -> list[dict]:
    """Get all page configurations.

    Returns:
        List of page dicts: [{route, name, status}, ...]
    """
    with _lock:
        return _load().get("pages", [])


def is_api_public() -> bool:
    """Check if API endpoints are publicly accessible.

    Returns:
        True if API endpoints bypass permission checks
    """
    with _lock:
        return _load().get("api_public", True)


def reload_cache() -> None:
    """Force reload of page status from disk."""
    global _cache
    with _lock:
        _cache = None
        _load()
        logger.info("Reloaded page status cache")
