# -*- coding: utf-8 -*-
"""Permission checking utilities."""

from __future__ import annotations

from functools import wraps
from typing import TYPE_CHECKING, Callable

from flask import jsonify, redirect, request, session, url_for

if TYPE_CHECKING:
    from typing import Any


def is_admin_logged_in() -> bool:
    """Check if an admin is currently logged in.

    Returns:
        True if 'admin' key exists in session
    """
    return "admin" in session


def get_current_admin() -> dict | None:
    """Get current logged-in admin info.

    Returns:
        Admin info dict or None if not logged in
    """
    return session.get("admin")


def _is_ajax_request() -> bool:
    """Check if the current request is an AJAX request.

    Returns:
        True if request appears to be AJAX (fetch/XHR)
    """
    # Check X-Requested-With header (jQuery style)
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return True
    # Check Accept header for JSON
    accept = request.headers.get("Accept", "")
    if "application/json" in accept:
        return True
    # Check Content-Type for JSON POST requests
    content_type = request.headers.get("Content-Type", "")
    if "application/json" in content_type:
        return True
    return False


def admin_required(f: Callable) -> Callable:
    """Decorator to require admin login for a route.

    For regular requests: Redirects to login page if not logged in.
    For AJAX requests: Returns JSON error with 401 status.
    """
    @wraps(f)
    def decorated(*args: Any, **kwargs: Any) -> Any:
        if not is_admin_logged_in():
            if _is_ajax_request():
                return jsonify({"error": "請先登入管理員帳號", "login_required": True}), 401
            return redirect(url_for("auth.login", next=request.url))
        return f(*args, **kwargs)
    return decorated
