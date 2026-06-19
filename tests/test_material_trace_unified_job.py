# -*- coding: utf-8 -*-
"""Unit tests for MaterialTraceJob unified pipeline — IP-7.

AC-1: flag=off → legacy enqueue_job path (rq_material_trace_job)
AC-2: flag=on  → enqueues "material-trace-unified" via enqueue_query_job
AC-3: flag=on + is_async_available=False → HTTP 503, no fallback
AC-4: spool column set equivalence (legacy _EXPORT_COLS == unified namespace)
AC-6: AST-walk proves no _check_memory_guard() call on unified path
AC-8: ID-list decomposes at 1000 per batch (workorder / material_lot modes)
flag default-off: MATERIAL_TRACE_USE_UNIFIED_JOB resolves falsy when env unset
"""
from __future__ import annotations

import ast
import importlib
import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from mes_dashboard import create_app
from mes_dashboard.core.cache import NoOpCache
from mes_dashboard.core.rate_limit import reset_rate_limits_for_tests


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def app():
    """Flask test application."""
    _app = create_app()
    _app.config["TESTING"] = True
    _app.extensions["cache"] = NoOpCache()
    return _app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    reset_rate_limits_for_tests()
    yield
    reset_rate_limits_for_tests()


# Minimal valid POST body for the query endpoint.
_VALID_BODY = {"mode": "workorder", "values": ["WO-001"]}


def _post_query(client, body=None, **kwargs):
    body = body or _VALID_BODY
    return client.post(
        "/api/material-trace/query",
        data=json.dumps(body),
        content_type="application/json",
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Helper: cause spool miss by mocking MaterialTraceDuckdbRuntime
# ---------------------------------------------------------------------------

def _patch_spool_miss(monkeypatch):
    """Make the spool-hit check return None (cold spool → dispatch path)."""
    mock_rt = MagicMock()
    mock_rt.is_available.return_value = False
    mock_rt.get_page.return_value = None
    monkeypatch.setattr(
        "mes_dashboard.routes.material_trace_routes.MaterialTraceDuckdbRuntime",
        MagicMock(return_value=mock_rt),
    )
    return mock_rt


# ---------------------------------------------------------------------------
# AC-1: flag=off → legacy enqueue_job path
# ---------------------------------------------------------------------------

class TestFlagOffLegacyPath:
    """AC-1: When MATERIAL_TRACE_USE_UNIFIED_JOB=False, legacy enqueue_job is called."""

    def test_flag_off_uses_legacy_concat_path(self, monkeypatch, client):
        """flag=off: enqueue_job (rq_material_trace_job) is called; enqueue_query_job is NOT."""
        import mes_dashboard.routes.material_trace_routes as routes_mod

        # Freeze flag to False (module-level constant; must use setattr, not setenv)
        monkeypatch.setattr(routes_mod, "MATERIAL_TRACE_USE_UNIFIED_JOB", False)

        _patch_spool_miss(monkeypatch)

        mock_enqueue_job = MagicMock(return_value=("mtrace-legacy-001", None))
        monkeypatch.setattr(
            "mes_dashboard.routes.material_trace_routes.enqueue_job",
            mock_enqueue_job,
        )
        monkeypatch.setattr(
            "mes_dashboard.core.permissions.get_owner_token",
            lambda: "test-user",
        )

        resp = _post_query(client)

        # Legacy enqueue_job must have been called
        assert mock_enqueue_job.called, "enqueue_job (legacy path) was not called when flag=off"
        call_kwargs = mock_enqueue_job.call_args.kwargs
        assert call_kwargs.get("worker_fn") is not None, "legacy path must pass worker_fn"

    def test_flag_off_unified_job_not_enqueued(self, monkeypatch, client):
        """flag=off: enqueue_query_job (unified path) must NOT be called."""
        import mes_dashboard.routes.material_trace_routes as routes_mod

        monkeypatch.setattr(routes_mod, "MATERIAL_TRACE_USE_UNIFIED_JOB", False)
        _patch_spool_miss(monkeypatch)

        monkeypatch.setattr(
            "mes_dashboard.routes.material_trace_routes.enqueue_job",
            MagicMock(return_value=("mtrace-legacy-001", None)),
        )
        monkeypatch.setattr(
            "mes_dashboard.core.permissions.get_owner_token",
            lambda: "test-user",
        )

        # Patch enqueue_query_job at its source; it should never be imported/called
        mock_unified = MagicMock(return_value=("mtrace-unified-001", None, "ok"))
        monkeypatch.setattr(
            "mes_dashboard.services.async_query_job_service.enqueue_query_job",
            mock_unified,
        )

        _post_query(client)
        assert not mock_unified.called, "enqueue_query_job must not be called when flag=off"


# ---------------------------------------------------------------------------
# AC-2: flag=on → enqueues "material-trace-unified"
# ---------------------------------------------------------------------------

class TestFlagOnUnifiedPath:
    """AC-2: When flag=on, enqueue_query_job is called with job_type 'material-trace-unified'."""

    def test_flag_on_enqueues_unified_job(self, monkeypatch, client):
        """flag=on + async available: enqueue_query_job called with 'material-trace-unified'."""
        import mes_dashboard.routes.material_trace_routes as routes_mod

        monkeypatch.setattr(routes_mod, "MATERIAL_TRACE_USE_UNIFIED_JOB", True)
        _patch_spool_miss(monkeypatch)

        monkeypatch.setattr(
            "mes_dashboard.core.permissions.get_owner_token",
            lambda: "test-user",
        )

        captured_args: dict[str, Any] = {}

        def _mock_enqueue_query_job(job_type, *, owner, params, sync_fallback_allowed, job_id, **kw):
            captured_args["job_type"] = job_type
            captured_args["params"] = params
            captured_args["sync_fallback_allowed"] = sync_fallback_allowed
            return (job_id, None, "enqueued")

        monkeypatch.setattr(
            "mes_dashboard.services.async_query_job_service.enqueue_query_job",
            _mock_enqueue_query_job,
        )
        monkeypatch.setattr(
            "mes_dashboard.services.async_query_job_service.is_async_available",
            lambda: True,
        )

        resp = _post_query(client)

        assert resp.status_code == 202, f"Expected 202 from unified path, got {resp.status_code}"
        assert captured_args.get("job_type") == "material-trace-unified", (
            f"Expected job_type='material-trace-unified', got {captured_args.get('job_type')!r}"
        )
        assert captured_args.get("sync_fallback_allowed") is False, (
            "Unified path must set sync_fallback_allowed=False (D4: no sync fallback)"
        )

    def test_flag_on_response_contains_job_id_and_status_url(self, monkeypatch, client):
        """flag=on: 202 response includes job_id and status_url."""
        import mes_dashboard.routes.material_trace_routes as routes_mod

        monkeypatch.setattr(routes_mod, "MATERIAL_TRACE_USE_UNIFIED_JOB", True)
        _patch_spool_miss(monkeypatch)

        monkeypatch.setattr(
            "mes_dashboard.core.permissions.get_owner_token",
            lambda: "test-user",
        )
        monkeypatch.setattr(
            "mes_dashboard.services.async_query_job_service.is_async_available",
            lambda: True,
        )
        monkeypatch.setattr(
            "mes_dashboard.services.async_query_job_service.enqueue_query_job",
            lambda job_type, *, owner, params, sync_fallback_allowed, job_id, **kw: (
                job_id, None, "enqueued"
            ),
        )

        resp = _post_query(client)
        payload = json.loads(resp.data)

        assert "job_id" in payload["data"], "202 response must include job_id"
        assert "status_url" in payload["data"], "202 response must include status_url"
        assert "/api/material-trace/job/" in payload["data"]["status_url"]


# ---------------------------------------------------------------------------
# AC-3: flag=on + no RQ → 503, no fallback
# ---------------------------------------------------------------------------

class TestFlagOnNoRqReturns503:
    """AC-3: flag=on + is_async_available=False → 503 SERVICE_UNAVAILABLE, no fallback enqueue."""

    def test_flag_on_no_rq_returns_503_no_fallback(self, monkeypatch, client):
        """flag=on + RQ unavailable: response is 503, no job enqueued."""
        import mes_dashboard.routes.material_trace_routes as routes_mod

        monkeypatch.setattr(routes_mod, "MATERIAL_TRACE_USE_UNIFIED_JOB", True)
        _patch_spool_miss(monkeypatch)

        monkeypatch.setattr(
            "mes_dashboard.core.permissions.get_owner_token",
            lambda: "test-user",
        )
        monkeypatch.setattr(
            "mes_dashboard.services.async_query_job_service.is_async_available",
            lambda: False,
        )

        mock_enqueue_q = MagicMock()
        monkeypatch.setattr(
            "mes_dashboard.services.async_query_job_service.enqueue_query_job",
            mock_enqueue_q,
        )
        legacy_enqueue = MagicMock()
        monkeypatch.setattr(
            "mes_dashboard.routes.material_trace_routes.enqueue_job",
            legacy_enqueue,
        )

        resp = _post_query(client)

        assert resp.status_code == 503, (
            f"Expected 503 when async unavailable with flag=on, got {resp.status_code}"
        )
        assert not mock_enqueue_q.called, "enqueue_query_job must NOT be called when async unavailable"
        assert not legacy_enqueue.called, "Legacy enqueue_job must NOT be called as fallback (D4)"

    def test_flag_on_no_rq_retry_after_header_present(self, monkeypatch, client):
        """flag=on + 503: Retry-After header must be present."""
        import mes_dashboard.routes.material_trace_routes as routes_mod

        monkeypatch.setattr(routes_mod, "MATERIAL_TRACE_USE_UNIFIED_JOB", True)
        _patch_spool_miss(monkeypatch)

        monkeypatch.setattr(
            "mes_dashboard.core.permissions.get_owner_token",
            lambda: "test-user",
        )
        monkeypatch.setattr(
            "mes_dashboard.services.async_query_job_service.is_async_available",
            lambda: False,
        )
        monkeypatch.setattr(
            "mes_dashboard.services.async_query_job_service.enqueue_query_job",
            MagicMock(),
        )

        resp = _post_query(client)
        assert resp.status_code == 503
        assert resp.headers.get("Retry-After") is not None, "503 must carry Retry-After header"


# ---------------------------------------------------------------------------
# AC-4: spool schema equivalence
# ---------------------------------------------------------------------------

class TestSpoolSchemaEquivalence:
    """AC-4: Unified path spool column set must match legacy _EXPORT_COLS."""

    def test_spool_schema_equivalent_flag_off_vs_on(self):
        """_EXPORT_COLS in duckdb_runtime must equal _CSV_COLUMNS keys in service (AC-4)."""
        from mes_dashboard.services.material_trace_duckdb_runtime import _EXPORT_COLS
        from mes_dashboard.services.material_trace_service import _CSV_COLUMNS

        unified_cols = set(_EXPORT_COLS)
        legacy_cols = set(_CSV_COLUMNS.keys())

        assert unified_cols == legacy_cols, (
            f"Column set mismatch between unified _EXPORT_COLS and legacy _CSV_COLUMNS.\n"
            f"  Only in unified: {unified_cols - legacy_cols}\n"
            f"  Only in legacy:  {legacy_cols - unified_cols}"
        )

    def test_spool_namespace_matches_legacy(self):
        """Unified namespace must be 'material_trace' (same as legacy spool key)."""
        from mes_dashboard.services.material_trace_duckdb_runtime import _SPOOL_NAMESPACE
        assert _SPOOL_NAMESPACE == "material_trace", (
            f"Namespace must be 'material_trace' for spool-key determinism, got {_SPOOL_NAMESPACE!r}"
        )


# ---------------------------------------------------------------------------
# AC-6: AST-walk proves _check_memory_guard absent from MaterialTraceJob
# ---------------------------------------------------------------------------

class TestNoMemoryGuardOnUnifiedPath:
    """AC-6: _check_memory_guard must not be called anywhere in MaterialTraceJob."""

    def test_no_memory_guard_call_on_unified_path_ast(self):
        """AST-walk: no ast.Call to _check_memory_guard within material_trace_duckdb_runtime.py."""
        runtime_path = (
            Path(__file__).parent.parent
            / "src" / "mes_dashboard" / "services" / "material_trace_duckdb_runtime.py"
        )
        source = runtime_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(runtime_path))

        forbidden_fn = "_check_memory_guard"
        violations: list[int] = []

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                # Direct call: _check_memory_guard(...)
                if isinstance(node.func, ast.Name) and node.func.id == forbidden_fn:
                    violations.append(node.lineno)
                # Attribute call: self._check_memory_guard(...)
                elif isinstance(node.func, ast.Attribute) and node.func.attr == forbidden_fn:
                    violations.append(node.lineno)

        assert not violations, (
            f"_check_memory_guard() is called at line(s) {violations} in "
            f"material_trace_duckdb_runtime.py — must be removed from unified path (AC-6/D2)"
        )


# ---------------------------------------------------------------------------
# AC-8: ID-list decomposition at 1000/batch
# ---------------------------------------------------------------------------

class TestIdListDecomposition:
    """AC-8: MaterialTraceJob.pre_query() (via __init__) decomposes IDs at 1000/batch."""

    def _make_job(self, mode: str, values: list[str]) -> "MaterialTraceJob":
        """Instantiate MaterialTraceJob and call pre_query() with mocked external deps.

        pre_query() lazily imports from material_trace_service and filter_cache.
        Patch at the definition site (where names are resolved at call time).
        For workorder / material_lot modes, _resolve_container_ids is not called.
        Only get_workcenter_mapping() and make_route_query_hash require mocking for
        these modes (no Oracle / Redis access).
        """
        from mes_dashboard.services.material_trace_duckdb_runtime import MaterialTraceJob

        with (
            patch("mes_dashboard.services.material_trace_service.make_route_query_hash",
                  return_value="test-hash-001"),
            patch("mes_dashboard.services.filter_cache.get_workcenter_mapping",
                  return_value={}),
        ):
            job = MaterialTraceJob(
                job_id="test-job-001",
                params={"mode": mode, "values": values},
            )
            job.pre_query()
            return job

    def test_id_list_decomposes_1000_per_batch(self):
        """2500 workorder IDs → 3 batches (ceil(2500/1000) = 3)."""
        values = [f"WO-{i:05d}" for i in range(2500)]
        job = self._make_job("workorder", values)

        assert len(job._chunks) == 3, (
            f"Expected 3 chunks for 2500 IDs at 1000/batch, got {len(job._chunks)}"
        )

    def test_each_batch_has_at_most_1000_ids(self):
        """Each chunk in the 2500-ID decomposition has ≤ 1000 values."""
        values = [f"WO-{i:05d}" for i in range(2500)]
        job = self._make_job("workorder", values)

        for idx, chunk in enumerate(job._chunks):
            batch = chunk["batch"]
            assert len(batch) <= 1000, (
                f"Chunk {idx} has {len(batch)} IDs, expected ≤ 1000 (AC-8)"
            )

    def test_batch_size_boundary_exactly_1000(self):
        """Exactly 1000 IDs → 1 single batch."""
        values = [f"WO-{i:05d}" for i in range(1000)]
        job = self._make_job("workorder", values)
        assert len(job._chunks) == 1, "Exactly 1000 IDs must produce exactly 1 chunk"
        assert len(job._chunks[0]["batch"]) == 1000

    def test_batch_size_1001_splits_into_two(self):
        """1001 IDs → 2 batches (boundary condition)."""
        values = [f"WO-{i:05d}" for i in range(1001)]
        job = self._make_job("workorder", values)
        assert len(job._chunks) == 2, (
            f"1001 IDs must split into 2 chunks, got {len(job._chunks)}"
        )
        assert len(job._chunks[0]["batch"]) == 1000
        assert len(job._chunks[1]["batch"]) == 1

    def test_material_lot_mode_also_decomposes_at_1000(self):
        """material_lot (reverse) mode decomposes at same 1000/batch boundary."""
        values = [f"MLOT-{i:05d}" for i in range(2500)]
        job = self._make_job("material_lot", values)
        assert len(job._chunks) == 3, (
            f"material_lot mode: expected 3 chunks for 2500 IDs, got {len(job._chunks)}"
        )


# ---------------------------------------------------------------------------
# Flag default-off assertion
# ---------------------------------------------------------------------------

class TestFlagDefaultOff:
    """Module-level MATERIAL_TRACE_USE_UNIFIED_JOB constant must default to falsy."""

    def test_flag_constant_defaults_off(self, monkeypatch):
        """MATERIAL_TRACE_USE_UNIFIED_JOB is False when env var is absent (monkeypatch.delenv)."""
        monkeypatch.delenv("MATERIAL_TRACE_USE_UNIFIED_JOB", raising=False)

        import mes_dashboard.routes.material_trace_routes as routes_mod
        importlib.reload(routes_mod)  # re-evaluate module with env var unset

        flag_value = routes_mod.MATERIAL_TRACE_USE_UNIFIED_JOB
        assert not flag_value, (
            f"MATERIAL_TRACE_USE_UNIFIED_JOB must be falsy when env var is absent, "
            f"got {flag_value!r}"
        )

    def test_flag_off_string_resolves_false(self, monkeypatch):
        """Explicit MATERIAL_TRACE_USE_UNIFIED_JOB=off → False."""
        monkeypatch.setenv("MATERIAL_TRACE_USE_UNIFIED_JOB", "off")

        import mes_dashboard.routes.material_trace_routes as routes_mod
        importlib.reload(routes_mod)

        assert not routes_mod.MATERIAL_TRACE_USE_UNIFIED_JOB, (
            "MATERIAL_TRACE_USE_UNIFIED_JOB='off' must resolve to False"
        )

    def test_flag_on_string_resolves_true(self, monkeypatch):
        """Explicit MATERIAL_TRACE_USE_UNIFIED_JOB=on → True."""
        monkeypatch.setenv("MATERIAL_TRACE_USE_UNIFIED_JOB", "on")

        import mes_dashboard.routes.material_trace_routes as routes_mod
        importlib.reload(routes_mod)

        assert routes_mod.MATERIAL_TRACE_USE_UNIFIED_JOB, (
            "MATERIAL_TRACE_USE_UNIFIED_JOB='on' must resolve to True"
        )
