# -*- coding: utf-8 -*-
"""Request validation helpers for API routes."""

from __future__ import annotations

import os
import re
from datetime import date
from dataclasses import dataclass
from typing import Any

from flask import current_app, request


@dataclass(frozen=True)
class JsonPayloadError:
    message: str
    status_code: int


_WORKCENTER_GROUP_RE = re.compile(r"^[\w\u4e00-\u9fff\-\s()./]+$", re.UNICODE)
_SUSPICIOUS_TEXT_TOKENS = ("--", ";", "/*", "*/", "' or", "\" or", "drop ", " union ", " select ")


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


def validate_optional_date_range(
    start_date: str | None,
    end_date: str | None,
    *,
    start_field: str = "start_date",
    end_field: str = "end_date",
) -> str | None:
    """Validate optional start/end date filters when both are provided."""
    start_raw = str(start_date or "").strip()
    end_raw = str(end_date or "").strip()
    if not start_raw and not end_raw:
        return None
    if not start_raw or not end_raw:
        return f"缺少必要參數: {start_field}, {end_field}"
    try:
        start_dt = date.fromisoformat(start_raw)
        end_dt = date.fromisoformat(end_raw)
    except ValueError:
        return f"{start_field} / {end_field} 日期格式需為 YYYY-MM-DD"
    if end_dt < start_dt:
        return "結束日期必須大於起始日期"
    return None


def validate_workcenter_group_filter(
    value: Any,
    *,
    field_name: str = "workcenter_group",
    max_length: int = 120,
) -> str | None:
    """Validate workcenter_group-like free-text query filters."""
    text = str(value or "").strip()
    if not text:
        return f"{field_name} 不可為空白"
    if len(text) > max_length:
        return f"{field_name} 長度不可超過 {max_length}"
    if any(ord(ch) < 32 for ch in text):
        return f"{field_name} 含有非法控制字元"
    if text.startswith("="):
        return f"{field_name} 格式不合法"

    lowered = text.lower()
    if any(token in lowered for token in _SUSPICIOUS_TEXT_TOKENS):
        return f"{field_name} 格式不合法"
    if "{" in text or "}" in text or "[" in text or "]" in text:
        return f"{field_name} 格式不合法"
    if not _WORKCENTER_GROUP_RE.fullmatch(text):
        return f"{field_name} 格式不合法"
    return None
