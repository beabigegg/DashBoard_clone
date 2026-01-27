# -*- coding: utf-8 -*-
"""Flask application factory for MES Dashboard."""

from __future__ import annotations

from flask import Flask, jsonify, render_template, request

from mes_dashboard.config.tables import TABLES_CONFIG
from mes_dashboard.config.settings import get_config
from mes_dashboard.core.cache import NoOpCache
from mes_dashboard.core.database import get_table_data, get_table_columns, get_engine, init_db, start_keepalive
from mes_dashboard.routes import register_routes


def create_app(config_name: str | None = None) -> Flask:
    """Create and configure the Flask app instance."""
    app = Flask(__name__, template_folder="templates")

    config_class = get_config(config_name)
    app.config.from_object(config_class)

    # Default cache backend (no-op)
    app.extensions["cache"] = NoOpCache()

    # Initialize database teardown and pool
    init_db(app)
    with app.app_context():
        get_engine()
        start_keepalive()  # Keep database connections alive

    # Register API routes
    register_routes(app)

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
