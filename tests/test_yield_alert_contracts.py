# -*- coding: utf-8 -*-
"""Unit tests for yield_alert_contracts.py — TypedDict contract assertions."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from mes_dashboard.services.yield_alert_contracts import (
    CacheMeta,
    LinkageQualityMeta,
    YieldSummaryItem,
    YieldTrendItem,
    YieldAlertRow,
    YieldAlertPagination,
    YieldAlertResponse,
    MatchStatus,
    RiskLevel,
)


class TestCacheMeta:
    def test_can_create_instance(self):
        meta: CacheMeta = {"hit": True, "key": "cache:abc"}
        assert meta["hit"] is True
        assert meta["key"] == "cache:abc"

    def test_has_required_keys(self):
        meta: CacheMeta = {"hit": False, "key": ""}
        assert "hit" in meta
        assert "key" in meta


class TestLinkageQualityMeta:
    def test_can_create_full_instance(self):
        q: LinkageQualityMeta = {
            "matched": 10,
            "partially_matched": 2,
            "unmatched": 1,
            "matched_scrap_qty": 100.0,
            "partially_matched_scrap_qty": 10.0,
            "unmatched_scrap_qty": 5.0,
            "total_scrap_qty": 115.0,
            "unmatched_ratio": 0.043,
            "warning": False,
            "warning_code": None,
        }
        assert q["matched"] == 10
        assert q["warning"] is False
        assert q["warning_code"] is None

    def test_warning_code_can_be_string(self):
        q: LinkageQualityMeta = {
            "matched": 0,
            "partially_matched": 0,
            "unmatched": 5,
            "matched_scrap_qty": 0.0,
            "partially_matched_scrap_qty": 0.0,
            "unmatched_scrap_qty": 50.0,
            "total_scrap_qty": 50.0,
            "unmatched_ratio": 1.0,
            "warning": True,
            "warning_code": "reason_unmapped",
        }
        assert q["warning"] is True
        assert q["warning_code"] == "reason_unmapped"


class TestYieldSummaryItem:
    def test_all_fields_numeric(self):
        item: YieldSummaryItem = {
            "transaction_qty": 1000.0,
            "scrap_qty": 50.0,
            "yield_pct": 95.0,
        }
        assert item["yield_pct"] == 95.0


class TestYieldTrendItem:
    def test_includes_date_bucket(self):
        item: YieldTrendItem = {
            "date_bucket": "2026-03-01",
            "transaction_qty": 500.0,
            "scrap_qty": 25.0,
            "yield_pct": 95.0,
        }
        assert item["date_bucket"] == "2026-03-01"


class TestYieldAlertPagination:
    def test_structure(self):
        p: YieldAlertPagination = {
            "page": 1,
            "per_page": 50,
            "total": 200,
            "total_pages": 4,
        }
        assert p["total_pages"] == 4


class TestYieldAlertResponse:
    def test_has_items_pagination_quality(self):
        resp: YieldAlertResponse = {
            "items": [],
            "pagination": {"page": 1, "per_page": 50, "total": 0, "total_pages": 0},
            "quality": {
                "matched": 0,
                "partially_matched": 0,
                "unmatched": 0,
                "matched_scrap_qty": 0.0,
                "partially_matched_scrap_qty": 0.0,
                "unmatched_scrap_qty": 0.0,
                "total_scrap_qty": 0.0,
                "unmatched_ratio": 0.0,
                "warning": False,
                "warning_code": None,
            },
        }
        assert "items" in resp
        assert "pagination" in resp
        assert "quality" in resp


class TestLiteralTypes:
    def test_match_status_values(self):
        valid: tuple = ("exact", "partial", "none")
        for v in valid:
            val: MatchStatus = v
            assert isinstance(val, str)

    def test_risk_level_values(self):
        for level in ("high", "medium", "low"):
            val: RiskLevel = level
            assert isinstance(val, str)
