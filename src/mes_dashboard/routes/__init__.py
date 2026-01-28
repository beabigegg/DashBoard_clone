# -*- coding: utf-8 -*-
"""API routes module for MES Dashboard.

Contains Flask Blueprints for different API endpoints.
"""

from .wip_routes import wip_bp
from .resource_routes import resource_bp
from .dashboard_routes import dashboard_bp
from .excel_query_routes import excel_query_bp
from .hold_routes import hold_bp
from .auth_routes import auth_bp
from .admin_routes import admin_bp


def register_routes(app) -> None:
    """Register all API blueprints on the Flask app."""
    app.register_blueprint(wip_bp)
    app.register_blueprint(resource_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(excel_query_bp)
    app.register_blueprint(hold_bp)

__all__ = [
    'wip_bp',
    'resource_bp',
    'dashboard_bp',
    'excel_query_bp',
    'hold_bp',
    'auth_bp',
    'admin_bp',
    'register_routes',
]
