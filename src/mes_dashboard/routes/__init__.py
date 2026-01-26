# -*- coding: utf-8 -*-
"""API routes module for MES Dashboard.

Contains Flask Blueprints for different API endpoints.
"""

from .wip_routes import wip_bp
from .resource_routes import resource_bp
from .dashboard_routes import dashboard_bp
from .excel_query_routes import excel_query_bp


def register_routes(app) -> None:
    """Register all API blueprints on the Flask app."""
    app.register_blueprint(wip_bp)
    app.register_blueprint(resource_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(excel_query_bp)

__all__ = [
    'wip_bp',
    'resource_bp',
    'dashboard_bp',
    'excel_query_bp',
    'register_routes',
]
