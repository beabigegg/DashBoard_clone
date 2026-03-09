# -*- coding: utf-8 -*-
"""API routes module for MES Dashboard.

Contains Flask Blueprints for different API endpoints.
"""

from .wip_routes import wip_bp
from .resource_routes import resource_bp
from .dashboard_routes import dashboard_bp
from .excel_query_routes import excel_query_bp
from .hold_routes import hold_bp
from .hold_overview_routes import hold_overview_bp
from .hold_history_routes import hold_history_bp
from .auth_routes import auth_bp
from .admin_routes import admin_bp
from .resource_history_routes import resource_history_bp
from .job_query_routes import job_query_bp
from .query_tool_routes import query_tool_bp
from .qc_gate_routes import qc_gate_bp
from .mid_section_defect_routes import mid_section_defect_bp
from .trace_routes import trace_bp
from .reject_history_routes import reject_history_bp
from .material_trace_routes import material_trace_bp
from .yield_alert_routes import yield_alert_bp


def register_routes(app) -> None:
    """Register all API blueprints on the Flask app."""
    app.register_blueprint(wip_bp)
    app.register_blueprint(resource_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(excel_query_bp)
    app.register_blueprint(hold_bp)
    app.register_blueprint(hold_overview_bp)
    app.register_blueprint(hold_history_bp)
    app.register_blueprint(resource_history_bp)
    app.register_blueprint(job_query_bp)
    app.register_blueprint(query_tool_bp)
    app.register_blueprint(qc_gate_bp)
    app.register_blueprint(mid_section_defect_bp)
    app.register_blueprint(trace_bp)
    app.register_blueprint(reject_history_bp)
    app.register_blueprint(material_trace_bp)
    app.register_blueprint(yield_alert_bp)

__all__ = [
    'wip_bp',
    'resource_bp',
    'dashboard_bp',
    'excel_query_bp',
    'hold_bp',
    'hold_overview_bp',
    'hold_history_bp',
    'auth_bp',
    'admin_bp',
    'resource_history_bp',
    'job_query_bp',
    'query_tool_bp',
    'qc_gate_bp',
    'mid_section_defect_bp',
    'trace_bp',
    'reject_history_bp',
    'material_trace_bp',
    'yield_alert_bp',
    'register_routes',
]
