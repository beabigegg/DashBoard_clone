# -*- coding: utf-8 -*-
"""Modernization policy helpers shared by routes and release gates."""

from __future__ import annotations

import copy
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from flask import current_app, redirect, render_template, request

from mes_dashboard.core.feature_flags import resolve_bool_flag


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DOCS_DIR = PROJECT_ROOT / "docs" / "migration" / "full-modernization-architecture-blueprint"
SCOPE_MATRIX_FILE = DOCS_DIR / "route_scope_matrix.json"
ASSET_MANIFEST_FILE = DOCS_DIR / "asset_readiness_manifest.json"


def _read_json(path: Path, fallback: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return dict(fallback)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return dict(fallback)


@lru_cache(maxsize=1)
def _load_scope_matrix_cached() -> dict[str, Any]:
    return _read_json(SCOPE_MATRIX_FILE, fallback={"in_scope": [], "deferred": []})


@lru_cache(maxsize=1)
def _load_asset_manifest_cached() -> dict[str, Any]:
    return _read_json(ASSET_MANIFEST_FILE, fallback={"in_scope_required_assets": {}, "deferred_routes": []})


def clear_modernization_policy_cache() -> None:
    """Clear in-process policy caches for tests/controlled refresh flows.

    Runtime expects these policy artifacts to be refreshed by worker restart.
    Keep this helper for explicit test setup or operational maintenance hooks.
    """
    _load_scope_matrix_cached.cache_clear()
    _load_asset_manifest_cached.cache_clear()


def load_scope_matrix() -> dict[str, Any]:
    # Defensive copy prevents callers from mutating the shared cached payload.
    return copy.deepcopy(_load_scope_matrix_cached())


def load_asset_manifest() -> dict[str, Any]:
    # Defensive copy prevents callers from mutating the shared cached payload.
    return copy.deepcopy(_load_asset_manifest_cached())


def get_in_scope_routes() -> list[str]:
    matrix = load_scope_matrix()
    routes = []
    for item in matrix.get("in_scope", []):
        route = str(item.get("route", "")).strip()
        if route.startswith("/"):
            routes.append(route)
    return routes


def get_in_scope_report_routes() -> list[str]:
    matrix = load_scope_matrix()
    routes = []
    for item in matrix.get("in_scope", []):
        route = str(item.get("route", "")).strip()
        category = str(item.get("category", "")).strip().lower()
        if route.startswith("/") and category == "report":
            routes.append(route)
    return routes


def get_deferred_routes() -> list[str]:
    matrix = load_scope_matrix()
    routes = []
    for item in matrix.get("deferred", []):
        route = str(item.get("route", "")).strip()
        if route.startswith("/"):
            routes.append(route)
    return routes


def is_in_scope_route(route: str) -> bool:
    return route in set(get_in_scope_routes())


def is_in_scope_report_route(route: str) -> bool:
    return route in set(get_in_scope_report_routes())


def is_deferred_route(route: str) -> bool:
    return route in set(get_deferred_routes())


def canonical_shell_path(route: str) -> str:
    normalized = str(route or "").strip()
    if not normalized.startswith("/"):
        normalized = f"/{normalized}"
    return f"/portal-shell{normalized}"


def should_apply_canonical_redirect() -> bool:
    # Canonical direct-entry compatibility policy only applies in shell-first mode.
    return bool(current_app.config.get("PORTAL_SPA_ENABLED", False))


def maybe_redirect_to_canonical_shell(route: str):
    # Intentional scope boundary: canonical redirects are for in-scope report routes only.
    # Admin routes are rendered as shell external targets; forcing canonical redirects for
    # those routes can create redirect loops between shell and legacy entry points.
    if not should_apply_canonical_redirect():
        return None
    if not is_in_scope_report_route(route):
        return None

    target = canonical_shell_path(route)
    query_string = request.query_string.decode("utf-8")
    if query_string:
        target = f"{target}?{query_string}"
    return redirect(target, code=302)


def is_runtime_fallback_retired_for_route(route: str) -> bool:
    retired = resolve_bool_flag(
        "MODERNIZATION_RETIRE_IN_SCOPE_RUNTIME_FALLBACK",
        config=current_app.config,
        default=bool(current_app.config.get("MODERNIZATION_RETIRE_IN_SCOPE_RUNTIME_FALLBACK", False)),
    )
    return retired and is_in_scope_route(route)


def is_asset_readiness_enforced() -> bool:
    return resolve_bool_flag(
        "MODERNIZATION_ENFORCE_ASSET_READINESS",
        config=current_app.config,
        default=bool(current_app.config.get("MODERNIZATION_ENFORCE_ASSET_READINESS", False)),
    )


def get_missing_in_scope_assets(dist_dir: Path) -> list[str]:
    manifest = load_asset_manifest()
    required_assets = manifest.get("in_scope_required_assets", {})
    missing: list[str] = []

    for route, assets in required_assets.items():
        for filename in assets:
            target = dist_dir / filename
            if not target.exists():
                missing.append(f"{route}:{filename}")
    return sorted(set(missing))


def missing_in_scope_asset_response(route: str, fallback_response: Any):
    """Apply retired-fallback policy with shared response contract."""
    if is_runtime_fallback_retired_for_route(route):
        return render_template("500.html"), 503
    return fallback_response
