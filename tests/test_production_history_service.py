# -*- coding: utf-8 -*-
"""Unit tests for production_history_service — parallel env var + partial failure."""

from __future__ import annotations

import pytest


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


class TestValidateQueryParamsModeSplit:
    """PHF-07 / PHF-08 — mode-split validation for prod-history-query-mode-tabs.

    Identifier mode (≥1 wildcard token present):
      - dates optional → wide 730-day window substituted when absent
      - pj_types NOT required
    Classification mode (no identifier token):
      - pj_types + start_date + end_date all still required
    """

    def test_identifier_mode_no_dates_accepted(self):
        """PHF-07 — wildcard tokens present, dates omitted → no raise, no pj_types needed."""
        from mes_dashboard.services.production_history_service import (
            validate_query_params,
        )
        params = validate_query_params({"lot_ids": ["GA001AB"]})
        assert params["lot_ids_tokens"], "lot_ids must parse to tokens"
        assert params["pj_types"] == []
        assert params["start_date"] and params["end_date"]

    def test_identifier_mode_runs_wide_window(self):
        """AC-5 — no-date identifier query produces a 730-day wide bind, not 30-day default."""
        from datetime import date, datetime
        from mes_dashboard.services.production_history_service import (
            MAX_DATE_RANGE_DAYS,
            validate_query_params,
        )
        params = validate_query_params({"mfg_orders": "MA2025*"})
        start_dt = datetime.strptime(params["start_date"], "%Y-%m-%d").date()
        end_dt = datetime.strptime(params["end_date"], "%Y-%m-%d").date()
        span = (end_dt - start_dt).days + 1
        assert span == MAX_DATE_RANGE_DAYS, f"wide window span must equal cap, got {span}"
        assert end_dt == date.today(), "wide window must be anchored at today"
        assert start_dt >= date.today() - __import__("datetime").timedelta(days=MAX_DATE_RANGE_DAYS)

    def test_classification_mode_missing_dates_still_raises(self):
        """PHF-08 — pj_types present, no identifier token, no dates → dates-required error."""
        from mes_dashboard.services.production_history_service import (
            validate_query_params,
        )
        with pytest.raises(ValueError, match="start_date, end_date"):
            validate_query_params({"pj_types": ["GA"]})

    def test_classification_mode_missing_pj_types_still_raises(self):
        """PHF-08 — no identifier token, no pj_types → pj_types-required error."""
        from mes_dashboard.services.production_history_service import (
            validate_query_params,
        )
        with pytest.raises(ValueError, match="pj_types"):
            validate_query_params({"start_date": "2026-03-01", "end_date": "2026-03-10"})

    def test_classification_mode_unchanged_with_dates(self):
        """AC-7 — existing type+date flow byte-identical bind."""
        from mes_dashboard.services.production_history_service import (
            validate_query_params,
        )
        params = validate_query_params({
            "pj_types": ["GA"],
            "start_date": "2026-03-01",
            "end_date": "2026-03-10",
        })
        assert params["start_date"] == "2026-03-01"
        assert params["end_date"] == "2026-03-10"
        assert params["end_date_exclusive"] == "2026-03-11"

    def test_identifier_mode_with_dates_still_honors_them(self):
        """PHF-07 — dates supplied alongside tokens → date predicate kept verbatim."""
        from mes_dashboard.services.production_history_service import (
            validate_query_params,
        )
        params = validate_query_params({
            "lot_ids": ["GA001AB"],
            "start_date": "2026-01-01",
            "end_date": "2026-01-31",
        })
        assert params["start_date"] == "2026-01-01"
        assert params["end_date"] == "2026-01-31"

    def test_identifier_mode_with_dates_over_cap_still_raises(self):
        """VAL-03 — identifier tokens + explicit dates > 730d → still raises."""
        from mes_dashboard.services.production_history_service import (
            validate_query_params,
        )
        with pytest.raises(ValueError, match="日期區間超過上限"):
            validate_query_params({
                "lot_ids": ["GA001AB"],
                "start_date": "2020-01-01",
                "end_date": "2026-03-25",
            })

    def test_query_identifier_wide_window_bounded(self):
        """AC-5 — no-date identifier path is date-bounded, never unbounded.

        Deterministic verification: the substituted window spans exactly the
        730-day cap and chunk_start ≥ today − 730d — no unbounded predicate
        ever reaches Oracle. No Oracle optimizer reliance.
        """
        from datetime import date, timedelta
        from mes_dashboard.services.batch_query_engine import decompose_by_time_range
        from mes_dashboard.services.production_history_service import (
            ENGINE_GRAIN_DAYS,
            MAX_DATE_RANGE_DAYS,
            validate_query_params,
        )
        params = validate_query_params({"wafer_lots": ["W12345*"]})
        chunks = decompose_by_time_range(
            params["start_date"], params["end_date"], grain_days=ENGINE_GRAIN_DAYS
        )
        assert chunks, "decompose must yield at least one chunk"
        floor = date.today() - timedelta(days=MAX_DATE_RANGE_DAYS)
        first_start = min(c["chunk_start"] for c in chunks)
        last_end = max(c["chunk_end"] for c in chunks)
        assert first_start >= floor.strftime("%Y-%m-%d"), "chunk_start must be ≥ today − 730d"
        first_dt = datetime_from(first_start)
        last_dt = datetime_from(last_end)
        total_span = (last_dt - first_dt).days + 1
        assert total_span == MAX_DATE_RANGE_DAYS, (
            f"total chunk span must equal the 730d cap, got {total_span}"
        )


def datetime_from(value: str):
    from datetime import datetime
    return datetime.strptime(value, "%Y-%m-%d").date()
