# -*- coding: utf-8 -*-
"""Unit tests for production_history_service — parallel env var + partial failure."""

from __future__ import annotations

import pandas as pd
from unittest.mock import MagicMock, patch


# ============================================================
# Task 9.4: Production engine parallel env var tests
# ============================================================

class TestProductionEngineParallel:
    """PRODUCTION_ENGINE_PARALLEL env var controls execute_plan parallel; hardcoded parallel=1 removed."""

    def _make_spool_env(self, monkeypatch, *, engine_calls):
        import mes_dashboard.services.production_history_service as prod_svc
        import mes_dashboard.core.query_spool_store as spool_mod

        def fake_execute_plan(chunks, query_fn, **kwargs):
            engine_calls.append(kwargs.get("parallel"))
            return kwargs.get("query_hash", "fake_hash")

        # Must patch on the service module since it imports at module level
        monkeypatch.setattr(prod_svc, "execute_plan", fake_execute_plan)
        monkeypatch.setattr(prod_svc, "merge_chunks_to_spool", lambda *a, **kw: ("/tmp/f.parquet", 1))
        monkeypatch.setattr(prod_svc, "get_batch_progress", lambda *a: {})
        monkeypatch.setattr(spool_mod, "register_spool_file", lambda *a, **kw: None)

    def test_no_hardcoded_parallel_1(self):
        """Verify execute_plan is NOT called with hardcoded parallel=1 in source."""
        import inspect
        import mes_dashboard.services.production_history_service as prod_svc
        src = inspect.getsource(prod_svc._run_oracle_to_spool)
        assert "parallel=1" not in src, "hardcoded parallel=1 must be replaced with _PRODUCTION_ENGINE_PARALLEL"

    def test_default_parallel_is_1(self, monkeypatch):
        """Without PRODUCTION_ENGINE_PARALLEL → execute_plan gets parallel=1."""
        import mes_dashboard.services.production_history_service as prod_svc

        engine_calls = []
        monkeypatch.setattr(prod_svc, "_PRODUCTION_ENGINE_PARALLEL", 1)
        self._make_spool_env(monkeypatch, engine_calls=engine_calls)

        prod_svc._run_oracle_to_spool(
            {
                "start_date": "2025-01-01",
                "end_date": "2025-03-31",
                "end_date_exclusive": "2025-04-01",
                "pj_types": ["WIP"],
                "lot_ids": [], "work_orders": [], "packages": [],
                "bop_codes": [], "workcenter_groups": [], "workcenter_names": [],
                "equipment_ids": [],
            },
            "ph-test-id",
        )

        assert len(engine_calls) == 1
        assert engine_calls[0] == 1

    def test_parallel_2_passed_to_execute_plan(self, monkeypatch):
        """PRODUCTION_ENGINE_PARALLEL=2 → execute_plan gets parallel=2."""
        import mes_dashboard.services.production_history_service as prod_svc

        engine_calls = []
        monkeypatch.setattr(prod_svc, "_PRODUCTION_ENGINE_PARALLEL", 2)
        self._make_spool_env(monkeypatch, engine_calls=engine_calls)

        prod_svc._run_oracle_to_spool(
            {
                "start_date": "2025-01-01",
                "end_date": "2025-03-31",
                "end_date_exclusive": "2025-04-01",
                "pj_types": ["WIP"],
                "lot_ids": [], "work_orders": [], "packages": [],
                "bop_codes": [], "workcenter_groups": [], "workcenter_names": [],
                "equipment_ids": [],
            },
            "ph-test-id",
        )

        assert len(engine_calls) == 1
        assert engine_calls[0] == 2


# ============================================================
# Task 10.8: Production partial failure propagation tests
# ============================================================

class TestProductionPartialFailure:
    """Production history partial failure propagates to response meta."""

    def _make_spool_env(self, monkeypatch, *, progress=None):
        import mes_dashboard.services.production_history_service as prod_svc
        import mes_dashboard.core.query_spool_store as spool_mod

        monkeypatch.setattr(prod_svc, "execute_plan", lambda *a, **kw: kw.get("query_hash", "fake"))
        monkeypatch.setattr(prod_svc, "merge_chunks_to_spool", lambda *a, **kw: ("/tmp/f.parquet", 1))
        monkeypatch.setattr(prod_svc, "get_batch_progress", lambda *a: progress or {})
        monkeypatch.setattr(spool_mod, "register_spool_file", lambda *a, **kw: None)

    def test_partial_failure_returned_from_spool(self, monkeypatch):
        """Chunk partial failure → _run_oracle_to_spool returns non-empty dict."""
        import mes_dashboard.services.production_history_service as prod_svc
        self._make_spool_env(
            monkeypatch,
            progress={"has_partial_failure": "True", "failed_chunk_count": "1", "failed_ranges": "2025-01-01~2025-01-31"},
        )

        result = prod_svc._run_oracle_to_spool(
            {
                "start_date": "2025-01-01",
                "end_date": "2025-03-31",
                "end_date_exclusive": "2025-04-01",
                "pj_types": ["WIP"],
                "lot_ids": [], "work_orders": [], "packages": [],
                "bop_codes": [], "workcenter_groups": [], "workcenter_names": [],
                "equipment_ids": [],
            },
            "ph-test-id",
        )

        assert result.get("has_partial_failure") is True

    def test_no_partial_failure_returns_empty_dict(self, monkeypatch):
        """All chunks succeed → _run_oracle_to_spool returns empty dict."""
        import mes_dashboard.services.production_history_service as prod_svc
        self._make_spool_env(monkeypatch)

        result = prod_svc._run_oracle_to_spool(
            {
                "start_date": "2025-01-01",
                "end_date": "2025-03-31",
                "end_date_exclusive": "2025-04-01",
                "pj_types": ["WIP"],
                "lot_ids": [], "work_orders": [], "packages": [],
                "bop_codes": [], "workcenter_groups": [], "workcenter_names": [],
                "equipment_ids": [],
            },
            "ph-test-id",
        )

        assert result == {}
