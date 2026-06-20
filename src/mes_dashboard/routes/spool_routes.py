# -*- coding: utf-8 -*-
"""Parquet spool download route.

Provides ``GET /api/spool/{namespace}/{query_id}.parquet`` for frontend clients
to download Parquet spool files produced by the dataset cache layer.
"""

import os
import re

from flask import Blueprint, request, Response

from mes_dashboard.core.csrf import validate_csrf, should_enforce_csrf
from mes_dashboard.core.query_spool_store import get_spool_file_path
from mes_dashboard.core.response import validation_error

spool_bp = Blueprint("spool", __name__, url_prefix="/api/spool")

# Allowed namespaces — whitelist to prevent path traversal
_ALLOWED_NAMESPACES = frozenset({
    "yield_alert_dataset",
    "reject_dataset",
    "resource_dataset",
    "hold_dataset",
    "downtime_analysis_base_events",
    "downtime_analysis_job_bridge",
    "eap_alarm",
    "wip_dataset",  # wip-rq-worker-chunks-cleanup: async WIP detail spool
})

# query_id must be 1-64 hex characters (SHA256 prefix)
_QUERY_ID_RE = re.compile(r'^[0-9a-f]{1,64}$', re.ASCII)


@spool_bp.route("/<namespace>/<query_id>.parquet", methods=["GET"])
def download_spool_parquet(namespace: str, query_id: str):
    """Stream a Parquet spool file to the client.

    Security:
      - CSRF token validated (same session-based check as other API endpoints)
      - Namespace validated against whitelist
      - query_id format validated (hex only, no path separators)
      - File path resolved via ``query_spool_store`` (no direct filesystem access)

    Returns:
      200 with Parquet bytes on success.
      410 Gone when spool has expired or does not exist.
      400 on invalid namespace or query_id format.
      403 on CSRF failure.
    """
    # CSRF validation
    if should_enforce_csrf(request):
        if not validate_csrf(request):
            return Response(
                '{"success": false, "error": "csrf_invalid"}',
                status=403,
                mimetype="application/json",
            )

    # Namespace whitelist
    if namespace not in _ALLOWED_NAMESPACES:
        return validation_error(f"Unknown spool namespace: {namespace}")

    # query_id format validation
    if not _QUERY_ID_RE.match(query_id):
        return validation_error("Invalid query_id format")

    # Resolve spool file path via store (handles TTL expiry + path traversal protection)
    parquet_path = get_spool_file_path(namespace, query_id)
    if parquet_path is None:
        # 410 Gone — spool expired or never existed
        return Response(
            '{"success": false, "error": "spool_expired", '
            '"message": "Spool file has expired or does not exist"}',
            status=410,
            mimetype="application/json",
        )

    # Stream file
    try:
        file_size = os.path.getsize(parquet_path)
        filename = f"{namespace}_{query_id}.parquet"

        def _stream():
            with open(parquet_path, "rb") as fh:
                while True:
                    chunk = fh.read(65536)
                    if not chunk:
                        break
                    yield chunk

        headers = {
            "Content-Type": "application/octet-stream",
            "Content-Length": str(file_size),
            "Content-Disposition": f'attachment; filename="{filename}"',
        }
        return Response(_stream(), status=200, headers=headers, direct_passthrough=True)

    except FileNotFoundError:
        return Response(
            '{"success": false, "error": "spool_expired", '
            '"message": "Spool file has expired or does not exist"}',
            status=410,
            mimetype="application/json",
        )
    except OSError as exc:
        return Response(
            f'{{"success": false, "error": "spool_read_error", "message": "{exc}"}}',
            status=500,
            mimetype="application/json",
        )
