# -*- coding: utf-8 -*-
"""AC-1: All endpoints in api-contract.md have typed (named) response schema refs.

Tests that:
- Every endpoint row in §4 has a response-schema cell that is either:
  a) A plain schema name (e.g. 'GenericSuccessResponse', 'AckResponse')
  b) A named content-type: 'text/csv stream', 'application/octet-stream',
     'application/x-ndjson stream', or 'HTTP 302 redirect'.
- No endpoint row still has the old prose values ('success_response',
  'health-payload', 'parquet-binary', 'ndjson-stream', 'csv-stream')
  or the old '→ ' prefixed prose format.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

CONTRACT_PATH = Path(__file__).parent.parent.parent / "contracts" / "api" / "api-contract.md"

# Valid schema name: starts with an uppercase letter (PascalCase)
VALID_SCHEMA_NAME_RE = re.compile(r"^[A-Z][A-Za-z0-9]+$")

VALID_CONTENT_TYPE_CELLS = {
    "text/csv stream",
    "application/octet-stream (parquet)",
    "application/x-ndjson stream",
    "HTTP 302 redirect",
}

OLD_PROSE_VALUES = {
    "success_response",
    "health-payload",
    "parquet-binary",
    "ndjson-stream",
    "csv-stream",
}


def _parse_endpoint_rows(content: str) -> list[dict]:
    """Extract endpoint rows from the §4 table."""
    rows = []
    in_table = False
    for line in content.splitlines():
        if "| method | path | auth | request schema | response schema |" in line:
            in_table = True
            continue
        if not in_table:
            continue
        if line.startswith("## ") and "4" not in line:
            in_table = False
            continue
        if not line.startswith("| ") or line.startswith("| ---"):
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 7:
            continue
        method = parts[1]
        if method not in {"GET", "POST", "PATCH", "PUT", "DELETE"}:
            continue
        rows.append({
            "method": method,
            "path": parts[2],
            "response_schema": parts[5],
        })
    return rows


def _is_valid_schema_cell(schema: str) -> bool:
    """Return True if the schema cell contains a valid typed reference."""
    # Plain schema name (PascalCase, no spaces)
    if VALID_SCHEMA_NAME_RE.match(schema):
        return True
    # Known content-type cells (binary/stream/redirect)
    if schema in VALID_CONTENT_TYPE_CELLS:
        return True
    # application/octet-stream with extra text
    if schema.startswith("application/octet-stream"):
        return True
    return False


def _classify_cell(schema: str) -> str:
    """Return 'ok', 'old-prose', 'old-arrow', or 'invalid'."""
    for prose in OLD_PROSE_VALUES:
        if prose in schema:
            return "old-prose"
    if schema.startswith("→ "):  # → character
        return "old-arrow"
    if _is_valid_schema_cell(schema):
        return "ok"
    return "invalid"


class TestSchemaCoverage:
    """AC-1: Every endpoint has a named typed schema ref."""

    def test_all_endpoints_have_typed_schema_ref(self):
        """No endpoint row should have a prose or old arrow-prefixed response-schema cell."""
        content = CONTRACT_PATH.read_text(encoding="utf-8")
        rows = _parse_endpoint_rows(content)
        assert rows, "No endpoint rows found in api-contract.md"

        failures = []
        for row in rows:
            schema = row["response_schema"]
            classification = _classify_cell(schema)
            if classification == "old-prose":
                failures.append(
                    f"{row['method']} {row['path']!r}: contains old prose: {schema!r}"
                )
            elif classification == "old-arrow":
                failures.append(
                    f"{row['method']} {row['path']!r}: "
                    f"still uses old arrow prefix format: {schema!r}"
                )
            elif classification == "invalid":
                failures.append(
                    f"{row['method']} {row['path']!r}: "
                    f"non-typed schema cell: {schema!r}"
                )

        assert not failures, (
            f"{len(failures)} endpoint(s) have non-typed response-schema cells:\n"
            + "\n".join(failures)
        )

    def test_no_arrow_prefix_in_table(self):
        """No endpoint row should use the old '-> SchemaName' arrow prefix format.

        After response-shape-adr0007, all cells use plain schema names.
        """
        content = CONTRACT_PATH.read_text(encoding="utf-8")
        rows = _parse_endpoint_rows(content)
        violators = [
            f"{r['method']} {r['path']}: {r['response_schema']!r}"
            for r in rows
            if r["response_schema"].startswith("→ ")
        ]
        assert not violators, (
            "Endpoints still using arrow prefix in schema column:\n"
            + "\n".join(violators)
        )

    def test_endpoint_count_at_least_154(self):
        """Endpoint table should have at least 154 rows (158 minus 4 drawer endpoints + 1 PUT pages = 155; net -3 from 158; floor set to 154 for tolerance)."""
        content = CONTRACT_PATH.read_text(encoding="utf-8")
        rows = _parse_endpoint_rows(content)
        assert len(rows) >= 154, (
            f"Expected at least 154 endpoint rows, found {len(rows)} (nav-config-to-code removed 4 drawer endpoints, added 1 PUT pages row)"
        )

    def test_no_prose_success_response_in_table(self):
        """The literal string 'success_response' must not appear in response schema column."""
        content = CONTRACT_PATH.read_text(encoding="utf-8")
        rows = _parse_endpoint_rows(content)
        violators = [
            f"{r['method']} {r['path']}"
            for r in rows
            if "success_response" in r["response_schema"]
        ]
        assert not violators, (
            "Endpoints still using 'success_response' prose in schema column:\n"
            + "\n".join(violators)
        )
