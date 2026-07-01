# -*- coding: utf-8 -*-
"""Unit tests for core.route_helpers (parse_multi_param, parse_pagination).

Explicit ``source`` is passed in every case so no Flask app context is needed.
parse_multi_param behaviour pins the contract the reject-history / yield-alert
routes previously implemented inline.
"""
from __future__ import annotations

from werkzeug.datastructures import MultiDict

from mes_dashboard.core.route_helpers import parse_multi_param, parse_pagination


class TestParseMultiParam:
    def test_get_repeated_params(self):
        src = MultiDict([("x", "a"), ("x", "b")])
        assert parse_multi_param("x", src) == ["a", "b"]

    def test_get_csv_value_is_split(self):
        src = MultiDict([("x", "a,b,c")])
        assert parse_multi_param("x", src) == ["a", "b", "c"]

    def test_get_repeated_and_csv_combined(self):
        src = MultiDict([("x", "a,b"), ("x", "c")])
        assert parse_multi_param("x", src) == ["a", "b", "c"]

    def test_order_preserving_dedup(self):
        src = MultiDict([("x", "a,b"), ("x", "a"), ("x", "c,b")])
        assert parse_multi_param("x", src) == ["a", "b", "c"]

    def test_whitespace_and_empty_tokens_dropped(self):
        src = MultiDict([("x", " a , , b ")])
        assert parse_multi_param("x", src) == ["a", "b"]

    def test_missing_key_returns_empty_list(self):
        assert parse_multi_param("x", MultiDict()) == []

    def test_post_dict_list_value_taken_verbatim(self):
        # List members are NOT CSV-split (matches the former reject behaviour).
        src = {"x": ["a,b", "c"]}
        assert parse_multi_param("x", src) == ["a,b", "c"]

    def test_post_dict_scalar_csv_is_split(self):
        src = {"x": "a,b,c"}
        assert parse_multi_param("x", src) == ["a", "b", "c"]

    def test_post_dict_none_returns_empty(self):
        assert parse_multi_param("x", {"x": None}) == []


class TestParsePagination:
    def test_defaults_when_absent(self):
        page, per_page = parse_pagination(MultiDict())
        assert (page, per_page) == (1, 50)

    def test_reads_valid_values(self):
        src = MultiDict([("page", "3"), ("per_page", "25")])
        assert parse_pagination(src) == (3, 25)

    def test_page_clamped_to_minimum_one(self):
        src = MultiDict([("page", "0")])
        assert parse_pagination(src)[0] == 1

    def test_per_page_capped_at_max(self):
        src = MultiDict([("per_page", "9999")])
        assert parse_pagination(src, max_per_page=200)[1] == 200

    def test_per_page_floor_one(self):
        src = MultiDict([("per_page", "0")])
        assert parse_pagination(src)[1] == 1

    def test_non_integer_falls_back_to_defaults(self):
        src = MultiDict([("page", "abc"), ("per_page", "xyz")])
        assert parse_pagination(src, default_per_page=50) == (1, 50)

    def test_custom_keys_and_default(self):
        src = MultiDict([("p", "2"), ("size", "10")])
        page, per_page = parse_pagination(
            src, default_per_page=100, max_per_page=500, page_key="p", per_page_key="size"
        )
        assert (page, per_page) == (2, 10)

    def test_post_dict_source(self):
        assert parse_pagination({"page": 4, "per_page": 30}) == (4, 30)
