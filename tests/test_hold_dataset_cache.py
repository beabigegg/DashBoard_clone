# -*- coding: utf-8 -*-
"""Unit tests for hold_dataset_cache — engine integration and DuckDB paths."""

from __future__ import annotations

import pandas as pd
from unittest.mock import MagicMock

from mes_dashboard.services import hold_dataset_cache as cache_svc


class TestHoldEngineDecomposition:
    """hold-history with long date range triggers engine."""

    def test_long_range_triggers_engine(self, monkeypatch):
        """Long range → engine activated with a SINGLE whole-range chunk.

        ③-b fix: hold runs base_facts ONCE over the full range (one chunk) instead of
        decompose_by_time_range's 31-day chunks. Splitting would re-fetch every open
        hold per chunk and merge without dedup, inflating the on-hold count ~Nx.
        Pinned end-to-end in tests/test_hold_history_chunk_duplication.py.
        """
        import mes_dashboard.services.batch_query_engine as engine_mod

        engine_calls = {"execute": 0, "merge": 0}

        def fake_execute_plan(chunks, query_fn, **kwargs):
            engine_calls["execute"] += 1
            assert len(chunks) == 1  # whole-range single chunk (no time splitting)
            assert chunks[0]["chunk_start"] == "2025-01-01"
            assert chunks[0]["chunk_end"] == "2025-03-31"
            return kwargs.get("query_hash", "fake_hash")

        def fake_merge_chunks_to_spool(prefix, qhash, **kwargs):
            engine_calls["merge"] += 1
            return ("/tmp/fake_spool.parquet", 1)

        monkeypatch.setattr(engine_mod, "execute_plan", fake_execute_plan)
        monkeypatch.setattr(engine_mod, "merge_chunks_to_spool", fake_merge_chunks_to_spool)
        monkeypatch.setattr(cache_svc, "_has_cached_df", lambda _: False)
        monkeypatch.setattr(cache_svc, "_store_df", lambda *a, **kw: None)
        monkeypatch.setattr(cache_svc, "_load_sql", lambda name: "SELECT 1 FROM dual")
        monkeypatch.setattr(cache_svc, "register_spool_file", lambda *a, **kw: "/tmp/fake_spool.parquet")
        monkeypatch.setattr(cache_svc, "_store_query_dates", lambda *a, **kw: None)
        monkeypatch.setattr(
            cache_svc,
            "apply_view",
            lambda **kw: {
                "trend": {"days": []},
                "reason_pareto": {"items": []},
                "duration": {"items": []},
                "list": {"items": [], "pagination": {"page": 1, "perPage": 20, "total": 0, "totalPages": 1}},
                "_meta": {},
            },
        )

        result = cache_svc.execute_primary_query(
            start_date="2025-01-01",
            end_date="2025-03-31",
        )

        assert engine_calls["execute"] == 1
        assert engine_calls["merge"] == 1

    def test_short_range_skips_engine(self, monkeypatch):
        """30-day range → direct path, no engine."""
        engine_calls = {"execute": 0}

        monkeypatch.setattr(cache_svc, "_has_cached_df", lambda _: False)
        monkeypatch.setattr(cache_svc, "_load_sql", lambda name: "SELECT 1 FROM dual")
        monkeypatch.setattr(
            cache_svc,
            "read_sql_df",
            lambda sql, params, caller=None: pd.DataFrame({"CONTAINERID": ["C1"]}),
        )
        monkeypatch.setattr(cache_svc, "_store_df", lambda *a, **kw: None)
        monkeypatch.setattr(cache_svc, "_store_query_dates", lambda *a, **kw: None)
        monkeypatch.setattr(
            cache_svc,
            "apply_view",
            lambda **kw: {
                "trend": {"days": []},
                "reason_pareto": {"items": []},
                "duration": {"items": []},
                "list": {"items": [], "pagination": {"page": 1, "perPage": 20, "total": 0, "totalPages": 1}},
                "_meta": {},
            },
        )

        result = cache_svc.execute_primary_query(
            start_date="2025-06-01",
            end_date="2025-06-30",
        )

        assert engine_calls["execute"] == 0  # Engine NOT used


class TestHoldViewSqlDateResolution:
    """Ensure apply_view forwards query date bounds to SQL runtime."""

    def test_apply_view_uses_cached_query_dates_for_sql_runtime(self, monkeypatch):
        captured = {}

        def _fake_sql_runtime(**kwargs):
            captured.update(kwargs)
            return None, {"view_sql_fallback_reason": "hold_history_sql_spool_miss"}

        monkeypatch.setattr(
            "mes_dashboard.services.hold_history_sql_runtime.try_compute_view_from_spool",
            _fake_sql_runtime,
        )
        monkeypatch.setattr(
            cache_svc,
            "_get_query_dates",
            lambda _qid: {"start": "2026-03-01", "end": "2026-03-31"},
        )

        cache_svc.apply_view(query_id="qid-uses-cached-dates")

        assert captured.get("start_date") == "2026-03-01"
        assert captured.get("end_date") == "2026-03-31"

    def test_apply_view_explicit_dates_override_cached_dates(self, monkeypatch):
        captured = {}

        def _fake_sql_runtime(**kwargs):
            captured.update(kwargs)
            return None, {"view_sql_fallback_reason": "hold_history_sql_spool_miss"}

        monkeypatch.setattr(
            "mes_dashboard.services.hold_history_sql_runtime.try_compute_view_from_spool",
            _fake_sql_runtime,
        )
        monkeypatch.setattr(
            cache_svc,
            "_get_query_dates",
            lambda _qid: {"start": "2026-03-01", "end": "2026-03-31"},
        )

        cache_svc.apply_view(
            query_id="qid-explicit-dates",
            _start_date="2026-04-10",
            _end_date="2026-04-12",
        )

        assert captured.get("start_date") == "2026-04-10"
        assert captured.get("end_date") == "2026-04-12"

    def test_apply_view_sql_result_none_returns_none(self, monkeypatch):
        """apply_view returns None when DuckDB runtime returns no result (spool miss)."""
        monkeypatch.setattr(
            "mes_dashboard.services.hold_history_sql_runtime.try_compute_view_from_spool",
            lambda **_kwargs: (None, {"view_sql_fallback_reason": "spool_miss"}),
        )
        monkeypatch.setattr(
            cache_svc,
            "_get_query_dates",
            lambda _qid: {},
        )

        result = cache_svc.apply_view(query_id="hold-none-qid")
        assert result is None


class TestHoldStoreDf:
    """_store_df writes to spool and sets L1 marker."""

    def test_store_df_calls_store_spooled_df(self, monkeypatch):
        """_store_df calls store_spooled_df (spool-first, no redis large df)."""
        spool_calls = []

        monkeypatch.setattr(
            cache_svc,
            "store_spooled_df",
            lambda ns, qid, df, **kw: spool_calls.append((ns, qid)),
        )
        monkeypatch.setattr(cache_svc, "_dataset_cache", MagicMock())

        df = pd.DataFrame({"CONTAINERID": ["C1"]})
        cache_svc._store_df("qid-hold-spool", df)

        assert len(spool_calls) == 1
        assert spool_calls[0] == (cache_svc._REDIS_NAMESPACE, "qid-hold-spool")


class TestHoldBootstrapFailureSemantics:
    """Task 2.3: execute_primary_query must fail loudly when spool exists but apply_view returns None."""

    def _make_hold_env(self, monkeypatch, *, spool_created: bool, apply_view_result):
        """Patch execute_primary_query environment for short direct path."""
        import mes_dashboard.services.batch_query_engine as engine_mod
        # Force direct path regardless of BATCH_QUERY_TIME_THRESHOLD_DAYS env setting
        monkeypatch.setattr(engine_mod, "should_decompose_by_time", lambda *a: False)
        monkeypatch.setattr(cache_svc, "_has_cached_df", lambda _: False)
        monkeypatch.setattr(cache_svc, "_load_sql", lambda name: "SELECT 1 FROM dual")
        monkeypatch.setattr(cache_svc, "_store_query_dates", lambda *a, **kw: None)
        if spool_created:
            monkeypatch.setattr(
                cache_svc,
                "read_sql_df",
                lambda sql, params, caller=None: pd.DataFrame({"CONTAINERID": ["C1"]}),
            )
            monkeypatch.setattr(cache_svc, "_store_df", lambda *a, **kw: None)
        else:
            monkeypatch.setattr(
                cache_svc,
                "read_sql_df",
                lambda sql, params, caller=None: pd.DataFrame(),
            )
        monkeypatch.setattr(
            cache_svc,
            "apply_view",
            lambda **kw: apply_view_result,
        )

    def test_spool_created_apply_view_none_raises(self, monkeypatch):
        """When Oracle produces data (spool created) but apply_view fails → RuntimeError."""
        self._make_hold_env(monkeypatch, spool_created=True, apply_view_result=None)
        import pytest
        with pytest.raises(RuntimeError, match="bootstrap render failure"):
            cache_svc.execute_primary_query(
                start_date="2025-06-01",
                end_date="2025-06-30",
            )

    def test_no_spool_apply_view_none_returns_empty(self, monkeypatch):
        """When Oracle returns empty data (no spool) and apply_view fails → empty result, no raise."""
        self._make_hold_env(monkeypatch, spool_created=False, apply_view_result=None)
        result = cache_svc.execute_primary_query(
            start_date="2025-06-01",
            end_date="2025-06-30",
        )
        assert result["query_id"] is not None
        assert result["trend"] == {"days": []}
        assert result["list"]["pagination"]["total"] == 0

    def test_cache_hit_apply_view_none_raises(self, monkeypatch):
        """When spool exists (cache hit) but apply_view fails → RuntimeError."""
        monkeypatch.setattr(cache_svc, "_has_cached_df", lambda _: True)
        monkeypatch.setattr(cache_svc, "apply_view", lambda **kw: None)
        import pytest
        with pytest.raises(RuntimeError, match="bootstrap render failure"):
            cache_svc.execute_primary_query(
                start_date="2025-06-01",
                end_date="2025-06-30",
            )


# ============================================================
# Task 9.2: Hold engine parallel env var tests
# ============================================================

class TestHoldEngineParallel:
    """HOLD_ENGINE_PARALLEL env var controls execute_plan parallel for hold cache."""

    def _make_engine_env(self, monkeypatch, *, engine_calls):
        import mes_dashboard.services.batch_query_engine as engine_mod

        def fake_execute_plan(chunks, query_fn, **kwargs):
            engine_calls.append(kwargs.get("parallel"))
            return kwargs.get("query_hash", "fake_hash")

        monkeypatch.setattr(engine_mod, "execute_plan", fake_execute_plan)
        monkeypatch.setattr(engine_mod, "merge_chunks_to_spool", lambda *a, **kw: ("/tmp/f.parquet", 1))
        monkeypatch.setattr(engine_mod, "get_batch_progress", lambda *a: {})
        monkeypatch.setattr(cache_svc, "_has_cached_df", lambda _: False)
        monkeypatch.setattr(cache_svc, "_load_sql", lambda name: "SELECT 1 FROM dual")
        monkeypatch.setattr(cache_svc, "register_spool_file", lambda *a, **kw: None)
        monkeypatch.setattr(cache_svc, "_store_query_dates", lambda *a, **kw: None)
        monkeypatch.setattr(
            cache_svc,
            "apply_view",
            lambda **kw: {
                "trend": {"days": []},
                "reason_pareto": {"items": []},
                "duration": {"items": []},
                "list": {"items": [], "pagination": {"page": 1, "perPage": 20, "total": 0, "totalPages": 1}},
                "_meta": {},
            },
        )

    def test_default_parallel_is_1(self, monkeypatch):
        """Without HOLD_ENGINE_PARALLEL → execute_plan gets parallel=1."""
        engine_calls = []
        monkeypatch.setattr(cache_svc, "_HOLD_ENGINE_PARALLEL", 1)
        self._make_engine_env(monkeypatch, engine_calls=engine_calls)

        cache_svc.execute_primary_query(start_date="2025-01-01", end_date="2025-03-31")

        assert len(engine_calls) == 1
        assert engine_calls[0] == 1

    def test_parallel_2_passed_to_execute_plan(self, monkeypatch):
        """HOLD_ENGINE_PARALLEL=2 → execute_plan gets parallel=2."""
        engine_calls = []
        monkeypatch.setattr(cache_svc, "_HOLD_ENGINE_PARALLEL", 2)
        self._make_engine_env(monkeypatch, engine_calls=engine_calls)

        cache_svc.execute_primary_query(start_date="2025-01-01", end_date="2025-03-31")

        assert len(engine_calls) == 1
        assert engine_calls[0] == 2


# ============================================================
# Task 10.6: Hold partial failure propagation tests
# ============================================================

class TestHoldPartialFailure:
    """Hold partial failure propagates to result['_meta']['partial_failure']."""

    def _make_engine_env(self, monkeypatch, *, progress=None):
        import mes_dashboard.services.batch_query_engine as engine_mod

        monkeypatch.setattr(engine_mod, "execute_plan", lambda *a, **kw: kw.get("query_hash", "fake"))
        monkeypatch.setattr(engine_mod, "merge_chunks_to_spool", lambda *a, **kw: ("/tmp/f.parquet", 1))
        monkeypatch.setattr(engine_mod, "get_batch_progress", lambda *a: progress or {})
        monkeypatch.setattr(cache_svc, "_has_cached_df", lambda _: False)
        monkeypatch.setattr(cache_svc, "_load_sql", lambda name: "SELECT 1 FROM dual")
        monkeypatch.setattr(cache_svc, "register_spool_file", lambda *a, **kw: None)
        monkeypatch.setattr(cache_svc, "_store_query_dates", lambda *a, **kw: None)
        monkeypatch.setattr(
            cache_svc,
            "apply_view",
            lambda **kw: {
                "trend": {"days": []},
                "reason_pareto": {"items": []},
                "duration": {"items": []},
                "list": {"items": [], "pagination": {"page": 1, "perPage": 20, "total": 0, "totalPages": 1}},
                "_meta": {},
            },
        )

    def test_partial_failure_in_meta(self, monkeypatch):
        """Chunk partial failure → result._meta.partial_failure.has_partial_failure == True."""
        self._make_engine_env(
            monkeypatch,
            progress={"has_partial_failure": "True", "failed_chunk_count": "1", "failed_ranges": "2025-01-01~2025-01-31"},
        )

        result = cache_svc.execute_primary_query(start_date="2025-01-01", end_date="2025-03-31")

        assert result["_meta"]["partial_failure"]["has_partial_failure"] is True

    def test_no_partial_failure_no_meta_key(self, monkeypatch):
        """All chunks succeed → no partial_failure in _meta."""
        self._make_engine_env(monkeypatch)

        result = cache_svc.execute_primary_query(start_date="2025-01-01", end_date="2025-03-31")

        assert "partial_failure" not in result.get("_meta", {})


class TestDurationPayloadShape:
    """Verify duration payload always includes new avgReleasedHours/avgOnHoldHours/maxReleasedHours/maxOnHoldHours keys.

    These are computed from spool data at query time (not stored in spool), so we verify the
    DuckDB runtime path passes them through apply_view without dropping them.
    """

    def test_apply_view_preserves_duration_new_fields(self, monkeypatch):
        """apply_view result containing new duration fields is passed through unchanged."""
        import mes_dashboard.services.hold_dataset_cache as cache_svc

        expected_duration = {
            "items": [{"range": "<4h", "count": 2, "qty": 200, "pct": 100.0}],
            "avgReleasedHours": 2.5,
            "avgOnHoldHours": 48.0,
            "maxReleasedHours": 3.8,
            "maxOnHoldHours": 200.0,
        }

        def fake_try_compute(*, query_id, **kwargs):
            return {
                "trend": {"days": []},
                "reason_pareto": {"items": []},
                "duration": expected_duration,
                "list": {"items": [], "pagination": {"page": 1, "perPage": 20, "total": 0, "totalPages": 1}},
            }, {"view_sql_latency_s": 0.01}

        monkeypatch.setattr(
            "mes_dashboard.services.hold_history_sql_runtime.try_compute_view_from_spool",
            fake_try_compute,
        )

        result = cache_svc.apply_view(query_id="test-qid-123", hold_type="quality")

        dur = result["duration"]
        assert dur["avgReleasedHours"] == 2.5
        assert dur["avgOnHoldHours"] == 48.0
        assert dur["maxReleasedHours"] == 3.8
        assert dur["maxOnHoldHours"] == 200.0
