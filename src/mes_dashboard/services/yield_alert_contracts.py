# -*- coding: utf-8 -*-
"""Typed contracts for Yield Alert Center APIs."""

from __future__ import annotations

from typing import Any, Literal, TypedDict


MatchStatus = Literal["exact", "partial", "none"]
RiskLevel = Literal["high", "medium", "low"]


class CacheMeta(TypedDict):
    hit: bool
    key: str


class LinkageQualityMeta(TypedDict):
    matched: int
    partially_matched: int
    unmatched: int
    matched_scrap_qty: float
    partially_matched_scrap_qty: float
    unmatched_scrap_qty: float
    total_scrap_qty: float
    unmatched_ratio: float
    warning: bool
    warning_code: str | None


class YieldSummaryItem(TypedDict):
    transaction_qty: float
    scrap_qty: float
    yield_pct: float


class YieldTrendItem(TypedDict):
    date_bucket: str
    transaction_qty: float
    scrap_qty: float
    yield_pct: float


class YieldAlertRow(TypedDict):
    date_bucket: str
    workorder: str
    reason_code: str
    reason_name: str
    department: str
    line: str
    package: str
    type: str
    function: str
    operation: str
    transaction_qty: float
    scrap_qty: float
    yield_pct: float
    scrap_rate_pct: float
    risk_level: RiskLevel
    risk_score: float
    match_status: MatchStatus
    fallback_reason: str | None
    reject_total_qty: float


class YieldAlertPagination(TypedDict):
    page: int
    per_page: int
    total: int
    total_pages: int


class YieldAlertResponse(TypedDict):
    items: list[YieldAlertRow]
    pagination: YieldAlertPagination
    quality: LinkageQualityMeta


class YieldDrilldownPayload(TypedDict):
    match_status: MatchStatus
    fallback_reason: str | None
    launch_href: str
    filters: dict[str, Any]
    linkage: dict[str, Any]
