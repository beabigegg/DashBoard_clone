# -*- coding: utf-8 -*-
"""Shared request-parameter parsing helpers for route blueprints.

Centralises the GET/POST-agnostic parsing that route modules otherwise re-roll
per file (each with subtly different defaults and edge-case handling):

- ``parse_multi_param`` — comma- or repeat-delimited multi-value list,
  order-preserving and de-duplicated.
- ``parse_pagination`` — ``(page, per_page)`` with caller-supplied default/cap.

Each helper accepts an explicit ``source`` — a Werkzeug ``MultiDict`` (from
``request.args``, GET) or a plain ``dict`` (from a JSON body, POST). When
``source`` is omitted it falls back to ``flask.request.args``.

These are pure functions (the only Flask coupling is the ``request.args``
fallback), so they unit-test without an app context when ``source`` is passed.
"""
from __future__ import annotations

from typing import Tuple

from flask import request


def _resolve_source(source):
    """Return the given source, or ``request.args`` when source is None."""
    return request.args if source is None else source


def parse_multi_param(name: str, source=None) -> list[str]:
    """Parse a multi-value parameter into an order-preserving, de-duped list.

    Accepts repeated params (``?x=a&x=b``) and comma-delimited values
    (``?x=a,b``) from a Werkzeug ``MultiDict`` (GET), and both list values and
    comma-delimited scalars from a plain ``dict`` (POST JSON body). Whitespace
    around each token is stripped; empty tokens are dropped.

    Behaviour matches the previous per-route ``_parse_multi_param`` copies
    (reject-history / yield-alert) exactly.
    """
    src = _resolve_source(source)
    values: list[str] = []
    if hasattr(src, "getlist"):
        # MultiDict (GET query string): each repeated value may itself be CSV.
        for raw in src.getlist(name):
            for token in str(raw).split(","):
                item = token.strip()
                if item:
                    values.append(item)
    else:
        # Plain dict (POST JSON body).
        raw_value = src.get(name)
        if isinstance(raw_value, list):
            # List members are taken verbatim (no CSV split).
            for item in raw_value:
                token = str(item).strip()
                if token:
                    values.append(token)
        elif raw_value is not None:
            for token in str(raw_value).split(","):
                item = token.strip()
                if item:
                    values.append(item)

    # De-duplicate while preserving first-seen order.
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def _coerce_int(value, default: int) -> int:
    """Return ``int(value)`` or ``default`` for None / non-integer input."""
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def parse_pagination(
    source=None,
    *,
    default_per_page: int = 50,
    max_per_page: int = 200,
    page_key: str = "page",
    per_page_key: str = "per_page",
) -> Tuple[int, int]:
    """Return ``(page, per_page)`` clamped to sane bounds.

    - ``page`` is clamped to ``>= 1``.
    - ``per_page`` is clamped to ``[1, max_per_page]``.
    - Missing or non-integer values fall back to ``1`` / ``default_per_page``
      (silent default — for routes that instead want an explicit 400 on a
      non-integer value, keep their bespoke parsing).

    Works for GET (``MultiDict``) and POST JSON (plain ``dict``).
    """
    src = _resolve_source(source)
    page = max(1, _coerce_int(src.get(page_key), 1))
    per_page = _coerce_int(src.get(per_page_key), default_per_page)
    per_page = max(1, min(per_page, max_per_page))
    return page, per_page
