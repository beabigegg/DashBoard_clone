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


def test_get_filter_options_reads_from_caches(monkeypatch):
    """get_filter_options returns workcenter_groups/packages/reasons from cache modules."""
    monkeypatch.setattr(svc, "get_excluded_reasons", lambda force_refresh=False: set())

    mock_wc_groups = [{"name": "WB", "sequence": 1}, {"name": "FA", "sequence": 5}]
    mock_packages = ["PKG-A", "PKG-B"]
    mock_reasons = ["001_CRACK", "002_BREAK"]

    import mes_dashboard.services.filter_cache as fc
    import mes_dashboard.services.container_filter_cache as cfc
    import mes_dashboard.services.reason_filter_cache as rfc

    monkeypatch.setattr(fc, "get_workcenter_groups", lambda force_refresh=False: mock_wc_groups)
    monkeypatch.setattr(cfc, "_CACHE", {"packages": mock_packages, "pj_types": [], "loaded": True, "updated_at": None})
    monkeypatch.setattr(rfc, "_CACHE", {"reject_reasons": mock_reasons, "loaded": True, "updated_at": None})

    result = svc.get_filter_options(
        start_date="2026-02-01",
        end_date="2026-02-07",
        workcenter_groups=["WB"],
        packages=["PKG-A"],
        reasons=["001_CRACK"],
        include_excluded_scrap=False,
    )

    assert result["packages"] == mock_packages
    assert result["reasons"] == mock_reasons
    assert result["workcenter_groups"][0]["name"] == "WB"
    assert result["workcenter_groups"][1]["name"] == "FA"
    # Date params are accepted and ignored — no Oracle call needed
    assert "meta" in result


def test_get_filter_options_does_not_narrow_packages_by_selection(monkeypatch):
    """Regression: reject-history filter-options is intentionally NON-cross-filter.

    Unlike WIP overview and production-history, reject-history serves the full
    cached lists for each field even when other fields are selected. The
    L1-cache architecture (filter_cache / container_filter_cache /
    reason_filter_cache) is per-field and has no co-occurrence index. This
    test pins that contract so a future "cross-filter the reject dropdowns"
    change must update the test deliberately rather than silently regressing.
    """
    monkeypatch.setattr(svc, "get_excluded_reasons", lambda force_refresh=False: set())

    mock_packages = ["PKG-A", "PKG-B", "PKG-C"]
    mock_reasons = ["001_CRACK", "002_BREAK", "003_SCRATCH"]

    import mes_dashboard.services.filter_cache as fc
    import mes_dashboard.services.container_filter_cache as cfc
    import mes_dashboard.services.reason_filter_cache as rfc

    monkeypatch.setattr(fc, "get_workcenter_groups", lambda force_refresh=False: [{"name": "WB", "sequence": 1}])
    monkeypatch.setattr(cfc, "_CACHE", {"packages": mock_packages, "pj_types": [], "loaded": True, "updated_at": None})
    monkeypatch.setattr(rfc, "_CACHE", {"reject_reasons": mock_reasons, "loaded": True, "updated_at": None})

    # Even when caller supplies workcenter_groups + reasons selections, the
    # packages list is NOT narrowed — full cache returned.
    result = svc.get_filter_options(
        workcenter_groups=["WB"],
        reasons=["001_CRACK"],
        packages=["PKG-A"],  # Even with explicit packages selection...
    )

    # ... the returned packages still contains all three (no co-occurrence narrowing).
    assert result["packages"] == mock_packages
    # And reasons is also the full cache.
    assert result["reasons"] == mock_reasons


def test_get_filter_options_date_params_backward_compat(monkeypatch):
    """get_filter_options accepts date params without error (backward compat)."""
    monkeypatch.setattr(svc, "get_excluded_reasons", lambda force_refresh=False: set())

    import mes_dashboard.services.filter_cache as fc
    import mes_dashboard.services.container_filter_cache as cfc
    import mes_dashboard.services.reason_filter_cache as rfc

    monkeypatch.setattr(fc, "get_workcenter_groups", lambda force_refresh=False: [])
    monkeypatch.setattr(cfc, "_CACHE", {"packages": [], "pj_types": [], "loaded": True, "updated_at": None})
    monkeypatch.setattr(rfc, "_CACHE", {"reject_reasons": [], "loaded": True, "updated_at": None})

    # Should not raise, date params are ignored
    result = svc.get_filter_options(start_date="2026-02-01", end_date="2026-02-07")
    assert "packages" in result
    assert "reasons" in result
    assert "workcenter_groups" in result


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
        captured["sql"] = _sql
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
    assert "COUNT(*) OVER () AS TOTAL_COUNT" in captured["sql"]
    assert "OFFSET :offset ROWS FETCH NEXT :limit ROWS ONLY" in captured["sql"]


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

    assert "扣帳報廢量" in payload
    assert "不扣帳報廢量" in payload
    assert "WORKFLOW" not in payload
    assert "2026-02-03" in payload


# ============================================================
# rh-primary-prefilter: _build_base_where tests
# ============================================================

def test_build_where_clause_injects_pj_types_into_base_where():
    """Non-empty pj_types list produces NVL(TRIM(c.PJ_TYPE), '(NA)') IN (...) in base_where."""
    base_where, params = svc._build_base_where(
        start_date="2026-01-01",
        end_date="2026-01-31",
        pj_types=["TYPE-A", "TYPE-B"],
        packages=[],
        pj_functions=[],
    )
    assert "NVL(TRIM(c.PJ_TYPE), '(NA)') IN" in base_where
    assert "TYPE-A" in params.values()
    assert "TYPE-B" in params.values()


def test_build_where_clause_injects_packages_into_base_where():
    """Non-empty packages list produces NVL(TRIM(c.PRODUCTLINENAME), '(NA)') IN (...) in base_where."""
    base_where, params = svc._build_base_where(
        start_date="2026-01-01",
        end_date="2026-01-31",
        pj_types=[],
        packages=["PKG-A"],
        pj_functions=[],
    )
    assert "NVL(TRIM(c.PRODUCTLINENAME), '(NA)') IN" in base_where
    assert "PKG-A" in params.values()


def test_build_where_clause_injects_pj_functions_into_base_where():
    """Non-empty pj_functions list produces NVL(TRIM(c.PJ_FUNCTION), '(NA)') IN (...) in base_where."""
    base_where, params = svc._build_base_where(
        start_date="2026-01-01",
        end_date="2026-01-31",
        pj_types=[],
        packages=[],
        pj_functions=["FUNC-X", "FUNC-Y"],
    )
    assert "NVL(TRIM(c.PJ_FUNCTION), '(NA)') IN" in base_where
    assert "FUNC-X" in params.values()
    assert "FUNC-Y" in params.values()


def test_build_where_clause_all_three_prefilters_combined():
    """All three prefilter lists present produce all three NVL IN clauses."""
    base_where, params = svc._build_base_where(
        start_date="2026-01-01",
        end_date="2026-01-31",
        pj_types=["TYPE-A"],
        packages=["PKG-B"],
        pj_functions=["FUNC-C"],
    )
    assert "NVL(TRIM(c.PJ_TYPE), '(NA)') IN" in base_where
    assert "NVL(TRIM(c.PRODUCTLINENAME), '(NA)') IN" in base_where
    assert "NVL(TRIM(c.PJ_FUNCTION), '(NA)') IN" in base_where
    assert "TYPE-A" in params.values()
    assert "PKG-B" in params.values()
    assert "FUNC-C" in params.values()


def test_build_where_clause_empty_prefilters_produce_no_restriction():
    """Empty lists add nothing beyond the date predicate — result identical to no prefilters."""
    base_where_empty, params_empty = svc._build_base_where(
        start_date="2026-01-01",
        end_date="2026-01-31",
        pj_types=[],
        packages=[],
        pj_functions=[],
    )
    base_where_none, params_none = svc._build_base_where(
        start_date="2026-01-01",
        end_date="2026-01-31",
    )
    assert base_where_empty == base_where_none
    assert params_empty == params_none
    # Only date params — no prefilter params in result
    assert "NVL" not in base_where_empty
    assert set(params_empty.keys()) == {"start_date", "end_date"}


def test_build_where_clause_absent_prefilters_produce_no_restriction():
    """Calling _build_base_where with no prefilter kwargs yields the date-only predicate."""
    base_where, params = svc._build_base_where(
        start_date="2026-06-01",
        end_date="2026-06-30",
    )
    assert "r.TXNDATE" in base_where
    assert "NVL" not in base_where
    assert params.get("start_date") == "2026-06-01"
    assert params.get("end_date") == "2026-06-30"


def test_build_where_clause_nvl_trim_form_not_raw_column_reference():
    """Prefilter must use NVL(TRIM(...)) form, not raw c.PJ_TYPE IN (...)."""
    base_where, _ = svc._build_base_where(
        start_date="2026-01-01",
        end_date="2026-01-31",
        pj_types=["TYPE-A"],
        packages=["PKG-B"],
        pj_functions=["FUNC-C"],
    )
    # Raw column IN is forbidden — NVL(TRIM) is required
    assert "c.PJ_TYPE IN" not in base_where
    assert "c.PRODUCTLINENAME IN" not in base_where
    assert "c.PJ_FUNCTION IN" not in base_where
    # NVL form present
    assert "NVL(TRIM(c.PJ_TYPE), '(NA)')" in base_where
    assert "NVL(TRIM(c.PRODUCTLINENAME), '(NA)')" in base_where
    assert "NVL(TRIM(c.PJ_FUNCTION), '(NA)')" in base_where


def test_build_where_clause_prefilters_absent_from_where_clause_fragment():
    """_build_where_clause (WHERE_CLAUSE) must NOT include PJ_TYPE/PRODUCTLINENAME/PJ_FUNCTION NVL IN clauses.

    AC-2: prefilters live in BASE_WHERE only (reject_raw CTE), not WHERE_CLAUSE (b.* scope).
    """
    import mes_dashboard.services.reject_history_service as _svc
    monkeypatch_helper = lambda: None  # just to confirm we can import the svc
    where_clause, _, _ = _svc._build_where_clause()

    assert "NVL(TRIM(c.PJ_TYPE)" not in where_clause
    assert "NVL(TRIM(c.PRODUCTLINENAME)" not in where_clause
    assert "NVL(TRIM(c.PJ_FUNCTION)" not in where_clause


def test_na_sentinel_in_pj_types_matches_null_pj_type_rows():
    """(NA) sentinel value appears verbatim in bind params so Oracle NVL maps NULL → '(NA)'."""
    _, params = svc._build_base_where(
        start_date="2026-01-01",
        end_date="2026-01-31",
        pj_types=["(NA)", "TYPE-A"],
    )
    param_values = list(params.values())
    assert "(NA)" in param_values
    assert "TYPE-A" in param_values


def test_na_sentinel_in_packages_matches_null_package_rows():
    """(NA) sentinel in packages list is preserved in bind params."""
    _, params = svc._build_base_where(
        start_date="2026-01-01",
        end_date="2026-01-31",
        packages=["(NA)", "PKG-A"],
    )
    param_values = list(params.values())
    assert "(NA)" in param_values
    assert "PKG-A" in param_values


def test_na_sentinel_in_pj_functions_matches_null_pj_function_rows():
    """(NA) sentinel in pj_functions list is preserved in bind params."""
    _, params = svc._build_base_where(
        start_date="2026-01-01",
        end_date="2026-01-31",
        pj_functions=["(NA)"],
    )
    param_values = list(params.values())
    assert "(NA)" in param_values


def test_pj_bop_param_absent_from_all_sql_paths():
    """pj_bop must not appear in _build_base_where or _build_where_clause outputs (AC-6)."""
    import inspect
    # _build_base_where signature must not accept pj_bop
    sig = inspect.signature(svc._build_base_where)
    assert "pj_bop" not in sig.parameters

    # _build_where_clause signature must not accept pj_bop
    sig_where = inspect.signature(svc._build_where_clause)
    assert "pj_bop" not in sig_where.parameters

    # Even if (hypothetically) called with arbitrary kwargs, no pj_bop in SQL output
    base_where, params = svc._build_base_where(
        start_date="2026-01-01",
        end_date="2026-01-31",
        pj_types=["TYPE-A"],
    )
    assert "pj_bop" not in base_where.lower()
    assert not any("pj_bop" in str(k).lower() for k in params)
