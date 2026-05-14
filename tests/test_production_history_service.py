# -*- coding: utf-8 -*-
"""Unit tests for production_history_service — parallel env var + partial failure."""

from __future__ import annotations



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


# ============================================================
# Change: prod-history-first-tier-cache-filters
# AC-3 / AC-4 / AC-5 / AC-8 / PHF-02..PHF-06
# ============================================================


class TestMainQueryNewParams:
    """validate_query_params + _build_extra_filters wire the 6 new filter params."""

    def _base(self) -> dict:
        return {
            "pj_types": ["GA"],
            "start_date": "2026-03-01",
            "end_date": "2026-03-10",
        }

    def test_main_query_accepts_new_filter_params(self):
        """AC-3 — pj_packages/pj_bops/pj_functions accepted and reflected."""
        from mes_dashboard.services.production_history_service import (
            validate_query_params,
        )
        params = validate_query_params({
            **self._base(),
            "pj_packages": ["PKG_A", "PKG_B"],
            "pj_bops": ["BOP_1"],
            "pj_functions": ["FN_X"],
        })
        assert params["pj_packages"] == ["PKG_A", "PKG_B"]
        assert params["pj_bops"] == ["BOP_1"]
        assert params["pj_functions"] == ["FN_X"]

    def test_main_query_accepts_wildcard_params(self):
        """AC-4 — mfg_orders / wafer_lots wildcard tokens parse OK."""
        from mes_dashboard.services.production_history_service import (
            validate_query_params,
        )
        params = validate_query_params({
            **self._base(),
            "mfg_orders": "MA2025*\nMA2026",
            "wafer_lots": ["W123*"],
        })
        mo = params["mfg_orders_tokens"]
        wl = params["wafer_lots_tokens"]
        assert any(t.bound_value == "MA2025%" for t in mo)
        assert any(t.bound_value == "MA2026" for t in mo)
        assert any(t.bound_value == "W123%" for t in wl)

    def test_extra_filters_wildcard_bind_emits_like_escape(self):
        """PHF-03 — wildcard token emits LIKE :bind ESCAPE '\\'."""
        from mes_dashboard.services.production_history_service import (
            _build_extra_filters,
            validate_query_params,
        )
        params = validate_query_params({
            **self._base(),
            "mfg_orders": "MA2025*",
        })
        sql, binds = _build_extra_filters(params)
        assert "c.MFGORDERNAME LIKE :" in sql
        assert "ESCAPE '\\'" in sql
        # Bound value must already contain the % translation.
        assert any(v == "MA2025%" for v in binds.values())
        # No string interpolation of the user token (PHF-03).
        assert "MA2025%" not in sql

    def test_backward_compat_type_only_flow_unchanged(self):
        """AC-3 — empty filters reproduce today's Type-only SQL fragment."""
        from mes_dashboard.services.production_history_service import (
            _build_extra_filters,
            validate_query_params,
        )
        params = validate_query_params(self._base())
        sql, binds = _build_extra_filters(params)
        # Only PJ_TYPE IN (...) appears
        assert "c.PJ_TYPE IN" in sql
        assert "MFGORDERNAME" not in sql
        assert "FIRSTNAME" not in sql
        assert "PJ_BOP" not in sql
        assert "PJ_FUNCTION" not in sql

    def test_empty_cache_state_validate_does_not_touch_cache(self):
        """validate_query_params must not depend on container_filter_cache state."""
        # If validation accidentally touched the cache, an empty cache state
        # would surface as a 500 — instead it must succeed.
        from mes_dashboard.services.production_history_service import (
            validate_query_params,
        )
        params = validate_query_params({
            **self._base(),
            "pj_packages": ["PKG_X"],
        })
        assert params["pj_packages"] == ["PKG_X"]

    def test_pj_function_null_handled(self):
        """Data-boundary — empty pj_functions list is valid (NULL-friendly)."""
        from mes_dashboard.services.production_history_service import (
            validate_query_params,
        )
        params = validate_query_params({
            **self._base(),
            "pj_functions": [],
        })
        assert params["pj_functions"] == []

    def test_stale_schema_v1_payload_ignored_by_get_pj_types(self):
        """AC-8 — get_pj_types after v1 payload encountered returns empty/safe."""
        import mes_dashboard.services.container_filter_cache as cache_mod
        # Force-clear and simulate L1 untouched + L2 returning legacy payload.
        cache_mod._CACHE["loaded"] = False

        class _FakeRedis:
            def get(self, _key):
                import json
                return json.dumps({"packages": ["X"], "pj_types": ["Y"]})  # no schema_version

            def set(self, *a, **kw):
                pass

        from unittest.mock import patch
        # _read_from_redis returns None (schema mismatch) → would fall through to lock+Oracle.
        # Patch Oracle to return empty so the cache stays unloaded but no crash.
        with patch.object(cache_mod, "get_redis_client", return_value=_FakeRedis()):
            with patch.object(cache_mod, "REDIS_ENABLED", True):
                with patch(
                    "mes_dashboard.services.container_filter_cache.read_sql_df",
                    return_value=None,
                ):
                    out = cache_mod.get_pj_types()
        assert out == []
