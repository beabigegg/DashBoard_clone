# -*- coding: utf-8 -*-
"""Authentication routes for admin login/logout."""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from datetime import datetime
from threading import Lock
from urllib.parse import urlparse

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from mes_dashboard.core.csrf import rotate_csrf_token
from mes_dashboard.services.auth_service import authenticate, is_admin

logger = logging.getLogger('mes_dashboard.auth_routes')
auth_bp = Blueprint("auth", __name__, url_prefix="/admin")


# ============================================================
# Rate Limiting for Login Endpoint
# ============================================================
# Redis-backed rate limiter (cross-worker) with in-memory fallback.
# Configuration: max 5 attempts per IP per 5 minutes

_rate_limit_lock = Lock()
_login_attempts: dict = defaultdict(list)  # IP -> list of timestamps
_last_cleanup = time.time()
RATE_LIMIT_MAX_ATTEMPTS = 5
RATE_LIMIT_WINDOW_SECONDS = 300  # 5 minutes
_CLEANUP_INTERVAL = 600  # Sweep stale entries every 10 minutes
_REDIS_LOGIN_KEY_PREFIX = "mes:login_attempts:"


def _get_redis():
    """Get Redis client if available."""
    try:
        from mes_dashboard.core.redis_client import get_redis_client
        return get_redis_client()
    except Exception:
        return None


def _sanitize_next_url(next_url: str | None) -> str:
    """Return a safe post-login redirect URL limited to local paths."""
    fallback = url_for("portal_index")
    if not next_url:
        return fallback

    parsed = urlparse(next_url)
    if parsed.scheme or parsed.netloc:
        logger.warning("Blocked external next redirect: %s", next_url)
        return fallback

    if not next_url.startswith("/") or next_url.startswith("//"):
        return fallback

    return next_url


def _cleanup_stale_entries() -> None:
    """Remove stale IP entries from the in-memory rate limiter."""
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
    """Check if an IP address is rate limited.

    Uses Redis when available for cross-worker consistency,
    falls back to in-memory dict otherwise.
    """
    redis_client = _get_redis()
    if redis_client:
        try:
            key = f"{_REDIS_LOGIN_KEY_PREFIX}{ip}"
            count = redis_client.get(key)
            return int(count or 0) >= RATE_LIMIT_MAX_ATTEMPTS
        except Exception:
            pass  # Fall through to in-memory

    current_time = time.time()
    window_start = current_time - RATE_LIMIT_WINDOW_SECONDS

    with _rate_limit_lock:
        _cleanup_stale_entries()
        _login_attempts[ip] = [
            ts for ts in _login_attempts[ip] if ts > window_start
        ]
        return len(_login_attempts[ip]) >= RATE_LIMIT_MAX_ATTEMPTS


def _record_login_attempt(ip: str) -> None:
    """Record a login attempt for rate limiting."""
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
            pass  # Fall through to in-memory

    with _rate_limit_lock:
        _login_attempts[ip].append(time.time())


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """Admin login page."""
    error = None

    if request.method == "POST":
        # Rate limiting check
        client_ip = request.remote_addr or "unknown"
        if _is_rate_limited(client_ip):
            logger.warning(f"Rate limit exceeded for IP: {client_ip}")
            error = "登入嘗試過於頻繁，請稍後再試"
            return render_template("login.html", error=error)

        # Record this attempt
        _record_login_attempt(client_ip)

        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not username or not password:
            error = "請輸入帳號和密碼"
        else:
            user = authenticate(username, password)
            if user is None:
                error = "帳號或密碼錯誤"
            elif not is_admin(user):
                error = "您不是管理員，無法登入後台"
            else:
                # Login successful
                session.clear()
                session["admin"] = {
                    "username": user.get("username"),
                    "displayName": user.get("displayName"),
                    "mail": user.get("mail"),
                    "department": user.get("department"),
                    "login_time": datetime.now().isoformat(),
                }
                rotate_csrf_token()
                next_url = _sanitize_next_url(request.args.get("next"))
                return redirect(next_url)

    return render_template("login.html", error=error)


@auth_bp.route("/logout")
def logout():
    """Admin logout."""
    session.clear()
    return redirect(url_for("portal_index"))
