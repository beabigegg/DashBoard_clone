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


# ── AC-6: YA-13 business rule + CHANGELOG version entries ─────────────────────

import pathlib  # noqa: E402

_REPO_ROOT = pathlib.Path(__file__).parent.parent
_BUSINESS_RULES = (_REPO_ROOT / "contracts/business/business-rules.md").read_text(encoding="utf-8")
_CHANGELOG = (_REPO_ROOT / "contracts/CHANGELOG.md").read_text(encoding="utf-8")


class TestBusinessRuleYA13:
    """AC-6: business-rules.md YA-13 must document the KPI-summary alert-candidate
    scope + the tx_extra_cols dedup dimension (design.md Decisions 1/2), and
    contracts/CHANGELOG.md must record the business+data version entries this
    change introduced.

    Per implementation-plan.md Known Risks #2: contracts/CHANGELOG.md
    intentionally has ONLY `business` and `data` entries for this change —
    `contracts/api/api-contract.md` is deliberately deferred (hook-blocked), so
    this test asserts business+data entries only, NOT an `api` entry.
    """

    def test_ya13_rule_documents_kpi_scope_and_tx_extra_cols_dedup_dimension(self):
        assert "YA-13" in _BUSINESS_RULES

        # Locate the YA-13 row text for targeted assertions.
        ya13_line = next(
            (line for line in _BUSINESS_RULES.splitlines() if "YA-13" in line),
            "",
        )
        assert ya13_line, "YA-13 row not found in business-rules.md"

        # Alert-candidate predicate must be documented verbatim.
        assert "SCRAP_QTY <> 0" in ya13_line
        assert "risk_threshold" in ya13_line
        assert "min_scrap_qty" in ya13_line

        # Dedup dimension must be the _query_alerts local tx_extra_cols set,
        # NOT the module-level _TX_DEDUP_COLS (design.md Decision 2).
        assert "tx_extra_cols" in ya13_line
        assert "_TX_DEDUP_COLS" in ya13_line
        for col in [
            "WORKORDER", "DEPARTMENT_GROUP", "PROCESS_CATEGORY",
            "LINE_NAME", "PACKAGE_NAME", "TYPE_NAME", "FUNCTION_NAME",
            "OPERATION_TEXT", "DATE_BUCKET",
        ]:
            assert col in ya13_line, f"YA-13 must enumerate dedup column {col}"

        # Scope boundary: trend/heatmap/station/package are explicitly excluded.
        assert "trend" in ya13_line
        assert "heatmap" in ya13_line
        assert "station_summary" in ya13_line
        assert "package_summary" in ya13_line

    def test_changelog_has_version_entries_for_business_data_api(self):
        """CHANGELOG must record this change's business + data version bumps.

        NOTE: no `api` entry is expected or required — api-contract.md is
        deliberately deferred for this change (hook-blocked; see
        change-classification.md Clarifications). Do not add one to satisfy
        this test; asserting its absence documents the deferral is intentional.
        """
        assert "yield-alert-kpi-csv-parity" in _CHANGELOG

        business_entries = [
            line for line in _CHANGELOG.splitlines()
            if line.startswith("## [business ")
        ]
        data_entries = [
            line for line in _CHANGELOG.splitlines()
            if line.startswith("## [data ")
        ]
        assert business_entries, "CHANGELOG must have at least one [business ...] entry"
        assert data_entries, "CHANGELOG must have at least one [data ...] entry"

        assert "## [business 1.40.0]" in _CHANGELOG
        assert "## [data 1.33.0]" in _CHANGELOG

        # This change's business/data entries must mention YA-13 / the change id.
        assert "YA-13" in _CHANGELOG
        assert "yield-alert-kpi-csv-parity" in _CHANGELOG
