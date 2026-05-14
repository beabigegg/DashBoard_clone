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


# ---------------------------------------------------------------------------
# WILDCARD_HOSTILE — payloads for `mfg_orders`, `lot_ids`, `wafer_lots`
# (change `prod-history-first-tier-cache-filters`, PHF-02 / PHF-06).
#
# Each entry MUST be rejected by `parse_wildcard_tokens` and surface as a
# 400 VALIDATION_ERROR with `field` matching the offending wildcard key.
# ---------------------------------------------------------------------------

WILDCARD_FIELDS = ("mfg_orders", "lot_ids", "wafer_lots")

# SQL meta-chars (PHF-06): each single-token MUST 400.
WILDCARD_META_CHARS = [
    "MA'25",       # single quote
    "MA;25",       # semicolon
    "MA--25",      # SQL line comment
    "MA/*25",     # block-comment opener
    "MA*/25",     # block-comment closer (also "looks like" two wildcards but caught by meta-char first)
    "q'[malicious]'",  # Oracle alt literal — caught via leading single quote
]

# Control-char rejections (\x00-\x1f except the explicit \t \n \r separators).
WILDCARD_CONTROL_CHARS = [chr(c) for c in range(0x00, 0x20) if c not in (0x09, 0x0a, 0x0d)]

# Grammar violations: multi-`*`, pure-`*`, single-char literal.
WILDCARD_GRAMMAR_INVALID = [
    "MA**",
    "M*A*B",
    "***",
    "*A*",        # 2 stars, non-`*` literal_len=1
    "*",           # pure star
    "A",           # single literal char
    "*A",          # literal_len=1 after stripping *
    "A*",          # literal_len=1 after stripping *
]

