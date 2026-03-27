# -*- coding: utf-8 -*-
"""Unit tests for yield alert service helpers."""

import pandas as pd

import mes_dashboard.services.yield_alert_service as yield_alert_service
from mes_dashboard.services.yield_alert_service import (
    build_canonical_key,
    build_drilldown_payload,
    build_query_cache_key,
    normalize_query_key_payload,
    normalize_reason_code,
)


def test_normalize_reason_code_prefers_prefix_tokens():
    assert normalize_reason_code("001_SHORT") == "001"
    assert normalize_reason_code("ab12-extra") == "AB12"


def test_normalize_reason_code_handles_textual_values_and_empty():
    assert normalize_reason_code("NG品") == "NG品"
    assert normalize_reason_code("") == "UNMAPPED_REASON"
    assert normalize_reason_code(None) == "UNMAPPED_REASON"


def test_canonical_key_is_stable_and_uppercases_workorder():
    key = build_canonical_key("2026-03-06", "wo-001", "001_reject")
    assert key == "2026-03-06|WO-001|001"


def test_normalize_query_payload_sorts_lists_and_drops_none():
    payload = {
        "start_date": "2026-03-01",
        "end_date": "2026-03-06",
        "departments": ["WB02", "WB01", "WB02"],
        "unused": None,
    }
    normalized = normalize_query_key_payload(payload)
    assert normalized["departments"] == ["WB01", "WB02"]
    assert "unused" not in normalized


def test_query_cache_key_is_deterministic_for_equivalent_payloads():
    payload_a = {"a": ["2", "1"], "b": "x"}
    payload_b = {"b": "x", "a": ["1", "2"]}
    assert build_query_cache_key("alerts", payload_a) == build_query_cache_key("alerts", payload_b)


def test_drilldown_payload_contains_launch_href_and_filters():
    payload = build_drilldown_payload(
        date_bucket="2026-03-06",
        workorder="WO-123",
        reason_code="001_SHORT",
    )
    assert payload["match_status"] in {"exact", "partial"}
    assert payload["filters"]["workorder"] == "WO-123"
    assert payload["launch_href"].startswith("/reject-history?")
    assert "start_date=2026-03-06" in payload["launch_href"]


def test_compute_reject_linkage_batches_workorders_for_oracle_in_limit(monkeypatch):
    calls: list[dict] = []

    def _fake_read_sql_df_slow(sql: str, params: dict):
        bind_values = [value for key, value in params.items() if key.startswith("p")]
        calls.append({"sql": sql, "params": params.copy(), "bind_values": bind_values})
        return pd.DataFrame(
            [
                {
                    "DATE_BUCKET": "2026-03-06",
                    "WORKORDER": bind_values[0] if bind_values else "WO-NA",
                    "REASON_NAME": "001_SHORT",
                    "REJECT_TOTAL_QTY": 1,
                }
            ]
        )

    monkeypatch.setattr(yield_alert_service, "_ORACLE_IN_MAX_EXPRESSIONS", 3)
    monkeypatch.setattr(yield_alert_service, "read_sql_df_slow", _fake_read_sql_df_slow)

    workorders = [f"wo-{idx}" for idx in range(1, 8)] + ["wo-1"]
    linked = yield_alert_service._compute_reject_linkage(
        start_date="2026-03-01",
        end_date="2026-03-06",
        workorders=workorders,
    )

    assert len(calls) == 3
    assert all(len([key for key in call["params"] if key.startswith("p")]) <= 3 for call in calls)
    assert all("IN (" in call["sql"] for call in calls)
    assert sum(linked.values()) == 3


def test_query_yield_summary_applies_reason_exclusion_policy(monkeypatch):
    captured: dict = {"sql_calls": []}

    monkeypatch.setattr(
        yield_alert_service,
        "get_excluded_reasons",
        lambda force_refresh=False: {"358", "REASON_X"},
    )

    def _fake_read_sql_df_slow(sql: str, params: dict):
        captured["sql_calls"].append(sql)
        captured["params"] = dict(params or {})
        if "FROM DWH.ERP_WIP_MOVETXN m" in sql:
            return pd.DataFrame(
                [
                    {
                        "TRANSACTION_QTY": 1000,
                        "SCRAP_QTY": 999,
                        "YIELD_PCT": 0.1,
                    }
                ]
            )
        return pd.DataFrame([{"SCRAP_QTY": 25}])

    monkeypatch.setattr(yield_alert_service, "read_sql_df_slow", _fake_read_sql_df_slow)
    result = yield_alert_service.query_yield_summary(
        start_date="2026-03-01",
        end_date="2026-03-06",
        filters={},
    )

    assert result["summary"]["transaction_qty"] == 1000
    assert result["summary"]["scrap_qty"] == 25
    assert result["summary"]["yield_pct"] == 97.5
    assert result["meta"]["reason_exclusion_applied"] is True
    assert result["meta"]["excluded_reason_count"] == 2
    assert len(captured["sql_calls"]) == 2
    assert any("FROM DWH.ERP_WIP_MOVETXN m" in sql for sql in captured["sql_calls"])
    assert any("NOT IN ('(UNMAPPED)', 'N/A', 'NA', '-')" in sql for sql in captured["sql_calls"])
    assert "358" in captured["params"].values()
    assert "REASON_X" in captured["params"].values()


def test_query_alert_candidates_excludes_unmapped_and_policy_reason(monkeypatch):
    monkeypatch.setattr(
        yield_alert_service,
        "get_excluded_reasons",
        lambda force_refresh=False: {"358"},
    )

    def _fake_read_sql_df_slow(_sql: str, _params: dict):
        return pd.DataFrame(
            [
                {
                    "DATE_BUCKET": "2026-03-06",
                    "WIP_ENTITY_NAME": "WO-1",
                    "REASON_RAW": "(UNMAPPED)",
                    "REASON_NAME": "(未填寫)",
                    "DEPARTMENT_NAME": "WB",
                    "LINE_NAME": "L1",
                    "PACKAGE_NAME": "PKG-A",
                    "TYPE_NAME": "TYPE-A",
                    "FUNCTION_NAME": "FUNC-A",
                    "OPERATION_SEQ_NUM": 10,
                    "TRANSACTION_QTY": 100,
                    "SCRAP_QTY": 10,
                    "YIELD_PCT": 90,
                    "SCRAP_RATE_PCT": 10,
                },
                {
                    "DATE_BUCKET": "2026-03-06",
                    "WIP_ENTITY_NAME": "WO-2",
                    "REASON_RAW": "358_FAIL",
                    "REASON_NAME": "358_FAIL",
                    "DEPARTMENT_NAME": "WB",
                    "LINE_NAME": "L1",
                    "PACKAGE_NAME": "PKG-A",
                    "TYPE_NAME": "TYPE-A",
                    "FUNCTION_NAME": "FUNC-A",
                    "OPERATION_SEQ_NUM": 20,
                    "TRANSACTION_QTY": 100,
                    "SCRAP_QTY": 8,
                    "YIELD_PCT": 92,
                    "SCRAP_RATE_PCT": 8,
                },
                {
                    "DATE_BUCKET": "2026-03-06",
                    "WIP_ENTITY_NAME": "WO-3",
                    "REASON_RAW": "001_SHORT",
                    "REASON_NAME": "001_SHORT",
                    "DEPARTMENT_NAME": "WB",
                    "LINE_NAME": "L1",
                    "PACKAGE_NAME": "PKG-A",
                    "TYPE_NAME": "TYPE-A",
                    "FUNCTION_NAME": "FUNC-A",
                    "OPERATION_SEQ_NUM": 30,
                    "TRANSACTION_QTY": 100,
                    "SCRAP_QTY": 6,
                    "YIELD_PCT": 94,
                    "SCRAP_RATE_PCT": 6,
                },
            ]
        )

    monkeypatch.setattr(yield_alert_service, "read_sql_df_slow", _fake_read_sql_df_slow)
    monkeypatch.setattr(yield_alert_service, "_compute_reject_linkage", lambda **_: {})

    result = yield_alert_service.query_alert_candidates(
        start_date="2026-03-01",
        end_date="2026-03-06",
        filters={},
        risk_threshold=99,
        min_scrap_qty=0,
    )

    assert result["pagination"]["total"] == 1
    assert len(result["items"]) == 1
    assert result["items"][0]["reason_code"] == "001"
    assert result["meta"]["reason_exclusion_applied"] is True
    assert result["meta"]["excluded_reason_count"] == 1


def test_query_alert_candidates_merges_dw_into_wb_group(monkeypatch):
    monkeypatch.setattr(
        yield_alert_service,
        "get_excluded_reasons",
        lambda force_refresh=False: set(),
    )

    def _fake_read_sql_df_slow(_sql: str, _params: dict):
        return pd.DataFrame(
            [
                {
                    "DATE_BUCKET": "2026-03-06",
                    "WIP_ENTITY_NAME": "WO-10",
                    "REASON_RAW": "001_SHORT",
                    "REASON_NAME": "001_SHORT",
                    "DEPARTMENT_NAME": "焊接_DW",
                    "LINE_NAME": "L1",
                    "PACKAGE_NAME": "PKG-A",
                    "TYPE_NAME": "TYPE-A",
                    "FUNCTION_NAME": "FUNC-A",
                    "OPERATION_SEQ_NUM": 10,
                    "TRANSACTION_QTY": 100,
                    "SCRAP_QTY": 5,
                    "YIELD_PCT": 95,
                    "SCRAP_RATE_PCT": 5,
                },
                {
                    "DATE_BUCKET": "2026-03-06",
                    "WIP_ENTITY_NAME": "WO-10",
                    "REASON_RAW": "001_SHORT",
                    "REASON_NAME": "001_SHORT",
                    "DEPARTMENT_NAME": "焊接_WB",
                    "LINE_NAME": "L1",
                    "PACKAGE_NAME": "PKG-A",
                    "TYPE_NAME": "TYPE-A",
                    "FUNCTION_NAME": "FUNC-A",
                    "OPERATION_SEQ_NUM": 10,
                    "TRANSACTION_QTY": 100,
                    "SCRAP_QTY": 5,
                    "YIELD_PCT": 95,
                    "SCRAP_RATE_PCT": 5,
                },
            ]
        )

    monkeypatch.setattr(yield_alert_service, "read_sql_df_slow", _fake_read_sql_df_slow)
    monkeypatch.setattr(yield_alert_service, "_compute_reject_linkage", lambda **_: {})

    result = yield_alert_service.query_alert_candidates(
        start_date="2026-03-01",
        end_date="2026-03-06",
        filters={},
        risk_threshold=99,
        min_scrap_qty=0,
    )

    assert result["pagination"]["total"] == 1
    assert len(result["items"]) == 1
    assert result["items"][0]["department"] == "焊接_WB"
    assert result["items"][0]["transaction_qty"] == 200
    assert result["items"][0]["scrap_qty"] == 10
    assert result["items"][0]["yield_pct"] == 95


def test_query_yield_trend_uses_movetxn_for_transaction_and_filtered_detail_for_scrap(monkeypatch):
    monkeypatch.setattr(
        yield_alert_service,
        "get_excluded_reasons",
        lambda force_refresh=False: {"358"},
    )

    def _fake_read_sql_df_slow(sql: str, _params: dict):
        if "FROM DWH.ERP_WIP_MOVETXN m" in sql:
            return pd.DataFrame(
                [
                    {
                        "DATE_BUCKET": "2026-03-06",
                        "TRANSACTION_QTY": 1000,
                        "SCRAP_QTY": 999,
                        "YIELD_PCT": 0.1,
                    }
                ]
            )
        return pd.DataFrame([{"DATE_BUCKET": "2026-03-06", "SCRAP_QTY": 25}])

    monkeypatch.setattr(yield_alert_service, "read_sql_df_slow", _fake_read_sql_df_slow)

    result = yield_alert_service.query_yield_trend(
        start_date="2026-03-01",
        end_date="2026-03-06",
        granularity="day",
        filters={},
    )

    assert len(result["items"]) == 1
    assert result["items"][0]["transaction_qty"] == 1000
    assert result["items"][0]["scrap_qty"] == 25
    assert result["items"][0]["yield_pct"] == 97.5


def test_expand_workcenter_groups_to_departments_merges_dw_into_wb():
    expanded = yield_alert_service.expand_workcenter_groups_to_departments(["焊接_WB", "成型"])
    assert "焊接_WB" in expanded
    assert "焊接_DW" in expanded
    assert "成型" in expanded


def test_get_yield_workcenter_group_options_applies_dw_merge(monkeypatch):
    monkeypatch.setattr(
        yield_alert_service,
        "get_workcenter_groups",
        lambda force_refresh=False: [
            {"name": "焊接_DB", "sequence": 1},
            {"name": "焊接_WB", "sequence": 2},
            {"name": "焊接_DW", "sequence": 3},
        ],
    )
    options = yield_alert_service.get_yield_workcenter_group_options()
    assert "焊接_DB" in options
    assert "焊接_WB" in options
    assert "焊接_DW" not in options


def test_query_yield_summary_preserves_department_filter_when_exclusion_enabled(monkeypatch):
    calls: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        yield_alert_service,
        "get_excluded_reasons",
        lambda force_refresh=False: {"358"},
    )

    def _fake_read_sql_df_slow(sql: str, params: dict):
        calls.append((sql, dict(params or {})))
        if "FROM DWH.ERP_WIP_MOVETXN m" in sql:
            return pd.DataFrame([{"TRANSACTION_QTY": 14039.147, "SCRAP_QTY": 17.155, "YIELD_PCT": 99.8778}])
        return pd.DataFrame([{"SCRAP_QTY": 17.155}])

    monkeypatch.setattr(yield_alert_service, "read_sql_df_slow", _fake_read_sql_df_slow)
    result = yield_alert_service.query_yield_summary(
        start_date="2026-02-21",
        end_date="2026-02-21",
        filters={"departments": ["焊接_WB", "焊接_DW"]},
    )

    assert result["summary"]["transaction_qty"] == 14039.147
    assert result["summary"]["scrap_qty"] == 17.155
    detail_call = next((params for sql, params in calls if "ERP_WIP_MOVETXN_DETAIL d" in sql), {})
    assert "焊接_WB" in detail_call.values()
    assert "焊接_DW" in detail_call.values()
    assert "358" in detail_call.values()


def test_query_alert_candidates_preserves_department_filter_with_exclusion_params(monkeypatch):
    calls: list = []
    monkeypatch.setattr(
        yield_alert_service,
        "get_excluded_reasons",
        lambda force_refresh=False: {"358"},
    )

    _tx_row = {
        "DATE_BUCKET": "2026-02-21",
        "WIP_ENTITY_NAME": "WO-1",
        "DEPARTMENT_NAME": "焊接_WB",
        "LINE_NAME": "L1",
        "PACKAGE_NAME": "PKG-A",
        "TYPE_NAME": "TYPE-A",
        "FUNCTION_NAME": "FUNC-A",
        "OPERATION_SEQ_NUM": 10,
        "TRANSACTION_QTY": 100,
    }

    _alert_row = {
        "DATE_BUCKET": "2026-02-21",
        "WIP_ENTITY_NAME": "WO-1",
        "REASON_RAW": "031_腳架氧化",
        "REASON_NAME": "031_腳架氧化",
        "DEPARTMENT_NAME": "焊接_WB",
        "LINE_NAME": "L1",
        "PACKAGE_NAME": "PKG-A",
        "TYPE_NAME": "TYPE-A",
        "FUNCTION_NAME": "FUNC-A",
        "OPERATION_SEQ_NUM": 10,
        "TRANSACTION_QTY": 0,
        "SCRAP_QTY": 10,
        "YIELD_PCT": 90,
        "SCRAP_RATE_PCT": 10,
    }

    def _fake_read_sql_df_slow(_sql: str, params: dict):
        calls.append({"sql": _sql, "params": dict(params or {})})
        if "alerts_tx_lookup" in _sql or "TRANSACTION_QTY" in _sql and "SCRAP" not in _sql:
            return pd.DataFrame([_tx_row])
        return pd.DataFrame([_alert_row])

    monkeypatch.setattr(yield_alert_service, "read_sql_df_slow", _fake_read_sql_df_slow)
    monkeypatch.setattr(yield_alert_service, "_compute_reject_linkage", lambda **_: {})

    result = yield_alert_service.query_alert_candidates(
        start_date="2026-02-21",
        end_date="2026-02-21",
        filters={"departments": ["焊接_WB", "焊接_DW"]},
        risk_threshold=99,
        min_scrap_qty=0,
    )

    assert result["pagination"]["total"] == 1
    # Alerts SQL call should have exclusion + department params
    alerts_call = calls[0]
    assert "焊接_WB" in alerts_call["params"].values()
    assert "焊接_DW" in alerts_call["params"].values()
    assert "358" in alerts_call["params"].values()
    # tx_lookup SQL call should have department params (no exclusion)
    tx_call = calls[1]
    assert "焊接_WB" in tx_call["params"].values()
    assert "焊接_DW" in tx_call["params"].values()
