# -*- coding: utf-8 -*-
"""Unit tests for shared utility helpers."""

from __future__ import annotations

from pathlib import Path

from mes_dashboard.core.utils import parse_bool_query


def test_parse_bool_query_truthy_values():
    assert parse_bool_query("true") is True
    assert parse_bool_query("1") is True
    assert parse_bool_query("YES") is True


def test_parse_bool_query_falsy_values():
    assert parse_bool_query("false") is False
    assert parse_bool_query("0") is False
    assert parse_bool_query("no") is False


def test_parse_bool_query_unknown_uses_default():
    assert parse_bool_query("", default=True) is True
    assert parse_bool_query("not-a-bool", default=False) is False


def test_route_modules_do_not_define_duplicate_parse_bool_helpers():
    routes_dir = Path(__file__).resolve().parents[1] / "src" / "mes_dashboard" / "routes"
    route_files = sorted(routes_dir.glob("*_routes.py"))
    duplicates = []

    for route_file in route_files:
        text = route_file.read_text(encoding="utf-8")
        if "def _parse_bool" in text:
            duplicates.append(route_file.name)

    assert duplicates == []
