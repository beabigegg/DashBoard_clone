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
from .resource_history_routes import resource_history_bp
from .job_query_routes import job_query_bp
from .query_tool_routes import query_tool_bp
from .tmtt_defect_routes import tmtt_defect_bp
from .qc_gate_routes import qc_gate_bp
from .mid_section_defect_routes import mid_section_defect_bp


def register_routes(app) -> None:
    """Register all API blueprints on the Flask app."""
    app.register_blueprint(wip_bp)
    app.register_blueprint(resource_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(excel_query_bp)
    app.register_blueprint(hold_bp)
    app.register_blueprint(resource_history_bp)
    app.register_blueprint(job_query_bp)
    app.register_blueprint(query_tool_bp)
    app.register_blueprint(tmtt_defect_bp)
    app.register_blueprint(qc_gate_bp)
    app.register_blueprint(mid_section_defect_bp)

__all__ = [
    'wip_bp',
    'resource_bp',
    'dashboard_bp',
    'excel_query_bp',
    'hold_bp',
    'auth_bp',
    'admin_bp',
    'resource_history_bp',
    'job_query_bp',
    'query_tool_bp',
    'tmtt_defect_bp',
    'qc_gate_bp',
    'mid_section_defect_bp',
    'register_routes',
]
