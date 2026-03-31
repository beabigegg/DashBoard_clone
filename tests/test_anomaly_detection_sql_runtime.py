# -*- coding: utf-8 -*-
"""Unit tests for anomaly_detection_sql_runtime.py — anomaly SQL helpers."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from mes_dashboard.services.anomaly_detection_sql_runtime import (
    _qid,
    _sql_str_literal,
    _sf,
    SQL_FALLBACK_DISABLED,
    SQL_FALLBACK_DEP_MISSING,
    SQL_FALLBACK_SPOOL_MISS,
    SQL_FALLBACK_RUNTIME_ERROR,
    _DEFAULT_YIELD_THRESHOLD,
    _DEFAULT_SPIKE_THRESHOLD,
    _DEFAULT_HOLD_PERCENTILE,
    _DEFAULT_DEVIATION_THRESHOLD,
)


class TestQidHelper:
    def test_simple_identifier(self):
        assert _qid("MY_COL") == '"MY_COL"'

    def test_identifier_with_double_quotes_escaped(self):
        result = _qid('col"name')
        assert '""' in result
        assert result.startswith('"')
        assert result.endswith('"')

    def test_empty_string(self):
        result = _qid("")
        assert result == '""'


class TestSqlStrLiteralHelper:
    def test_simple_string(self):
        assert _sql_str_literal("hello") == "'hello'"

    def test_string_with_single_quotes_escaped(self):
        result = _sql_str_literal("it's")
        assert "''" in result

    def test_empty_string(self):
        assert _sql_str_literal("") == "''"


class TestSfHelper:
    def test_converts_numeric_value(self):
        assert _sf(3.14) == 3.14

    def test_none_returns_default(self):
        assert _sf(None) == 0.0

    def test_none_returns_custom_default(self):
        assert _sf(None, default=99.0) == 99.0

    def test_invalid_string_returns_default(self):
        assert _sf("not-a-number") == 0.0

    def test_integer_converted_to_float(self):
        result = _sf(5)
        assert result == 5.0
        assert isinstance(result, float)


class TestFallbackConstants:
    def test_fallback_disabled(self):
        assert SQL_FALLBACK_DISABLED == "analytics_disabled"

    def test_fallback_dep_missing(self):
        assert SQL_FALLBACK_DEP_MISSING == "analytics_dependency_missing"

    def test_fallback_spool_miss(self):
        assert SQL_FALLBACK_SPOOL_MISS == "analytics_spool_miss"

    def test_fallback_runtime_error(self):
        assert SQL_FALLBACK_RUNTIME_ERROR == "analytics_runtime_error"


class TestThresholdDefaults:
    def test_yield_threshold_is_zscore(self):
        assert isinstance(_DEFAULT_YIELD_THRESHOLD, float)
        assert _DEFAULT_YIELD_THRESHOLD > 0

    def test_spike_threshold_is_percentage(self):
        assert _DEFAULT_SPIKE_THRESHOLD > 0

    def test_hold_percentile_is_between_0_and_1(self):
        assert 0 < _DEFAULT_HOLD_PERCENTILE < 1

    def test_deviation_threshold_is_positive(self):
        assert _DEFAULT_DEVIATION_THRESHOLD > 0
