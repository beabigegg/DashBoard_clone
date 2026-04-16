# -*- coding: utf-8 -*-
"""Regression guard: query_tool_service.py must not contain return-error-dict patterns.

This test is the canonical guard that prevents future code from re-introducing
the ``return {"error": "..."}`` anti-pattern in the service layer.  It runs a
static regex search against the source file and fails immediately if any match
is found, giving a clear message about which line violated the contract.

Design rationale (Decision 5 in design.md):
  Fast, cheap, runs in CI with zero DB dependency.  Any PR that re-introduces
  an error dict in the service will be caught here before merge.
"""

import pathlib
import re


_SERVICE_PATH = (
    pathlib.Path(__file__).parent.parent
    / "src" / "mes_dashboard" / "services" / "query_tool_service.py"
)

# Pattern: return { followed by "error" or 'error' as the first key
_ERROR_DICT_PATTERN = re.compile(r"return\s*\{[\"']error[\"']")


def test_no_error_dict_returns():
    """query_tool_service.py must contain zero `return {\"error\": ...}` patterns."""
    src = _SERVICE_PATH.read_text(encoding="utf-8")
    matches = [
        (i + 1, line.rstrip())
        for i, line in enumerate(src.splitlines())
        if _ERROR_DICT_PATTERN.search(line)
    ]
    assert matches == [], (
        f"Found {len(matches)} error-dict return(s) in {_SERVICE_PATH.name}.\n"
        "All error conditions must raise a typed exception from core.exceptions.\n"
        "Offending lines:\n"
        + "\n".join(f"  L{lineno}: {text}" for lineno, text in matches)
    )
