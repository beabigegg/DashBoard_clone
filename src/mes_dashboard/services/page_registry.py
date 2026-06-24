# -*- coding: utf-8 -*-
"""Page registry service for managing page access status.

After nav-config-to-code:
  - Runtime-writable store shape: {api_public: bool, statuses: {route: status}}.
  - Structure (drawers, names, order) lives in the frontend navigationManifest.js.
  - Back-compat read: legacy full-CMS file ({pages:[], drawers:[]}) yields correct
    statuses from pages[].status; no forced rewrite.
  - Fail-safe: missing file / absent route → 'released'.
  - api_public MUST be preserved (gates is_api_public() site-wide auth bypass).
"""

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
_cache_mtime: float = 0.0


def _load() -> dict:
    """Load page status configuration.

    Returns a normalised dict with at least ``api_public`` and ``statuses`` keys.
    Handles three input shapes:
      1. New shrunk shape: {api_public, statuses}
      2. Legacy full-CMS shape: {pages:[], drawers:[], api_public}
      3. Missing / corrupt file → fail-safe defaults {api_public:false, statuses:{}}

    Detects file changes across gunicorn workers by comparing mtime.
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
                raw = json.loads(DATA_FILE.read_text(encoding="utf-8"))
                _cache = _normalise_store(raw)
                _cache_mtime = DATA_FILE.stat().st_mtime
                logger.debug("Loaded page status from %s", DATA_FILE)
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("Failed to load page status: %s", e)
                _cache = {"api_public": False, "statuses": {}}
                _cache_mtime = 0.0
        else:
            logger.info("Page status file not found, using defaults")
            _cache = {"api_public": False, "statuses": {}}
            _cache_mtime = 0.0
    return _cache


def _normalise_store(raw: dict) -> dict:
    """Normalise a raw file payload to {api_public, statuses}.

    Supports:
      - New shape {api_public, statuses}
      - Legacy full-CMS shape {pages:[], drawers:[], ...} — derives statuses
        from pages[].status; ignores drawers/db_scan.
    Always preserves api_public; absent key → False (safe default).
    """
    api_public = raw.get("api_public", False)

    # New shrunk shape — already correct.
    if "statuses" in raw:
        return {
            "api_public": api_public,
            "statuses": dict(raw.get("statuses", {})),
        }

    # Legacy full-CMS shape — derive statuses from pages[].status.
    statuses: dict[str, str] = {}
    for page in raw.get("pages", []):
        route = page.get("route")
        status = page.get("status")
        if route and status in ("released", "dev"):
            statuses[route] = status

    logger.debug(
        "Back-compat: derived %d statuses from legacy full-CMS pages array", len(statuses)
    )
    return {"api_public": api_public, "statuses": statuses}


def _save(data: dict) -> None:
    """Save page status configuration (shrunk {api_public, statuses} shape)."""
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


def get_page_status(route: str) -> str | None:
    """Get page status ('released' or 'dev').

    After nav-config-to-code: reads from the ``statuses`` dict.
    Absent route → None (not registered — let Flask handle it).
    Fail-safe: missing file or absent key → None (treated as released by callers).

    Args:
        route: Page route path (e.g., '/wip-overview')

    Returns:
        'released', 'dev', or None if route is not in statuses.
    """
    with _lock:
        data = _load()
        return data.get("statuses", {}).get(route)


def is_page_registered(route: str) -> bool:
    """Check if a page is registered in the page registry.

    Args:
        route: Page route path (e.g., '/wip-overview')

    Returns:
        True if page has an explicit status entry, False otherwise.
    """
    return get_page_status(route) is not None


def set_page_status(route: str, status: str) -> None:
    """Set page status (status-only; structure fields not accepted).

    Args:
        route: Page route path (e.g., '/admin/dashboard')
        status: 'released' or 'dev'
    """
    if status not in ("released", "dev"):
        raise ValueError(f"Invalid status: {status}")

    with _lock:
        data = _load()
        statuses = data.setdefault("statuses", {})
        statuses[route] = status
        _save(data)
        logger.info("Set page status: %s -> %s", route, status)


def get_all_pages() -> list[dict]:
    """Get all page status entries as slim {route, status} dicts.

    Returns:
        List of dicts: [{route: str, status: 'released'|'dev'}, ...]
        Only routes with explicit statuses are included.
    """
    with _lock:
        data = _load()
        return [
            {"route": route, "status": status}
            for route, status in data.get("statuses", {}).items()
        ]


def get_navigation_config() -> dict[str, str]:
    """Return the route→status map for portal navigation.

    After nav-config-to-code: returns the raw statuses dict.
    Structure (drawers/names/order) lives in the frontend navigationManifest.js.
    Absent route defaults to 'released' in all consumers.

    Returns:
        dict mapping route → 'released'|'dev'
    """
    with _lock:
        data = _load()
        return dict(data.get("statuses", {}))


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
