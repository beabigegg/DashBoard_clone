# -*- coding: utf-8 -*-
"""Contract tests: async threshold env var removal + QUERY_TOOL_USE_RQ addition.

query-path-c-elimination-cleanup (IP-11, P5):
  AC-5: The 4 *_ASYNC_DAY_THRESHOLD vars are absent from env.schema.json.
  AC-6: global_concurrency semaphore semantics re-documented as "limit RQ Oracle concurrency".
  AC-7: QUERY_TOOL_USE_RQ present in env.schema.json with default "off".
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).parent.parent.parent
_SCHEMA_PATH = _REPO_ROOT / "contracts" / "env" / "env.schema.json"
_ENV_CONTRACT_PATH = _REPO_ROOT / "contracts" / "env" / "env-contract.md"
_GLOBAL_CONCURRENCY_PATH = (
    _REPO_ROOT / "src" / "mes_dashboard" / "core" / "global_concurrency.py"
)


@pytest.fixture(scope="module")
def schema() -> dict:
    return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# AC-5: Removed vars must NOT appear in env.schema.json
# ---------------------------------------------------------------------------


def test_downtime_async_day_threshold_absent_from_schema(schema):
    """DOWNTIME_ASYNC_DAY_THRESHOLD must be absent from env.schema.json (AC-5, R4)."""
    assert "DOWNTIME_ASYNC_DAY_THRESHOLD" not in schema.get("properties", {}), (
        "DOWNTIME_ASYNC_DAY_THRESHOLD was removed (query-path-c-elimination-cleanup, IP-7) "
        "but is still present in env.schema.json. Remove it."
    )


def test_hold_async_day_threshold_absent_from_schema(schema):
    """HOLD_ASYNC_DAY_THRESHOLD must be absent from env.schema.json (AC-5, R4)."""
    assert "HOLD_ASYNC_DAY_THRESHOLD" not in schema.get("properties", {}), (
        "HOLD_ASYNC_DAY_THRESHOLD was removed (query-path-c-elimination-cleanup, IP-7) "
        "but is still present in env.schema.json. Remove it."
    )


def test_resource_async_day_threshold_absent_from_schema(schema):
    """RESOURCE_ASYNC_DAY_THRESHOLD must be absent from env.schema.json (AC-5, R4)."""
    assert "RESOURCE_ASYNC_DAY_THRESHOLD" not in schema.get("properties", {}), (
        "RESOURCE_ASYNC_DAY_THRESHOLD was removed (query-path-c-elimination-cleanup, IP-7) "
        "but is still present in env.schema.json. Remove it."
    )


def test_reject_async_day_threshold_absent_from_schema(schema):
    """REJECT_ASYNC_DAY_THRESHOLD must be absent from env.schema.json (AC-5, R4)."""
    assert "REJECT_ASYNC_DAY_THRESHOLD" not in schema.get("properties", {}), (
        "REJECT_ASYNC_DAY_THRESHOLD was removed (query-path-c-elimination-cleanup, IP-7) "
        "but is still present in env.schema.json. Remove it."
    )


# ---------------------------------------------------------------------------
# AC-7: QUERY_TOOL_USE_RQ must be present with default="on"
# ---------------------------------------------------------------------------


def test_query_tool_use_rq_present_with_default_on(schema):
    """QUERY_TOOL_USE_RQ must be in env.schema.json with default 'on' (AC-7, promoted 2026-06-20)."""
    props = schema.get("properties", {})
    assert "QUERY_TOOL_USE_RQ" in props, (
        "QUERY_TOOL_USE_RQ not found in env.schema.json. "
        "Add it per query-path-c-elimination-cleanup IP-9."
    )
    entry = props["QUERY_TOOL_USE_RQ"]
    assert entry.get("default") == "on", (
        f"QUERY_TOOL_USE_RQ default must be 'on', got {entry.get('default')!r}. "
        "Default promoted to on 2026-06-20 after pool manager wiring complete."
    )
    assert "enum" in entry, (
        "QUERY_TOOL_USE_RQ must have 'enum' field for typo-guard validation."
    )
    assert "off" in entry["enum"], (
        f"'off' must be in QUERY_TOOL_USE_RQ enum. Got: {entry['enum']}"
    )
    assert "on" in entry["enum"], (
        f"'on' must be in QUERY_TOOL_USE_RQ enum. Got: {entry['enum']}"
    )


# ---------------------------------------------------------------------------
# AC-6: global_concurrency semantics note (RQ Oracle concurrency)
# ---------------------------------------------------------------------------


def test_semaphore_semantics_note_in_env_contract():
    """env-contract.md or global_concurrency.py must document 'RQ Oracle concurrency' (AC-6, D3).

    Per design.md D3, the semaphore role is documented (no runtime change).
    Acceptable in either global_concurrency.py docstring or env-contract.md.
    """
    gc_text = _GLOBAL_CONCURRENCY_PATH.read_text(encoding="utf-8")
    contract_text = _ENV_CONTRACT_PATH.read_text(encoding="utf-8")

    # Accept any of the equivalent phrases used in the docstring re-write.
    _SEMANTICS_PHRASES = [
        "RQ Oracle concurrency",
        "concurrent RQ jobs hitting Oracle",
        "concurrent RQ heavy jobs hitting Oracle",
        "concurrent RQ heavy jobs concurrently hitting Oracle",
    ]
    _found = any(
        phrase in gc_text or phrase in contract_text
        for phrase in _SEMANTICS_PHRASES
    )
    assert _found, (
        "Neither global_concurrency.py nor env-contract.md contains "
        "the expected RQ-Oracle-concurrency semantics phrase. "
        "Expected one of: " + repr(_SEMANTICS_PHRASES) + ". "
        "Update one of them per query-path-c-elimination-cleanup IP-8 (D3)."
    )
