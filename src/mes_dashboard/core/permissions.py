# -*- coding: utf-8 -*-
"""Permission checking utilities."""

from __future__ import annotations

from functools import wraps
from typing import TYPE_CHECKING, Callable

from flask import redirect, request, session, url_for

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


def admin_required(f: Callable) -> Callable:
    """Decorator to require admin login for a route.

    Redirects to login page if not logged in.
    """
    @wraps(f)
    def decorated(*args: Any, **kwargs: Any) -> Any:
        if not is_admin_logged_in():
            return redirect(url_for("auth.login", next=request.url))
        return f(*args, **kwargs)
    return decorated
