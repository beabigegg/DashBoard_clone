# -*- coding: utf-8 -*-
"""Tier-0 (no Oracle) tests for query-tool partial-trackout aggregation.

Covers:
- SQL structure (no ROW_NUMBER dedup in lot_history, equipment_lots, adjacent_lots)
- aggregate_partial_trackouts function logic
- Strict guard (divergent non-key → raw rows)
- Decrementing TRACKINQTY fixture (MES domain semantics)
- API response shape (partial_count field)
- Contract file presence (QT-05, QT-06, partial_count)
"""

from __future__ import annotations

import pathlib
import re
import unittest
from datetime import datetime

import pandas as pd

from mes_dashboard.services.query_tool_sql_runtime import (
    aggregate_partial_trackouts,
    _PARTIAL_KEY_COLS_4,
    _PARTIAL_KEY_COLS_3,
    _PARTIAL_NONKEY_COLS_LOT,
    _PARTIAL_NONKEY_COLS_ADJACENT,
)

# ── Fixture helpers ────────────────────────────────────────────────────────────

_T1 = datetime(2024, 1, 15, 8, 0, 0)
_T2 = datetime(2024, 1, 15, 10, 0, 0)


def _lot_row(
    *,
    container_id: str = "AAAA000000000001",
    equipment_id: str = "EQ01",
    spec_name: str = "SPEC_A",
    trackin_ts: datetime = _T1,
    trackout_ts: datetime | None = None,
    trackin_qty: int = 100,
    trackout_qty: int = 100,
    workcenter: str = "WC01",
    equip_name: str = "EQ_NAME_01",
    finishedruncard: str = "RC01",
    pj_workorder: str = "WO01",
    containername: str = "LOT_A",
    pj_type: str = "TYPE_A",
    pj_bop: str = "BOP_A",
    wafer_lot_id: str = "W_LOT_01",
) -> dict:
    return {
        "CONTAINERID": container_id,
        "EQUIPMENTID": equipment_id,
        "SPECNAME": spec_name,
        "TRACKINTIMESTAMP": trackin_ts,
        "TRACKOUTTIMESTAMP": trackout_ts or _T1,
        "TRACKINQTY": trackin_qty,
        "TRACKOUTQTY": trackout_qty,
        "WORKCENTERNAME": workcenter,
        "EQUIPMENTNAME": equip_name,
        "FINISHEDRUNCARD": finishedruncard,
        "PJ_WORKORDER": pj_workorder,
        "CONTAINERNAME": containername,
        "PJ_TYPE": pj_type,
        "PJ_BOP": pj_bop,
        "WAFER_LOT_ID": wafer_lot_id,
    }


def _adj_row(
    *,
    container_id: str = "AAAA000000000001",
    equipment_id: str = "EQ01",
    spec_name: str = "SPEC_A",
    trackin_ts: datetime = _T1,
    trackout_ts: datetime | None = None,
    trackin_qty: int = 100,
    trackout_qty: int = 100,
    relative_position: int = 0,
    equip_name: str = "EQ_NAME_01",
    finishedruncard: str = "RC01",
    pj_workorder: str = "WO01",
    containername: str = "LOT_A",
    pj_type: str = "TYPE_A",
    pj_bop: str = "BOP_A",
    wafer_lot_id: str = "W_LOT_01",
) -> dict:
    return {
        "CONTAINERID": container_id,
        "EQUIPMENTID": equipment_id,
        "SPECNAME": spec_name,
        "TRACKINTIMESTAMP": trackin_ts,
        "TRACKOUTTIMESTAMP": trackout_ts or _T1,
        "TRACKINQTY": trackin_qty,
        "TRACKOUTQTY": trackout_qty,
        "EQUIPMENTNAME": equip_name,
        "FINISHEDRUNCARD": finishedruncard,
        "PJ_WORKORDER": pj_workorder,
        "CONTAINERNAME": containername,
        "PJ_TYPE": pj_type,
        "PJ_BOP": pj_bop,
        "WAFER_LOT_ID": wafer_lot_id,
        "RELATIVE_POSITION": relative_position,
    }


# ── SQL paths ──────────────────────────────────────────────────────────────────

_BASE = pathlib.Path(__file__).parent.parent
_LOT_HISTORY_SQL = (_BASE / "src/mes_dashboard/sql/query_tool/lot_history.sql").read_text()
_EQUIP_LOTS_SQL = (_BASE / "src/mes_dashboard/sql/query_tool/equipment_lots.sql").read_text()
_ADJACENT_SQL = (_BASE / "src/mes_dashboard/sql/query_tool/adjacent_lots.sql").read_text()
_BUSINESS_RULES = (_BASE / "contracts/business/business-rules.md").read_text()
_DATA_SHAPE = (_BASE / "contracts/data/data-shape-contract.md").read_text()


# ==============================================================================
# SQL Structure Tests
# ==============================================================================

class TestLotHistorySqlStructure(unittest.TestCase):

    def test_lot_history_sql_has_no_row_number_dedup(self):
        """lot_history.sql must not use ROW_NUMBER() for dedup."""
        self.assertNotIn(
            "ROW_NUMBER()",
            _LOT_HISTORY_SQL.upper(),
            "lot_history.sql should not contain ROW_NUMBER() dedup",
        )

    def test_lot_history_sql_has_group_by_four_tuple(self):
        """lot_history.sql must not filter rn=1 and must ORDER BY TRACKINTIMESTAMP."""
        self.assertNotIn("WHERE rn = 1", _LOT_HISTORY_SQL)
        self.assertIn("ORDER BY TRACKINTIMESTAMP", _LOT_HISTORY_SQL)

    def test_lot_history_sql_projects_partial_count(self):
        """partial_count is added by Python layer; verify aggregation produces it."""
        row1 = _lot_row(trackout_ts=datetime(2024, 1, 15, 9, 0), trackout_qty=50)
        row2 = _lot_row(
            trackin_qty=50, trackout_qty=50, trackout_ts=datetime(2024, 1, 15, 10, 0)
        )
        df = pd.DataFrame([row1, row2])
        result = aggregate_partial_trackouts(df, _PARTIAL_KEY_COLS_4, _PARTIAL_NONKEY_COLS_LOT)
        self.assertIn("partial_count", result.columns)

    def test_lot_history_sql_projects_trackinqty_max(self):
        """TRACKINQTY must appear in lot_history.sql."""
        self.assertIn("TRACKINQTY", _LOT_HISTORY_SQL)

    def test_lot_history_sql_projects_trackoutqty_sum(self):
        """TRACKOUTQTY must appear in lot_history.sql."""
        self.assertIn("TRACKOUTQTY", _LOT_HISTORY_SQL)


class TestEquipmentLotsSqlStructure(unittest.TestCase):

    def test_equipment_lots_sql_has_no_row_number_dedup(self):
        """equipment_lots.sql must not use ROW_NUMBER() for dedup."""
        self.assertNotIn(
            "ROW_NUMBER()",
            _EQUIP_LOTS_SQL.upper(),
            "equipment_lots.sql should not contain ROW_NUMBER() dedup",
        )

    def test_equipment_lots_sql_has_group_by_four_tuple(self):
        """equipment_lots.sql must not filter rn=1."""
        self.assertNotIn("WHERE rn = 1", _EQUIP_LOTS_SQL)

    def test_equipment_lots_sql_projects_partial_count(self):
        """partial_count is added by Python layer; verify aggregation produces it."""
        row1 = _lot_row(trackout_ts=datetime(2024, 1, 15, 9, 0), trackout_qty=50)
        row2 = _lot_row(
            trackin_qty=50, trackout_qty=50, trackout_ts=datetime(2024, 1, 15, 10, 0)
        )
        df = pd.DataFrame([row1, row2])
        result = aggregate_partial_trackouts(df, _PARTIAL_KEY_COLS_4, _PARTIAL_NONKEY_COLS_LOT)
        self.assertIn("partial_count", result.columns)


class TestAdjacentLotsSqlStructure(unittest.TestCase):

    def test_adjacent_lots_inner_dedup_is_group_by_three_tuple(self):
        """adjacent_lots.sql inner dedup_rn must be removed."""
        self.assertNotIn("dedup_rn", _ADJACENT_SQL)
        self.assertNotIn("deduped_lots", _ADJACENT_SQL)

    def test_adjacent_lots_outer_row_number_preserved(self):
        """adjacent_lots.sql must still contain outer ROW_NUMBER() OVER for rn."""
        # The outer ranked_lots CTE uses ROW_NUMBER() OVER (PARTITION BY EQUIPMENTID ...)
        self.assertIn("ROW_NUMBER() OVER", _ADJACENT_SQL)

    def test_adjacent_lots_sql_projects_partial_count(self):
        """RELATIVE_POSITION must still be projected in adjacent_lots.sql (outer structure preserved)."""
        self.assertIn("RELATIVE_POSITION", _ADJACENT_SQL)


# ==============================================================================
# Aggregation Tests
# ==============================================================================

class TestLotHistoryAggregation(unittest.TestCase):

    def test_two_partials_same_trackin_merge_to_one_row(self):
        row1 = _lot_row(trackout_ts=datetime(2024, 1, 15, 9, 0), trackout_qty=60)
        row2 = _lot_row(
            trackin_qty=40, trackout_qty=40, trackout_ts=datetime(2024, 1, 15, 10, 0)
        )
        df = pd.DataFrame([row1, row2])
        result = aggregate_partial_trackouts(df, _PARTIAL_KEY_COLS_4, _PARTIAL_NONKEY_COLS_LOT)
        self.assertEqual(len(result), 1)

    def test_partial_count_equals_group_size(self):
        row1 = _lot_row(trackout_ts=datetime(2024, 1, 15, 9, 0), trackout_qty=60)
        row2 = _lot_row(
            trackin_qty=40, trackout_qty=40, trackout_ts=datetime(2024, 1, 15, 10, 0)
        )
        df = pd.DataFrame([row1, row2])
        result = aggregate_partial_trackouts(df, _PARTIAL_KEY_COLS_4, _PARTIAL_NONKEY_COLS_LOT)
        self.assertEqual(int(result.iloc[0]["partial_count"]), 2)

    def test_different_trackin_timestamps_not_merged(self):
        row1 = _lot_row(trackin_ts=_T1)
        row2 = _lot_row(trackin_ts=_T2)
        df = pd.DataFrame([row1, row2])
        result = aggregate_partial_trackouts(df, _PARTIAL_KEY_COLS_4, _PARTIAL_NONKEY_COLS_LOT)
        self.assertEqual(len(result), 2)
        self.assertTrue(all(int(r) == 1 for r in result["partial_count"]))

    def test_trackouttimestamp_is_max_over_group(self):
        ts_early = datetime(2024, 1, 15, 9, 0)
        ts_late = datetime(2024, 1, 15, 10, 30)
        row1 = _lot_row(trackout_ts=ts_early, trackout_qty=60)
        row2 = _lot_row(trackin_qty=40, trackout_qty=40, trackout_ts=ts_late)
        df = pd.DataFrame([row1, row2])
        result = aggregate_partial_trackouts(df, _PARTIAL_KEY_COLS_4, _PARTIAL_NONKEY_COLS_LOT)
        self.assertEqual(result.iloc[0]["TRACKOUTTIMESTAMP"], ts_late)


class TestEquipmentLotsAggregation(unittest.TestCase):

    def test_two_partials_same_trackin_merge_to_one_row(self):
        row1 = _lot_row(trackout_qty=70)
        row2 = _lot_row(trackin_qty=30, trackout_qty=30)
        df = pd.DataFrame([row1, row2])
        result = aggregate_partial_trackouts(df, _PARTIAL_KEY_COLS_4, _PARTIAL_NONKEY_COLS_LOT)
        self.assertEqual(len(result), 1)

    def test_partial_count_equals_group_size(self):
        row1 = _lot_row(trackout_qty=70)
        row2 = _lot_row(trackin_qty=30, trackout_qty=30)
        df = pd.DataFrame([row1, row2])
        result = aggregate_partial_trackouts(df, _PARTIAL_KEY_COLS_4, _PARTIAL_NONKEY_COLS_LOT)
        self.assertEqual(int(result.iloc[0]["partial_count"]), 2)

    def test_trackinqty_is_max_trackoutqty_is_sum(self):
        row1 = _lot_row(trackin_qty=100, trackout_qty=70)
        row2 = _lot_row(trackin_qty=30, trackout_qty=30)
        df = pd.DataFrame([row1, row2])
        result = aggregate_partial_trackouts(df, _PARTIAL_KEY_COLS_4, _PARTIAL_NONKEY_COLS_LOT)
        self.assertEqual(result.iloc[0]["TRACKINQTY"], 100)
        self.assertEqual(result.iloc[0]["TRACKOUTQTY"], 100)


class TestAdjacentLotsAggregation(unittest.TestCase):

    def test_two_partials_same_trackin_merge_in_inner_dedup(self):
        row1 = _adj_row(trackout_qty=60, relative_position=0)
        row2 = _adj_row(trackin_qty=40, trackout_qty=40, relative_position=0)
        df = pd.DataFrame([row1, row2])
        result = aggregate_partial_trackouts(df, _PARTIAL_KEY_COLS_3, _PARTIAL_NONKEY_COLS_ADJACENT)
        self.assertEqual(len(result), 1)

    def test_relative_position_of_target_is_zero(self):
        row = _adj_row(relative_position=0)
        df = pd.DataFrame([row])
        result = aggregate_partial_trackouts(df, _PARTIAL_KEY_COLS_3, _PARTIAL_NONKEY_COLS_ADJACENT)
        self.assertIn("RELATIVE_POSITION", result.columns)
        self.assertEqual(int(result.iloc[0]["RELATIVE_POSITION"]), 0)


class TestAdjacentLotsRelativePosition(unittest.TestCase):

    def test_neighbors_have_correct_relative_positions_after_aggregation(self):
        """After aggregation, RELATIVE_POSITION is preserved for each distinct lot."""
        rows = [
            _adj_row(container_id="ID01", trackin_ts=_T1, relative_position=-1),
            _adj_row(container_id="ID02", trackin_ts=_T2, relative_position=0),
        ]
        df = pd.DataFrame(rows)
        result = aggregate_partial_trackouts(df, _PARTIAL_KEY_COLS_3, _PARTIAL_NONKEY_COLS_ADJACENT)
        self.assertEqual(len(result), 2)
        positions = set(int(r) for r in result["RELATIVE_POSITION"])
        self.assertEqual(positions, {-1, 0})


# ==============================================================================
# Strict Guard Tests
# ==============================================================================

class TestStrictGuardLotHistory(unittest.TestCase):

    def test_divergent_equipmentname_emits_raw_rows_partial_count_one(self):
        row1 = _lot_row(equip_name="EQ_NAME_01", trackout_qty=60)
        row2 = _lot_row(equip_name="EQ_NAME_DIFFERENT", trackin_qty=40, trackout_qty=40)
        df = pd.DataFrame([row1, row2])
        result = aggregate_partial_trackouts(df, _PARTIAL_KEY_COLS_4, _PARTIAL_NONKEY_COLS_LOT)
        self.assertEqual(len(result), 2)
        self.assertTrue(all(int(r) == 1 for r in result["partial_count"]))

    def test_divergent_workcentername_emits_raw_rows(self):
        row1 = _lot_row(workcenter="WC01", trackout_qty=60)
        row2 = _lot_row(workcenter="WC02", trackin_qty=40, trackout_qty=40)
        df = pd.DataFrame([row1, row2])
        result = aggregate_partial_trackouts(df, _PARTIAL_KEY_COLS_4, _PARTIAL_NONKEY_COLS_LOT)
        self.assertEqual(len(result), 2)
        self.assertTrue(all(int(r) == 1 for r in result["partial_count"]))

    def test_divergent_finishedruncard_emits_raw_rows(self):
        row1 = _lot_row(finishedruncard="RC01", trackout_qty=60)
        row2 = _lot_row(finishedruncard="RC02", trackin_qty=40, trackout_qty=40)
        df = pd.DataFrame([row1, row2])
        result = aggregate_partial_trackouts(df, _PARTIAL_KEY_COLS_4, _PARTIAL_NONKEY_COLS_LOT)
        self.assertEqual(len(result), 2)
        self.assertTrue(all(int(r) == 1 for r in result["partial_count"]))

    def test_consistent_non_key_columns_merge_normally(self):
        row1 = _lot_row(trackout_qty=60)
        row2 = _lot_row(trackin_qty=40, trackout_qty=40)
        df = pd.DataFrame([row1, row2])
        result = aggregate_partial_trackouts(df, _PARTIAL_KEY_COLS_4, _PARTIAL_NONKEY_COLS_LOT)
        self.assertEqual(len(result), 1)
        self.assertEqual(int(result.iloc[0]["partial_count"]), 2)


class TestStrictGuardEquipmentLots(unittest.TestCase):

    def test_divergent_pj_type_emits_raw_rows_partial_count_one(self):
        row1 = _lot_row(pj_type="TYPE_A", trackout_qty=70)
        row2 = _lot_row(pj_type="TYPE_B", trackin_qty=30, trackout_qty=30)
        df = pd.DataFrame([row1, row2])
        result = aggregate_partial_trackouts(df, _PARTIAL_KEY_COLS_4, _PARTIAL_NONKEY_COLS_LOT)
        self.assertEqual(len(result), 2)
        self.assertTrue(all(int(r) == 1 for r in result["partial_count"]))

    def test_consistent_non_key_columns_merge_normally(self):
        row1 = _lot_row(pj_type="TYPE_A", trackout_qty=70)
        row2 = _lot_row(pj_type="TYPE_A", trackin_qty=30, trackout_qty=30)
        df = pd.DataFrame([row1, row2])
        result = aggregate_partial_trackouts(df, _PARTIAL_KEY_COLS_4, _PARTIAL_NONKEY_COLS_LOT)
        self.assertEqual(len(result), 1)
        self.assertEqual(int(result.iloc[0]["partial_count"]), 2)


class TestStrictGuardAdjacentLots(unittest.TestCase):

    def test_divergent_specname_emits_raw_rows_partial_count_one(self):
        """SPECNAME is a non-key col in adjacent_lots (3-tuple key)."""
        row1 = _adj_row(spec_name="SPEC_A", trackout_qty=60)
        row2 = _adj_row(spec_name="SPEC_B", trackin_qty=40, trackout_qty=40)
        df = pd.DataFrame([row1, row2])
        result = aggregate_partial_trackouts(df, _PARTIAL_KEY_COLS_3, _PARTIAL_NONKEY_COLS_ADJACENT)
        self.assertEqual(len(result), 2)
        self.assertTrue(all(int(r) == 1 for r in result["partial_count"]))

    def test_consistent_non_key_columns_merge_normally(self):
        row1 = _adj_row(spec_name="SPEC_A", trackout_qty=60)
        row2 = _adj_row(spec_name="SPEC_A", trackin_qty=40, trackout_qty=40)
        df = pd.DataFrame([row1, row2])
        result = aggregate_partial_trackouts(df, _PARTIAL_KEY_COLS_3, _PARTIAL_NONKEY_COLS_ADJACENT)
        self.assertEqual(len(result), 1)
        self.assertEqual(int(result.iloc[0]["partial_count"]), 2)


# ==============================================================================
# Decrementing TRACKINQTY Fixture Tests (key discriminator)
# ==============================================================================

class TestDecrementingTrackinQty(unittest.TestCase):
    """
    Fixture arithmetic (MES domain semantics):
      Partial 1: TRACKINQTY=99424, TRACKOUTQTY=72800, TRACKINTIMESTAMP=T
      Partial 2: TRACKINQTY=26624 (=99424-72800), TRACKOUTQTY=26624, TRACKINTIMESTAMP=T
      Expected: TRACKINQTY=99424 (MAX), TRACKOUTQTY=99424 (SUM), partial_count=2
    """

    def _make_two_partials(self, extra_cols: dict | None = None) -> pd.DataFrame:
        base = dict(
            container_id="AAAA000000000001",
            equipment_id="EQ01",
            spec_name="SPEC_A",
            trackin_ts=_T1,
            equip_name="EQ_NAME_01",
            finishedruncard="RC01",
            pj_workorder="WO01",
            containername="LOT_A",
            pj_type="TYPE_A",
            pj_bop="BOP_A",
            wafer_lot_id="W_LOT_01",
        )
        if extra_cols:
            base.update(extra_cols)
        row1 = {**_lot_row(**base), "TRACKINQTY": 99424, "TRACKOUTQTY": 72800,
                "TRACKOUTTIMESTAMP": datetime(2024, 1, 15, 9, 0)}
        row2 = {**_lot_row(**base), "TRACKINQTY": 26624, "TRACKOUTQTY": 26624,
                "TRACKOUTTIMESTAMP": datetime(2024, 1, 15, 10, 0)}
        return pd.DataFrame([row1, row2])

    def test_lot_history_decrementing_trackinqty_produces_max_and_sum(self):
        df = self._make_two_partials()
        result = aggregate_partial_trackouts(df, _PARTIAL_KEY_COLS_4, _PARTIAL_NONKEY_COLS_LOT)
        self.assertEqual(len(result), 1, "Two partials with same TRACKINTIMESTAMP must merge")
        row = result.iloc[0]
        self.assertEqual(row["TRACKINQTY"], 99424, "TRACKINQTY must be MAX")
        self.assertEqual(row["TRACKOUTQTY"], 99424, "TRACKOUTQTY must be SUM (72800+26624)")
        self.assertEqual(int(row["partial_count"]), 2)

    def test_equipment_lots_decrementing_trackinqty_produces_max_and_sum(self):
        df = self._make_two_partials()
        result = aggregate_partial_trackouts(df, _PARTIAL_KEY_COLS_4, _PARTIAL_NONKEY_COLS_LOT)
        self.assertEqual(len(result), 1)
        row = result.iloc[0]
        self.assertEqual(row["TRACKINQTY"], 99424)
        self.assertEqual(row["TRACKOUTQTY"], 99424)
        self.assertEqual(int(row["partial_count"]), 2)

    def test_adjacent_lots_decrementing_trackinqty_produces_max_and_sum(self):
        """adjacent_lots uses 3-tuple key; SPECNAME not in key."""
        row1 = {**_adj_row(), "TRACKINQTY": 99424, "TRACKOUTQTY": 72800,
                "TRACKOUTTIMESTAMP": datetime(2024, 1, 15, 9, 0)}
        row2 = {**_adj_row(), "TRACKINQTY": 26624, "TRACKOUTQTY": 26624,
                "TRACKOUTTIMESTAMP": datetime(2024, 1, 15, 10, 0)}
        df = pd.DataFrame([row1, row2])
        result = aggregate_partial_trackouts(df, _PARTIAL_KEY_COLS_3, _PARTIAL_NONKEY_COLS_ADJACENT)
        self.assertEqual(len(result), 1)
        row = result.iloc[0]
        self.assertEqual(row["TRACKINQTY"], 99424)
        self.assertEqual(row["TRACKOUTQTY"], 99424)
        self.assertEqual(int(row["partial_count"]), 2)


# ==============================================================================
# API Shape Tests
# ==============================================================================

class TestApiResponseShape(unittest.TestCase):

    def test_lot_history_response_includes_partial_count_field(self):
        row1 = _lot_row(trackout_qty=60)
        row2 = _lot_row(trackin_qty=40, trackout_qty=40)
        df = pd.DataFrame([row1, row2])
        result = aggregate_partial_trackouts(df, _PARTIAL_KEY_COLS_4, _PARTIAL_NONKEY_COLS_LOT)
        self.assertIn("partial_count", result.columns)

    def test_equipment_lots_response_includes_partial_count_field(self):
        row1 = _lot_row(trackout_qty=70)
        row2 = _lot_row(trackin_qty=30, trackout_qty=30)
        df = pd.DataFrame([row1, row2])
        result = aggregate_partial_trackouts(df, _PARTIAL_KEY_COLS_4, _PARTIAL_NONKEY_COLS_LOT)
        self.assertIn("partial_count", result.columns)

    def test_trackinqty_trackoutqty_field_names_unchanged(self):
        """Field names TRACKINQTY/TRACKOUTQTY must remain stable in API output."""
        row1 = _lot_row(trackout_qty=60)
        row2 = _lot_row(trackin_qty=40, trackout_qty=40)
        df = pd.DataFrame([row1, row2])
        result = aggregate_partial_trackouts(df, _PARTIAL_KEY_COLS_4, _PARTIAL_NONKEY_COLS_LOT)
        self.assertIn("TRACKINQTY", result.columns)
        self.assertIn("TRACKOUTQTY", result.columns)


# ==============================================================================
# Contract File Presence Tests
# ==============================================================================

class TestContractFilePresence(unittest.TestCase):

    def test_business_rules_enumerates_query_tool_ph06(self):
        """business-rules.md must contain QT-05."""
        self.assertIn("QT-05", _BUSINESS_RULES)

    def test_business_rules_enumerates_query_tool_ph07(self):
        """business-rules.md must contain QT-06."""
        self.assertIn("QT-06", _BUSINESS_RULES)

    def test_data_shape_contract_includes_partial_count_query_tool(self):
        """data-shape-contract.md must reference both partial_count and query-tool."""
        self.assertIn("partial_count", _DATA_SHAPE)
        self.assertIn("query-tool", _DATA_SHAPE.lower())


if __name__ == "__main__":
    unittest.main()
