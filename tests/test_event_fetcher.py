# -*- coding: utf-8 -*-
"""Unit tests for EventFetcher."""

from __future__ import annotations

from unittest.mock import patch

from mes_dashboard.core.query_quality_contract import (
    QUALITY_STATUS_COMPLETE,
    QUALITY_STATUS_PARTIAL,
    QUALITY_STATUS_TRUNCATED,
)
from mes_dashboard.services.event_fetcher import EventFetcher


def _iter_result(columns, rows):
    """Helper: create a generator that yields a single (columns, rows) batch."""
    def _gen(*args, **kwargs):
        yield columns, rows
    return _gen


def _iter_empty(*args, **kwargs):
    """Helper: generator that yields nothing (empty result)."""
    return iter([])


def test_cache_key_is_stable_for_sorted_ids():
    key1 = EventFetcher._cache_key("history", ["CID-B", "CID-A", "CID-A"])
    key2 = EventFetcher._cache_key("history", ["CID-A", "CID-B"])

    assert key1 == key2
    assert key1.startswith("evt:history:")


def test_get_rate_limit_config_supports_env_override(monkeypatch):
    monkeypatch.setenv("EVT_HISTORY_RATE_MAX_REQUESTS", "33")
    monkeypatch.setenv("EVT_HISTORY_RATE_WINDOW_SECONDS", "77")

    config = EventFetcher._get_rate_limit_config("history")

    assert config["bucket"] == "event-history"
    assert config["max_attempts"] == 33
    assert config["window_seconds"] == 77


@patch("mes_dashboard.services.event_fetcher.read_sql_df_slow_iter")
@patch("mes_dashboard.services.event_fetcher.cache_get")
def test_fetch_events_cache_hit_skips_db(mock_cache_get, mock_iter):
    mock_cache_get.return_value = {"CID-1": [{"CONTAINERID": "CID-1"}]}

    result = EventFetcher.fetch_events(["CID-1"], "materials")

    assert result["records_by_cid"]["CID-1"][0]["CONTAINERID"] == "CID-1"
    assert result["quality_meta"]["status"] == QUALITY_STATUS_COMPLETE
    mock_iter.assert_not_called()


@patch("mes_dashboard.services.event_fetcher.cache_set")
@patch("mes_dashboard.services.event_fetcher.cache_get", return_value=None)
@patch("mes_dashboard.services.event_fetcher.read_sql_df_slow_iter")
@patch("mes_dashboard.services.event_fetcher.SQLLoader.load_with_params")
def test_fetch_events_upstream_history_branch(
    mock_sql_load,
    mock_iter,
    _mock_cache_get,
    mock_cache_set,
):
    mock_sql_load.return_value = "SELECT * FROM UPSTREAM"
    mock_iter.side_effect = _iter_result(
        ["CONTAINERID", "WORKCENTER_GROUP"],
        [("CID-1", "DB"), ("CID-2", "WB")],
    )

    result = EventFetcher.fetch_events(["CID-1", "CID-2"], "upstream_history")

    assert sorted(result["records_by_cid"].keys()) == ["CID-1", "CID-2"]
    assert result["quality_meta"]["status"] == QUALITY_STATUS_COMPLETE
    assert mock_sql_load.call_args.args[0] == "mid_section_defect/upstream_history"
    sql_arg, params_arg = mock_iter.call_args.args
    assert len(params_arg) == 2
    mock_cache_set.assert_called_once()
    assert mock_cache_set.call_args.args[0].startswith("evt:upstream_history:")


@patch("mes_dashboard.services.event_fetcher.cache_set")
@patch("mes_dashboard.services.event_fetcher.cache_get", return_value=None)
@patch("mes_dashboard.services.event_fetcher.read_sql_df_slow_iter")
@patch("mes_dashboard.services.event_fetcher.SQLLoader.load")
def test_fetch_events_history_branch_replaces_container_filter(
    mock_sql_load,
    mock_iter,
    _mock_cache_get,
    _mock_cache_set,
):
    mock_sql_load.return_value = (
        "SELECT * FROM t WHERE h.CONTAINERID = :container_id {{ WORKCENTER_FILTER }}"
    )
    mock_iter.side_effect = _iter_empty

    EventFetcher.fetch_events(["CID-1"], "history")

    sql_arg, params_arg = mock_iter.call_args.args
    assert "h.CONTAINERID = :container_id" not in sql_arg
    assert "{{ WORKCENTER_FILTER }}" not in sql_arg
    assert params_arg == {"p0": "CID-1"}


@patch("mes_dashboard.services.event_fetcher.cache_set")
@patch("mes_dashboard.services.event_fetcher.cache_get", return_value=None)
@patch("mes_dashboard.services.event_fetcher.read_sql_df_slow_iter")
@patch("mes_dashboard.services.event_fetcher.SQLLoader.load")
def test_fetch_events_materials_branch_replaces_aliased_container_filter(
    mock_sql_load,
    mock_iter,
    _mock_cache_get,
    _mock_cache_set,
):
    mock_sql_load.return_value = (
        "SELECT * FROM t m WHERE m.CONTAINERID = :container_id ORDER BY TXNDATE"
    )
    mock_iter.side_effect = _iter_empty

    EventFetcher.fetch_events(["CID-1", "CID-2"], "materials")

    sql_arg, params_arg = mock_iter.call_args.args
    assert "m.CONTAINERID = :container_id" not in sql_arg
    assert "IN" in sql_arg.upper()
    assert params_arg == {"p0": "CID-1", "p1": "CID-2"}


@patch("mes_dashboard.services.event_fetcher.cache_set")
@patch("mes_dashboard.services.event_fetcher.cache_get", return_value=None)
@patch("mes_dashboard.services.event_fetcher.read_sql_df_slow_iter")
@patch("mes_dashboard.services.event_fetcher.SQLLoader.load")
def test_fetch_events_rejects_branch_replaces_aliased_container_filter(
    mock_sql_load,
    mock_iter,
    _mock_cache_get,
    _mock_cache_set,
):
    mock_sql_load.return_value = (
        "SELECT * FROM t r LEFT JOIN c ON c.CONTAINERID = r.CONTAINERID "
        "WHERE r.CONTAINERID = :container_id ORDER BY r.TXNDATE"
    )
    mock_iter.side_effect = _iter_empty

    EventFetcher.fetch_events(["CID-1", "CID-2"], "rejects")

    sql_arg, params_arg = mock_iter.call_args.args
    assert "r.CONTAINERID = :container_id" not in sql_arg
    assert "IN" in sql_arg.upper()
    assert params_arg == {"p0": "CID-1", "p1": "CID-2"}


@patch("mes_dashboard.services.event_fetcher.cache_set")
@patch("mes_dashboard.services.event_fetcher.cache_get", return_value=None)
@patch("mes_dashboard.services.event_fetcher.read_sql_df_slow_iter")
@patch("mes_dashboard.services.event_fetcher.SQLLoader.load")
def test_fetch_events_holds_branch_replaces_aliased_container_filter(
    mock_sql_load,
    mock_iter,
    _mock_cache_get,
    _mock_cache_set,
):
    mock_sql_load.return_value = (
        "SELECT * FROM t h LEFT JOIN c ON c.CONTAINERID = h.CONTAINERID "
        "WHERE h.CONTAINERID = :container_id ORDER BY h.HOLDTXNDATE DESC"
    )
    mock_iter.side_effect = _iter_empty

    EventFetcher.fetch_events(["CID-1", "CID-2"], "holds")

    sql_arg, params_arg = mock_iter.call_args.args
    assert "h.CONTAINERID = :container_id" not in sql_arg
    assert "IN" in sql_arg.upper()
    assert params_arg == {"p0": "CID-1", "p1": "CID-2"}


def test_event_fetcher_uses_slow_iter_connection():
    """Regression: event_fetcher must use read_sql_df_slow_iter (non-pooled)."""
    import mes_dashboard.services.event_fetcher as ef
    from mes_dashboard.core.database import read_sql_df_slow_iter

    assert ef.read_sql_df_slow_iter is read_sql_df_slow_iter


@patch("mes_dashboard.services.event_fetcher.cache_set")
@patch("mes_dashboard.services.event_fetcher.cache_get", return_value=None)
@patch("mes_dashboard.services.event_fetcher.read_sql_df_slow_iter")
@patch("mes_dashboard.services.event_fetcher.SQLLoader.load_with_params")
def test_fetch_events_sanitizes_nan_values(
    mock_sql_load,
    mock_iter,
    _mock_cache_get,
    _mock_cache_set,
):
    """NaN float values in records should be replaced with None."""
    mock_sql_load.return_value = "SELECT * FROM UPSTREAM"
    mock_iter.side_effect = _iter_result(
        ["CONTAINERID", "VALUE"],
        [("CID-1", float("nan"))],
    )

    result = EventFetcher.fetch_events(["CID-1"], "upstream_history")

    assert result["records_by_cid"]["CID-1"][0]["VALUE"] is None


@patch("mes_dashboard.services.event_fetcher.cache_set")
@patch("mes_dashboard.services.event_fetcher.cache_get", return_value=None)
@patch("mes_dashboard.services.event_fetcher.read_sql_df_slow_iter")
@patch("mes_dashboard.services.event_fetcher.SQLLoader.load")
def test_fetch_events_raises_when_parallel_batch_fails_and_partial_disabled(
    mock_sql_load,
    mock_iter,
    _mock_cache_get,
    _mock_cache_set,
    monkeypatch,
):
    mock_sql_load.return_value = "SELECT * FROM t WHERE h.CONTAINERID = :container_id {{ WORKCENTER_FILTER }}"
    monkeypatch.setattr("mes_dashboard.services.event_fetcher.EVENT_FETCHER_ALLOW_PARTIAL_RESULTS", False)
    monkeypatch.setattr("mes_dashboard.services.event_fetcher.EVENT_FETCHER_MAX_WORKERS", 2)

    def _side_effect(sql, params, timeout_seconds=60):
        if "CID-1000" in params.values():
            raise RuntimeError("chunk fail")
        return iter([])

    mock_iter.side_effect = _side_effect
    cids = [f"CID-{i}" for i in range(1001)]  # force >1 batch

    try:
        EventFetcher.fetch_events(cids, "history")
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "chunk failed" in str(exc)


@patch("mes_dashboard.services.event_fetcher.cache_set")
@patch("mes_dashboard.services.event_fetcher.cache_get", return_value=None)
@patch("mes_dashboard.services.event_fetcher.read_sql_df_slow_iter")
@patch("mes_dashboard.services.event_fetcher.SQLLoader.load")
def test_fetch_events_allows_partial_when_enabled(
    mock_sql_load,
    mock_iter,
    _mock_cache_get,
    _mock_cache_set,
    monkeypatch,
):
    mock_sql_load.return_value = "SELECT * FROM t WHERE h.CONTAINERID = :container_id {{ WORKCENTER_FILTER }}"
    monkeypatch.setattr("mes_dashboard.services.event_fetcher.EVENT_FETCHER_ALLOW_PARTIAL_RESULTS", True)
    monkeypatch.setattr("mes_dashboard.services.event_fetcher.EVENT_FETCHER_MAX_WORKERS", 2)

    def _side_effect(sql, params, timeout_seconds=60):
        if "CID-1000" in params.values():
            raise RuntimeError("chunk fail")
        return iter([])

    mock_iter.side_effect = _side_effect
    cids = [f"CID-{i}" for i in range(1001)]

    result = EventFetcher.fetch_events(cids, "history")
    assert result["records_by_cid"] == {}
    assert result["quality_meta"]["status"] == QUALITY_STATUS_PARTIAL
    assert "chunk_failure" in result["quality_meta"]["reasons"]
    assert result["quality_meta"]["has_partial_failure"] is True
    assert result["quality_meta"]["failed_chunk_count"] == 1


@patch("mes_dashboard.services.event_fetcher.cache_get")
def test_fetch_events_cache_hit_legacy_meta_is_adapted(mock_cache_get):
    mock_cache_get.return_value = {
        "CID-1": [{"CONTAINERID": "CID-1"}],
        "__meta__": {
            "truncated": True,
            "total_rows_fetched": 200,
            "max_total_rows": 100,
        },
    }

    result = EventFetcher.fetch_events(["CID-1"], "history")
    assert "__meta__" not in result["records_by_cid"]
    assert result["quality_meta"]["status"] == QUALITY_STATUS_TRUNCATED
    assert result["quality_meta"]["observed_rows"] == 200
    assert result["quality_meta"]["max_rows"] == 100


@patch("mes_dashboard.services.event_fetcher.cache_set")
@patch("mes_dashboard.services.event_fetcher.cache_get", return_value=None)
@patch("mes_dashboard.services.event_fetcher.read_sql_df_slow_iter")
@patch("mes_dashboard.services.event_fetcher.SQLLoader.load")
def test_fetch_events_truncation_meta_contains_row_limit_context(
    mock_sql_load,
    mock_iter,
    _mock_cache_get,
    _mock_cache_set,
    monkeypatch,
):
    mock_sql_load.return_value = "SELECT * FROM t WHERE h.CONTAINERID = :container_id {{ WORKCENTER_FILTER }}"
    monkeypatch.setattr("mes_dashboard.services.event_fetcher.EVENT_FETCHER_MAX_TOTAL_ROWS", 2)
    mock_iter.side_effect = _iter_result(
        ["CONTAINERID", "EVENTTYPE"],
        [
            ("CID-1", "A"),
            ("CID-1", "B"),
            ("CID-1", "C"),
        ],
    )

    result = EventFetcher.fetch_events(["CID-1"], "history")
    assert len(result["records_by_cid"]["CID-1"]) == 2
    assert result["quality_meta"]["status"] == QUALITY_STATUS_TRUNCATED
    assert result["quality_meta"]["observed_rows"] == 2
    assert result["quality_meta"]["max_rows"] == 2
