# -*- coding: utf-8 -*-
"""DB Scheduling API routes.

Blueprint: db_scheduling_bp
Endpoint: GET /api/db-scheduling/queue → DbSchedulingQueueResponse

Auth: handled by app-level permission middleware (no decorator needed).
      Unauthenticated requests return 401 via before_request hook in app.py.
"""

from flask import Blueprint, request

from mes_dashboard.core.response import (
    INTERNAL_ERROR,
    error_response,
    success_response,
)
from mes_dashboard.services.db_scheduling_service import (
    get_db_scheduling_queue,
    get_equipment_detail,
)

db_scheduling_bp = Blueprint(
    'db_scheduling', __name__, url_prefix='/api/db-scheduling'
)


@db_scheduling_bp.route('/queue', methods=['GET'])
def get_queue():
    """GET /api/db-scheduling/queue — return DB scheduling queue.

    Returns one row per recommended equipment per D/B-START lot.
    No query parameters; auth required (middleware handles 401).

    Returns:
        200 + DbSchedulingQueueResponse on success.
        500 on unexpected service error.
    """
    try:
        rows = get_db_scheduling_queue()
        return success_response(data=rows)
    except Exception as exc:  # pragma: no cover — service wraps internally
        return error_response(
            INTERNAL_ERROR,
            '伺服器內部錯誤',
            str(exc),
            status_code=500,
        )


@db_scheduling_bp.route('/equipment-detail', methods=['GET'])
def equipment_detail():
    """GET /api/db-scheduling/equipment-detail?equipment=<id>

    Returns real-time machine status (E10 + JOB) and the running lot's
    product info for the given equipment ID. Both data sources come from
    process-level caches (realtime-equipment-cache + WIP cache) so this
    endpoint is fast enough for on-demand pill-click use.

    Returns:
        200 + EquipmentDetailResponse on success.
        400 if `equipment` param is missing.
        500 on unexpected service error.
    """
    equipment = request.args.get('equipment', '').strip()
    if not equipment:
        return error_response('INVALID_PARAMS', 'equipment param required', status_code=400)
    try:
        detail = get_equipment_detail(equipment)
        return success_response(data=detail)
    except Exception as exc:  # pragma: no cover
        return error_response(
            INTERNAL_ERROR,
            '伺服器內部錯誤',
            str(exc),
            status_code=500,
        )
