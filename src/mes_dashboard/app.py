# -*- coding: utf-8 -*-
"""Flask application factory for MES Dashboard."""

from __future__ import annotations

import logging
import os
import sys

from flask import Flask, jsonify, redirect, render_template, request, session, url_for

from mes_dashboard.config.tables import TABLES_CONFIG
from mes_dashboard.config.settings import get_config
from mes_dashboard.core.cache import NoOpCache
from mes_dashboard.core.database import get_table_data, get_table_columns, get_engine, init_db, start_keepalive
from mes_dashboard.core.permissions import is_admin_logged_in
from mes_dashboard.routes import register_routes
from mes_dashboard.routes.auth_routes import auth_bp
from mes_dashboard.routes.admin_routes import admin_bp
from mes_dashboard.routes.health_routes import health_bp
from mes_dashboard.services.page_registry import get_page_status, is_api_public
from mes_dashboard.core.cache_updater import start_cache_updater, stop_cache_updater
from mes_dashboard.services.realtime_equipment_cache import init_realtime_equipment_cache


def _configure_logging(app: Flask) -> None:
    """Configure application logging.

    Sets up logging to stderr (captured by Gunicorn's --capture-output).
    Log levels:
    - DEBUG: Query completion times, connection events
    - WARNING: Slow queries (>1s)
    - ERROR: Connection failures, query errors with ORA codes
    """
    # Configure the mes_dashboard logger
    logger = logging.getLogger('mes_dashboard')
    logger.setLevel(logging.DEBUG if app.debug else logging.INFO)

    # Only add handler if not already configured (avoid duplicates)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter(
            '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    # Prevent propagation to root logger (avoid duplicate logs)
    logger.propagate = False


def create_app(config_name: str | None = None) -> Flask:
    """Create and configure the Flask app instance."""
    app = Flask(__name__, template_folder="templates")

    config_class = get_config(config_name)
    app.config.from_object(config_class)

    # Session configuration
    app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-prod")

    # Configure logging first
    _configure_logging(app)

    # Default cache backend (no-op)
    app.extensions["cache"] = NoOpCache()

    # Initialize database teardown and pool
    init_db(app)
    with app.app_context():
        get_engine()
        start_keepalive()  # Keep database connections alive
        start_cache_updater()  # Start Redis cache updater
        init_realtime_equipment_cache(app)  # Start realtime equipment status cache

    # Register API routes
    register_routes(app)

    # Register auth, admin, and health routes
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(health_bp)

    # ========================================================
    # Permission Middleware
    # ========================================================

    @app.before_request
    def check_page_access():
        """Check page access permissions before each request."""
        # Skip static files
        if request.endpoint == "static":
            return None

        # Health check endpoint - no auth required
        if request.path == "/health":
            return None

        # API endpoints check
        if request.path.startswith("/api/"):
            if is_api_public():
                return None
            if not is_admin_logged_in():
                return jsonify({"error": "Unauthorized"}), 401
            return None

        # Skip auth-related pages (login/logout)
        if request.path.startswith("/admin/login") or request.path.startswith("/admin/logout"):
            return None

        # Admin pages require login
        if request.path.startswith("/admin/"):
            if not is_admin_logged_in():
                return redirect(url_for("auth.login", next=request.url))
            return None

        # Check page status for registered pages only
        # Unregistered pages pass through to Flask routing (may return 404)
        page_status = get_page_status(request.path)
        if page_status == "dev" and not is_admin_logged_in():
            return render_template("403.html"), 403

        return None

    # ========================================================
    # Template Context Processor
    # ========================================================

    @app.context_processor
    def inject_admin():
        """Inject admin info into all templates."""
        admin = is_admin_logged_in()

        def can_view_page(route: str) -> bool:
            """Check if current user can view a page."""
            status = get_page_status(route)
            # Unregistered pages (None) are viewable
            if status is None:
                return True
            # Released pages are viewable by all
            if status == "released":
                return True
            # Dev pages only viewable by admin
            return admin

        return {
            "is_admin": admin,
            "admin_user": session.get("admin"),
            "can_view_page": can_view_page,
        }

    # ========================================================
    # Page Routes
    # ========================================================

    @app.route('/')
    def portal_index():
        """Portal home with tabs."""
        return render_template('portal.html')

    @app.route('/tables')
    def tables_page():
        """Table viewer page."""
        return render_template('index.html', tables_config=TABLES_CONFIG)

    @app.route('/wip-overview')
    def wip_overview_page():
        """WIP Overview Dashboard - for executives."""
        return render_template('wip_overview.html')

    @app.route('/wip-detail')
    def wip_detail_page():
        """WIP Detail Dashboard - for production lines."""
        return render_template('wip_detail.html')

    @app.route('/resource')
    def resource_page():
        """Resource status report page."""
        return render_template('resource_status.html')

    @app.route('/excel-query')
    def excel_query_page():
        """Excel batch query tool page."""
        return render_template('excel_query.html')

    @app.route('/resource-history')
    def resource_history_page():
        """Resource history analysis page."""
        return render_template('resource_history.html')

    # ========================================================
    # Table Query APIs (for table_data_viewer)
    # ========================================================

    @app.route('/api/query_table', methods=['POST'])
    def query_table():
        """API: query table data with optional column filters."""
        data = request.get_json()
        table_name = data.get('table_name')
        limit = data.get('limit', 1000)
        time_field = data.get('time_field')
        filters = data.get('filters')

        if not table_name:
            return jsonify({'error': '請指定表名'}), 400

        result = get_table_data(table_name, limit, time_field, filters)
        return jsonify(result)

    @app.route('/api/get_table_columns', methods=['POST'])
    def api_get_table_columns():
        """API: get column names for a table."""
        data = request.get_json()
        table_name = data.get('table_name')

        if not table_name:
            return jsonify({'error': '請指定表名'}), 400

        columns = get_table_columns(table_name)
        return jsonify({'columns': columns})

    @app.route('/api/get_table_info', methods=['GET'])
    def get_table_info():
        """API: get tables config."""
        return jsonify(TABLES_CONFIG)

    return app
