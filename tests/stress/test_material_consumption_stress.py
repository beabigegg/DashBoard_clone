# -*- coding: utf-8 -*-
"""Tier 3 nightly stress tests for material-consumption service.

Tests aggregate performance and concurrent granularity-switch behavior.
Run with: pytest tests/stress/test_material_consumption_stress.py -v --run-stress

Marks: @pytest.mark.stress (Tier 3 nightly — NOT pre-merge per CLAUDE.md).
"""

from __future__ import annotations

import datetime
import time
from unittest.mock import patch

import pandas as pd
import pytest


def _large_summary_df(n_rows: int = 100_000) -> pd.DataFrame:
    """Build a large summary spool fixture for performance testing."""
    import numpy as np

    rng = np.random.default_rng(42)
    base_date = datetime.date(2025, 1, 1)
    dates = [base_date + datetime.timedelta(days=int(d)) for d in rng.integers(0, 365, n_rows)]
    parts = [f"MAT-{i % 20:03d}" for i in range(n_rows)]
    pj_types = [f"Type{chr(65 + (i % 4))}" for i in range(n_rows)]
    cats = [f"Cat{i % 5}" for i in range(n_rows)]
    return pd.DataFrame({
        "txn_date": dates,
        "material_part": parts,
        "pj_type": pj_types,
        "primary_category": cats,
        "total_consumed": rng.uniform(10, 1000, n_rows).astype(float),
        "total_required": rng.uniform(10, 1200, n_rows).astype(float),
        "lot_count": rng.integers(1, 50, n_rows).astype(int),
        "workorder_count": rng.integers(1, 20, n_rows).astype(int),
    })


@pytest.mark.stress
def test_summary_aggregate_large_table_under_5s(tmp_path):
    """Granularity regroup on 100k-row spool must complete under 5s (MC-01)."""
    import mes_dashboard.services.material_consumption_duckdb_runtime as rt

    df = _large_summary_df(100_000)
    spool_path = tmp_path / "stress_summary.parquet"
    df.to_parquet(str(spool_path), engine="pyarrow", index=False)

    start = time.monotonic()
    for granularity in ("week", "month", "quarter"):
        result = rt.regroup_summary(str(spool_path), granularity=granularity)
        assert "trend" in result, f"Missing trend for {granularity}"
    elapsed = time.monotonic() - start

    assert elapsed < 5.0, (
        f"Granularity regroup on 100k rows took {elapsed:.2f}s — must be < 5s (MC-01). "
        f"If this consistently fails, the Oracle query needs date-range narrowing."
    )


@pytest.mark.stress
def test_concurrent_granularity_switches_cache_only(tmp_path):
    """Concurrent granularity switches from spool should not race-fail."""
    import concurrent.futures
    import mes_dashboard.services.material_consumption_duckdb_runtime as rt

    df = _large_summary_df(50_000)
    spool_path = tmp_path / "concurrent_summary.parquet"
    df.to_parquet(str(spool_path), engine="pyarrow", index=False)

    granularities = ["week", "month", "quarter", "week", "month"]
    errors = []

    def _do_regroup(gran):
        try:
            result = rt.regroup_summary(str(spool_path), granularity=gran)
            if "trend" not in result:
                return f"Missing trend for {gran}"
        except Exception as exc:
            return str(exc)
        return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        futs = [pool.submit(_do_regroup, g) for g in granularities]
        for fut in concurrent.futures.as_completed(futs):
            err = fut.result()
            if err:
                errors.append(err)

    assert not errors, f"Concurrent granularity switch errors: {errors}"
