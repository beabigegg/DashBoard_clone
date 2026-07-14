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

_SEEDED_12 = [
    ("焊接_WB", "焊接_WB"),
    ("焊接_DW", "焊接_WB"),
    ("焊接_DB", "焊接_DB"),
    ("成型", "成型"),
    ("去膠", "去膠"),
    ("移印", "移印"),
    ("水吹砂", "水吹砂"),
    ("電鍍", "電鍍"),
    ("切彎腳", "切彎腳"),
    ("TMTT", "TMTT"),
    ("品檢", "品檢"),
    ("FQC", "FQC"),
]

_EXCLUDED_15 = [
    "切割", "PKG_SAW", "點測", "可靠性", "補鍍", "預備站", "成品倉", "IST",
    "CP線邊倉", "成品入庫", "已CP入庫", "已CP倉", "DS線邊倉", "MA", "TCT",
]


class TestResolveWorkcenterMergeGroupD2Semantics:
    """Python mirror of the client-side D2 INNER JOIN resolution
    (business-rules.md PA-10) -- test/parity-verification helper only; the
    real resolution runs client-side in DuckDB-WASM."""

    def test_seeded_raw_group_resolves_to_merged(self):
        mapping = dict(_SEEDED_12)
        assert resolve_workcenter_merge_group("焊接_DW", mapping) == "焊接_WB"
        assert resolve_workcenter_merge_group("焊接_DB", mapping) == "焊接_DB"

    def test_absent_raw_group_is_excluded_not_fallback(self):
        """INNER JOIN semantics: a raw value with NO row in the map is
        EXCLUDED (resolves to None) -- never falls back to itself (that
        would be D1's package_lf_map semantics)."""
        mapping = dict(_SEEDED_12)
        assert resolve_workcenter_merge_group("切割", mapping) is None

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
    """PA-10: the DDL seed script (Phase 2) contains exactly the 12 seeded
    groups and excludes all 15 non-production raw groups."""

    def test_twelve_seeded_groups_present(self):
        sql_text = _DDL_PATH.read_text(encoding="utf-8")
        assert len(_SEEDED_12) == 12
        for raw, merged in _SEEDED_12:
            assert f"'{raw}'" in sql_text and f"'{merged}'" in sql_text, (
                f"seed row for {raw!r}->{merged!r} missing from DDL script"
            )

    def test_each_of_fifteen_excluded_groups_absent(self):
        sql_text = _DDL_PATH.read_text(encoding="utf-8")
        assert len(_EXCLUDED_15) == 15
        # Isolate the workcenter_merge_map seed INSERT block so a coincidental
        # substring match elsewhere in the file (e.g. a comment) can't hide
        # a real omission or a real accidental inclusion.
        start = sql_text.index("INSERT IGNORE INTO production_achievement_workcenter_merge_map")
        end = sql_text.index(";", start)
        seed_block = sql_text[start:end]
        for raw in _EXCLUDED_15:
            assert f"'{raw}'" not in seed_block, (
                f"{raw!r} must be excluded from the seed block (D2 default-deny)"
            )


class TestGetWorkcenterMergeEntries:
    @patch("mes_dashboard.services.production_achievement_workcenter_merge_service.MYSQL_OPS_ENABLED", True)
    @patch("mes_dashboard.services.production_achievement_workcenter_merge_service.get_mysql_connection")
    def test_get_entries_returns_full_rows(self, mock_conn_ctx):
        conn = MagicMock()
        row = MagicMock()
        row._mapping = {
            "raw_workcenter_group": "焊接_DW",
            "merged_workcenter_group": "焊接_WB",
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
                "updated_at": "2026-07-01T00:00:00",
                "updated_by": "tester",
            }
        ]

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
            "updated_at": "2026-07-01T00:00:00",
            "updated_by": "tester",
        }
        result = MagicMock()
        result.fetchall.return_value = [row]
        conn.execute.return_value = result
        mock_conn_ctx.return_value.__enter__.return_value = conn

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
