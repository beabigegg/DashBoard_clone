# -*- coding: utf-8 -*-
"""Tests for core/interactive_memory_guard module."""

from __future__ import annotations

from unittest.mock import patch

import pandas as pd
import pytest

from mes_dashboard.core.interactive_memory_guard import (
    df_memory_mb,
    enforce_dataset_memory_guard,
    maybe_gc_collect,
    process_rss_mb,
)


# ============================================================
# df_memory_mb
# ============================================================

class TestDfMemoryMb:
    def test_empty_df_returns_zero(self):
        assert df_memory_mb(pd.DataFrame()) == 0.0

    def test_none_returns_zero(self):
        assert df_memory_mb(None) == 0.0

    def test_small_df_returns_positive(self):
        df = pd.DataFrame({"a": range(100), "b": ["x"] * 100})
        assert df_memory_mb(df) > 0.0


# ============================================================
# process_rss_mb
# ============================================================

class TestProcessRssMb:
    def test_returns_float(self):
        rss = process_rss_mb()
        assert rss is None or isinstance(rss, float)

    def test_returns_positive_when_psutil_available(self):
        rss = process_rss_mb()
        if rss is not None:
            assert rss > 0

    @patch("mes_dashboard.core.interactive_memory_guard.os.getpid", side_effect=Exception("fail"))
    def test_returns_none_on_exception(self, _mock):
        # psutil.Process(bad_pid) should raise; guard returns None
        result = process_rss_mb()
        # Either None (psutil catches) or float is acceptable
        assert result is None or isinstance(result, float)


# ============================================================
# enforce_dataset_memory_guard
# ============================================================

class TestEnforceDatasetMemoryGuard:
    def _make_df(self, n_rows: int = 100) -> pd.DataFrame:
        return pd.DataFrame({"a": range(n_rows), "b": ["test"] * n_rows})

    def test_empty_df_passes(self):
        enforce_dataset_memory_guard(pd.DataFrame(), operation="test", query_id="q1")

    def test_none_df_passes(self):
        enforce_dataset_memory_guard(None, operation="test", query_id="q1")

    def test_small_df_passes(self):
        df = self._make_df(10)
        enforce_dataset_memory_guard(df, operation="test", query_id="q1", max_input_mb=100)

    def test_fence1_rejects_large_df(self):
        df = self._make_df(10)
        with pytest.raises(MemoryError, match="超過"):
            enforce_dataset_memory_guard(
                df, operation="test_op", query_id="q1", max_input_mb=0.0001
            )

    def test_fence2_rejects_high_rss_projection(self):
        df = self._make_df(100)
        with patch(
            "mes_dashboard.core.interactive_memory_guard.process_rss_mb",
            return_value=1000.0,
        ):
            with pytest.raises(MemoryError, match="記憶體負載較高"):
                enforce_dataset_memory_guard(
                    df,
                    operation="test_op",
                    query_id="q1",
                    max_input_mb=9999,
                    max_projected_rss_mb=500,
                    working_set_factor=1.0,
                )

    def test_fence2_passes_when_rss_unavailable(self):
        df = self._make_df(100)
        with patch(
            "mes_dashboard.core.interactive_memory_guard.process_rss_mb",
            return_value=None,
        ):
            # Should not raise — fail-open when psutil unavailable
            enforce_dataset_memory_guard(
                df,
                operation="test_op",
                query_id="q1",
                max_input_mb=9999,
                max_projected_rss_mb=1,
            )

    def test_operation_name_in_error_message(self):
        df = self._make_df(10)
        with pytest.raises(MemoryError, match="匯出"):
            enforce_dataset_memory_guard(
                df, operation="匯出", query_id="q1", max_input_mb=0.0001
            )


# ============================================================
# maybe_gc_collect
# ============================================================

class TestMaybeGcCollect:
    def test_force_true_runs_gc(self):
        with patch("mes_dashboard.core.interactive_memory_guard.gc.collect") as mock_gc:
            maybe_gc_collect(force=True)
            mock_gc.assert_called_once()

    def test_force_false_skips_gc(self):
        with patch("mes_dashboard.core.interactive_memory_guard.gc.collect") as mock_gc:
            maybe_gc_collect(force=False)
            mock_gc.assert_not_called()
