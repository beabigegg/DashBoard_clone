# -*- coding: utf-8 -*-
"""Unit tests for shared container resolution policy helpers."""

from __future__ import annotations

from mes_dashboard.services import container_resolution_policy as policy


def test_validate_resolution_request_rejects_empty_values():
    assert policy.validate_resolution_request("lot_id", []) is not None


def test_validate_resolution_request_rejects_broad_pattern(monkeypatch):
    monkeypatch.setenv("CONTAINER_RESOLVE_PATTERN_MIN_PREFIX_LEN", "2")
    error = policy.validate_resolution_request("lot_id", ["%"])
    assert error is not None
    assert "萬用字元條件過於寬鬆" in error


def test_validate_resolution_request_allows_pattern_with_prefix(monkeypatch):
    monkeypatch.setenv("CONTAINER_RESOLVE_PATTERN_MIN_PREFIX_LEN", "2")
    error = policy.validate_resolution_request("lot_id", ["GA26%"])
    assert error is None


def test_validate_resolution_result_rejects_excessive_expansion(monkeypatch):
    monkeypatch.setenv("CONTAINER_RESOLVE_MAX_EXPANSION_PER_TOKEN", "3")
    result = {
        "data": [{"container_id": "C1"}],
        "expansion_info": {"GA%": 10},
    }
    error = policy.validate_resolution_result(result)
    assert error is not None
    assert "單一條件展開過大" in error


def test_validate_resolution_result_rejects_excessive_container_count(monkeypatch):
    monkeypatch.setenv("CONTAINER_RESOLVE_MAX_CONTAINER_IDS", "2")
    result = {
        "data": [
            {"container_id": "C1"},
            {"container_id": "C2"},
            {"container_id": "C3"},
        ],
        "expansion_info": {},
    }
    error = policy.validate_resolution_result(result)
    assert error is not None
    assert "解析結果過大" in error


def test_validate_resolution_result_non_strict_allows_overflow(monkeypatch):
    monkeypatch.setenv("CONTAINER_RESOLVE_MAX_CONTAINER_IDS", "2")
    result = {
        "data": [
            {"container_id": "C1"},
            {"container_id": "C2"},
            {"container_id": "C3"},
        ],
        "expansion_info": {"GA%": 999},
    }
    error = policy.validate_resolution_result(result, strict=False)
    assert error is None


def test_extract_container_ids_deduplicates_and_preserves_order():
    rows = [
        {"container_id": "C1"},
        {"container_id": "C1"},
        {"CONTAINERID": "C2"},
        {"container_id": "C3"},
    ]
    assert policy.extract_container_ids(rows) == ["C1", "C2", "C3"]
