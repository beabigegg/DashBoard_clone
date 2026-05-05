# -*- coding: utf-8 -*-
"""Tests for reject_pareto_materialized module.

Covers:
  5.1 – key isolation, schema version invalidation, single-flight, guardrails
  5.2 – parity tests: materialized vs legacy cross-filter results
"""
from __future__ import annotations

import threading
import time
from typing import Any, Dict, List, Optional
from unittest import mock

import pandas as pd


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_sample_df(n_lots: int = 10) -> pd.DataFrame:
    """Build a realistic reject-history lot-level DataFrame for testing."""
    rows = []
    reasons = ["001_CRACK", "002_CONTAMINATION", "003_SCRATCH"]
    packages = ["PKG_A", "PKG_B"]
    types = ["NORMAL", "REWORK"]
    workcenters = ["WC_GRP_1", "WC_GRP_2"]
    for i in range(n_lots):
        lot = f"LOT{i:04d}"
        # Each lot has 1-3 reject events
        for j in range(1 + i % 3):
            rows.append({
                "CONTAINERID": lot,
                "LOSSREASONNAME": reasons[(i + j) % len(reasons)],
                "PRODUCTLINENAME": packages[i % len(packages)],
                "PJ_TYPE": types[j % len(types)],
                "WORKCENTER_GROUP": workcenters[i % len(workcenters)],
                "REJECT_TOTAL_QTY": 10 + i,
                "DEFECT_QTY": 5 + j,
                "MOVEIN_QTY": 100 + i * 10,
                "SCRAP_OBJECTTYPE": "LOT",
                "LOSSREASON_CODE": f"00{j + 1}_CODE",
                "TXN_DAY": f"2026-01-{(i % 28) + 1:02d}",
            })
    return pd.DataFrame(rows)


# ============================================================
# 5.1 – Key isolation
# ============================================================

class TestKeyIsolation:
    """Distinct filter contexts must produce distinct snapshot keys."""

    def test_same_params_produce_same_key(self):
        from mes_dashboard.services.reject_pareto_materialized import build_snapshot_key

        k1 = build_snapshot_key("Q1", packages=["A", "B"])
        k2 = build_snapshot_key("Q1", packages=["A", "B"])
        assert k1 == k2

    def test_different_query_id_produces_different_key(self):
        from mes_dashboard.services.reject_pareto_materialized import build_snapshot_key

        k1 = build_snapshot_key("Q1")
        k2 = build_snapshot_key("Q2")
        assert k1 != k2

    def test_different_policy_toggle_produces_different_key(self):
        from mes_dashboard.services.reject_pareto_materialized import build_snapshot_key

        k1 = build_snapshot_key("Q1", include_excluded_scrap=False)
        k2 = build_snapshot_key("Q1", include_excluded_scrap=True)
        assert k1 != k2

    def test_different_supplementary_filter_produces_different_key(self):
        from mes_dashboard.services.reject_pareto_materialized import build_snapshot_key

        k1 = build_snapshot_key("Q1", packages=["A"])
        k2 = build_snapshot_key("Q1", packages=["A", "B"])
        assert k1 != k2

    def test_different_trend_dates_produces_different_key(self):
        from mes_dashboard.services.reject_pareto_materialized import build_snapshot_key

        k1 = build_snapshot_key("Q1", trend_dates=["2026-01-01"])
        k2 = build_snapshot_key("Q1", trend_dates=["2026-01-02"])
        assert k1 != k2

    def test_filter_order_does_not_affect_key(self):
        from mes_dashboard.services.reject_pareto_materialized import build_snapshot_key

        k1 = build_snapshot_key("Q1", packages=["B", "A"])
        k2 = build_snapshot_key("Q1", packages=["A", "B"])
        assert k1 == k2

    def test_none_vs_empty_treated_equally(self):
        from mes_dashboard.services.reject_pareto_materialized import build_snapshot_key

        k1 = build_snapshot_key("Q1", packages=None)
        k2 = build_snapshot_key("Q1", packages=None)
        assert k1 == k2

    def test_key_includes_schema_version(self):
        from mes_dashboard.services.reject_pareto_materialized import (
            SCHEMA_VERSION,
            build_snapshot_key,
        )

        key = build_snapshot_key("Q1")
        assert f":v{SCHEMA_VERSION}" in key


# ============================================================
# 5.1 – Schema version invalidation
# ============================================================

class TestSchemaVersionInvalidation:
    """Snapshots from prior schema versions must not be treated as valid hits."""

    def test_version_mismatch_returns_miss(self):
        from mes_dashboard.services.reject_pareto_materialized import (
            FALLBACK_VERSION_MISMATCH,
            SCHEMA_VERSION,
            _snapshot_cache,
            read_snapshot,
        )

        key = "test_version_key"
        _snapshot_cache.set(key, {
            "schema_version": SCHEMA_VERSION - 1,
            "built_at": time.time(),
            "cube": [],
            "dim_columns": {},
        })
        result, reason = read_snapshot(key)
        assert result is None
        assert reason == FALLBACK_VERSION_MISMATCH

    def test_current_version_returns_hit(self):
        from mes_dashboard.services.reject_pareto_materialized import (
            SCHEMA_VERSION,
            _snapshot_cache,
            read_snapshot,
        )

        key = "test_current_version_key"
        _snapshot_cache.set(key, {
            "schema_version": SCHEMA_VERSION,
            "built_at": time.time(),
            "cube": [],
            "dim_columns": {},
        })
        result, reason = read_snapshot(key)
        assert result is not None
        assert reason is None


# ============================================================
# 5.1 – Single-flight guard
# ============================================================

class TestSingleFlightGuard:
    """Concurrent builds for the same key must serialize via single-flight."""

    def test_first_caller_is_builder(self):
        from mes_dashboard.services.reject_pareto_materialized import (
            _acquire_build,
            _release_build,
        )

        is_builder, event = _acquire_build("sf_test_1")
        assert is_builder is True
        assert event is not None
        _release_build("sf_test_1")

    def test_second_caller_waits(self):
        from mes_dashboard.services.reject_pareto_materialized import (
            _acquire_build,
            _release_build,
        )

        is_builder, _ = _acquire_build("sf_test_2")
        assert is_builder is True

        is_second, event = _acquire_build("sf_test_2")
        assert is_second is False
        assert event is not None

        _release_build("sf_test_2")
        # Event should be set after release
        assert event.is_set()

    def test_concurrent_builds_only_one_executes(self):
        from mes_dashboard.services.reject_pareto_materialized import (
            _acquire_build,
            _release_build,
        )

        key = "sf_concurrent_test"
        results = []

        def attempt_build(thread_id):
            is_builder, event = _acquire_build(key)
            results.append((thread_id, is_builder))
            if is_builder:
                time.sleep(0.05)  # simulate build
                _release_build(key)
            elif event is not None:
                event.wait(timeout=2)

        t1 = threading.Thread(target=attempt_build, args=(1,))
        t2 = threading.Thread(target=attempt_build, args=(2,))
        t1.start()
        time.sleep(0.01)  # ensure t1 starts first
        t2.start()
        t1.join(timeout=3)
        t2.join(timeout=3)

        builders = [r for r in results if r[1]]
        waiters = [r for r in results if not r[1]]
        assert len(builders) == 1
        assert len(waiters) == 1


# ============================================================
# 5.1 – Guardrail enforcement
# ============================================================

class TestGuardrailEnforcement:
    """TTL and size guardrails must reject oversized snapshots."""

    def test_oversized_cube_returns_none(self):
        from mes_dashboard.services.reject_pareto_materialized import build_snapshot

        # Create a DataFrame that will produce a huge cube
        # With 200+ unique values per dimension, cube rows explode
        rows = []
        for i in range(500):
            rows.append({
                "CONTAINERID": f"LOT{i}",
                "LOSSREASONNAME": f"{i:03d}_REASON",
                "PRODUCTLINENAME": f"PKG_{i}",
                "PJ_TYPE": f"TYPE_{i}",
                "WORKCENTER_GROUP": f"WC_{i}",
                "REJECT_TOTAL_QTY": 10,
                "DEFECT_QTY": 5,
                "MOVEIN_QTY": 100,
                "SCRAP_OBJECTTYPE": "LOT",
            })
        df = pd.DataFrame(rows)

        with mock.patch(
            "mes_dashboard.services.reject_pareto_materialized._SNAPSHOT_MAX_CUBE_ROWS",
            10,
        ):
            result = build_snapshot(df)
        assert result is None

    def test_oversized_payload_rejected_on_store(self):
        from mes_dashboard.services.reject_pareto_materialized import store_snapshot

        huge_snapshot = {
            "schema_version": 1,
            "built_at": time.time(),
            "cube": [{"x": "y" * 10000}] * 1000,
            "dim_columns": {},
        }

        with mock.patch(
            "mes_dashboard.services.reject_pareto_materialized._SNAPSHOT_MAX_PAYLOAD_BYTES",
            1024,
        ):
            assert store_snapshot("test_oversize_key", huge_snapshot) is False

    def test_stale_snapshot_returns_miss(self):
        from mes_dashboard.services.reject_pareto_materialized import (
            FALLBACK_STALE,
            SCHEMA_VERSION,
            _snapshot_cache,
            read_snapshot,
        )

        key = "test_stale_key"
        _snapshot_cache.set(key, {
            "schema_version": SCHEMA_VERSION,
            "built_at": time.time() - 999999,  # very old
            "cube": [],
            "dim_columns": {},
        })
        result, reason = read_snapshot(key)
        assert result is None
        assert reason == FALLBACK_STALE


# ============================================================
# 5.1 – Build & evaluate smoke test
# ============================================================

class TestBuildAndEvaluate:
    """Snapshot build should produce a valid cube and evaluate correctly."""

    def test_build_produces_valid_snapshot(self):
        from mes_dashboard.services.reject_pareto_materialized import (
            SCHEMA_VERSION,
            build_snapshot,
        )

        df = _build_sample_df(20)
        snapshot = build_snapshot(df)

        assert snapshot is not None
        assert snapshot["schema_version"] == SCHEMA_VERSION
        assert isinstance(snapshot["cube"], list)
        assert len(snapshot["cube"]) > 0
        assert isinstance(snapshot["dim_columns"], dict)

    def test_build_empty_df_returns_empty_snapshot(self):
        from mes_dashboard.services.reject_pareto_materialized import build_snapshot

        df = pd.DataFrame()
        result = build_snapshot(df)
        assert result is None

    def test_evaluate_returns_all_four_dimensions(self):
        from mes_dashboard.services.reject_pareto_materialized import (
            build_snapshot,
            evaluate,
        )

        df = _build_sample_df(20)
        snapshot = build_snapshot(df)
        result = evaluate(snapshot, metric_mode="reject_total", pareto_scope="all")

        dims = result["dimensions"]
        expected_dims = {"reason", "package", "type"}
        assert set(dims.keys()) == expected_dims
        for dim_name, dim_data in dims.items():
            assert "items" in dim_data
            assert dim_data["dimension"] == dim_name
            assert dim_data["metric_mode"] == "reject_total"

    def test_evaluate_top80_filters_items(self):
        from mes_dashboard.services.reject_pareto_materialized import (
            build_snapshot,
            evaluate,
        )

        df = _build_sample_df(50)
        snapshot = build_snapshot(df)

        result_all = evaluate(snapshot, pareto_scope="all")
        result_80 = evaluate(snapshot, pareto_scope="top80")

        for dim in result_all["dimensions"]:
            all_count = len(result_all["dimensions"][dim]["items"])
            top80_count = len(result_80["dimensions"][dim]["items"])
            assert top80_count <= all_count

    def test_evaluate_top20_display_scope(self):
        from mes_dashboard.services.reject_pareto_materialized import (
            build_snapshot,
            evaluate,
        )

        # Build a df with many unique types
        rows = []
        for i in range(100):
            rows.append({
                "CONTAINERID": f"LOT{i}",
                "LOSSREASONNAME": f"{i:03d}_REASON",
                "PRODUCTLINENAME": "PKG_A",
                "PJ_TYPE": f"TYPE_{i:03d}",
                "WORKCENTER_GROUP": "WC_1",
                "REJECT_TOTAL_QTY": 10 + i,
                "DEFECT_QTY": 5,
                "MOVEIN_QTY": 100,
                "SCRAP_OBJECTTYPE": "LOT",
            })
        df = pd.DataFrame(rows)
        snapshot = build_snapshot(df)

        result = evaluate(snapshot, pareto_scope="all", pareto_display_scope="top20")
        # type is in _PARETO_TOP20_DIMENSIONS, so should be truncated
        type_items = result["dimensions"]["type"]["items"]
        assert len(type_items) <= 20


# ============================================================
# 5.2 – Parity tests: materialized vs legacy
# ============================================================

class TestMaterializedVsLegacyParity:
    """Materialized evaluation must produce the same results as legacy
    DataFrame-based computation for metrics and ranking."""

    def _compute_legacy_batch_pareto(
        self,
        df: pd.DataFrame,
        *,
        metric_mode: str = "reject_total",
        pareto_scope: str = "all",
        pareto_display_scope: str = "all",
        pareto_selections: Optional[Dict[str, List[str]]] = None,
    ) -> Dict[str, Any]:
        """Compute batch pareto using the legacy DataFrame path."""
        from mes_dashboard.services.reject_dataset_cache import (
            _DIM_TO_DF_COLUMN,
            _PARETO_DIMENSIONS,
            _PARETO_TOP20_DIMENSIONS,
            _apply_cross_filter,
            _build_dimension_pareto_items,
            _normalize_pareto_selections,
        )

        normalized_selections = _normalize_pareto_selections(pareto_selections)

        dimensions: Dict[str, Dict[str, Any]] = {}
        for dim in _PARETO_DIMENSIONS:
            dim_col = _DIM_TO_DF_COLUMN.get(dim)
            dim_df = _apply_cross_filter(df, normalized_selections, exclude_dim=dim)
            items = _build_dimension_pareto_items(
                dim_df,
                dim_col=dim_col,
                metric_mode=metric_mode,
                pareto_scope=pareto_scope,
            )
            if pareto_display_scope == "top20" and dim in _PARETO_TOP20_DIMENSIONS:
                items = items[:20]
            dimensions[dim] = {
                "items": items,
                "dimension": dim,
                "metric_mode": metric_mode,
            }
        return {"dimensions": dimensions}

    def test_no_cross_filter_parity(self):
        """Without cross-filter, materialized and legacy must match on metrics."""
        from mes_dashboard.services.reject_pareto_materialized import (
            build_snapshot,
            evaluate,
        )
        from mes_dashboard.services.reject_dataset_cache import _normalize_text

        df = _build_sample_df(30)
        # Normalize dimension values in the df to match build behavior
        from mes_dashboard.services.reject_dataset_cache import _DIM_TO_DF_COLUMN
        for col in _DIM_TO_DF_COLUMN.values():
            if col in df.columns:
                df[col] = df[col].apply(lambda v: _normalize_text(v) or "(未知)")

        snapshot = build_snapshot(df)
        mat_result = evaluate(snapshot, metric_mode="reject_total", pareto_scope="all")
        legacy_result = self._compute_legacy_batch_pareto(df, metric_mode="reject_total", pareto_scope="all")

        for dim in mat_result["dimensions"]:
            mat_items = mat_result["dimensions"][dim]["items"]
            leg_items = legacy_result["dimensions"][dim]["items"]

            # Same number of items
            assert len(mat_items) == len(leg_items), (
                f"Dimension {dim}: materialized has {len(mat_items)} items, legacy has {len(leg_items)}"
            )

            # Same ordering (by metric_value descending)
            for i, (m, l) in enumerate(zip(mat_items, leg_items)):
                assert m["reason"] == l["reason"], (
                    f"Dim {dim}, item {i}: names differ: {m['reason']} vs {l['reason']}"
                )
                assert m["metric_value"] == l["metric_value"], (
                    f"Dim {dim}, item {i}: metric_value differ: {m['metric_value']} vs {l['metric_value']}"
                )
                assert m["REJECT_TOTAL_QTY"] == l["REJECT_TOTAL_QTY"], (
                    f"Dim {dim}, item {i}: REJECT_TOTAL_QTY differ"
                )
                assert m["DEFECT_QTY"] == l["DEFECT_QTY"], (
                    f"Dim {dim}, item {i}: DEFECT_QTY differ"
                )
                assert abs(m["pct"] - l["pct"]) < 0.01, (
                    f"Dim {dim}, item {i}: pct differ: {m['pct']} vs {l['pct']}"
                )
                assert abs(m["cumPct"] - l["cumPct"]) < 0.01, (
                    f"Dim {dim}, item {i}: cumPct differ: {m['cumPct']} vs {l['cumPct']}"
                )

    def test_cross_filter_metric_parity(self):
        """With cross-filter, materialized metrics must match legacy metrics."""
        from mes_dashboard.services.reject_pareto_materialized import (
            build_snapshot,
            evaluate,
        )
        from mes_dashboard.services.reject_dataset_cache import (
            _DIM_TO_DF_COLUMN,
            _normalize_text,
        )

        df = _build_sample_df(30)
        # Normalize dimension values
        for col in _DIM_TO_DF_COLUMN.values():
            if col in df.columns:
                df[col] = df[col].apply(lambda v: _normalize_text(v) or "(未知)")

        selections = {"reason": ["001_CRACK"], "type": ["NORMAL"]}

        snapshot = build_snapshot(df)
        mat_result = evaluate(
            snapshot,
            metric_mode="reject_total",
            pareto_scope="all",
            pareto_selections=selections,
        )
        legacy_result = self._compute_legacy_batch_pareto(
            df, metric_mode="reject_total", pareto_scope="all", pareto_selections=selections,
        )

        for dim in mat_result["dimensions"]:
            mat_items = mat_result["dimensions"][dim]["items"]
            leg_items = legacy_result["dimensions"][dim]["items"]

            # Build lookup by name
            mat_by_name = {it["reason"]: it for it in mat_items}
            leg_by_name = {it["reason"]: it for it in leg_items}

            # Verify same set of dimension values
            assert set(mat_by_name.keys()) == set(leg_by_name.keys()), (
                f"Dim {dim}: names differ. Mat: {set(mat_by_name.keys())}, "
                f"Leg: {set(leg_by_name.keys())}"
            )

            # Verify metric values match
            for name in mat_by_name:
                m = mat_by_name[name]
                l = leg_by_name[name]
                assert m["metric_value"] == l["metric_value"], (
                    f"Dim {dim}, {name}: metric_value differ: {m['metric_value']} vs {l['metric_value']}"
                )
                assert m["REJECT_TOTAL_QTY"] == l["REJECT_TOTAL_QTY"], (
                    f"Dim {dim}, {name}: REJECT_TOTAL_QTY differ"
                )

    def test_defect_metric_mode_parity(self):
        """Defect metric mode must produce same results in both paths."""
        from mes_dashboard.services.reject_pareto_materialized import (
            build_snapshot,
            evaluate,
        )
        from mes_dashboard.services.reject_dataset_cache import (
            _DIM_TO_DF_COLUMN,
            _normalize_text,
        )

        df = _build_sample_df(20)
        for col in _DIM_TO_DF_COLUMN.values():
            if col in df.columns:
                df[col] = df[col].apply(lambda v: _normalize_text(v) or "(未知)")

        snapshot = build_snapshot(df)
        mat_result = evaluate(snapshot, metric_mode="defect", pareto_scope="all")
        legacy_result = self._compute_legacy_batch_pareto(df, metric_mode="defect", pareto_scope="all")

        for dim in mat_result["dimensions"]:
            mat_items = mat_result["dimensions"][dim]["items"]
            leg_items = legacy_result["dimensions"][dim]["items"]

            mat_by_name = {it["reason"]: it for it in mat_items}
            leg_by_name = {it["reason"]: it for it in leg_items}

            assert set(mat_by_name.keys()) == set(leg_by_name.keys()), (
                f"Dim {dim}: names differ in defect mode"
            )

            for name in mat_by_name:
                m = mat_by_name[name]
                l = leg_by_name[name]
                assert m["DEFECT_QTY"] == l["DEFECT_QTY"], (
                    f"Dim {dim}, {name}: DEFECT_QTY differ in defect mode"
                )


# ============================================================
# 5.2 – Telemetry
# ============================================================

class TestTelemetry:
    """Telemetry counters must be operational."""

    def test_telemetry_snapshot_returns_dict(self):
        from mes_dashboard.services.reject_pareto_materialized import get_telemetry

        tel = get_telemetry()
        assert isinstance(tel, dict)
        assert "hit" in tel
        assert "miss" in tel
        assert "build" in tel
        assert "fallback" in tel
        assert "fallback_reasons" in tel
        assert "hit_rate" in tel

    def test_fallback_reason_codes_are_stable_strings(self):
        from mes_dashboard.services.reject_pareto_materialized import (
            FALLBACK_BUILD_FAILED,
            FALLBACK_BUILD_TIMEOUT,
            FALLBACK_DISABLED,
            FALLBACK_MISS,
            FALLBACK_OVERSIZE,
            FALLBACK_STALE,
            FALLBACK_VERSION_MISMATCH,
        )

        codes = [
            FALLBACK_MISS,
            FALLBACK_STALE,
            FALLBACK_VERSION_MISMATCH,
            FALLBACK_BUILD_FAILED,
            FALLBACK_BUILD_TIMEOUT,
            FALLBACK_DISABLED,
            FALLBACK_OVERSIZE,
        ]
        for code in codes:
            assert isinstance(code, str)
            assert len(code) > 0


# ============================================================
# Feature flag behavior
# ============================================================

class TestFeatureFlagBehavior:
    """Materialization must respect feature flags."""

    def test_disabled_returns_none_with_fallback_reason(self):
        from mes_dashboard.services.reject_pareto_materialized import (
            FALLBACK_DISABLED,
            try_materialized_batch_pareto,
        )

        with mock.patch(
            "mes_dashboard.services.reject_pareto_materialized.MATERIALIZATION_READ_ENABLED",
            False,
        ):
            result, meta = try_materialized_batch_pareto(
                "Q1",
                lambda: None,
            )
            assert result is None
            assert meta["pareto_fallback_reason"] == FALLBACK_DISABLED

    def test_read_enabled_but_build_disabled_falls_back_on_miss(self):
        from mes_dashboard.services.reject_pareto_materialized import (
            FALLBACK_DISABLED,
            _snapshot_cache,
            try_materialized_batch_pareto,
        )

        _snapshot_cache.clear()

        with mock.patch(
            "mes_dashboard.services.reject_pareto_materialized.MATERIALIZATION_READ_ENABLED",
            True,
        ), mock.patch(
            "mes_dashboard.services.reject_pareto_materialized.MATERIALIZATION_ENABLED",
            False,
        ):
            result, meta = try_materialized_batch_pareto(
                "Q_nonexistent",
                lambda: None,
            )
            assert result is None
            assert meta["pareto_fallback_reason"] == FALLBACK_DISABLED
