# -*- coding: utf-8 -*-
"""Shared malicious input constants for route fuzz parametrize tests.

Each entry is a dict (or scalar) representing a query payload that a route
handler MUST reject with HTTP 400/422 and error.code == 'VALIDATION_ERROR'.
The set covers representative attack / edge-case categories agreed in design.md.
"""

from __future__ import annotations

# SQL-style injection characters that must not reach Oracle unescaped.
_SQL_INJECTION = "' OR 1=1 --; DROP TABLE LOTS;"

# Extremely long string (100 000 chars) to exercise length validators.
_LONG_STRING = "A" * 100_000

# Unicode special characters including BMP plane emoji, zero-width space,
# right-to-left override, and a null byte.
_UNICODE_SPECIAL = "😀🔥💥\u0000\u200b\u202e\uffff"

# Whitespace-only string — should be rejected as missing / blank value.
_WHITESPACE_ONLY = "   \t\n   "

# Inverted date range: end_date before start_date — validators must catch this.
_INVERTED_DATES = {"start_date": "2026-12-31", "end_date": "2026-01-01"}

# Negative pagination parameters.
_NEGATIVE_PAGINATION = {"page": -1, "page_size": -10}

# Null bytes embedded in a normal-looking string.
_NULL_BYTE_STRING = "LOT\x00INJECT"

# CSV injection starter (value beginning with =) — no CSV import APIs yet,
# but route validators should still reject this as an invalid lot/id format.
_CSV_INJECTION = "=SUM(A1:A10)"

MALICIOUS_INPUTS = [
    _SQL_INJECTION,
    _LONG_STRING,
    _UNICODE_SPECIAL,
    _WHITESPACE_ONLY,
    _INVERTED_DATES,
    _NEGATIVE_PAGINATION,
    _NULL_BYTE_STRING,
    _CSV_INJECTION,
]
