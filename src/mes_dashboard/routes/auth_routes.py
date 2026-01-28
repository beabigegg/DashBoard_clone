# -*- coding: utf-8 -*-
"""Authentication routes for admin login/logout."""

from __future__ import annotations

from datetime import datetime

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from mes_dashboard.services.auth_service import authenticate, is_admin

auth_bp = Blueprint("auth", __name__, url_prefix="/admin")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """Admin login page."""
    error = None

    if request.method == "POST":
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
                session["admin"] = {
                    "username": user.get("username"),
                    "displayName": user.get("displayName"),
                    "mail": user.get("mail"),
                    "department": user.get("department"),
                    "login_time": datetime.now().isoformat(),
                }
                next_url = request.args.get("next", url_for("portal_index"))
                return redirect(next_url)

    return render_template("login.html", error=error)


@auth_bp.route("/logout")
def logout():
    """Admin logout."""
    session.pop("admin", None)
    return redirect(url_for("portal_index"))
