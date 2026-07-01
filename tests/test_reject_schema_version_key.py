# -*- coding: utf-8 -*-
"""Regression tripwire: reject_dataset embeds its schema version in the query_id.

Context (query-arch A-4): the cache-spool audit claimed reject_dataset did NOT
embed _CACHE_SCHEMA_VERSION in its query_id, risking stale-schema parquet reads
after a version bump. Verification showed the embed IS present at every call
site, so there was no defect to fix. These tests convert that already-correct
behaviour into a protected contract so a future refactor cannot silently drop
the embed (which WOULD reintroduce the stale-parquet risk).

Invariant: bumping _CACHE_SCHEMA_VERSION must change the query_id for the same
logical query, so old parquet under the previous version is orphaned, not read.
"""
from __future__ import annotations

import ast
from pathlib import Path

from mes_dashboard.services import reject_dataset_cache as cache_svc

_SRC = Path(__file__).parent.parent / "src/mes_dashboard/services/reject_dataset_cache.py"


def test_make_query_id_is_sensitive_to_schema_version():
    """Two otherwise-identical inputs with different schema versions hash differently."""
    base = {
        "mode": "lot",
        "start_date": "2025-01-01",
        "end_date": "2025-01-31",
        "container_values": ["LOT001"],
    }
    id_v7 = cache_svc._make_query_id({"cache_schema_version": 7, **base})
    id_v8 = cache_svc._make_query_id({"cache_schema_version": 8, **base})
    assert id_v7 != id_v8, "query_id must change when the schema version changes"


def test_schema_version_constant_is_present():
    """The version constant exists (its value is free to bump)."""
    assert isinstance(cache_svc._CACHE_SCHEMA_VERSION, int)


def test_every_make_query_id_call_site_includes_schema_version():
    """AST guard: every function that builds a reject query_id references the
    schema version, so the embed cannot be dropped from any call site.
    """
    tree = ast.parse(_SRC.read_text(encoding="utf-8"))

    # Functions whose body calls _make_query_id(...).
    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        calls_make_query_id = any(
            isinstance(c, ast.Call)
            and (
                (isinstance(c.func, ast.Name) and c.func.id == "_make_query_id")
                or (isinstance(c.func, ast.Attribute) and c.func.attr == "_make_query_id")
            )
            for c in ast.walk(node)
        )
        if not calls_make_query_id:
            continue
        # The same function must reference cache_schema_version / _CACHE_SCHEMA_VERSION.
        references_version = any(
            (isinstance(n, ast.Constant) and n.value == "cache_schema_version")
            or (isinstance(n, ast.Name) and n.id == "_CACHE_SCHEMA_VERSION")
            for n in ast.walk(node)
        )
        if not references_version:
            offenders.append(node.name)

    assert not offenders, (
        "These functions build a reject query_id without embedding the schema "
        f"version (stale-parquet risk on version bump): {offenders}"
    )
