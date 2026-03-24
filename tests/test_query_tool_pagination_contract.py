# -*- coding: utf-8 -*-
"""Query-tool pagination + quality metadata contract tests."""

from __future__ import annotations

import pandas as pd

import mes_dashboard.services.query_tool_service as qts


def test_lot_history_batch_returns_pagination_and_quality_meta(monkeypatch):
    monkeypatch.setattr(qts, "_check_rss_guard", lambda *_a, **_k: None)
    monkeypatch.setattr(
        qts,
        "_fetch_domain_records",
        lambda *_a, **_k: (
            {
                "CID-A": [
                    {"CONTAINERID": "CID-A", "SEQ": 1},
                    {"CONTAINERID": "CID-A", "SEQ": 2},
                    {"CONTAINERID": "CID-A", "SEQ": 3},
                ],
                "CID-B": [
                    {"CONTAINERID": "CID-B", "SEQ": 4},
                    {"CONTAINERID": "CID-B", "SEQ": 5},
                ],
            },
            {"status": "truncated", "reasons": ["max_total_rows_exceeded"], "max_rows": 4},
        ),
    )

    result = qts.get_lot_history_batch(
        ["CID-A", "CID-B"],
        page=2,
        per_page=2,
    )

    assert result["total"] == 5
    assert result["pagination"] == {
        "page": 2,
        "per_page": 2,
        "total": 5,
        "total_pages": 3,
    }
    assert [row["SEQ"] for row in result["data"]] == [3, 4]
    assert result["quality_meta"]["status"] == "truncated"
    assert "max_total_rows_exceeded" in result["quality_meta"]["reasons"]


def test_lot_history_batch_uses_spool_runtime_before_rss_guard(monkeypatch):
    monkeypatch.setattr(
        qts,
        "_try_query_tool_spool_page",
        lambda **_kwargs: (
            {
                "data": [{"CONTAINERID": "CID-A", "SEQ": 10}],
                "total": 1,
                "pagination": {"page": 1, "per_page": 1, "total": 1, "total_pages": 1},
            },
            {"view_runtime": "duckdb"},
        ),
    )
    monkeypatch.setattr(
        qts,
        "_check_rss_guard",
        lambda *_a, **_k: (_ for _ in ()).throw(MemoryError("should not hit guard")),
    )

    result = qts.get_lot_history_batch(["CID-A"], page=1, per_page=50)

    assert result["total"] == 1
    assert result["data"][0]["SEQ"] == 10
    assert result["quality_meta"]["runtime"] == "duckdb"
    assert result["quality_meta"]["runtime_path"] == "spool"


def test_lot_associations_batch_returns_pagination_and_quality_meta(monkeypatch):
    monkeypatch.setattr(qts, "_check_rss_guard", lambda *_a, **_k: None)
    monkeypatch.setattr(
        qts,
        "_fetch_domain_records",
        lambda *_a, **_k: (
            {
                "CID-A": [
                    {"CONTAINERID": "CID-A", "MATERIALLOTNAME": "M-1"},
                    {"CONTAINERID": "CID-A", "MATERIALLOTNAME": "M-2"},
                ],
                "CID-B": [
                    {"CONTAINERID": "CID-B", "MATERIALLOTNAME": "M-3"},
                ],
            },
            {
                "status": "partial",
                "reasons": ["chunk_failure"],
                "failed_ranges": [{"start": "CID-C", "end": "CID-D"}],
            },
        ),
    )

    result = qts.get_lot_associations_batch(
        ["CID-A", "CID-B"],
        "materials",
        page=1,
        per_page=2,
    )

    assert result["total"] == 3
    assert len(result["data"]) == 2
    assert result["pagination"]["total_pages"] == 2
    assert result["quality_meta"]["status"] == "partial"
    assert result["quality_meta"]["failed_ranges"] == [{"start": "CID-C", "end": "CID-D"}]


def test_lot_associations_batch_uses_spool_runtime_before_rss_guard(monkeypatch):
    monkeypatch.setattr(
        qts,
        "_try_query_tool_spool_page",
        lambda **_kwargs: (
            {
                "data": [{"CONTAINERID": "CID-A", "MATERIALLOTNAME": "M-10"}],
                "total": 1,
                "pagination": {"page": 1, "per_page": 1, "total": 1, "total_pages": 1},
            },
            {"view_runtime": "duckdb"},
        ),
    )
    monkeypatch.setattr(
        qts,
        "_check_rss_guard",
        lambda *_a, **_k: (_ for _ in ()).throw(MemoryError("should not hit guard")),
    )

    result = qts.get_lot_associations_batch(["CID-A"], "materials", page=1, per_page=50)

    assert result["total"] == 1
    assert result["data"][0]["MATERIALLOTNAME"] == "M-10"
    assert result["quality_meta"]["runtime"] == "duckdb"
    assert result["quality_meta"]["runtime_path"] == "spool"


def test_equipment_lots_returns_paginated_rows(monkeypatch):
    monkeypatch.setattr(qts, "_check_rss_guard", lambda *_a, **_k: None)
    monkeypatch.setattr(qts.SQLLoader, "load_with_params", lambda *_a, **_k: "SELECT 1")
    monkeypatch.setattr(
        qts,
        "read_sql_df_slow",
        lambda *_a, **_k: pd.DataFrame(
            [
                {"CONTAINERID": "CID-1"},
                {"CONTAINERID": "CID-2"},
                {"CONTAINERID": "CID-3"},
                {"CONTAINERID": "CID-4"},
                {"CONTAINERID": "CID-5"},
            ]
        ),
    )

    result = qts.get_equipment_lots(
        ["EQ-1"],
        "2024-01-01",
        "2024-01-31",
        page=3,
        per_page=2,
    )

    assert result["total"] == 5
    assert result["pagination"] == {
        "page": 3,
        "per_page": 2,
        "total": 5,
        "total_pages": 3,
    }
    assert result["data"] == [{"CONTAINERID": "CID-5"}]


def test_lot_associations_batch_rejects_applies_policy_and_group_alignment(monkeypatch):
    monkeypatch.setattr(qts, "_check_rss_guard", lambda *_a, **_k: None)
    monkeypatch.setattr(
        qts,
        "_fetch_domain_records",
        lambda *_a, **_k: (
            {
                "CID-A": [
                    {
                        "CONTAINERID": "CID-A",
                        "WORKCENTERNAME": "焊_DB_料",
                        "LOSSREASONNAME": "001_VALID",
                        "LOSSREASON_CODE": "001_VALID",
                        "SCRAP_OBJECTTYPE": "LOT",
                        "PRODUCTLINENAME": "SOT-23",
                    },
                    {
                        "CONTAINERID": "CID-A",
                        "WORKCENTERNAME": "焊_DB_料",
                        "LOSSREASONNAME": "002_EXCLUDED",
                        "LOSSREASON_CODE": "002_EXCLUDED",
                        "SCRAP_OBJECTTYPE": "LOT",
                        "PRODUCTLINENAME": "SOT-23",
                    },
                    {
                        "CONTAINERID": "CID-A",
                        "WORKCENTERNAME": "焊_DB_料",
                        "LOSSREASONNAME": "003_MATERIAL",
                        "LOSSREASON_CODE": "003_MATERIAL",
                        "SCRAP_OBJECTTYPE": "MATERIAL",
                        "PRODUCTLINENAME": "SOT-23",
                    },
                    {
                        "CONTAINERID": "CID-A",
                        "WORKCENTERNAME": "焊_DB_料",
                        "LOSSREASONNAME": "XXX_DEBUG",
                        "LOSSREASON_CODE": "XXX_DEBUG",
                        "SCRAP_OBJECTTYPE": "LOT",
                        "PRODUCTLINENAME": "SOT-23",
                    },
                    {
                        "CONTAINERID": "CID-A",
                        "WORKCENTERNAME": "焊_DB_料",
                        "LOSSREASONNAME": "004_PB",
                        "LOSSREASON_CODE": "004_PB",
                        "SCRAP_OBJECTTYPE": "LOT",
                        "PRODUCTLINENAME": "PB_ABC",
                    },
                ],
            },
            {"status": "complete"},
        ),
    )
    monkeypatch.setattr(
        qts,
        "_try_query_tool_spool_page",
        lambda **_kwargs: (None, {"view_sql_fallback_reason": "miss"}),
    )

    import mes_dashboard.services.filter_cache as filter_cache
    import mes_dashboard.services.scrap_reason_exclusion_cache as reason_cache

    monkeypatch.setattr(filter_cache, "get_workcenter_mapping", lambda *_a, **_k: {})
    monkeypatch.setattr(filter_cache, "get_spec_workcenter_mapping", lambda *_a, **_k: {})
    monkeypatch.setattr(reason_cache, "get_excluded_reasons", lambda: {"002_EXCLUDED"})

    result = qts.get_lot_associations_batch(["CID-A"], "rejects", page=1, per_page=50)

    assert result["total"] == 1
    assert len(result["data"]) == 1
    row = result["data"][0]
    assert row["LOSSREASONNAME"] == "001_VALID"
    assert row["WORKCENTER_GROUP"] == "焊接_DB"


def test_lot_associations_batch_rejects_spool_runtime_receives_policy(monkeypatch):
    captured: dict = {}

    def _fake_spool(**kwargs):
        captured.update(kwargs)
        return (
            {
                "data": [
                    {
                        "CONTAINERID": "CID-A",
                        "WORKCENTERNAME": "焊_DB_料",
                        "LOSSREASONNAME": "001_VALID",
                    }
                ],
                "total": 1,
                "pagination": {"page": 1, "per_page": 1, "total": 1, "total_pages": 1},
            },
            {"view_runtime": "duckdb"},
        )

    monkeypatch.setattr(qts, "_try_query_tool_spool_page", _fake_spool)

    import mes_dashboard.services.filter_cache as filter_cache

    monkeypatch.setattr(filter_cache, "get_workcenter_mapping", lambda *_a, **_k: {})
    monkeypatch.setattr(filter_cache, "get_spec_workcenter_mapping", lambda *_a, **_k: {})

    result = qts.get_lot_associations_batch(["CID-A"], "rejects", page=1, per_page=20)

    assert result["total"] == 1
    assert captured["reject_policy"]["include_excluded_scrap"] is False
    assert captured["reject_policy"]["exclude_material_scrap"] is True
    assert captured["reject_policy"]["exclude_pb_diode"] is True


def test_lot_rejects_single_applies_policy_filter(monkeypatch):
    monkeypatch.setattr(
        qts,
        "_fetch_domain_records",
        lambda *_a, **_k: (
            {
                "CID-A": [
                    {
                        "CONTAINERID": "CID-A",
                        "WORKCENTERNAME": "焊_DB_料",
                        "LOSSREASONNAME": "001_VALID",
                        "LOSSREASON_CODE": "001_VALID",
                        "SCRAP_OBJECTTYPE": "LOT",
                    },
                    {
                        "CONTAINERID": "CID-A",
                        "WORKCENTERNAME": "焊_DB_料",
                        "LOSSREASONNAME": "003_MATERIAL",
                        "LOSSREASON_CODE": "003_MATERIAL",
                        "SCRAP_OBJECTTYPE": "MATERIAL",
                    },
                ],
            },
            {"status": "complete"},
        ),
    )

    import mes_dashboard.services.filter_cache as filter_cache
    import mes_dashboard.services.scrap_reason_exclusion_cache as reason_cache

    monkeypatch.setattr(filter_cache, "get_workcenter_mapping", lambda *_a, **_k: {})
    monkeypatch.setattr(filter_cache, "get_spec_workcenter_mapping", lambda *_a, **_k: {})
    monkeypatch.setattr(reason_cache, "get_excluded_reasons", lambda: set())

    result = qts.get_lot_rejects("CID-A", page=1, per_page=50)

    assert result["total"] == 1
    assert result["data"][0]["LOSSREASONNAME"] == "001_VALID"
    assert result["data"][0]["WORKCENTER_GROUP"] == "焊接_DB"
