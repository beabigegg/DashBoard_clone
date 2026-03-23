# -*- coding: utf-8 -*-
"""AI Query API routes.

Thin route layer: parameter parsing → ai_query_service → response formatting.
All business logic (LLM pipeline, service dispatch) lives in ai_query_service.py.
"""

from __future__ import annotations

import logging
import os

from flask import Blueprint, request

from mes_dashboard.core.rate_limit import configured_rate_limit
from mes_dashboard.core.response import (
    external_service_error,
    external_service_timeout_error,
    not_found_error,
    success_response,
    validation_error,
)
from mes_dashboard.services import ai_query_service

logger = logging.getLogger("mes_dashboard.ai_routes")

ai_bp = Blueprint("ai", __name__)

_AI_QUERY_ENABLED = os.getenv("AI_QUERY_ENABLED", "false").strip().lower() in {
    "1", "true", "yes", "on"
}

_AI_RATE_LIMIT = configured_rate_limit(
    bucket="ai-query",
    max_attempts_env="AI_RATE_LIMIT_MAX_REQUESTS",
    window_seconds_env="AI_RATE_LIMIT_WINDOW_SECONDS",
    default_max_attempts=3,
    default_window_seconds=60,
)


@ai_bp.route("/api/ai/query", methods=["POST"])
@_AI_RATE_LIMIT
def ai_query():
    """POST /api/ai/query — process a natural language query via 3-round LLM pipeline."""
    if not _AI_QUERY_ENABLED:
        return not_found_error("功能未啟用")

    body = request.get_json(silent=True) or {}
    question = (body.get("question") or "").strip()
    conversation_id = (body.get("conversation_id") or "").strip() or None
    if not question:
        return validation_error("question 不可為空")

    try:
        result = ai_query_service.process_query(
            question=question,
            conversation_id=conversation_id,
        )
        return success_response(result)

    except TimeoutError as exc:
        return external_service_timeout_error(str(exc))

    except ConnectionError as exc:
        logger.error("AI query ConnectionError: %s", exc)
        return external_service_error(str(exc))

    except ValueError as exc:
        logger.error("AI query ValueError: %s", exc)
        return validation_error(str(exc))

    except Exception as exc:
        logger.exception("Unexpected error in ai_query: %s", exc)
        return external_service_error(str(exc))
