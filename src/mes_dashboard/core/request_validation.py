# -*- coding: utf-8 -*-
"""Request validation helpers for API routes."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from flask import current_app, request


@dataclass(frozen=True)
class JsonPayloadError:
    message: str
    status_code: int


def _resolve_max_json_body_bytes(explicit_max: int | None = None) -> int:
    if explicit_max is not None:
        return max(int(explicit_max), 1)
    try:
        value = int(current_app.config.get("MAX_JSON_BODY_BYTES", 262144))
        return max(value, 1)
    except Exception:
        pass
    try:
        return max(int(os.getenv("MAX_JSON_BODY_BYTES", "262144")), 1)
    except Exception:
        return 262144


def parse_json_payload(
    *,
    require_object: bool = True,
    require_non_empty_object: bool = False,
    max_body_bytes: int | None = None,
) -> tuple[Any | None, JsonPayloadError | None]:
    """Parse and validate JSON request payload with deterministic 4xx errors."""
    content_length = request.content_length
    max_bytes = _resolve_max_json_body_bytes(max_body_bytes)
    if content_length is not None and content_length > max_bytes:
        return None, JsonPayloadError(
            f"請求內容過大，限制 {max_bytes} bytes",
            413,
        )

    if not request.is_json:
        return None, JsonPayloadError(
            "Content-Type 必須為 application/json",
            415,
        )

    payload = request.get_json(silent=True)
    if payload is None:
        return None, JsonPayloadError("JSON 格式錯誤", 400)

    if require_object and not isinstance(payload, dict):
        return None, JsonPayloadError("JSON 內容必須為物件", 400)

    if require_non_empty_object and isinstance(payload, dict) and not payload:
        return None, JsonPayloadError("請求內容不可為空", 400)

    return payload, None
