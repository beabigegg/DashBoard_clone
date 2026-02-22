# -*- coding: utf-8 -*-
"""Unit tests for reject_history_service."""

from __future__ import annotations

import pandas as pd
import pytest

from mes_dashboard.services import reject_history_service as svc


def test_query_summary_returns_metrics_and_policy_meta(monkeypatch):
    monkeypatch.setattr(svc, "get_excluded_reasons", lambda force_refresh=False: {"358"})

    captured = {}

    def _fake_read_sql_df(_sql, params=None):
        captured["params"] = dict(params or {})
        return pd.DataFrame(
            [
                {
                    "MOVEIN_QTY": 1000,
                    "REJECT_TOTAL_QTY": 25,
                    "DEFECT_QTY": 10,
                    "REJECT_RATE_PCT": 2.5,
                    "DEFECT_RATE_PCT": 1.0,
                    "REJECT_SHARE_PCT": 71.4286,
                    "AFFECTED_LOT_COUNT": 12,
                    "AFFECTED_WORKORDER_COUNT": 7,
                }
            ]
        )

    monkeypatch.setattr(svc, "read_sql_df", _fake_read_sql_df)

    result = svc.query_summary(
        start_date="2026-02-01",
        end_date="2026-02-07",
        include_excluded_scrap=False,
    )

    assert result["MOVEIN_QTY"] == 1000
    assert result["REJECT_TOTAL_QTY"] == 25
    assert result["DEFECT_QTY"] == 10
    assert result["AFFECTED_LOT_COUNT"] == 12
    assert result["meta"]["include_excluded_scrap"] is False
    assert result["meta"]["exclusion_applied"] is True
    assert result["meta"]["excluded_reason_count"] == 1

    assert captured["params"]["start_date"] == "2026-02-01"
    assert captured["params"]["end_date"] == "2026-02-07"
    assert "358" in captured["params"].values()


def test_query_summary_include_override_skips_exclusion_filter(monkeypatch):
    monkeypatch.setattr(svc, "get_excluded_reasons", lambda force_refresh=False: {"358", "REASON_X"})

    captured = {}

    def _fake_read_sql_df(_sql, params=None):
        captured["params"] = dict(params or {})
        return pd.DataFrame(
            [
                {
                    "MOVEIN_QTY": 1000,
                    "REJECT_TOTAL_QTY": 25,
                    "DEFECT_QTY": 10,
                    "REJECT_RATE_PCT": 2.5,
                    "DEFECT_RATE_PCT": 1.0,
                    "REJECT_SHARE_PCT": 71.4286,
                    "AFFECTED_LOT_COUNT": 12,
                    "AFFECTED_WORKORDER_COUNT": 7,
                }
            ]
        )

    monkeypatch.setattr(svc, "read_sql_df", _fake_read_sql_df)
    result = svc.query_summary(
        start_date="2026-02-01",
        end_date="2026-02-07",
        include_excluded_scrap=True,
    )

    assert result["meta"]["include_excluded_scrap"] is True
    assert result["meta"]["exclusion_applied"] is False
    assert result["meta"]["excluded_reason_count"] == 0
    assert "358" not in captured["params"].values()
    assert "REASON_X" not in captured["params"].values()


def test_build_where_clause_applies_reason_prefix_policy_by_default(monkeypatch):
    monkeypatch.setattr(svc, "get_excluded_reasons", lambda force_refresh=False: set())
    where_clause, _params, meta = svc._build_where_clause(include_excluded_scrap=False)

    assert "REGEXP_LIKE(UPPER(NVL(TRIM(b.LOSSREASONNAME), '')), '^[0-9]{3}_')" in where_clause
    assert "NOT REGEXP_LIKE(UPPER(NVL(TRIM(b.LOSSREASONNAME), '')), '^(XXX|ZZZ)_')" in where_clause
    assert meta["reason_name_prefix_policy_applied"] is True
    assert meta["exclusion_applied"] is True


def test_build_where_clause_include_override_skips_reason_prefix_policy(monkeypatch):
    monkeypatch.setattr(svc, "get_excluded_reasons", lambda force_refresh=False: {"358"})
    where_clause, params, meta = svc._build_where_clause(
        include_excluded_scrap=True,
        packages=["PKG-A"],
    )

    assert "REGEXP_LIKE(UPPER(NVL(TRIM(b.LOSSREASONNAME), '')), '^[0-9]{3}_')" not in where_clause
    assert "NOT REGEXP_LIKE(UPPER(NVL(TRIM(b.LOSSREASONNAME), '')), '^(XXX|ZZZ)_')" not in where_clause
    assert meta["reason_name_prefix_policy_applied"] is False
    assert meta["exclusion_applied"] is False
    assert meta["package_filter_count"] == 1
    assert "358" not in params.values()


def test_get_filter_options_includes_packages(monkeypatch):
    monkeypatch.setattr(svc, "get_excluded_reasons", lambda force_refresh=False: set())
    captured: dict = {}

    def _fake_read_sql_df(_sql, params=None):
        captured["params"] = dict(params or {})
        return pd.DataFrame(
            [
                {
                    "WORKCENTER_GROUP": "WB",
                    "WORKCENTERSEQUENCE_GROUP": 1,
                    "REASON": "R1",
                    "PACKAGE": "PKG-A",
                    "SCRAP_OBJECTTYPE": "LOT",
                },
                {
                    "WORKCENTER_GROUP": "FA",
                    "WORKCENTERSEQUENCE_GROUP": 5,
                    "REASON": "R2",
                    "PACKAGE": "PKG-B",
                    "SCRAP_OBJECTTYPE": "LOT",
                },
            ]
        )

    monkeypatch.setattr(svc, "read_sql_df", _fake_read_sql_df)

    result = svc.get_filter_options(
        start_date="2026-02-01",
        end_date="2026-02-07",
        workcenter_groups=["WB"],
        packages=["PKG-A"],
        reasons=["R1"],
        include_excluded_scrap=False,
    )

    assert result["reasons"] == ["R1", "R2"]
    assert result["packages"] == ["PKG-A", "PKG-B"]
    assert result["workcenter_groups"][0]["name"] == "WB"
    assert result["workcenter_groups"][1]["name"] == "FA"

    assert captured["params"]["start_date"] == "2026-02-01"
    assert captured["params"]["end_date"] == "2026-02-07"
    assert "WB" in captured["params"].values()
    assert "PKG-A" in captured["params"].values()
    assert "R1" in captured["params"].values()


def test_get_filter_options_appends_material_reason_option(monkeypatch):
    monkeypatch.setattr(svc, "get_excluded_reasons", lambda force_refresh=False: set())
    def _fake_read_sql_df(_sql, _params=None):
        return pd.DataFrame(
            [
                {
                    "WORKCENTER_GROUP": "WB",
                    "WORKCENTERSEQUENCE_GROUP": 1,
                    "REASON": "001_TEST",
                    "PACKAGE": "PKG-A",
                    "SCRAP_OBJECTTYPE": "MATERIAL",
                }
            ]
        )

    monkeypatch.setattr(svc, "read_sql_df", _fake_read_sql_df)

    result = svc.get_filter_options(start_date="2026-02-01", end_date="2026-02-07")
    assert svc.MATERIAL_REASON_OPTION in result["reasons"]


def test_build_where_clause_with_material_reason_adds_objecttype_condition(monkeypatch):
    monkeypatch.setattr(svc, "get_excluded_reasons", lambda force_refresh=False: set())
    where_clause, _params, meta = svc._build_where_clause(reasons=[svc.MATERIAL_REASON_OPTION])

    assert "UPPER(NVL(TRIM(b.SCRAP_OBJECTTYPE), '-')) = 'MATERIAL'" in where_clause
    assert meta["material_reason_selected"] is True


def test_build_where_clause_exclude_material_scrap_adds_not_material_condition(monkeypatch):
    monkeypatch.setattr(svc, "get_excluded_reasons", lambda force_refresh=False: set())
    where_clause, _params, meta = svc._build_where_clause(exclude_material_scrap=True)

    assert "UPPER(NVL(TRIM(b.SCRAP_OBJECTTYPE), '-')) <> 'MATERIAL'" in where_clause
    assert meta["exclude_material_scrap"] is True
    assert meta["material_exclusion_applied"] is True


def test_sql_template_replacement_does_not_introduce_fake_bind_placeholders():
    sql = svc._prepare_sql(
        "summary",
        where_clause="WHERE 1=1",
        bucket_expr="TRUNC(b.TXN_DAY)",
        metric_column="b.REJECT_TOTAL_QTY",
    )

    assert ":BASE" not in sql
    assert ":WHERE" not in sql
    assert ":BUCKET" not in sql
    assert ":METRIC" not in sql


def test_base_with_cte_sql_flattens_nested_with(monkeypatch):
    monkeypatch.setattr(
        svc,
        "_load_sql",
        lambda name: (
            "-- comment line\n"
            "WITH c1 AS (SELECT 1 AS X FROM DUAL),\n"
            "c2 AS (SELECT X FROM c1)\n"
            "SELECT X FROM c2"
        )
        if name == "performance_daily"
        else "",
    )

    rendered = svc._base_with_cte_sql("base")
    assert rendered.startswith("WITH c1 AS")
    assert "base AS (\nSELECT X FROM c2\n)" in rendered
    assert "WITH base AS (\nWITH c1" not in rendered


def test_query_trend_invalid_granularity_raises():
    with pytest.raises(ValueError, match="Invalid granularity"):
        svc.query_trend(start_date="2026-02-01", end_date="2026-02-07", granularity="hour")


def test_query_reason_pareto_top80_scope(monkeypatch):
    monkeypatch.setattr(svc, "get_excluded_reasons", lambda force_refresh=False: set())

    monkeypatch.setattr(
        svc,
        "read_sql_df",
        lambda _sql, _params=None: pd.DataFrame(
            [
                {"REASON": "R1", "CATEGORY": "C1", "METRIC_VALUE": 50, "MOVEIN_QTY": 100, "REJECT_TOTAL_QTY": 50, "DEFECT_QTY": 0, "AFFECTED_LOT_COUNT": 10, "PCT": 50, "CUM_PCT": 50},
                {"REASON": "R2", "CATEGORY": "C1", "METRIC_VALUE": 29, "MOVEIN_QTY": 100, "REJECT_TOTAL_QTY": 29, "DEFECT_QTY": 0, "AFFECTED_LOT_COUNT": 8, "PCT": 29, "CUM_PCT": 79},
                {"REASON": "R3", "CATEGORY": "C2", "METRIC_VALUE": 13, "MOVEIN_QTY": 100, "REJECT_TOTAL_QTY": 13, "DEFECT_QTY": 0, "AFFECTED_LOT_COUNT": 6, "PCT": 13, "CUM_PCT": 92},
                {"REASON": "R4", "CATEGORY": "C3", "METRIC_VALUE": 8, "MOVEIN_QTY": 100, "REJECT_TOTAL_QTY": 8, "DEFECT_QTY": 0, "AFFECTED_LOT_COUNT": 5, "PCT": 8, "CUM_PCT": 100},
            ]
        ),
    )

    top80 = svc.query_reason_pareto(
        start_date="2026-02-01",
        end_date="2026-02-07",
        metric_mode="reject_total",
        pareto_scope="top80",
    )
    assert len(top80["items"]) == 2
    assert top80["items"][-1]["reason"] == "R2"
    assert "category" not in top80["items"][0]

    all_items = svc.query_reason_pareto(
        start_date="2026-02-01",
        end_date="2026-02-07",
        metric_mode="reject_total",
        pareto_scope="all",
    )
    assert len(all_items["items"]) == 4


def test_query_list_pagination_and_caps(monkeypatch):
    monkeypatch.setattr(svc, "get_excluded_reasons", lambda force_refresh=False: set())

    captured = {}

    def _fake_read_sql_df(_sql, params=None):
        captured["params"] = dict(params or {})
        return pd.DataFrame(
            [
                {
                    "TXN_DAY": "2026-02-03",
                    "TXN_MONTH": "2026-02",
                    "WORKCENTER_GROUP": "WB",
                    "WORKCENTERNAME": "WB01",
                    "SPECNAME": "S1",
                    "PRODUCTLINENAME": "P1",
                    "PJ_TYPE": "TYPE1",
                    "LOSSREASONNAME": "R1",
                    "LOSSREASON_CODE": "001",
                    "REJECTCATEGORYNAME": "CAT",
                    "MOVEIN_QTY": 100,
                    "REJECT_QTY": 3,
                    "STANDBY_QTY": 1,
                    "QTYTOPROCESS_QTY": 1,
                    "INPROCESS_QTY": 1,
                    "PROCESSED_QTY": 1,
                    "REJECT_TOTAL_QTY": 7,
                    "DEFECT_QTY": 2,
                    "REJECT_RATE_PCT": 7,
                    "DEFECT_RATE_PCT": 2,
                    "REJECT_SHARE_PCT": 77.777,
                    "AFFECTED_LOT_COUNT": 3,
                    "AFFECTED_WORKORDER_COUNT": 2,
                    "TOTAL_COUNT": 12,
                }
            ]
        )

    monkeypatch.setattr(svc, "read_sql_df", _fake_read_sql_df)

    result = svc.query_list(
        start_date="2026-02-01",
        end_date="2026-02-07",
        page=2,
        per_page=500,
        packages=["PKG1"],
    )

    assert result["pagination"]["page"] == 2
    assert result["pagination"]["perPage"] == 200
    assert result["pagination"]["total"] == 12
    assert result["pagination"]["totalPages"] == 1
    assert captured["params"]["offset"] == 200
    assert captured["params"]["limit"] == 200
    assert "PKG1" in captured["params"].values()


def test_export_csv_contains_semantic_headers(monkeypatch):
    monkeypatch.setattr(svc, "get_excluded_reasons", lambda force_refresh=False: set())
    monkeypatch.setattr(
        svc,
        "read_sql_df",
        lambda _sql, _params=None: pd.DataFrame(
            [
                {
                    "TXN_DAY": "2026-02-03",
                    "TXN_MONTH": "2026-02",
                    "WORKCENTER_GROUP": "WB",
                    "WORKCENTERNAME": "WB01",
                    "SPECNAME": "S1",
                    "PRODUCTLINENAME": "P1",
                    "PJ_TYPE": "TYPE1",
                    "LOSSREASONNAME": "R1",
                    "LOSSREASON_CODE": "001",
                    "REJECTCATEGORYNAME": "CAT",
                    "MOVEIN_QTY": 100,
                    "REJECT_QTY": 3,
                    "STANDBY_QTY": 1,
                    "QTYTOPROCESS_QTY": 1,
                    "INPROCESS_QTY": 1,
                    "PROCESSED_QTY": 1,
                    "REJECT_TOTAL_QTY": 7,
                    "DEFECT_QTY": 2,
                    "REJECT_RATE_PCT": 7,
                    "DEFECT_RATE_PCT": 2,
                    "REJECT_SHARE_PCT": 77.777,
                    "AFFECTED_LOT_COUNT": 3,
                    "AFFECTED_WORKORDER_COUNT": 2,
                }
            ]
        ),
    )

    chunks = list(
        svc.export_csv(
            start_date="2026-02-01",
            end_date="2026-02-07",
        )
    )
    payload = "".join(chunks)

    assert "REJECT_TOTAL_QTY" in payload
    assert "DEFECT_QTY" in payload
    assert "2026-02-03" in payload
