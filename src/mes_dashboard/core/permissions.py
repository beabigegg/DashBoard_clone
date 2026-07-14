# -*- coding: utf-8 -*-
"""Permission checking utilities."""

from __future__ import annotations

from functools import wraps
from typing import TYPE_CHECKING, Callable
from uuid import uuid4

from flask import session

from mes_dashboard.core.response import forbidden_error, unauthorized_error

if TYPE_CHECKING:
    from typing import Any


def get_owner_token() -> str:
    """Return a stable owner identity for the current session.

    For logged-in users, returns ``session["user"]["username"]``.
    For anonymous users, lazily mints a uuid4 hex token stored in
    ``session["mes_owner_token"]``.

    Note: The first call for an anonymous user mutates the session (lazy mint),
    which marks it dirty and causes a Set-Cookie on the response.
    """
    user = session.get("user")
    if user:
        return user.get("username", "")
    token = session.get("mes_owner_token")
    if not token:
        token = uuid4().hex
        session["mes_owner_token"] = token
    return token


def is_admin_logged_in() -> bool:
    """Check if an admin is currently logged in via session["user"]."""
    return session.get("user", {}).get("is_admin", False)


def get_current_user() -> dict | None:
    """Get current logged-in user info.

    Returns:
        User info dict or None if not logged in
    """
    return session.get("user")


def is_user_logged_in() -> bool:
    """Check if any user (admin or regular) is currently logged in."""
    return "user" in session


def _is_ajax_request() -> bool:
    """Check if the current request is an AJAX request."""
    from flask import request
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return True
    accept = request.headers.get("Accept", "")
    if "application/json" in accept:
        return True
    content_type = request.headers.get("Content-Type", "")
    if "application/json" in content_type:
        return True
    return False


def login_required(f: Callable) -> Callable:
    """Decorator: require any authenticated user. Returns JSON 401 if not logged in."""
    @wraps(f)
    def decorated(*args: Any, **kwargs: Any) -> Any:
        if not is_user_logged_in():
            return unauthorized_error("未登入")
        return f(*args, **kwargs)
    return decorated


def admin_required(f: Callable) -> Callable:
    """Decorator: require admin login for a route. Returns JSON 401/403."""
    @wraps(f)
    def decorated(*args: Any, **kwargs: Any) -> Any:
        if not is_user_logged_in():
            return unauthorized_error("請先登入")
        if not is_admin_logged_in():
            return forbidden_error("需要管理員權限")
        return f(*args, **kwargs)
    return decorated


def can_edit_targets(user_identifier: str | None = None) -> bool:
    """Check whether a user may edit production-achievement target values.

    New independent single-flag gate (production-achievement-kanban),
    unrelated to ``is_admin_logged_in``/``admin_required``. Delegates the
    MySQL whitelist lookup to
    ``services.production_achievement_permission_service.is_user_whitelisted``,
    which already fails closed (returns False) on a missing row,
    ``MYSQL_OPS_ENABLED=false``, or any MySQL exception -- this function does
    not add its own try/except because the service never raises.

    Scope widened by production-achievement-overhaul (verbatim reuse, no
    code/mechanism change here): this same whitelist flag now ALSO gates
    write access to the 3 new MySQL-backed config tables --
    ``production_achievement_package_lf_map`` (D1),
    ``production_achievement_workcenter_merge_map`` (D2), and
    ``production_achievement_daily_plans`` -- via their
    ``GET/PUT/DELETE /api/production-achievement/{package-lf-map,
    workcenter-merge-map}[/{raw}]`` and ``GET/PUT .../daily-plans``
    endpoints, reached from the standalone
    ``/production-achievement-settings`` mini-app. There is still no new
    permission system: a whitelisted user can now edit 4 tables (targets +
    3 new) with the exact same single ``can_edit_targets`` flag, not 4
    independent flags.

    Args:
        user_identifier: Explicit identity to check. Defaults to the current
            session's username (``session["user"]["username"]``), matching
            ``get_owner_token()``'s canonical identity form.

    Returns:
        True only if a whitelist row exists with ``can_edit_targets = true``.
        Always False (deny) on any failure mode -- never fails open.
    """
    if user_identifier is None:
        user = session.get("user") or {}
        user_identifier = user.get("username", "")

    if not user_identifier:
        return False

    try:
        from mes_dashboard.services.production_achievement_permission_service import (
            is_user_whitelisted,
        )
        return bool(is_user_whitelisted(user_identifier))
    except Exception:
        # Defense in depth: even though is_user_whitelisted already fails
        # closed internally, never let an unexpected exception here escape
        # as an allow.
        return False


def targets_edit_required(f: Callable) -> Callable:
    """Decorator: require the can_edit_targets whitelist flag for a route.

    Returns JSON 401 when not logged in, 403 (forbidden_error) when the
    current session's user is not whitelisted. Independent of
    ``admin_required`` -- an admin user without a whitelist row is still
    denied (design.md Key Decisions).

    Note: the 10 new production-achievement-overhaul route handlers
    (package-lf-map / workcenter-merge-map / daily-plans) call
    ``can_edit_targets()`` directly (mirroring the existing ``PUT /targets``
    handler's inline-check style in
    ``routes/production_achievement_routes.py``) rather than this decorator,
    for consistency with that file's established per-endpoint pattern --
    the underlying gate is identical either way.
    """
    @wraps(f)
    def decorated(*args: Any, **kwargs: Any) -> Any:
        if not is_user_logged_in():
            return unauthorized_error("請先登入")
        if not can_edit_targets():
            return forbidden_error("無權限編輯目標值")
        return f(*args, **kwargs)
    return decorated
