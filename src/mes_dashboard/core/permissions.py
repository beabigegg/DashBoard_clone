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
