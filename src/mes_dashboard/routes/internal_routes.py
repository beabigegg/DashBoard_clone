# -*- coding: utf-8 -*-
"""Internal-only metrics endpoint for soak / nightly observability probes.

CONTRACT — INTERNAL ONLY, NOT AN ADMIN API
-------------------------------------------
This blueprint exposes `GET /internal/metrics` under three independent
gates (openspec harden-real-infra-test-coverage spec 3.1):

  * Layer 1 — Registration gate: the app factory MUST only import + register
    this blueprint when ``app.config["REGISTER_INTERNAL_METRICS"]`` is True.
    Production config SHALL NOT set that flag, which keeps the module itself
    unimported in prod (no URL rule, no code path).  (Flask's
    ``Config.from_object`` only copies UPPERCASE attributes, so the key is
    intentionally capitalised.)
  * Layer 2 — Runtime env gate: even when registered, the handler returns
    404 unless ``INTERNAL_METRICS_ENABLED == "1"``.
  * Layer 3 — Loopback defense-in-depth: ``request.remote_addr`` must be
    ``127.0.0.1`` or ``::1``; everything else returns 404.  This layer is
    belt-and-suspenders; the security posture does NOT rely on it alone.

The response uses the standard ``success_response()`` envelope and returns
a dict with exactly seven keys produced by
``services.internal_metrics_service.collect_internal_metrics()``.

This endpoint MUST NOT appear in any production deploy config and MUST NOT
be a stepping-stone for future observability endpoints — any real admin
API should live under ``/api/admin/...`` with proper auth.
"""

from __future__ import annotations

import logging
import os

from flask import Blueprint, request

from mes_dashboard.core.response import not_found_error, success_response
from mes_dashboard.services.internal_metrics_service import collect_internal_metrics

logger = logging.getLogger("mes_dashboard.internal_routes")

internal_bp = Blueprint("internal", __name__)

_LOOPBACK_ADDRS = frozenset({"127.0.0.1", "::1"})


@internal_bp.route("/internal/metrics", methods=["GET"])
def internal_metrics():
    """Return the seven-category metrics snapshot, gated by three layers.

    Behavior:
      * Layer 2 fail → 404 ``NOT_FOUND`` envelope.
      * Layer 3 fail → 404 ``NOT_FOUND`` envelope + access-log line with
        the rejected remote_addr (so an operator can see if something
        non-loopback is probing the gate by accident).
      * All gates pass → 200 ``{data: {pool, duckdb, redis, spool,
        worker_rss, circuit_breaker, rq}}``.
    """
    if os.getenv("INTERNAL_METRICS_ENABLED") != "1":
        return not_found_error()

    remote_addr = request.remote_addr or ""
    if remote_addr not in _LOOPBACK_ADDRS:
        logger.warning(
            "internal_metrics: rejected non-loopback request from %s",
            remote_addr or "<unknown>",
        )
        return not_found_error()

    snapshot = collect_internal_metrics()
    return success_response(snapshot)


__all__ = ["internal_bp"]
