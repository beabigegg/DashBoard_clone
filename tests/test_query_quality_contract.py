# -*- coding: utf-8 -*-
"""Unit tests for query quality contract helpers."""

from __future__ import annotations

from mes_dashboard.core.query_quality_contract import (
    QUALITY_SCOPE_DOMAIN,
    QUALITY_SCOPE_QUERY,
    QUALITY_STATUS_COMPLETE,
    QUALITY_STATUS_FAILED,
    QUALITY_STATUS_PARTIAL,
    QUALITY_STATUS_TRUNCATED,
    adapt_legacy_event_map,
    build_event_fetch_result,
    build_quality_meta,
    merge_quality_metas,
    unpack_event_fetch_result,
)


def test_build_quality_meta_normalizes_payload():
    meta = build_quality_meta(
        status="TRUNCATED",
        scope="DOMAIN",
        reasons=["row_limit", "row_limit", ""],
        domain="history",
        observed_rows="123",
        max_rows="100",
    )

    assert meta["status"] == QUALITY_STATUS_TRUNCATED
    assert meta["scope"] == QUALITY_SCOPE_DOMAIN
    assert meta["reasons"] == ["row_limit"]
    assert meta["domain"] == "history"
    assert meta["observed_rows"] == 123
    assert meta["max_rows"] == 100


def test_merge_quality_metas_promotes_failed_domain_to_partial_query():
    history_meta = build_quality_meta(
        status=QUALITY_STATUS_COMPLETE,
        scope=QUALITY_SCOPE_DOMAIN,
        domain="history",
    )
    materials_meta = build_quality_meta(
        status=QUALITY_STATUS_FAILED,
        scope=QUALITY_SCOPE_DOMAIN,
        domain="materials",
        reasons=["domain_fetch_failed"],
    )

    merged = merge_quality_metas([history_meta, materials_meta], scope=QUALITY_SCOPE_QUERY)

    assert merged["status"] == QUALITY_STATUS_PARTIAL
    assert "materials" in merged.get("failed_domains", [])
    assert "domain_failure" in merged.get("reasons", [])


def test_adapt_legacy_event_map_extracts_truncation_meta():
    records, quality_meta = adapt_legacy_event_map(
        {
            "CID-1": [{"CONTAINERID": "CID-1"}],
            "__meta__": {
                "truncated": True,
                "total_rows_fetched": 50,
                "max_total_rows": 20,
            },
        },
        domain="history",
    )

    assert list(records.keys()) == ["CID-1"]
    assert quality_meta["status"] == QUALITY_STATUS_TRUNCATED
    assert quality_meta["domain"] == "history"
    assert quality_meta["observed_rows"] == 50
    assert quality_meta["max_rows"] == 20


def test_unpack_event_fetch_result_supports_new_shape():
    payload = build_event_fetch_result(
        {"CID-2": [{"CONTAINERID": "CID-2"}]},
        build_quality_meta(
            status=QUALITY_STATUS_COMPLETE,
            scope=QUALITY_SCOPE_DOMAIN,
            domain="materials",
        ),
    )
    records, quality_meta = unpack_event_fetch_result(payload, domain="materials")

    assert list(records.keys()) == ["CID-2"]
    assert quality_meta["status"] == QUALITY_STATUS_COMPLETE
    assert quality_meta["domain"] == "materials"


def test_unpack_event_fetch_result_legacy_without_meta_defaults_complete():
    records, quality_meta = unpack_event_fetch_result(
        {"CID-3": [{"CONTAINERID": "CID-3"}]},
        domain="rejects",
    )

    assert list(records.keys()) == ["CID-3"]
    assert quality_meta["status"] == QUALITY_STATUS_COMPLETE
    assert quality_meta["domain"] == "rejects"
