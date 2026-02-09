# -*- coding: utf-8 -*-
"""QC-GATE API routes."""

from __future__ import annotations

from flask import Blueprint, jsonify

from mes_dashboard.services.qc_gate_service import get_qc_gate_summary

qc_gate_bp = Blueprint('qc_gate', __name__, url_prefix='/api/qc-gate')


@qc_gate_bp.route('/summary')
def api_qc_gate_summary():
    """Return per-station QC-GATE lot summary from cached WIP data."""
    result = get_qc_gate_summary()
    if result is not None:
        return jsonify({'success': True, 'data': result})
    return jsonify({'success': False, 'error': '查詢失敗'}), 500
