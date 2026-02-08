# -*- coding: utf-8 -*-
"""Authentication routes for admin login/logout."""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from datetime import datetime
from threading import Lock

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from mes_dashboard.core.csrf import rotate_csrf_token
from mes_dashboard.services.auth_service import authenticate, is_admin

logger = logging.getLogger('mes_dashboard.auth_routes')
auth_bp = Blueprint("auth", __name__, url_prefix="/admin")


# ============================================================
# Rate Limiting for Login Endpoint
# ============================================================
# Simple in-memory rate limiter to prevent brute force attacks
# Configuration: max 5 attempts per IP per 5 minutes

_rate_limit_lock = Lock()
_login_attempts: dict = defaultdict(list)  # IP -> list of timestamps
RATE_LIMIT_MAX_ATTEMPTS = 5
RATE_LIMIT_WINDOW_SECONDS = 300  # 5 minutes


def _is_rate_limited(ip: str) -> bool:
    """Check if an IP address is rate limited.

    Args:
        ip: Client IP address.

    Returns:
        True if rate limited, False otherwise.
    """
    current_time = time.time()
    window_start = current_time - RATE_LIMIT_WINDOW_SECONDS

    with _rate_limit_lock:
        # Clean up old attempts
        _login_attempts[ip] = [
            ts for ts in _login_attempts[ip] if ts > window_start
        ]

        # Check if limit exceeded
        if len(_login_attempts[ip]) >= RATE_LIMIT_MAX_ATTEMPTS:
            return True

        return False


def _record_login_attempt(ip: str) -> None:
    """Record a login attempt for rate limiting.

    Args:
        ip: Client IP address.
    """
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
                next_url = request.args.get("next", url_for("portal_index"))
                return redirect(next_url)

    return render_template("login.html", error=error)


@auth_bp.route("/logout")
def logout():
    """Admin logout."""
    session.clear()
    return redirect(url_for("portal_index"))
