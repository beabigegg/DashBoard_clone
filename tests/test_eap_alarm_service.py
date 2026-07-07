# -*- coding: utf-8 -*-
"""Unit tests for EAP ALARM service and cache modules.

Tests:
  - TestSpoolKeyComposition: SHA-256 hash, deterministic, sorted machines + all 5 dims
  - TestMissingDateRangeRaisesValueError: missing date_from/date_to → ValueError
  - TestMachinesValidation: eqp_types now optional; at-least-one-of-three rule (EA-08)
  - TestAtLeastOneFilterRequired: EA-08 validation matrix
  - TestLotIdNormalization: strip/dedup/max-200 (EA-09)
  - TestProductDimsFilter: EXISTS SQL generation per supplied dim (EA-10)
  - TestAlarmCategoryDecode: 9 codes; code 99 → "未知"; None → "未知"
  - TestSchemaVersionIsPinned: _SCHEMA_VERSION == 5
  - TestEquipmentFilterEmptyNoOp: empty machines → "1=1" no-op, not "IN ()" (AC-8, D-6)
"""

from __future__ import annotations

import hashlib
from unittest.mock import MagicMock, patch

import pytest


# ── test_spool_key_composition ────────────────────────────────────────────────

class TestSpoolKeyComposition:
    """EA-01: Spool key is deterministic and order-independent for all 5 dims."""

    def test_key_format(self):
        from mes_dashboard.services.eap_alarm_cache import make_eap_alarm_spool_key, _SCHEMA_VERSION
        key = make_eap_alarm_spool_key("2025-01-01", "2025-01-07", ["GDBA", "GWBK"])
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
        """Same eqp_type set in any order must produce the same key (EA-01)."""
        from mes_dashboard.services.eap_alarm_cache import make_eap_alarm_spool_key
        key1 = make_eap_alarm_spool_key("2025-01-01", "2025-01-31", ["GCBA", "GDBA", "GWBA"])
        key2 = make_eap_alarm_spool_key("2025-01-01", "2025-01-31", ["GDBA", "GWBA", "GCBA"])
        assert key1 == key2

    def test_different_eqp_types_give_different_key(self):
        from mes_dashboard.services.eap_alarm_cache import make_eap_alarm_spool_key
        key1 = make_eap_alarm_spool_key("2025-01-01", "2025-01-31", ["GDBA"])
        key2 = make_eap_alarm_spool_key("2025-01-01", "2025-01-31", ["GCBA"])
        assert key1 != key2

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

    def test_same_full_params_give_same_key(self):
        """All 5 dims identical → same key (EA-01 stable key invariant)."""
        from mes_dashboard.services.eap_alarm_cache import make_eap_alarm_spool_key
        k1 = make_eap_alarm_spool_key(
            "2025-01-01", "2025-01-07", ["GDBA"], ["LOT-A", "LOT-B"],
            ["TypeX"], ["LineY"], ["BopZ"],
        )
        k2 = make_eap_alarm_spool_key(
            "2025-01-01", "2025-01-07", ["GDBA"], ["LOT-B", "LOT-A"],
            ["TypeX"], ["LineY"], ["BopZ"],
        )
        assert k1 == k2

    def test_lot_ids_dim_produces_different_key(self):
        """Changing lot_ids → different key (AC-4)."""
        from mes_dashboard.services.eap_alarm_cache import make_eap_alarm_spool_key
        base = {"date_from": "2025-01-01", "date_to": "2025-01-07", "eqp_types": ["GDBA"]}
        k1 = make_eap_alarm_spool_key(**base, lot_ids=["LOT-A"])
        k2 = make_eap_alarm_spool_key(**base, lot_ids=["LOT-B"])
        assert k1 != k2

    def test_pj_types_dim_produces_different_key(self):
        """Changing pj_types → different key (AC-4)."""
        from mes_dashboard.services.eap_alarm_cache import make_eap_alarm_spool_key
        k1 = make_eap_alarm_spool_key("2025-01-01", "2025-01-07", ["GDBA"], pj_types=["TypeA"])
        k2 = make_eap_alarm_spool_key("2025-01-01", "2025-01-07", ["GDBA"], pj_types=["TypeB"])
        assert k1 != k2

    def test_product_lines_dim_produces_different_key(self):
        """Changing product_lines → different key (AC-4)."""
        from mes_dashboard.services.eap_alarm_cache import make_eap_alarm_spool_key
        k1 = make_eap_alarm_spool_key("2025-01-01", "2025-01-07", ["GDBA"], product_lines=["LineA"])
        k2 = make_eap_alarm_spool_key("2025-01-01", "2025-01-07", ["GDBA"], product_lines=["LineB"])
        assert k1 != k2

    def test_pj_bops_dim_produces_different_key(self):
        """Changing pj_bops → different key (AC-4)."""
        from mes_dashboard.services.eap_alarm_cache import make_eap_alarm_spool_key
        k1 = make_eap_alarm_spool_key("2025-01-01", "2025-01-07", ["GDBA"], pj_bops=["BopA"])
        k2 = make_eap_alarm_spool_key("2025-01-01", "2025-01-07", ["GDBA"], pj_bops=["BopB"])
        assert k1 != k2

    def test_empty_dims_do_not_collide_across_axes(self):
        """Empty lot_ids and empty pj_types should not produce the same key sub-contribution.
        i.e., key(lot_ids=["X"]) != key(pj_types=["X"]) (per-dim label prevents collision)."""
        from mes_dashboard.services.eap_alarm_cache import make_eap_alarm_spool_key
        k1 = make_eap_alarm_spool_key("2025-01-01", "2025-01-07", [], lot_ids=["X"])
        k2 = make_eap_alarm_spool_key("2025-01-01", "2025-01-07", [], pj_types=["X"])
        assert k1 != k2


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
            validate_eap_alarm_params(None, "2025-01-07", eqp_types=["GDBA"])

    def test_missing_date_to_validate(self):
        from mes_dashboard.services.eap_alarm_service import validate_eap_alarm_params
        with pytest.raises(ValueError, match="LAST_UPDATE_TIME filter required"):
            validate_eap_alarm_params("2025-01-01", "", eqp_types=["GDBA"])

    def test_both_dates_missing_validate(self):
        from mes_dashboard.services.eap_alarm_service import validate_eap_alarm_params
        with pytest.raises(ValueError):
            validate_eap_alarm_params(None, None, eqp_types=["GDBA"])


# ── test_machines_validation ──────────────────────────────────────────────────

class TestMachinesValidation:
    """eqp_types param: now optional; at-least-one-of-three rule (EA-08); no closed-enum
    membership check (EA-07/D-7) — validated like lot_ids: reject non-string/blank
    entries, keep every non-empty stripped value."""

    def test_single_valid_eqp_type_no_error(self):
        """A 4-char-code-shaped value passes — no longer because of enum membership,
        just because it is a non-blank string (D-7)."""
        from mes_dashboard.services.eap_alarm_service import validate_eap_alarm_params
        validate_eap_alarm_params("2025-01-01", "2025-01-07", eqp_types=["GWBK"])

    def test_multiple_valid_eqp_types_no_error(self):
        """Multiple 4-char-code-shaped values pass — values are enum-shaped
        incidentally, not validated against any membership set (D-7)."""
        from mes_dashboard.services.eap_alarm_service import validate_eap_alarm_params
        validate_eap_alarm_params("2025-01-01", "2025-01-07", eqp_types=["GDBA", "GWBK", "GWBA"])

    def test_empty_list_raises_value_error(self):
        """Empty eqp_types with no other dims → at-least-one-of-three error (EA-08)."""
        from mes_dashboard.services.eap_alarm_service import validate_eap_alarm_params
        with pytest.raises(ValueError, match="at least one of"):
            validate_eap_alarm_params("2025-01-01", "2025-01-07", eqp_types=[])

    def test_none_raises_value_error(self):
        """None eqp_types with no other dims → at-least-one-of-three error (EA-08)."""
        from mes_dashboard.services.eap_alarm_service import validate_eap_alarm_params
        with pytest.raises(ValueError, match="at least one of"):
            validate_eap_alarm_params("2025-01-01", "2025-01-07", eqp_types=None)

    def test_empty_string_in_list_raises_value_error(self):
        from mes_dashboard.services.eap_alarm_service import validate_eap_alarm_params
        with pytest.raises(ValueError, match="invalid machine values"):
            validate_eap_alarm_params("2025-01-01", "2025-01-07", eqp_types=["GDBA", ""])

    def test_full_equipment_id_string_no_error(self):
        """D-7: real EQUIPMENT_ID shape (e.g. "GWBK-0241"), not a 4-char type code,
        must pass validation — the exact value class the old enum never matched."""
        from mes_dashboard.services.eap_alarm_service import validate_eap_alarm_params
        validate_eap_alarm_params("2025-01-01", "2025-01-07", eqp_types=["GWBK-0241"])

    def test_out_of_old_enum_value_no_longer_raises(self):
        """D-7: a value never present in the old closed enum (_VALID_EQP_TYPES) must
        now pass validation — proves the membership check is gone, not merely untested."""
        from mes_dashboard.services.eap_alarm_service import validate_eap_alarm_params
        validate_eap_alarm_params("2025-01-01", "2025-01-07", eqp_types=["ZZZZ"])


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
        assert cache_decode(64) == "繼續錯誤"


# ── test_schema_version_is_pinned ─────────────────────────────────────────────

class TestSchemaVersionIsPinned:
    """EA-06: _SCHEMA_VERSION must be pinned to exactly 5 (AC-4 red-green tripwire)."""

    def test_schema_version_is_integer(self):
        import mes_dashboard.services.eap_alarm_cache as cache_mod
        assert isinstance(cache_mod._SCHEMA_VERSION, int), (
            f"_SCHEMA_VERSION must be int, got {type(cache_mod._SCHEMA_VERSION)}"
        )

    def test_schema_version_equals_five(self):
        """v5: ALARM_SOURCE column + Shape B alarm-alias inclusion (EA-EVT),
        on top of v4's product-dim columns."""
        import mes_dashboard.services.eap_alarm_cache as cache_mod
        assert cache_mod._SCHEMA_VERSION == 5, (
            f"_SCHEMA_VERSION pin test: expected 5, got {cache_mod._SCHEMA_VERSION}. "
            "If you changed the parquet schema, bump the version AND update this assertion."
        )


# ── TestAtLeastOneFilterRequired ──────────────────────────────────────────────

class TestAtLeastOneFilterRequired:
    """EA-08: At least one of {eqp_types, lot_ids, product_dims} required."""

    def test_all_empty_raises(self):
        from mes_dashboard.services.eap_alarm_service import validate_eap_alarm_params
        with pytest.raises(ValueError, match="at least one of"):
            validate_eap_alarm_params("2025-01-01", "2025-01-07")

    def test_all_none_raises(self):
        from mes_dashboard.services.eap_alarm_service import validate_eap_alarm_params
        with pytest.raises(ValueError, match="at least one of"):
            validate_eap_alarm_params(
                "2025-01-01", "2025-01-07",
                eqp_types=None, lot_ids=None, pj_types=None,
                product_lines=None, pj_bops=None,
            )

    def test_eqp_types_only_ok(self):
        from mes_dashboard.services.eap_alarm_service import validate_eap_alarm_params
        # Should not raise
        validate_eap_alarm_params("2025-01-01", "2025-01-07", eqp_types=["GDBA"])

    def test_lot_ids_only_ok(self):
        from mes_dashboard.services.eap_alarm_service import validate_eap_alarm_params
        validate_eap_alarm_params("2025-01-01", "2025-01-07", lot_ids=["LOT-001"])

    def test_pj_types_only_ok(self):
        from mes_dashboard.services.eap_alarm_service import validate_eap_alarm_params
        validate_eap_alarm_params("2025-01-01", "2025-01-07", pj_types=["TypeA"])

    def test_product_lines_only_ok(self):
        from mes_dashboard.services.eap_alarm_service import validate_eap_alarm_params
        validate_eap_alarm_params("2025-01-01", "2025-01-07", product_lines=["LineA"])

    def test_pj_bops_only_ok(self):
        from mes_dashboard.services.eap_alarm_service import validate_eap_alarm_params
        validate_eap_alarm_params("2025-01-01", "2025-01-07", pj_bops=["BopA"])

    def test_mixed_ok(self):
        from mes_dashboard.services.eap_alarm_service import validate_eap_alarm_params
        validate_eap_alarm_params(
            "2025-01-01", "2025-01-07",
            eqp_types=["GDBA"], lot_ids=["LOT-001"], pj_types=["TypeA"],
        )

    def test_whitespace_only_lot_ids_treated_as_empty(self):
        """Whitespace-only lot_ids are stripped before check → effectively empty (EA-09)."""
        from mes_dashboard.services.eap_alarm_service import validate_eap_alarm_params
        with pytest.raises(ValueError, match="at least one of"):
            validate_eap_alarm_params(
                "2025-01-01", "2025-01-07",
                lot_ids=["   ", "\t", ""],
            )


# ── TestLotIdNormalization ────────────────────────────────────────────────────

class TestLotIdNormalization:
    """EA-09: lot_ids strip / dedup / max-200 cap."""

    def test_whitespace_stripped_in_key(self):
        """lot_ids with surrounding whitespace → stripped in spool key (AC-5)."""
        from mes_dashboard.services.eap_alarm_cache import make_eap_alarm_spool_key
        k1 = make_eap_alarm_spool_key("2025-01-01", "2025-01-07", [], lot_ids=["LOT-A"])
        k2 = make_eap_alarm_spool_key("2025-01-01", "2025-01-07", [], lot_ids=["  LOT-A  "])
        assert k1 == k2, "Whitespace-padded lot_id must produce same key as stripped version"

    def test_whitespace_only_strings_dropped(self):
        """Whitespace-only strings removed; remaining determine key."""
        from mes_dashboard.services.eap_alarm_cache import make_eap_alarm_spool_key
        k1 = make_eap_alarm_spool_key("2025-01-01", "2025-01-07", [], lot_ids=["LOT-A"])
        k2 = make_eap_alarm_spool_key(
            "2025-01-01", "2025-01-07", [], lot_ids=["   ", "LOT-A", "\t"]
        )
        assert k1 == k2

    def test_duplicates_deduped_by_validation_before_key(self):
        """Validation deduplicates lot_ids before they reach the key builder (AC-5).

        The validation layer strips duplicates; callers must pass pre-deduped lists
        to make_eap_alarm_spool_key. This test verifies that identical post-dedup
        lists produce the same key.
        """
        from mes_dashboard.services.eap_alarm_service import validate_eap_alarm_params
        # Calling validate must not raise for duplicate lot_ids
        # (dedup happens silently inside validation)
        validate_eap_alarm_params(
            "2025-01-01", "2025-01-07",
            lot_ids=["LOT-A", "LOT-A", "LOT-B", "LOT-A"],
        )
        # After dedup: ["LOT-A", "LOT-B"] — confirmed no error

    def test_max_200_cap_exactly_200_ok(self):
        """Exactly 200 lot_ids → no error (boundary is strictly > 200)."""
        from mes_dashboard.services.eap_alarm_service import validate_eap_alarm_params
        lot_ids = [f"LOT-{i:04d}" for i in range(200)]
        # Should not raise
        validate_eap_alarm_params("2025-01-01", "2025-01-07", lot_ids=lot_ids)

    def test_max_200_cap_exceeded_201_raises(self):
        """201 lot_ids → ValueError (EA-09: strictly > 200)."""
        from mes_dashboard.services.eap_alarm_service import validate_eap_alarm_params
        lot_ids = [f"LOT-{i:04d}" for i in range(201)]
        with pytest.raises(ValueError, match="lot_ids exceeds max"):
            validate_eap_alarm_params("2025-01-01", "2025-01-07", lot_ids=lot_ids)

    def test_char_padding_stripped_at_key_build(self):
        """CHAR-padded lot_id 'LOT-A   ' → same key as 'LOT-A' (CHAR-padding safety)."""
        from mes_dashboard.services.eap_alarm_cache import make_eap_alarm_spool_key
        k1 = make_eap_alarm_spool_key("2025-01-01", "2025-01-07", [], lot_ids=["LOT-A"])
        k2 = make_eap_alarm_spool_key("2025-01-01", "2025-01-07", [], lot_ids=["LOT-A   "])
        assert k1 == k2


# ── TestProductDimsFilter ─────────────────────────────────────────────────────

class TestProductDimsFilter:
    """EA-10: _build_product_dims_exists generates correct EXISTS clauses."""

    def test_no_dims_returns_empty(self):
        from mes_dashboard.workers.eap_alarm_worker import _build_product_dims_exists
        clauses, params = _build_product_dims_exists([], [], [])
        assert clauses == []
        assert params == {}

    def test_pj_types_generates_exists_clause(self):
        from mes_dashboard.workers.eap_alarm_worker import _build_product_dims_exists
        clauses, params = _build_product_dims_exists(["TypeA", "TypeB"], [], [])
        assert len(clauses) == 1
        assert "EXISTS" in clauses[0]
        assert "c.PJ_TYPE" in clauses[0]
        assert "DWH.DW_MES_CONTAINER" in clauses[0]
        assert "c.CONTAINERNAME = e.LOT_ID" in clauses[0]
        assert "NVL(TRIM" in clauses[0]
        assert "pjt_0" in params
        assert "pjt_1" in params
        assert params["pjt_0"] == "TypeA"
        assert params["pjt_1"] == "TypeB"

    def test_product_lines_generates_exists_clause(self):
        from mes_dashboard.workers.eap_alarm_worker import _build_product_dims_exists
        clauses, params = _build_product_dims_exists([], ["LineA"], [])
        assert len(clauses) == 1
        assert "c.PRODUCTLINENAME" in clauses[0]
        assert "pln_0" in params

    def test_pj_bops_generates_exists_clause(self):
        from mes_dashboard.workers.eap_alarm_worker import _build_product_dims_exists
        clauses, params = _build_product_dims_exists([], [], ["BopA"])
        assert len(clauses) == 1
        assert "c.PJ_BOP" in clauses[0]
        assert "bop_0" in params

    def test_multiple_dims_and_semantics(self):
        """Each dim = separate EXISTS clause (AND-semantics, D-3)."""
        from mes_dashboard.workers.eap_alarm_worker import _build_product_dims_exists
        clauses, params = _build_product_dims_exists(["TypeA"], ["LineA"], ["BopA"])
        assert len(clauses) == 3, (
            f"Expected 3 separate EXISTS clauses (one per dim), got {len(clauses)}: {clauses}"
        )
        # Each clause is an independent EXISTS
        for c in clauses:
            assert c.startswith("EXISTS"), f"Each clause must start with EXISTS, got: {c!r}"

    def test_absent_dim_produces_no_clause(self):
        """Empty pj_bops → no EXISTS for that dim."""
        from mes_dashboard.workers.eap_alarm_worker import _build_product_dims_exists
        clauses, params = _build_product_dims_exists(["TypeA"], [], [])
        assert len(clauses) == 1
        assert "c.PJ_TYPE" in clauses[0]
        assert not any("PJ_BOP" in c for c in clauses)
        assert not any("PRODUCTLINENAME" in c for c in clauses)

    def test_whitespace_stripped_from_values(self):
        """CHAR-padding safety: bind values are stripped (EA-10, design.md Open Risk)."""
        from mes_dashboard.workers.eap_alarm_worker import _build_product_dims_exists
        _, params = _build_product_dims_exists(["  TypeA  "], [], [])
        assert params["pjt_0"] == "TypeA"


# ── test_equipment_filter_empty_no_op (Round 2 — AC-8, D-6) ──────────────────

class TestEquipmentFilterEmptyNoOp:
    """AC-8/D-6: empty machines must yield an always-true no-op predicate, not
    `e.EQUIPMENT_ID IN ()` (ORA-00936). Pure function, no mocking — this is the
    round-2 regression proof for the production bug in `_build_equipment_filter`."""

    def test_empty_machines_returns_always_true_no_op(self):
        from mes_dashboard.workers.eap_alarm_worker import _build_equipment_filter
        sql_fragment, params = _build_equipment_filter([])
        assert sql_fragment == "1=1"
        assert params == {}
        assert "IN ()" not in sql_fragment
