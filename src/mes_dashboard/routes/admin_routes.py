# -*- coding: utf-8 -*-
"""Admin routes for page management."""

from __future__ import annotations

from flask import Blueprint, jsonify, render_template, request

from mes_dashboard.core.permissions import admin_required
from mes_dashboard.services.page_registry import get_all_pages, set_page_status

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.route("/pages")
@admin_required
def pages():
    """Page management interface."""
    return render_template("admin/pages.html")


@admin_bp.route("/api/pages", methods=["GET"])
@admin_required
def api_get_pages():
    """API: Get all page configurations."""
    return jsonify({"success": True, "pages": get_all_pages()})


@admin_bp.route("/api/pages/<path:route>", methods=["PUT"])
@admin_required
def api_update_page(route: str):
    """API: Update page status."""
    data = request.get_json()
    status = data.get("status")
    name = data.get("name")

    if status not in ("released", "dev"):
        return jsonify({"success": False, "error": "Invalid status"}), 400

    # Ensure route starts with /
    if not route.startswith("/"):
        route = "/" + route

    try:
        set_page_status(route, status, name)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
