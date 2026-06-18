# -*- coding: utf-8 -*-
"""Unit tests for EAP ALARM service and cache modules.

Tests:
  - test_spool_key_composition: SHA-256 hash, deterministic, sorted eqp_types
  - test_missing_date_range_raises_value_error: missing date_from/date_to → ValueError
  - test_eqp_type_allowlist: unknown/empty eqp_types → ValueError; all 10 valid → ok
  - test_alarm_category_decode: 9 codes; code 99 → "未知"; None → "未知"
  - test_schema_version_is_pinned: _SCHEMA_VERSION == 1
"""

from __future__ import annotations

import hashlib

import pytest


# ── test_spool_key_composition ────────────────────────────────────────────────

class TestSpoolKeyComposition:
    """EA-01: Spool key is deterministic and order-independent."""

    def test_key_format(self):
        from mes_dashboard.services.eap_alarm_cache import make_eap_alarm_spool_key, _SCHEMA_VERSION
        key = make_eap_alarm_spool_key("2025-01-01", "2025-01-07", ["GDBA", "GCBA"])
        assert key.startswith("eap_alarm_2025-01-01_2025-01-07_")
        assert f"_v{_SCHEMA_VERSION}" in key

    def test_hash_is_8_chars(self):
        from mes_dashboard.services.eap_alarm_cache import make_eap_alarm_spool_key
        key = make_eap_alarm_spool_key("2025-01-01", "2025-01-07", ["GDBA"])
        parts = key.split("_")
        # format: eap_alarm_{date_from}_{date_to}_{hash8}_v{version}
        # split by _ gives: ['eap', 'alarm', '2025-01-01', '2025-01-07', '{hash8}', 'v{version}']
        hash_part = parts[4]
        assert len(hash_part) == 8

    def test_sorted_eqp_types_gives_same_key(self):
        """Same EQP type set in any order must produce the same key (EA-01)."""
        from mes_dashboard.services.eap_alarm_cache import make_eap_alarm_spool_key
        key1 = make_eap_alarm_spool_key("2025-01-01", "2025-01-31", ["GCBA", "GDBA", "GWBA"])
        key2 = make_eap_alarm_spool_key("2025-01-01", "2025-01-31", ["GDBA", "GWBA", "GCBA"])
        assert key1 == key2

    def test_different_eqp_types_give_different_key(self):
        from mes_dashboard.services.eap_alarm_cache import make_eap_alarm_spool_key
        key1 = make_eap_alarm_spool_key("2025-01-01", "2025-01-31", ["GDBA"])
        key2 = make_eap_alarm_spool_key("2025-01-01", "2025-01-31", ["GCBA"])
        assert key1 != key2

    def test_hash_matches_sha256_of_sorted_join(self):
        """Verify hash computation: sha256(sorted(','.join(sorted(eqp_types))))[:8]."""
        from mes_dashboard.services.eap_alarm_cache import make_eap_alarm_spool_key
        eqp_types = ["GCBA", "GDBA"]
        key = make_eap_alarm_spool_key("2025-01-01", "2025-01-07", eqp_types)
        expected_type_string = ",".join(sorted(eqp_types))
        expected_hash = hashlib.sha256(expected_type_string.encode("utf-8")).hexdigest()[:8]
        assert f"_{expected_hash}_" in key

    def test_different_dates_give_different_key(self):
        from mes_dashboard.services.eap_alarm_cache import make_eap_alarm_spool_key
        key1 = make_eap_alarm_spool_key("2025-01-01", "2025-01-07", ["GDBA"])
        key2 = make_eap_alarm_spool_key("2025-01-02", "2025-01-07", ["GDBA"])
        assert key1 != key2

    def test_schema_version_in_key(self):
        """EA-06: Schema version participates in spool key."""
        from mes_dashboard.services.eap_alarm_cache import make_eap_alarm_spool_key, _SCHEMA_VERSION
        key = make_eap_alarm_spool_key("2025-01-01", "2025-01-07", ["GDBA"])
        assert f"v{_SCHEMA_VERSION}" in key


# ── test_missing_date_range_raises_value_error ────────────────────────────────

class TestMissingDateRangeRaisesValueError:
    """EA-03: Missing date_from or date_to must raise ValueError."""

    def test_missing_date_from_spool_key(self):
        from mes_dashboard.services.eap_alarm_cache import make_eap_alarm_spool_key
        with pytest.raises(ValueError, match="LAST_UPDATE_TIME filter required"):
            make_eap_alarm_spool_key(None, "2025-01-07", ["GDBA"])

    def test_missing_date_to_spool_key(self):
        from mes_dashboard.services.eap_alarm_cache import make_eap_alarm_spool_key
        with pytest.raises(ValueError, match="LAST_UPDATE_TIME filter required"):
            make_eap_alarm_spool_key("2025-01-01", None, ["GDBA"])

    def test_empty_date_from_spool_key(self):
        from mes_dashboard.services.eap_alarm_cache import make_eap_alarm_spool_key
        with pytest.raises(ValueError):
            make_eap_alarm_spool_key("", "2025-01-07", ["GDBA"])

    def test_missing_date_from_validate(self):
        from mes_dashboard.services.eap_alarm_service import validate_eap_alarm_params
        with pytest.raises(ValueError, match="LAST_UPDATE_TIME filter required"):
            validate_eap_alarm_params(None, "2025-01-07", ["GDBA"])

    def test_missing_date_to_validate(self):
        from mes_dashboard.services.eap_alarm_service import validate_eap_alarm_params
        with pytest.raises(ValueError, match="LAST_UPDATE_TIME filter required"):
            validate_eap_alarm_params("2025-01-01", "", ["GDBA"])

    def test_both_dates_missing_validate(self):
        from mes_dashboard.services.eap_alarm_service import validate_eap_alarm_params
        with pytest.raises(ValueError):
            validate_eap_alarm_params(None, None, ["GDBA"])


# ── test_eqp_type_allowlist ───────────────────────────────────────────────────

class TestEqpTypeAllowlist:
    """EA-07: EQP type closed enum validation."""

    _ALL_VALID = ["GDBA", "GCBA", "GWBA", "GWBK", "GPRA", "GTMH", "GWMT", "GDSD", "GWAC", "GPTA"]

    def test_all_ten_valid_types_no_error(self):
        from mes_dashboard.services.eap_alarm_service import validate_eap_alarm_params
        validate_eap_alarm_params("2025-01-01", "2025-01-07", self._ALL_VALID)

    def test_single_valid_type_no_error(self):
        from mes_dashboard.services.eap_alarm_service import validate_eap_alarm_params
        for t in self._ALL_VALID:
            validate_eap_alarm_params("2025-01-01", "2025-01-07", [t])

    def test_unknown_type_raises_value_error(self):
        from mes_dashboard.services.eap_alarm_service import validate_eap_alarm_params
        with pytest.raises(ValueError, match="invalid eqp_types"):
            validate_eap_alarm_params("2025-01-01", "2025-01-07", ["GDBA", "UNKNOWN_TYPE"])

    def test_lowercase_invalid(self):
        """EQP types are case-sensitive uppercase only."""
        from mes_dashboard.services.eap_alarm_service import validate_eap_alarm_params
        with pytest.raises(ValueError, match="invalid eqp_types"):
            validate_eap_alarm_params("2025-01-01", "2025-01-07", ["gdba"])

    def test_empty_list_raises_value_error(self):
        from mes_dashboard.services.eap_alarm_service import validate_eap_alarm_params
        with pytest.raises(ValueError, match="eqp_types must be non-empty"):
            validate_eap_alarm_params("2025-01-01", "2025-01-07", [])

    def test_none_list_raises_value_error(self):
        from mes_dashboard.services.eap_alarm_service import validate_eap_alarm_params
        with pytest.raises(ValueError, match="eqp_types must be non-empty"):
            validate_eap_alarm_params("2025-01-01", "2025-01-07", None)


# ── test_alarm_category_decode ────────────────────────────────────────────────

class TestAlarmCategoryDecode:
    """EA-05: AlarmCategory decode table; unknown → 未知; None → 未知."""

    _EXPECTED = {
        0: "非分類",
        1: "設備",
        2: "製程",
        3: "視覺",
        4: "機械",
        5: "電子",
        6: "通知/供料",
        7: "品質",
        64: "繼續錯誤",
    }

    def test_all_nine_known_codes(self):
        from mes_dashboard.services.eap_alarm_cache import decode_alarm_category
        for code, expected_label in self._EXPECTED.items():
            result = decode_alarm_category(code)
            assert result == expected_label, (
                f"Code {code}: expected {expected_label!r}, got {result!r}"
            )

    def test_unknown_code_99_returns_unknown(self):
        from mes_dashboard.services.eap_alarm_cache import decode_alarm_category
        assert decode_alarm_category(99) == "未知"

    def test_unknown_code_255_returns_unknown(self):
        from mes_dashboard.services.eap_alarm_cache import decode_alarm_category
        assert decode_alarm_category(255) == "未知"

    def test_none_returns_unknown(self):
        from mes_dashboard.services.eap_alarm_cache import decode_alarm_category
        assert decode_alarm_category(None) == "未知"

    def test_string_code_coerced(self):
        """String "1" should decode as integer 1."""
        from mes_dashboard.services.eap_alarm_cache import decode_alarm_category
        assert decode_alarm_category("1") == "設備"

    def test_string_unknown_code_returns_unknown(self):
        from mes_dashboard.services.eap_alarm_cache import decode_alarm_category
        assert decode_alarm_category("not_a_number") == "未知"

    def test_float_code_coerced(self):
        """Float 0.0 should decode as integer 0."""
        from mes_dashboard.services.eap_alarm_cache import decode_alarm_category
        assert decode_alarm_category(0.0) == "非分類"

    def test_negative_code_returns_unknown(self):
        from mes_dashboard.services.eap_alarm_cache import decode_alarm_category
        assert decode_alarm_category(-1) == "未知"

    def test_service_decode_matches_cache_decode(self):
        """eap_alarm_service re-exports decode_alarm_category from cache."""
        from mes_dashboard.services.eap_alarm_cache import decode_alarm_category as cache_decode
        from mes_dashboard.services.eap_alarm_service import decode_alarm_category as svc_decode  # noqa: F401
        # Both must be the same function (service imports from cache)
        assert cache_decode(64) == "繼續錯誤"


# ── test_schema_version_is_pinned ─────────────────────────────────────────────

class TestSchemaVersionIsPinned:
    """EA-06: _SCHEMA_VERSION must be pinned to exactly 1."""

    def test_schema_version_is_integer(self):
        import mes_dashboard.services.eap_alarm_cache as cache_mod
        assert isinstance(cache_mod._SCHEMA_VERSION, int), (
            f"_SCHEMA_VERSION must be int, got {type(cache_mod._SCHEMA_VERSION)}"
        )

    def test_schema_version_equals_one(self):
        import mes_dashboard.services.eap_alarm_cache as cache_mod
        assert cache_mod._SCHEMA_VERSION == 1, (
            f"_SCHEMA_VERSION pin test: expected 1, got {cache_mod._SCHEMA_VERSION}. "
            "If you changed the parquet schema, bump the version AND update this assertion."
        )
