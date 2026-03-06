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
