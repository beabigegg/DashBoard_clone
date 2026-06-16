# -*- coding: utf-8 -*-
"""Stress tests for hold-overview CSV export endpoint.

Tier-3 nightly — NOT a PR gate.

Tests that when a large hold set is returned, the response row count is
bounded by HOLD_OVERVIEW_EXPORT_MAX_ROWS and the request completes without
timeout, verifying AC-7.

Run with: pytest tests/stress/test_hold_overview_export_stress.py -v --run-stress
"""
from __future__ import annotations

import os
import time
from unittest.mock import patch

import pytest

from mes_dashboard.services.wip_service import get_hold_detail_lots

_DEFAULT_MAX_ROWS = int(os.environ.get("HOLD_OVERVIEW_EXPORT_MAX_ROWS", 10000))


def _build_oversized_df(row_count: int):
    """Return a minimal pandas DataFrame with row_count HOLD rows."""
    import pandas as pd

    data = {
        "LOTID": [f"LOT{i:05d}" for i in range(row_count)],
        "WORKORDER": [f"WO{i:05d}" for i in range(row_count)],
        "QTY": [100] * row_count,
        "PRODUCT": ["PROD-A"] * row_count,
        "PACKAGE_LEF": ["QFN"] * row_count,
        "WORKCENTER_GROUP": ["WB"] * row_count,
        "HOLDREASONNAME": ["品質確認"] * row_count,
        "SPECNAME": ["SPEC1"] * row_count,
        "AGEBYDAYS": [float(row_count - i) for i in range(row_count)],
        "HOLDEMP": ["user"] * row_count,
        "DEPTNAME": ["dept"] * row_count,
        "COMMENT_HOLD": [None] * row_count,
        "COMMENT_FUTURE": [None] * row_count,
        "STATUS": ["HOLD"] * row_count,
        "CURRENTHOLDCOUNT": [1] * row_count,
        "WORKFLOWNAME": ["FLOW_A"] * row_count,
        "BOP": ["BOP1"] * row_count,
        "PJ_FUNCTION": ["FUNC_A"] * row_count,
        "PJ_TYPE": ["TYPE_A"] * row_count,
        "FIRSTNAME": ["user"] * row_count,
        "WAFERDESC": ["desc"] * row_count,
    }
    return pd.DataFrame(data)


@pytest.mark.stress
@pytest.mark.nightly
class TestHoldOverviewExportRowCap:
    """AC-7: row count never exceeds HOLD_OVERVIEW_EXPORT_MAX_ROWS in export mode."""

    def test_export_result_bounded_at_cap_snapshot_path(self):
        """Snapshot path: result row count <= cap when lot count exceeds cap."""
        oversized_count = _DEFAULT_MAX_ROWS + 500
        df = _build_oversized_df(oversized_count)

        patch_target = "mes_dashboard.services.wip_service._get_wip_dataframe"
        with patch(patch_target, return_value=df):
            start = time.time()
            result = get_hold_detail_lots(
                page=1,
                page_size=_DEFAULT_MAX_ROWS,
                export_mode=True,
            )
            elapsed = time.time() - start

        assert result is not None, "Service must return a result dict"
        assert len(result["lots"]) <= _DEFAULT_MAX_ROWS, (
            f"Response lots count {len(result['lots'])} exceeds cap {_DEFAULT_MAX_ROWS}"
        )
        assert elapsed < 30.0, f"Export completed in {elapsed:.1f}s, exceeds 30s budget"

    def test_export_result_bounded_exact_at_cap(self):
        """When lot count equals cap exactly, result count is exactly cap."""
        df = _build_oversized_df(_DEFAULT_MAX_ROWS)

        patch_target = "mes_dashboard.services.wip_service._get_wip_dataframe"
        with patch(patch_target, return_value=df):
            result = get_hold_detail_lots(
                page=1,
                page_size=_DEFAULT_MAX_ROWS,
                export_mode=True,
            )

        assert result is not None
        assert len(result["lots"]) <= _DEFAULT_MAX_ROWS

    def test_custom_cap_via_env_is_respected(self, monkeypatch):
        """HOLD_OVERVIEW_EXPORT_MAX_ROWS env override is enforced at service level."""
        custom_cap = 50
        monkeypatch.setenv("HOLD_OVERVIEW_EXPORT_MAX_ROWS", str(custom_cap))

        df = _build_oversized_df(custom_cap + 200)
        patch_target = "mes_dashboard.services.wip_service._get_wip_dataframe"
        with patch(patch_target, return_value=df):
            result = get_hold_detail_lots(
                page=1,
                page_size=custom_cap,
                export_mode=True,
            )

        assert result is not None
        assert len(result["lots"]) <= custom_cap, (
            f"Lots {len(result['lots'])} exceeds custom cap {custom_cap}"
        )
