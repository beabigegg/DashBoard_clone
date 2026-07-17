# -*- coding: utf-8 -*-
"""Unit tests for production_achievement_workcenter_merge_service.

Data-shape §3.31: production_achievement_workcenter_merge_map table (D2 --
explicit-inclusion, exclude-by-absence -- the OPPOSITE default from
production_achievement_package_lf_map/D1). Mirrors
test_production_achievement_target_service.py's hand-rolled text()/
get_mysql_connection() idiom. business-rules.md PA-10.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from mes_dashboard.services.production_achievement_package_lf_service import (
    resolve_package_lf_group,
)
from mes_dashboard.services.production_achievement_workcenter_merge_service import (
    resolve_workcenter_merge_group,
    get_workcenter_merge_entries,
    get_workcenter_merge_map,
    upsert_workcenter_merge,
    delete_workcenter_merge,
    MySQLUnavailableError,
)

_DDL_PATH = (
    Path(__file__).parent.parent / "scripts" / "sql" / "production_achievement_tables.sql"
)

# PA-19 taxonomy: raw -> (merged 子站, parent 大項). 電鍍 is two-layer. 切割
# was a second two-layer station (parent of 切割/PKG_SAW) until the
# production-achievement-moveout PKG_SAW fix (2026-07): PKG_SAW is Live's
# own separate report column, never part of 切割 -- see
# production_achievement_moveout.sql's header comment. 切割 is now
# single-layer like every other station here, and PKG_SAW moved to _EXCLUDED.
_SEEDED = [
    ("焊接_WB", "焊接_WB", "焊接_WB"),
    ("焊接_DW", "焊接_WB", "焊接_WB"),
    ("焊接_DB", "焊接_DB", "焊接_DB"),
    ("成型", "成型", "成型"),
    ("去膠", "去膠", "去膠"),
    ("移印", "移印", "移印"),
    ("水吹砂", "水吹砂", "水吹砂"),
    ("切彎腳", "切彎腳", "切彎腳"),
    ("TMTT", "TMTT", "TMTT"),
    ("品檢", "品檢", "品檢"),
    ("FQC", "FQC", "FQC"),
    ("成品入庫", "成品入庫", "成品入庫"),
    ("切割", "切割", "切割"),
    ("掛鍍", "掛鍍", "電鍍"),
    ("條鍍", "條鍍", "電鍍"),
    ("滾鍍", "滾鍍", "電鍍"),
    ("BANDL", "委外", "電鍍"),
    ("TOTAI", "委外", "電鍍"),
]

# Raw workcenters intentionally NOT seeded (D2 default-deny). 切割/成品入庫 were
# previously excluded but are now INCLUDED (PA-19), so they left this list.
# PKG_SAW moved back INTO this list by the production-achievement-moveout
# PKG_SAW fix (2026-07) -- it is Live's own separate report column
# (WorkCenter85), never summed into 切割.
_EXCLUDED = [
    "TCT", "MA", "IST", "補鍍", "點測", "可靠性", "預備站", "成品倉",
    "CP線邊倉", "已CP入庫", "已CP倉", "DS線邊倉", "PKG_SAW",
]


class TestResolveWorkcenterMergeGroupD2Semantics:
    """Python mirror of the client-side D2 INNER JOIN resolution
    (business-rules.md PA-10) -- test/parity-verification helper only; the
    real resolution runs client-side in DuckDB-WASM."""

    def test_seeded_raw_group_resolves_to_merged(self):
        mapping = {raw: merged for raw, merged, _ in _SEEDED}
        assert resolve_workcenter_merge_group("焊接_DW", mapping) == "焊接_WB"
        assert resolve_workcenter_merge_group("焊接_DB", mapping) == "焊接_DB"
        # 委外 子站 is BANDL+TOTAI merged (PA-19)
        assert resolve_workcenter_merge_group("BANDL", mapping) == "委外"
        assert resolve_workcenter_merge_group("TOTAI", mapping) == "委外"

    def test_absent_raw_group_is_excluded_not_fallback(self):
        """INNER JOIN semantics: a raw value with NO row in the map is
        EXCLUDED (resolves to None) -- never falls back to itself (that
        would be D1's package_lf_map semantics). TCT/MA/IST/補鍍 stay excluded
        under PA-19 (切割 is now INCLUDED, so no longer a good example; PKG_SAW
        moved back to excluded by the PKG_SAW fix, see _EXCLUDED)."""
        mapping = {raw: merged for raw, merged, _ in _SEEDED}
        assert resolve_workcenter_merge_group("TCT", mapping) is None
        assert resolve_workcenter_merge_group("補鍍", mapping) is None
        assert resolve_workcenter_merge_group("PKG_SAW", mapping) is None

    def test_inner_join_not_left_join_semantics(self):
        """Guard against the easiest copy-paste inversion (business-rules.md
        PA-09/PA-10 explicitly flags this): for the SAME absent raw value,
        workcenter_merge (D2) must EXCLUDE while package_lf (D1) would
        FALL BACK TO SELF -- the two resolvers must never agree on an
        absent key."""
        absent_raw = "SOME-BRAND-NEW-RAW-VALUE"
        assert resolve_workcenter_merge_group(absent_raw, {}) is None
        assert resolve_package_lf_group(absent_raw, {}) == absent_raw


class TestSeedDataInDDLScript:
    """PA-10/PA-19: the DDL seed script contains exactly the PA-19 seeded
    rows (raw -> merged 子站 + parent 大項) and excludes all non-production
    raw groups."""

    def test_seeded_groups_present_with_parent(self):
        sql_text = _DDL_PATH.read_text(encoding="utf-8")
        start = sql_text.index("INSERT IGNORE INTO production_achievement_workcenter_merge_map")
        end = sql_text.index(";", start)
        seed_block = sql_text[start:end]
        for raw, merged, parent in _SEEDED:
            assert f"'{raw}'" in seed_block, (
                f"seed row for {raw!r} missing from DDL seed block"
            )
            assert f"'{merged}'" in seed_block, (
                f"merged {merged!r} for {raw!r} missing from DDL seed block"
            )
            assert f"'{parent}'" in seed_block, (
                f"parent_group {parent!r} for {raw!r} missing from DDL seed block"
            )

    def test_excluded_groups_absent(self):
        sql_text = _DDL_PATH.read_text(encoding="utf-8")
        # Isolate the workcenter_merge_map seed INSERT block so a coincidental
        # substring match elsewhere in the file (e.g. a comment) can't hide
        # a real omission or a real accidental inclusion.
        start = sql_text.index("INSERT IGNORE INTO production_achievement_workcenter_merge_map")
        end = sql_text.index(";", start)
        seed_block = sql_text[start:end]
        for raw in _EXCLUDED:
            assert f"'{raw}'" not in seed_block, (
                f"{raw!r} must be excluded from the seed block (D2 default-deny)"
            )

    def test_electroplating_two_layer_children_roll_up_to_parent(self):
        """PA-19: 掛鍍/條鍍/滾鍍/委外 -> 電鍍 (the one remaining two-layer
        station). BANDL/TOTAI both merge to the '委外' 子站 (Excel
        presentation-layer merge). 切割 is single-layer (parent = itself) --
        see the PKG_SAW fix note on _SEEDED/_EXCLUDED above."""
        by_raw = {raw: (merged, parent) for raw, merged, parent in _SEEDED}
        for raw in ("掛鍍", "條鍍", "滾鍍"):
            assert by_raw[raw] == (raw, "電鍍")
        assert by_raw["BANDL"] == ("委外", "電鍍")
        assert by_raw["TOTAI"] == ("委外", "電鍍")
        assert by_raw["切割"] == ("切割", "切割")


class TestGetWorkcenterMergeEntries:
    @patch("mes_dashboard.services.production_achievement_workcenter_merge_service.MYSQL_OPS_ENABLED", True)
    @patch("mes_dashboard.services.production_achievement_workcenter_merge_service.get_mysql_connection")
    def test_get_entries_returns_full_rows(self, mock_conn_ctx):
        conn = MagicMock()
        row = MagicMock()
        row._mapping = {
            "raw_workcenter_group": "焊接_DW",
            "merged_workcenter_group": "焊接_WB",
            "parent_group": "焊接_WB",
            "updated_at": "2026-07-01T00:00:00",
            "updated_by": "tester",
        }
        result = MagicMock()
        result.fetchall.return_value = [row]
        conn.execute.return_value = result
        mock_conn_ctx.return_value.__enter__.return_value = conn

        rows = get_workcenter_merge_entries()
        assert rows == [
            {
                "raw_workcenter_group": "焊接_DW",
                "merged_workcenter_group": "焊接_WB",
                "parent_group": "焊接_WB",
                "updated_at": "2026-07-01T00:00:00",
                "updated_by": "tester",
            }
        ]

    @patch("mes_dashboard.services.production_achievement_workcenter_merge_service.MYSQL_OPS_ENABLED", True)
    @patch("mes_dashboard.services.production_achievement_workcenter_merge_service.get_mysql_connection")
    def test_null_parent_group_falls_back_to_merged(self, mock_conn_ctx):
        """PA-19: a legacy row with NULL parent_group (pre-backfill install)
        must fall back to its merged_workcenter_group, never collapse out."""
        conn = MagicMock()
        row = MagicMock()
        row._mapping = {
            "raw_workcenter_group": "去膠",
            "merged_workcenter_group": "去膠",
            "parent_group": None,
            "updated_at": "2026-07-01T00:00:00",
            "updated_by": "tester",
        }
        result = MagicMock()
        result.fetchall.return_value = [row]
        conn.execute.return_value = result
        mock_conn_ctx.return_value.__enter__.return_value = conn

        rows = get_workcenter_merge_entries()
        assert rows[0]["parent_group"] == "去膠"

    @patch("mes_dashboard.services.production_achievement_workcenter_merge_service.MYSQL_OPS_ENABLED", False)
    def test_read_degrades_empty_when_ops_disabled(self):
        """D2: an empty table means the INNER JOIN matches nothing and the
        whole report renders empty -- NOT the same degrade meaning as D1's
        empty-table fallback-to-self (data-shape-contract.md §3.31)."""
        assert get_workcenter_merge_entries() == []
        assert get_workcenter_merge_map() == {}

    @patch("mes_dashboard.services.production_achievement_workcenter_merge_service.MYSQL_OPS_ENABLED", True)
    @patch("mes_dashboard.services.production_achievement_workcenter_merge_service.get_mysql_connection")
    def test_read_degrades_empty_on_mysql_exception(self, mock_conn_ctx):
        mock_conn_ctx.side_effect = RuntimeError("connection refused")
        assert get_workcenter_merge_entries() == []
        assert get_workcenter_merge_map() == {}


class TestGetWorkcenterMergeMap:
    @patch("mes_dashboard.services.production_achievement_workcenter_merge_service.MYSQL_OPS_ENABLED", True)
    @patch("mes_dashboard.services.production_achievement_workcenter_merge_service.get_mysql_connection")
    def test_map_is_raw_to_merged_dict(self, mock_conn_ctx):
        conn = MagicMock()
        row = MagicMock()
        row._mapping = {
            "raw_workcenter_group": "焊接_DW",
            "merged_workcenter_group": "焊接_WB",
            "parent_group": "焊接_WB",
            "updated_at": "2026-07-01T00:00:00",
            "updated_by": "tester",
        }
        result = MagicMock()
        result.fetchall.return_value = [row]
        conn.execute.return_value = result
        mock_conn_ctx.return_value.__enter__.return_value = conn

        # get_workcenter_merge_map is still raw->merged (子站) -- unchanged by PA-19.
        assert get_workcenter_merge_map() == {"焊接_DW": "焊接_WB"}


class TestUpsertWorkcenterMerge:
    @patch("mes_dashboard.services.production_achievement_workcenter_merge_service.MYSQL_OPS_ENABLED", True)
    @patch("mes_dashboard.services.production_achievement_workcenter_merge_service.get_mysql_connection")
    def test_upsert_unique_key_raw_workcenter_group(self, mock_conn_ctx):
        conn = MagicMock()
        mock_conn_ctx.return_value.__enter__.return_value = conn

        upsert_workcenter_merge(
            raw_workcenter_group="焊接_DW", merged_workcenter_group="焊接_WB", updated_by="tester"
        )

        assert conn.execute.called
        call_args = conn.execute.call_args
        sql_text = str(call_args.args[0])
        assert "ON DUPLICATE KEY UPDATE" in sql_text
        assert "production_achievement_workcenter_merge_map" in sql_text
        params = call_args.args[1] if len(call_args.args) > 1 else call_args.kwargs.get("parameters")
        assert params["raw_workcenter_group"] == "焊接_DW"
        assert params["merged_workcenter_group"] == "焊接_WB"
        assert params["updated_by"] == "tester"

    @patch("mes_dashboard.services.production_achievement_workcenter_merge_service.MYSQL_OPS_ENABLED", False)
    def test_write_raises_mysqlunavailableerror_when_ops_disabled(self):
        with pytest.raises(MySQLUnavailableError):
            upsert_workcenter_merge(
                raw_workcenter_group="焊接_DW", merged_workcenter_group="焊接_WB", updated_by="tester"
            )


class TestDeleteWorkcenterMerge:
    @patch("mes_dashboard.services.production_achievement_workcenter_merge_service.MYSQL_OPS_ENABLED", True)
    @patch("mes_dashboard.services.production_achievement_workcenter_merge_service.get_mysql_connection")
    def test_delete_returns_true_when_row_existed(self, mock_conn_ctx):
        conn = MagicMock()
        result = MagicMock()
        result.rowcount = 1
        conn.execute.return_value = result
        mock_conn_ctx.return_value.__enter__.return_value = conn

        assert delete_workcenter_merge(raw_workcenter_group="焊接_DW") is True
        call_args = conn.execute.call_args
        sql_text = str(call_args.args[0])
        assert "DELETE" in sql_text.upper()
        assert "production_achievement_workcenter_merge_map" in sql_text

    @patch("mes_dashboard.services.production_achievement_workcenter_merge_service.MYSQL_OPS_ENABLED", True)
    @patch("mes_dashboard.services.production_achievement_workcenter_merge_service.get_mysql_connection")
    def test_delete_returns_false_when_row_absent(self, mock_conn_ctx):
        conn = MagicMock()
        result = MagicMock()
        result.rowcount = 0
        conn.execute.return_value = result
        mock_conn_ctx.return_value.__enter__.return_value = conn

        assert delete_workcenter_merge(raw_workcenter_group="NOT-THERE") is False

    @patch("mes_dashboard.services.production_achievement_workcenter_merge_service.MYSQL_OPS_ENABLED", False)
    def test_delete_raises_mysqlunavailableerror_when_ops_disabled(self):
        with pytest.raises(MySQLUnavailableError):
            delete_workcenter_merge(raw_workcenter_group="焊接_DW")
