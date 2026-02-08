# -*- coding: utf-8 -*-
"""CSRF token utilities for admin form and API mutation protection."""

from __future__ import annotations

import hmac
import secrets
from typing import Optional

from flask import Request, request, session

CSRF_SESSION_KEY = "_csrf_token"
CSRF_HEADER_NAME = "X-CSRF-Token"
CSRF_FORM_FIELD = "csrf_token"
_MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def get_csrf_token() -> str:
    """Get a stable CSRF token for the current session."""
    token = session.get(CSRF_SESSION_KEY)
    if not token:
        token = _new_csrf_token()
        session[CSRF_SESSION_KEY] = token
    return token


def rotate_csrf_token() -> str:
    """Rotate session CSRF token after authentication state changes."""
    token = _new_csrf_token()
    session[CSRF_SESSION_KEY] = token
    return token


def _extract_request_token(req: Request) -> Optional[str]:
    header_token = req.headers.get(CSRF_HEADER_NAME)
    if header_token:
        return header_token

    form_token = req.form.get(CSRF_FORM_FIELD)
    if form_token:
        return form_token

    if req.is_json:
        payload = req.get_json(silent=True) or {}
        json_token = payload.get(CSRF_FORM_FIELD)
        if json_token:
            return str(json_token)

    return None


def should_enforce_csrf(req: Request = request, enabled: bool = True) -> bool:
    """Determine whether current request needs CSRF validation."""
    if not enabled:
        return False

    if req.method.upper() not in _MUTATING_METHODS:
        return False

    path = req.path or ""
    if path == "/admin/login":
        return True
    if path.startswith("/admin/api/"):
        return True
    if path.startswith("/admin/"):
        return True

    return False


def validate_csrf(req: Request = request) -> bool:
    """Validate request CSRF token against current session token."""
    expected = session.get(CSRF_SESSION_KEY)
    if not expected:
        return False

    provided = _extract_request_token(req)
    if not provided:
        return False

    return hmac.compare_digest(str(expected), str(provided))
