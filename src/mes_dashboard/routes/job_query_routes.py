# -*- coding: utf-8 -*-
"""Job Query API routes.

Contains Flask Blueprint for maintenance job query endpoints:
- Job list query by resources
- Job transaction history detail
- CSV export with full history
"""

import logging

from flask import Blueprint, jsonify, request, Response, render_template

from mes_dashboard.core.rate_limit import configured_rate_limit
from mes_dashboard.services.job_query_service import (
    get_jobs_by_resources,
    get_job_txn_history,
    export_jobs_with_history,
    validate_date_range,
)

# Create Blueprint
job_query_bp = Blueprint('job_query', __name__)
logger = logging.getLogger('mes_dashboard.job_query_routes')

MAX_RESOURCE_IDS = 50

_JOB_QUERY_RATE_LIMIT = configured_rate_limit(
    bucket="job-query",
    max_attempts_env="JOB_QUERY_RATE_LIMIT_MAX_REQUESTS",
    window_seconds_env="JOB_QUERY_RATE_LIMIT_WINDOW_SECONDS",
    default_max_attempts=60,
    default_window_seconds=60,
)

_JOB_EXPORT_RATE_LIMIT = configured_rate_limit(
    bucket="job-export",
    max_attempts_env="JOB_EXPORT_RATE_LIMIT_MAX_REQUESTS",
    window_seconds_env="JOB_EXPORT_RATE_LIMIT_WINDOW_SECONDS",
    default_max_attempts=10,
    default_window_seconds=60,
)


# ============================================================
# Page Route
# ============================================================

@job_query_bp.route('/job-query')
def job_query_page():
    """Render the job query page."""
    return render_template('job_query.html')


# ============================================================
# API Routes
# ============================================================

@job_query_bp.route('/api/job-query/resources', methods=['GET'])
def get_resources():
    """Get available resources for selection.

    Returns resources from cache for equipment selection.
    """
    from mes_dashboard.services.resource_cache import get_all_resources

    try:
        resources = get_all_resources()
        if not resources:
            return jsonify({'error': '無法載入設備資料'}), 500

        # Return minimal data for selection UI
        data = []
        for r in resources:
            data.append({
                'RESOURCEID': r.get('RESOURCEID'),
                'RESOURCENAME': r.get('RESOURCENAME'),
                'WORKCENTERNAME': r.get('WORKCENTERNAME'),
                'RESOURCEFAMILYNAME': r.get('RESOURCEFAMILYNAME'),
            })

        # Sort by WORKCENTERNAME, then RESOURCENAME
        data.sort(key=lambda x: (x.get('WORKCENTERNAME', ''), x.get('RESOURCENAME', '')))

        return jsonify({
            'data': data,
            'total': len(data)
        })

    except Exception as exc:
        logger.exception("Failed to load job-query resources: %s", exc)
        return jsonify({'error': '服務暫時無法使用'}), 500


@job_query_bp.route('/api/job-query/jobs', methods=['POST'])
@_JOB_QUERY_RATE_LIMIT
def query_jobs():
    """Query jobs for selected resources.

    Expects JSON body:
    {
        "resource_ids": ["id1", "id2", ...],
        "start_date": "2024-01-01",
        "end_date": "2024-12-31"
    }

    Returns job list.
    """
    data = request.get_json()

    resource_ids = data.get('resource_ids', [])
    start_date = data.get('start_date')
    end_date = data.get('end_date')

    # Validation
    if not resource_ids:
        return jsonify({'error': '請選擇至少一台設備'}), 400
    if len(resource_ids) > MAX_RESOURCE_IDS:
        return jsonify({'error': f'設備數量不可超過 {MAX_RESOURCE_IDS} 台'}), 400
    if not start_date or not end_date:
        return jsonify({'error': '請指定日期範圍'}), 400

    validation_error = validate_date_range(start_date, end_date)
    if validation_error:
        return jsonify({'error': validation_error}), 400

    result = get_jobs_by_resources(resource_ids, start_date, end_date)

    if 'error' in result:
        return jsonify(result), 400

    return jsonify(result)


@job_query_bp.route('/api/job-query/txn/<job_id>', methods=['GET'])
@_JOB_QUERY_RATE_LIMIT
def query_job_txn_history(job_id: str):
    """Query transaction history for a single job.

    Args:
        job_id: The JOBID to query

    Returns transaction history list.
    """
    if not job_id:
        return jsonify({'error': '請指定工單 ID'}), 400

    result = get_job_txn_history(job_id)

    if 'error' in result:
        return jsonify(result), 400

    return jsonify(result)


@job_query_bp.route('/api/job-query/export', methods=['POST'])
@_JOB_EXPORT_RATE_LIMIT
def export_jobs():
    """Export jobs with full transaction history as CSV.

    Expects JSON body:
    {
        "resource_ids": ["id1", "id2", ...],
        "start_date": "2024-01-01",
        "end_date": "2024-12-31"
    }

    Returns streaming CSV response.
    """
    data = request.get_json()

    resource_ids = data.get('resource_ids', [])
    start_date = data.get('start_date')
    end_date = data.get('end_date')

    # Validation
    if not resource_ids:
        return jsonify({'error': '請選擇至少一台設備'}), 400
    if len(resource_ids) > MAX_RESOURCE_IDS:
        return jsonify({'error': f'設備數量不可超過 {MAX_RESOURCE_IDS} 台'}), 400
    if not start_date or not end_date:
        return jsonify({'error': '請指定日期範圍'}), 400

    validation_error = validate_date_range(start_date, end_date)
    if validation_error:
        return jsonify({'error': validation_error}), 400

    # Stream CSV response
    return Response(
        export_jobs_with_history(resource_ids, start_date, end_date),
        mimetype='text/csv; charset=utf-8',
        headers={
            'Content-Disposition': 'attachment; filename=job_history_export.csv'
        }
    )
