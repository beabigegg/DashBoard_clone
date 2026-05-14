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


# ============================================================
# Wildcard token parser (PHF-02 / PHF-06 — change `prod-history-first-tier-cache-filters`)
# ============================================================

# Meta-char regex applied to each parsed token: rejects SQL injection
# vectors. Control chars are handled separately on the raw entry BEFORE
# splitting (otherwise `\x1f` etc. would be consumed as whitespace by the
# splitter and silently dropped, defeating PHF-06).
_WILDCARD_META_RE = re.compile(r"[\'\;]|--|/\*|\*/")

# Pre-split control-char detector: any C0 control char (\x00-\x1f) except
# the explicit separators (\t \n \r) we want to honour. Note: \x0b and
# \x0c (vertical tab, form feed) are also rejected because they're never
# legitimate input and are part of \s.
_WILDCARD_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

# Split tokens on newline, comma, tab, or any whitespace.
_WILDCARD_SPLIT_RE = re.compile(r"[\s,]+")

# Per-field cap (PHF-02 §5).
WILDCARD_MAX_PATTERNS_PER_FIELD = 100


class WildcardValidationError(ValueError):
    """Raised when a wildcard token fails PHF-02 / PHF-06 validation.

    Subclasses ValueError so existing route exception handlers map it to
    400 VALIDATION_ERROR automatically. The ``field`` attribute carries
    the offending field name for downstream error context.
    """

    def __init__(self, message: str, *, field: str) -> None:
        super().__init__(message)
        self.field = field


@dataclass(frozen=True)
class WildcardToken:
    """One parsed wildcard token.

    Attributes:
        kind: ``'exact'`` (no ``*``) or ``'pattern'`` (single ``*`` present).
        bound_value: For ``exact`` — the original token; for ``pattern`` —
            the SQL-ready string with ``%``/``_`` escaped and ``*`` → ``%``.
            Always ready to be bound directly to ``IN`` placeholders or to a
            ``LIKE :bind ESCAPE '\\'`` clause.
    """

    kind: str
    bound_value: str


def _escape_like_literal(text: str) -> str:
    """Escape SQL LIKE meta-chars ``%`` and ``_`` with the ``\\`` escape char.

    Backslash is NOT pre-escaped because the SQL emitter uses
    ``ESCAPE '\\'`` and the underlying tokens are not expected to contain
    literal backslashes (the meta-char regex does not block them today, but
    they are exceedingly rare in MES identifiers; if a future token format
    needs backslash literals, add ``\\`` to the meta-char block list and
    revisit this escape order).
    """
    return text.replace("%", r"\%").replace("_", r"\_")


def parse_wildcard_tokens(field: str, raw: Any) -> list[WildcardToken]:
    """Parse and validate user-supplied wildcard tokens.

    Implements PHF-02 (wildcard grammar) + PHF-06 (SQL meta-char rejection)
    from ``contracts/business/business-rules.md``.

    Pipeline (in order):
      1. Coerce ``raw`` (``str`` or ``list[str]``) into a flat sequence.
      2. Split each entry on newline / comma / whitespace; trim.
      3. Drop empty tokens.
      4. Reject any token matching meta-char regex (``'``, ``;``, ``--``,
         ``/*``, ``*/``, ``\\x00-\\x1f``) → ``WildcardValidationError``.
      5. Reject any token with ``*`` count > 1.
      6. Reject any token whose non-``*`` char count < 2 (pure ``*`` and
         single-char tokens rejected).
      7. Escape ``%`` and ``_`` in the literal portion, then translate
         ``*`` → ``%``.
      8. Deduplicate (case-insensitive) preserving insertion order.
      9. Cap at ``WILDCARD_MAX_PATTERNS_PER_FIELD`` (100) per field.

    The output is idempotent under re-parsing: ``parse(format(parse(x))) ==
    parse(x)`` where ``format`` re-emits ``bound_value`` (with ``%``
    translated back to ``*`` and ``\\%``/``\\_`` unescaped). The dataclass
    representation itself is the canonical form; passing the emitted
    ``bound_value`` back through ``parse_wildcard_tokens`` yields the same
    list (AC-5).

    Args:
        field: Field name used for error context (echoed in the raised
            exception's ``field`` attribute, NOT in the message).
        raw: Either a ``str`` (single multi-line textarea value) or a
            ``list[str]`` (already-split client-side).

    Returns:
        List of :class:`WildcardToken` in insertion order; empty list if
        ``raw`` yields no non-empty tokens.

    Raises:
        WildcardValidationError: If any token violates the grammar or the
            per-field cap is exceeded. The exception always carries the
            ``field`` name so callers can attribute the failure.
    """
    # Step 1 — flatten input shape.
    if raw is None:
        return []
    if isinstance(raw, str):
        entries: list[str] = [raw]
    elif isinstance(raw, (list, tuple)):
        entries = [str(v) for v in raw]
    else:
        raise WildcardValidationError(
            f"{field} 必須為字串或字串陣列",
            field=field,
        )

    # Steps 2-3 — split + trim + drop empties.
    # Pre-check raw entries for control chars (PHF-06) before splitting —
    # otherwise the split regex would silently consume \x00-\x1f as
    # whitespace and the per-token meta-char check would never see them.
    tokens: list[str] = []
    for entry in entries:
        if _WILDCARD_CTRL_RE.search(entry):
            raise WildcardValidationError(
                f"{field} 含有不允許的控制字元",
                field=field,
            )
        for piece in _WILDCARD_SPLIT_RE.split(entry):
            piece = piece.strip()
            if piece:
                tokens.append(piece)

    if not tokens:
        return []

    # Dedup tracking — case-insensitive, insertion-order preserving.
    seen_keys: set[str] = set()
    out: list[WildcardToken] = []

    for tok in tokens:
        # Step 4 — meta-char rejection (PHF-06).
        if _WILDCARD_META_RE.search(tok):
            raise WildcardValidationError(
                f"{field} 含有不允許的字元（'、;、--、/*、*/、控制字元）",
                field=field,
            )

        # Step 5 — at most one ``*``.
        star_count = tok.count("*")
        if star_count > 1:
            raise WildcardValidationError(
                f"{field} 萬用字元 * 每筆最多一個（收到 {star_count} 個）",
                field=field,
            )

        # Step 6 — non-``*`` char count ≥ 2.
        literal_len = len(tok) - star_count
        if literal_len < 2:
            raise WildcardValidationError(
                f"{field} 萬用字元 token 去除 * 後需至少 2 個字元",
                field=field,
            )

        # Step 7 — escape %/_ then translate * → %.
        if star_count == 0:
            kind = "exact"
            bound_value = tok  # exact match — no LIKE escaping needed
        else:
            kind = "pattern"
            escaped = _escape_like_literal(tok)
            bound_value = escaped.replace("*", "%")

        # Step 8 — dedup (case-insensitive on the bound value).
        dedup_key = bound_value.casefold()
        if dedup_key in seen_keys:
            continue
        seen_keys.add(dedup_key)
        out.append(WildcardToken(kind=kind, bound_value=bound_value))

        # Step 9 — per-field cap.
        if len(out) > WILDCARD_MAX_PATTERNS_PER_FIELD:
            raise WildcardValidationError(
                f"{field} 萬用字元 token 超過上限 "
                f"{WILDCARD_MAX_PATTERNS_PER_FIELD}",
                field=field,
            )

    return out
