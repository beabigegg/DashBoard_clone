# -*- coding: utf-8 -*-
"""Unit tests for reject_dataset_cache helpers."""

from __future__ import annotations

import pandas as pd
import pytest

from mes_dashboard.services import reject_dataset_cache as cache_svc


def test_compute_dimension_pareto_applies_policy_filters_before_grouping(monkeypatch):
    """Cached pareto should honor the same policy toggles as view/query paths."""
    df = pd.DataFrame(
        [
            {
                "CONTAINERID": "C1",
                "LOSSREASONNAME": "001_A",
                "LOSSREASON_CODE": "001_A",
                "SCRAP_OBJECTTYPE": "MATERIAL",
                "PRODUCTLINENAME": "(NA)",
                "WORKCENTER_GROUP": "WB",
                "REJECT_TOTAL_QTY": 100,
                "DEFECT_QTY": 0,
                "MOVEIN_QTY": 1000,
            },
            {
                "CONTAINERID": "C2",
                "LOSSREASONNAME": "001_A",
                "LOSSREASON_CODE": "001_A",
                "SCRAP_OBJECTTYPE": "LOT",
                "PRODUCTLINENAME": "PKG-A",
                "WORKCENTER_GROUP": "WB",
                "REJECT_TOTAL_QTY": 50,
                "DEFECT_QTY": 0,
                "MOVEIN_QTY": 900,
            },
        ]
    )

    monkeypatch.setattr(cache_svc, "_get_cached_df", lambda _query_id: df)
    monkeypatch.setattr(
        "mes_dashboard.services.scrap_reason_exclusion_cache.get_excluded_reasons",
        lambda: [],
    )

    excluded_material = cache_svc.compute_dimension_pareto(
        query_id="qid-1",
        dimension="package",
        pareto_scope="all",
        include_excluded_scrap=False,
        exclude_material_scrap=True,
        exclude_pb_diode=True,
    )
    kept_all = cache_svc.compute_dimension_pareto(
        query_id="qid-1",
        dimension="package",
        pareto_scope="all",
        include_excluded_scrap=False,
        exclude_material_scrap=False,
        exclude_pb_diode=True,
    )

    excluded_labels = {item.get("reason") for item in excluded_material.get("items", [])}
    all_labels = {item.get("reason") for item in kept_all.get("items", [])}

    assert "PKG-A" in excluded_labels
    assert "(NA)" not in excluded_labels
    assert "(NA)" in all_labels


def _build_detail_filter_df():
    return pd.DataFrame(
        [
            {
                "CONTAINERID": "C1",
                "CONTAINERNAME": "LOT-001",
                "TXN_DAY": pd.Timestamp("2026-02-01"),
                "TXN_TIME": pd.Timestamp("2026-02-01 08:00:00"),
                "WORKCENTERSEQUENCE_GROUP": 1,
                "WORKCENTER_GROUP": "WB",
                "WORKCENTERNAME": "WB-A",
                "SPECNAME": "SPEC-A",
                "WORKFLOWNAME": "WF-A",
                "PRIMARY_EQUIPMENTNAME": "EQ-1",
                "EQUIPMENTNAME": "EQ-1",
                "PRODUCTLINENAME": "PKG-A",
                "PJ_TYPE": "TYPE-A",
                "LOSSREASONNAME": "001_A",
                "LOSSREASON_CODE": "001_A",
                "SCRAP_OBJECTTYPE": "LOT",
                "MOVEIN_QTY": 100,
                "REJECT_TOTAL_QTY": 30,
                "DEFECT_QTY": 0,
            },
            {
                "CONTAINERID": "C2",
                "CONTAINERNAME": "LOT-002",
                "TXN_DAY": pd.Timestamp("2026-02-01"),
                "TXN_TIME": pd.Timestamp("2026-02-01 09:00:00"),
                "WORKCENTERSEQUENCE_GROUP": 1,
                "WORKCENTER_GROUP": "WB",
                "WORKCENTERNAME": "WB-B",
                "SPECNAME": "SPEC-B",
                "WORKFLOWNAME": "WF-B",
                "PRIMARY_EQUIPMENTNAME": "EQ-2",
                "EQUIPMENTNAME": "EQ-2",
                "PRODUCTLINENAME": "PKG-B",
                "PJ_TYPE": "TYPE-B",
                "LOSSREASONNAME": "001_A",
                "LOSSREASON_CODE": "001_A",
                "SCRAP_OBJECTTYPE": "LOT",
                "MOVEIN_QTY": 100,
                "REJECT_TOTAL_QTY": 20,
                "DEFECT_QTY": 0,
            },
            {
                "CONTAINERID": "C3",
                "CONTAINERNAME": "LOT-003",
                "TXN_DAY": pd.Timestamp("2026-02-01"),
                "TXN_TIME": pd.Timestamp("2026-02-01 10:00:00"),
                "WORKCENTERSEQUENCE_GROUP": 1,
                "WORKCENTER_GROUP": "WB",
                "WORKCENTERNAME": "WB-C",
                "SPECNAME": "SPEC-C",
                "WORKFLOWNAME": "WF-C",
                "PRIMARY_EQUIPMENTNAME": "EQ-3",
                "EQUIPMENTNAME": "EQ-3",
                "PRODUCTLINENAME": "PKG-C",
                "PJ_TYPE": "TYPE-C",
                "LOSSREASONNAME": "002_B",
                "LOSSREASON_CODE": "002_B",
                "SCRAP_OBJECTTYPE": "LOT",
                "MOVEIN_QTY": 100,
                "REJECT_TOTAL_QTY": 10,
                "DEFECT_QTY": 0,
            },
        ]
    )


def test_apply_view_and_export_share_same_pareto_multi_select_filter(monkeypatch):
    df = _build_detail_filter_df()

    monkeypatch.setattr(cache_svc, "_get_cached_df", lambda _query_id: df)
    monkeypatch.setattr(
        "mes_dashboard.services.scrap_reason_exclusion_cache.get_excluded_reasons",
        lambda: [],
    )

    view_result = cache_svc.apply_view(
        query_id="qid-2",
        pareto_dimension="type",
        pareto_values=["TYPE-A", "TYPE-C"],
    )
    export_rows = cache_svc.export_csv_from_cache(
        query_id="qid-2",
        pareto_dimension="type",
        pareto_values=["TYPE-A", "TYPE-C"],
    )

    detail_items = view_result["detail"]["items"]
    detail_types = {item["PJ_TYPE"] for item in detail_items}
    exported_types = {row["TYPE"] for row in export_rows}

    assert view_result["detail"]["pagination"]["total"] == 2
    assert detail_types == {"TYPE-A", "TYPE-C"}
    assert exported_types == {"TYPE-A", "TYPE-C"}
    assert len(export_rows) == 2


def test_apply_view_rejects_invalid_pareto_dimension(monkeypatch):
    df = _build_detail_filter_df()
    monkeypatch.setattr(cache_svc, "_get_cached_df", lambda _query_id: df)

    with pytest.raises(ValueError, match="不支援的 pareto_dimension"):
        cache_svc.apply_view(
            query_id="qid-3",
            pareto_dimension="invalid-dimension",
            pareto_values=["X"],
        )

    with pytest.raises(ValueError, match="不支援的 pareto_dimension"):
        cache_svc.export_csv_from_cache(
            query_id="qid-3",
            pareto_dimension="invalid-dimension",
            pareto_values=["X"],
        )
