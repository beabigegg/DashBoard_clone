# -*- coding: utf-8 -*-
"""Unit tests for EventFetcher."""

from __future__ import annotations

from unittest.mock import patch

import pandas as pd

from mes_dashboard.services.event_fetcher import EventFetcher


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


@patch("mes_dashboard.services.event_fetcher.read_sql_df")
@patch("mes_dashboard.services.event_fetcher.cache_get")
def test_fetch_events_cache_hit_skips_db(mock_cache_get, mock_read_sql_df):
    mock_cache_get.return_value = {"CID-1": [{"CONTAINERID": "CID-1"}]}

    result = EventFetcher.fetch_events(["CID-1"], "materials")

    assert result["CID-1"][0]["CONTAINERID"] == "CID-1"
    mock_read_sql_df.assert_not_called()


@patch("mes_dashboard.services.event_fetcher.cache_set")
@patch("mes_dashboard.services.event_fetcher.cache_get", return_value=None)
@patch("mes_dashboard.services.event_fetcher.read_sql_df")
@patch("mes_dashboard.services.event_fetcher.SQLLoader.load_with_params")
def test_fetch_events_upstream_history_branch(
    mock_sql_load,
    mock_read_sql_df,
    _mock_cache_get,
    mock_cache_set,
):
    mock_sql_load.return_value = "SELECT * FROM UPSTREAM"
    mock_read_sql_df.return_value = pd.DataFrame(
        [
            {"CONTAINERID": "CID-1", "WORKCENTER_GROUP": "DB"},
            {"CONTAINERID": "CID-2", "WORKCENTER_GROUP": "WB"},
        ]
    )

    result = EventFetcher.fetch_events(["CID-1", "CID-2"], "upstream_history")

    assert sorted(result.keys()) == ["CID-1", "CID-2"]
    assert mock_sql_load.call_args.args[0] == "mid_section_defect/upstream_history"
    _, params = mock_read_sql_df.call_args.args
    assert len(params) == 2
    mock_cache_set.assert_called_once()
    assert mock_cache_set.call_args.args[0].startswith("evt:upstream_history:")


@patch("mes_dashboard.services.event_fetcher.cache_set")
@patch("mes_dashboard.services.event_fetcher.cache_get", return_value=None)
@patch("mes_dashboard.services.event_fetcher.read_sql_df")
@patch("mes_dashboard.services.event_fetcher.SQLLoader.load")
def test_fetch_events_history_branch_replaces_container_filter(
    mock_sql_load,
    mock_read_sql_df,
    _mock_cache_get,
    _mock_cache_set,
):
    mock_sql_load.return_value = (
        "SELECT * FROM t WHERE h.CONTAINERID = :container_id {{ WORKCENTER_FILTER }}"
    )
    mock_read_sql_df.return_value = pd.DataFrame([])

    EventFetcher.fetch_events(["CID-1"], "history")

    sql, params = mock_read_sql_df.call_args.args
    assert "h.CONTAINERID = :container_id" not in sql
    assert "{{ WORKCENTER_FILTER }}" not in sql
    assert params == {"p0": "CID-1"}


@patch("mes_dashboard.services.event_fetcher.cache_set")
@patch("mes_dashboard.services.event_fetcher.cache_get", return_value=None)
@patch("mes_dashboard.services.event_fetcher.read_sql_df")
@patch("mes_dashboard.services.event_fetcher.SQLLoader.load")
def test_fetch_events_materials_branch_replaces_aliased_container_filter(
    mock_sql_load,
    mock_read_sql_df,
    _mock_cache_get,
    _mock_cache_set,
):
    mock_sql_load.return_value = (
        "SELECT * FROM t m WHERE m.CONTAINERID = :container_id ORDER BY TXNDATE"
    )
    mock_read_sql_df.return_value = pd.DataFrame([])

    EventFetcher.fetch_events(["CID-1", "CID-2"], "materials")

    sql, params = mock_read_sql_df.call_args.args
    assert "m.CONTAINERID = :container_id" not in sql
    assert "IN" in sql.upper()
    assert params == {"p0": "CID-1", "p1": "CID-2"}


@patch("mes_dashboard.services.event_fetcher.cache_set")
@patch("mes_dashboard.services.event_fetcher.cache_get", return_value=None)
@patch("mes_dashboard.services.event_fetcher.read_sql_df")
@patch("mes_dashboard.services.event_fetcher.SQLLoader.load")
def test_fetch_events_rejects_branch_replaces_aliased_container_filter(
    mock_sql_load,
    mock_read_sql_df,
    _mock_cache_get,
    _mock_cache_set,
):
    mock_sql_load.return_value = (
        "SELECT * FROM t r LEFT JOIN c ON c.CONTAINERID = r.CONTAINERID "
        "WHERE r.CONTAINERID = :container_id ORDER BY r.TXNDATE"
    )
    mock_read_sql_df.return_value = pd.DataFrame([])

    EventFetcher.fetch_events(["CID-1", "CID-2"], "rejects")

    sql, params = mock_read_sql_df.call_args.args
    assert "r.CONTAINERID = :container_id" not in sql
    assert "IN" in sql.upper()
    assert params == {"p0": "CID-1", "p1": "CID-2"}


@patch("mes_dashboard.services.event_fetcher.cache_set")
@patch("mes_dashboard.services.event_fetcher.cache_get", return_value=None)
@patch("mes_dashboard.services.event_fetcher.read_sql_df")
@patch("mes_dashboard.services.event_fetcher.SQLLoader.load")
def test_fetch_events_holds_branch_replaces_aliased_container_filter(
    mock_sql_load,
    mock_read_sql_df,
    _mock_cache_get,
    _mock_cache_set,
):
    mock_sql_load.return_value = (
        "SELECT * FROM t h LEFT JOIN c ON c.CONTAINERID = h.CONTAINERID "
        "WHERE h.CONTAINERID = :container_id ORDER BY h.HOLDTXNDATE DESC"
    )
    mock_read_sql_df.return_value = pd.DataFrame([])

    EventFetcher.fetch_events(["CID-1", "CID-2"], "holds")

    sql, params = mock_read_sql_df.call_args.args
    assert "h.CONTAINERID = :container_id" not in sql
    assert "IN" in sql.upper()
    assert params == {"p0": "CID-1", "p1": "CID-2"}


def test_event_fetcher_uses_slow_connection():
    """Regression: event_fetcher must use read_sql_df_slow (non-pooled)."""
    import mes_dashboard.services.event_fetcher as ef
    from mes_dashboard.core.database import read_sql_df_slow

    assert ef.read_sql_df is read_sql_df_slow
