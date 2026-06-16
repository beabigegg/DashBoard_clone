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


# REMOVED BY yield-alert-spool-refactor: _compute_reject_linkage separate Oracle round-trip removed.
# The reject linkage is now inlined in the spool query via LEFT JOIN.
# test_compute_reject_linkage_batches_workorders_for_oracle_in_limit was deleted per
# test-plan.md Test Update Contract (AC-5/D3).


def test_query_yield_summary_raises_not_implemented_after_spool_refactor():
    """B5: query_yield_summary must raise NotImplementedError (Oracle path retired).

    Updated per test-plan.md Test Update Contract — the live Oracle summary path
    was retired by yield-alert-spool-refactor.  Callers must use apply_cached_view.
    """
    import pytest
    with pytest.raises(NotImplementedError, match="live Oracle path retired"):
        yield_alert_service.query_yield_summary(
            start_date="2026-03-01",
            end_date="2026-03-06",
            filters={},
        )


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


def test_query_yield_trend_raises_not_implemented_after_spool_refactor():
    """B5: query_yield_trend must raise NotImplementedError (Oracle path retired).

    Updated per test-plan.md Test Update Contract — the live Oracle trend path was
    retired by yield-alert-spool-refactor.  Callers must use apply_cached_view.
    The old test (test_query_yield_trend_uses_movetxn_for_transaction_and_filtered_detail_for_scrap)
    is replaced by this assertion.
    """
    import pytest
    with pytest.raises(NotImplementedError, match="live Oracle path retired"):
        yield_alert_service.query_yield_trend(
            start_date="2026-03-01",
            end_date="2026-03-06",
            granularity="day",
            filters={},
        )


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


def test_query_yield_summary_oracle_path_is_dead_code():
    """B5: query_yield_summary raises NotImplementedError regardless of filters.

    Updated from test_query_yield_summary_preserves_department_filter_when_exclusion_enabled
    per test-plan.md Test Update Contract.  The Oracle path is dead code.
    """
    import pytest
    with pytest.raises(NotImplementedError):
        yield_alert_service.query_yield_summary(
            start_date="2026-02-21",
            end_date="2026-02-21",
            filters={"departments": ["焊接_WB", "焊接_DW"]},
        )


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


# ──────────────────────────────────────────────────────────────────────────────
# yield-alert-spool-refactor: new service tests (B5)
# ──────────────────────────────────────────────────────────────────────────────

def test_query_yield_trend_no_longer_calls_oracle(monkeypatch):
    """B5: query_yield_trend must NOT call read_sql_df_slow (Oracle) after the spool refactor.

    The function should raise NotImplementedError or be retired (dead code),
    or alternatively be redirected to read from the spool.  Either way,
    a live Oracle call via read_sql_df_slow must NOT happen.
    """
    oracle_called = {"called": False}

    def _fake_read_sql_df_slow(sql, params, **kwargs):
        oracle_called["called"] = True
        import pandas as pd
        return pd.DataFrame()

    monkeypatch.setattr(yield_alert_service, "read_sql_df_slow", _fake_read_sql_df_slow)
    monkeypatch.setattr(
        yield_alert_service,
        "get_excluded_reasons",
        lambda force_refresh=False: set(),
    )

    # After B5 the function should either be removed or replaced.
    # If it's removed, calling it should raise AttributeError.
    # If it now reads from spool, it should NOT hit read_sql_df_slow.
    try:
        yield_alert_service.query_yield_trend(
            start_date="2026-02-01",
            end_date="2026-02-28",
            granularity="day",
            filters={},
        )
    except (NotImplementedError, AttributeError):
        pass  # acceptable: function retired

    assert not oracle_called["called"], (
        "query_yield_trend must NOT call Oracle (read_sql_df_slow) after spool refactor"
    )


def test_query_yield_summary_no_longer_calls_oracle(monkeypatch):
    """B5: query_yield_summary must NOT call read_sql_df_slow (Oracle) after the spool refactor."""
    oracle_called = {"called": False}

    def _fake_read_sql_df_slow(sql, params, **kwargs):
        oracle_called["called"] = True
        import pandas as pd
        return pd.DataFrame()

    monkeypatch.setattr(yield_alert_service, "read_sql_df_slow", _fake_read_sql_df_slow)
    monkeypatch.setattr(
        yield_alert_service,
        "get_excluded_reasons",
        lambda force_refresh=False: set(),
    )

    try:
        yield_alert_service.query_yield_summary(
            start_date="2026-02-01",
            end_date="2026-02-28",
            filters={},
        )
    except (NotImplementedError, AttributeError):
        pass  # acceptable: function retired

    assert not oracle_called["called"], (
        "query_yield_summary must NOT call Oracle (read_sql_df_slow) after spool refactor"
    )
