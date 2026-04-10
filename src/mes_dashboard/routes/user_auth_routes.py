# -*- coding: utf-8 -*-
"""User authentication API routes (login/logout/me/heartbeat)."""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from datetime import datetime
from threading import Lock

from flask import Blueprint, request, session

from mes_dashboard.core.csrf import rotate_csrf_token
from mes_dashboard.core.permissions import login_required
from mes_dashboard.core.response import (
    success_response,
    validation_error,
    too_many_requests_error,
)
from mes_dashboard.services.auth_service import authenticate, is_admin

logger = logging.getLogger('mes_dashboard.user_auth_routes')
user_auth_bp = Blueprint("user_auth", __name__)

# ============================================================
# Rate Limiting (Redis-backed + in-memory fallback)
# ============================================================

_rate_limit_lock = Lock()
_login_attempts: dict = defaultdict(list)
_last_cleanup = time.time()
RATE_LIMIT_MAX_ATTEMPTS = 5
RATE_LIMIT_WINDOW_SECONDS = 300  # 5 minutes
_CLEANUP_INTERVAL = 600
_REDIS_LOGIN_KEY_PREFIX = "mes:login_attempts:"


def _get_redis():
    try:
        from mes_dashboard.core.redis_client import get_redis_client
        return get_redis_client()
    except Exception:
        return None


def _cleanup_stale_entries() -> None:
    global _last_cleanup
    now = time.time()
    if now - _last_cleanup < _CLEANUP_INTERVAL:
        return
    _last_cleanup = now
    window_start = now - RATE_LIMIT_WINDOW_SECONDS
    stale_ips = [
        ip for ip, timestamps in _login_attempts.items()
        if not timestamps or timestamps[-1] <= window_start
    ]
    for ip in stale_ips:
        del _login_attempts[ip]


def _is_rate_limited(ip: str) -> bool:
    redis_client = _get_redis()
    if redis_client:
        try:
            key = f"{_REDIS_LOGIN_KEY_PREFIX}{ip}"
            count = redis_client.get(key)
            return int(count or 0) >= RATE_LIMIT_MAX_ATTEMPTS
        except Exception:
            pass

    current_time = time.time()
    window_start = current_time - RATE_LIMIT_WINDOW_SECONDS

    with _rate_limit_lock:
        _cleanup_stale_entries()
        _login_attempts[ip] = [
            ts for ts in _login_attempts[ip] if ts > window_start
        ]
        return len(_login_attempts[ip]) >= RATE_LIMIT_MAX_ATTEMPTS


def _record_login_attempt(ip: str) -> None:
    redis_client = _get_redis()
    if redis_client:
        try:
            key = f"{_REDIS_LOGIN_KEY_PREFIX}{ip}"
            pipe = redis_client.pipeline()
            pipe.incr(key)
            pipe.expire(key, RATE_LIMIT_WINDOW_SECONDS)
            pipe.execute()
            return
        except Exception:
            pass

    with _rate_limit_lock:
        _login_attempts[ip].append(time.time())


# ============================================================
# Helpers
# ============================================================

def _extract_real_name(display_name: str) -> str:
    """Extract Chinese name from displayName like 'ymirliu 劉念萱'."""
    parts = display_name.strip().split(" ", 1)
    if len(parts) == 2:
        return parts[1]
    return display_name


# ============================================================
# Routes
# ============================================================

@user_auth_bp.route("/api/auth/login", methods=["POST"])
def login():
    """Authenticate user and create a session."""
    client_ip = request.remote_addr or "unknown"

    if _is_rate_limited(client_ip):
        logger.warning("Rate limit exceeded for IP: %s", client_ip)
        return too_many_requests_error()

    body = request.get_json(silent=True) or {}
    username = str(body.get("username", "")).strip()
    password = str(body.get("password", ""))

    if not username or not password:
        return validation_error("請輸入帳號和密碼")

    user = authenticate(username, password)
    if user is None:
        _record_login_attempt(client_ip)
        return validation_error("帳號或密碼錯誤")

    display_name = user.get("displayName", "")
    real_name = _extract_real_name(display_name)
    admin_flag = is_admin(user)

    from mes_dashboard.core.login_session_store import get_login_session_store
    login_store = get_login_session_store()

    user_payload = {
        "username": user.get("username"),
        "displayName": display_name,
        "real_name": real_name,
        "mail": user.get("mail"),
        "department": user.get("department"),
        "telephoneNumber": user.get("telephoneNumber"),
        "domain": user.get("domain"),
        "is_admin": admin_flag,
        "login_time": datetime.now().isoformat(),
        "ip": client_ip,
    }

    session_id = login_store.create_session(user_payload, client_ip)
    user_payload["session_id"] = session_id

    session.clear()
    session["user"] = user_payload
    session.permanent = True
    new_csrf = rotate_csrf_token()

    logger.info("User logged in: %s (admin=%s)", username, admin_flag)

    return success_response({
        "username": user_payload["username"],
        "displayName": user_payload["displayName"],
        "real_name": user_payload["real_name"],
        "mail": user_payload["mail"],
        "department": user_payload["department"],
        "telephoneNumber": user_payload["telephoneNumber"],
        "is_admin": admin_flag,
        "csrf_token": new_csrf,
    })


@user_auth_bp.route("/api/auth/logout", methods=["POST"])
def logout():
    """Log out the current user."""
    user = session.get("user")
    if user:
        session_id = user.get("session_id")
        if session_id:
            try:
                from mes_dashboard.core.login_session_store import get_login_session_store
                get_login_session_store().close_session(session_id)
            except Exception as e:
                logger.warning("Failed to close login session: %s", e)
        username = user.get("username", "unknown")
        logger.info("User logged out: %s", username)

    session.clear()
    return success_response(None)


@user_auth_bp.route("/api/auth/me", methods=["GET"])
def me():
    """Return current login state. Returns null data if not logged in."""
    user = session.get("user")
    if user is None:
        return success_response(None)
    return success_response({
        "username": user.get("username"),
        "displayName": user.get("displayName"),
        "real_name": user.get("real_name"),
        "mail": user.get("mail"),
        "department": user.get("department"),
        "telephoneNumber": user.get("telephoneNumber"),
        "is_admin": user.get("is_admin", False),
    })


@user_auth_bp.route("/api/auth/heartbeat", methods=["PATCH"])
@login_required
def heartbeat():
    """Update last_active timestamp for the current session."""
    user = session.get("user", {})
    session_id = user.get("session_id")
    online_count = None
    if session_id:
        try:
            from mes_dashboard.core.login_session_store import get_login_session_store
            store = get_login_session_store()
            store.update_last_active(session_id)
            online_count = store.get_active_count()
        except Exception as e:
            logger.warning("Failed to update heartbeat: %s", e)
    data = {"online_count": online_count} if online_count is not None else None
    return success_response(data)
