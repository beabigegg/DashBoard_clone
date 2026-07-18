# -*- coding: utf-8 -*-
"""Unit tests for production_achievement_package_lf_service.

Data-shape §3.30: production_achievement_package_lf_map table (D1 -- sparse
exceptions-only override layer on top of an Oracle default, fallback-to-self
on absence from both). Mirrors test_production_achievement_target_service.py's
hand-rolled text()/get_mysql_connection() idiom. business-rules.md PA-09.
"""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from mes_dashboard.services.production_achievement_package_lf_service import (
    resolve_package_lf_group,
    get_package_lf_entries,
    get_package_lf_map,
    get_oracle_package_lf_map,
    upsert_package_lf,
    delete_package_lf,
    MySQLUnavailableError,
)

_DDL_PATH = (
    Path(__file__).parent.parent / "scripts" / "sql" / "production_achievement_tables.sql"
)


@pytest.fixture(autouse=True)
def reset_oracle_cache():
    """Reset the global Oracle default-map cache before/after each test."""
    import mes_dashboard.services.production_achievement_package_lf_service as svc
    svc._ORACLE_CACHE.clear()
    yield
    svc._ORACLE_CACHE.clear()


def _oracle_lf_df(rows):
    return pd.DataFrame(rows, columns=["RAW_PACKAGE_LF", "ORACLE_MERGED_GROUP"])


class TestResolvePackageLfGroupD1Semantics:
    """Python mirror of the client-side D1 LEFT JOIN + COALESCE resolution
    (business-rules.md PA-09) -- test/parity-verification helper only; the
    real resolution runs client-side in DuckDB-WASM."""

    def test_absent_raw_falls_back_to_self(self):
        """LEFT JOIN semantics: a raw value with NO row in the map is NOT
        excluded -- it groups under itself (never INNER JOIN's exclusion)."""
        mapping = {"SOT23-5L": "SOT23-5L/6L"}
        assert resolve_package_lf_group("UNMAPPED-RAW-VALUE", mapping) == "UNMAPPED-RAW-VALUE"

    def test_null_blank_raw_to_weizonglei_sentinel(self):
        assert resolve_package_lf_group(None, {}) == "(未分類)"
        assert resolve_package_lf_group("", {}) == "(未分類)"
        assert resolve_package_lf_group("   ", {}) == "(未分類)"

    def test_four_confirmed_merges_resolve(self):
        mapping = {
            "SOD-123FL OP1": "SOD-123FL",
            "SOD-123FL": "SOD-123FL",
            "SOT23-5L": "SOT23-5L/6L",
            "SOT23-6L": "SOT23-5L/6L",
            "SOT-543": "SOT-543/553/563",
            "SOT-553": "SOT-543/553/563",
            "SOT-563": "SOT-543/553/563",
            "TO-277": "TO-277(B)",
            "TO-277B": "TO-277(B)",
        }
        assert resolve_package_lf_group("SOD-123FL OP1", mapping) == "SOD-123FL"
        assert resolve_package_lf_group("SOT23-6L", mapping) == "SOT23-5L/6L"
        assert resolve_package_lf_group("SOT-553", mapping) == "SOT-543/553/563"
        assert resolve_package_lf_group("TO-277B", mapping) == "TO-277(B)"

    def test_left_join_not_inner_join_semantics(self):
        """Guard against the easiest copy-paste inversion (business-rules.md
        PA-09/PA-10): an absent raw value must resolve to ITSELF, never to
        None/exclusion (that would be D2's workcenter_merge_map semantics)."""
        resolved = resolve_package_lf_group("SOME-BRAND-NEW-RAW-VALUE", {})
        assert resolved is not None
        assert resolved == "SOME-BRAND-NEW-RAW-VALUE"


class TestSeedDataInDDLScript:
    """PA-09: the DDL seed script (Phase 2) matches the exact 7 rows behind
    the 3 confirmed merges. SOT23-5L/SOT23-6L -> 'SOT23-5L/6L' was REMOVED
    from this seed (production-achievement-oracle-plan-source, caught by
    user review): it never matched Oracle's real PACKAGE_REPORT value
    'SOT-23-5L/6L' (hyphenated), and D1's Oracle default layer now covers
    both raw codes correctly without a manual row -- see
    scripts/sql/production_achievement_tables.sql's inline comment."""

    def test_seven_seed_rows_present(self):
        sql_text = _DDL_PATH.read_text(encoding="utf-8")
        for raw, merged in [
            ("SOD-123FL OP1", "SOD-123FL"),
            ("SOD-123FL", "SOD-123FL"),
            ("SOT-543", "SOT-543/553/563"),
            ("SOT-553", "SOT-543/553/563"),
            ("SOT-563", "SOT-543/553/563"),
            ("TO-277", "TO-277(B)"),
            ("TO-277B", "TO-277(B)"),
        ]:
            assert f"'{raw}'" in sql_text and f"'{merged}'" in sql_text, (
                f"seed row for {raw!r}->{merged!r} missing from DDL script"
            )


class TestGetOraclePackageLfMap:
    """production-achievement-oracle-plan-source (PA-09 amendment): D1's
    default layer, sourced from the full un-joined MES_WIP_OUTPUTPLAN_DETAIL
    table. Cached globally (not month-keyed, this is a static reference
    table) -- mirrors production_achievement_plan_service's cache tests."""

    def test_maps_raw_to_oracle_group(self):
        df = _oracle_lf_df([("DFN0603", "DFN2510/0603"), ("SOT-563", "SOT-543/553/563")])
        with patch(
            "mes_dashboard.services.production_achievement_package_lf_service.read_sql_df",
            return_value=df,
        ):
            result = get_oracle_package_lf_map()

        assert result == {"DFN0603": "DFN2510/0603", "SOT-563": "SOT-543/553/563"}

    def test_second_call_within_ttl_reuses_cache_no_oracle_call(self):
        df = _oracle_lf_df([("DFN0603", "DFN2510/0603")])
        with patch(
            "mes_dashboard.services.production_achievement_package_lf_service.read_sql_df",
            return_value=df,
        ) as mock_sql:
            get_oracle_package_lf_map()
            get_oracle_package_lf_map()

        mock_sql.assert_called_once()

    def test_force_refresh_bypasses_cache(self):
        df = _oracle_lf_df([("DFN0603", "DFN2510/0603")])
        with patch(
            "mes_dashboard.services.production_achievement_package_lf_service.read_sql_df",
            return_value=df,
        ) as mock_sql:
            get_oracle_package_lf_map()
            get_oracle_package_lf_map(force_refresh=True)

        assert mock_sql.call_count == 2

    def test_expired_ttl_triggers_requery(self):
        import mes_dashboard.services.production_achievement_package_lf_service as svc

        df = _oracle_lf_df([("DFN0603", "DFN2510/0603")])
        with patch(
            "mes_dashboard.services.production_achievement_package_lf_service.read_sql_df",
            return_value=df,
        ) as mock_sql:
            svc.get_oracle_package_lf_map()
            svc._ORACLE_CACHE["loaded_at"] = time.time() - svc._ORACLE_CACHE_TTL_SECONDS - 1
            svc.get_oracle_package_lf_map()

        assert mock_sql.call_count == 2

    def test_oracle_failure_degrades_to_empty_dict(self):
        with patch(
            "mes_dashboard.services.production_achievement_package_lf_service.read_sql_df",
            side_effect=RuntimeError("ORA-12541: TNS:no listener"),
        ):
            result = get_oracle_package_lf_map()

        assert result == {}

    def test_oracle_failure_falls_back_to_last_known_good_cache(self):
        good_df = _oracle_lf_df([("DFN0603", "DFN2510/0603")])
        with patch(
            "mes_dashboard.services.production_achievement_package_lf_service.read_sql_df",
            return_value=good_df,
        ):
            first = get_oracle_package_lf_map()

        with patch(
            "mes_dashboard.services.production_achievement_package_lf_service.read_sql_df",
            side_effect=RuntimeError("ORA-12541: TNS:no listener"),
        ):
            second = get_oracle_package_lf_map(force_refresh=True)

        assert first == second == {"DFN0603": "DFN2510/0603"}


class TestGetPackageLfEntries:
    @patch("mes_dashboard.services.production_achievement_package_lf_service.MYSQL_OPS_ENABLED", True)
    @patch("mes_dashboard.services.production_achievement_package_lf_service.get_mysql_connection")
    def test_get_entries_returns_full_rows(self, mock_conn_ctx):
        conn = MagicMock()
        row = MagicMock()
        row._mapping = {
            "raw_package_lf": "SOT23-5L",
            "merged_group": "SOT23-5L/6L",
            "updated_at": "2026-07-01T00:00:00",
            "updated_by": "tester",
        }
        result = MagicMock()
        result.fetchall.return_value = [row]
        conn.execute.return_value = result
        mock_conn_ctx.return_value.__enter__.return_value = conn

        rows = get_package_lf_entries()
        assert rows == [
            {
                "raw_package_lf": "SOT23-5L",
                "merged_group": "SOT23-5L/6L",
                "updated_at": "2026-07-01T00:00:00",
                "updated_by": "tester",
            }
        ]

    @patch("mes_dashboard.services.production_achievement_package_lf_service.get_oracle_package_lf_map", return_value={})
    @patch("mes_dashboard.services.production_achievement_package_lf_service.MYSQL_OPS_ENABLED", False)
    def test_read_degrades_empty_when_ops_disabled(self, _mock_oracle):
        """D1: an empty table under fallback-to-self default means every raw
        value groups under itself -- a valid (if maximally-fragmented)
        report, not an error state (data-shape-contract.md §3.30)."""
        assert get_package_lf_entries() == []
        assert get_package_lf_map() == {}

    @patch("mes_dashboard.services.production_achievement_package_lf_service.get_oracle_package_lf_map", return_value={})
    @patch("mes_dashboard.services.production_achievement_package_lf_service.MYSQL_OPS_ENABLED", True)
    @patch("mes_dashboard.services.production_achievement_package_lf_service.get_mysql_connection")
    def test_read_degrades_empty_on_mysql_exception(self, mock_conn_ctx, _mock_oracle):
        mock_conn_ctx.side_effect = RuntimeError("connection refused")
        assert get_package_lf_entries() == []
        assert get_package_lf_map() == {}


class TestGetPackageLfMap:
    @patch("mes_dashboard.services.production_achievement_package_lf_service.get_oracle_package_lf_map", return_value={})
    @patch("mes_dashboard.services.production_achievement_package_lf_service.MYSQL_OPS_ENABLED", True)
    @patch("mes_dashboard.services.production_achievement_package_lf_service.get_mysql_connection")
    def test_map_is_raw_to_merged_dict(self, mock_conn_ctx, _mock_oracle):
        conn = MagicMock()
        row = MagicMock()
        row._mapping = {
            "raw_package_lf": "TO-277",
            "merged_group": "TO-277(B)",
            "updated_at": "2026-07-01T00:00:00",
            "updated_by": "tester",
        }
        result = MagicMock()
        result.fetchall.return_value = [row]
        conn.execute.return_value = result
        mock_conn_ctx.return_value.__enter__.return_value = conn

        assert get_package_lf_map() == {"TO-277": "TO-277(B)"}

    @patch("mes_dashboard.services.production_achievement_package_lf_service.MYSQL_OPS_ENABLED", True)
    @patch("mes_dashboard.services.production_achievement_package_lf_service.get_mysql_connection")
    def test_manual_row_overrides_oracle_default_for_same_raw(self, mock_conn_ctx):
        """A manual D1 row always wins over Oracle's value for the same raw
        code -- that's what makes D1 an override layer, not a duplicate."""
        conn = MagicMock()
        row = MagicMock()
        row._mapping = {
            "raw_package_lf": "SOT-563",
            "merged_group": "SOT-CUSTOM-OVERRIDE",
            "updated_at": "2026-07-01T00:00:00",
            "updated_by": "tester",
        }
        result = MagicMock()
        result.fetchall.return_value = [row]
        conn.execute.return_value = result
        mock_conn_ctx.return_value.__enter__.return_value = conn

        oracle_df = _oracle_lf_df([("SOT-563", "SOT-543/553/563"), ("TO-277", "TO-277(B)")])
        with patch(
            "mes_dashboard.services.production_achievement_package_lf_service.read_sql_df",
            return_value=oracle_df,
        ):
            merged = get_package_lf_map()

        assert merged["SOT-563"] == "SOT-CUSTOM-OVERRIDE"
        assert merged["TO-277"] == "TO-277(B)"

    @patch("mes_dashboard.services.production_achievement_package_lf_service.MYSQL_OPS_ENABLED", True)
    @patch("mes_dashboard.services.production_achievement_package_lf_service.get_mysql_connection")
    def test_oracle_only_raw_resolves_without_any_manual_row(self, mock_conn_ctx):
        """A raw code Oracle knows but D1 has no manual row for still
        resolves via the Oracle default -- no manual seeding required."""
        conn = MagicMock()
        result = MagicMock()
        result.fetchall.return_value = []
        conn.execute.return_value = result
        mock_conn_ctx.return_value.__enter__.return_value = conn

        oracle_df = _oracle_lf_df([("DFN0603", "DFN2510/0603")])
        with patch(
            "mes_dashboard.services.production_achievement_package_lf_service.read_sql_df",
            return_value=oracle_df,
        ):
            merged = get_package_lf_map()

        assert merged == {"DFN0603": "DFN2510/0603"}


class TestUpsertPackageLf:
    @patch("mes_dashboard.services.production_achievement_package_lf_service.MYSQL_OPS_ENABLED", True)
    @patch("mes_dashboard.services.production_achievement_package_lf_service.get_mysql_connection")
    def test_upsert_unique_key_raw_package_lf(self, mock_conn_ctx):
        conn = MagicMock()
        mock_conn_ctx.return_value.__enter__.return_value = conn

        upsert_package_lf(
            raw_package_lf="SOT23-5L", merged_group="SOT23-5L/6L", updated_by="tester"
        )

        assert conn.execute.called
        call_args = conn.execute.call_args
        sql_text = str(call_args.args[0])
        assert "ON DUPLICATE KEY UPDATE" in sql_text
        assert "production_achievement_package_lf_map" in sql_text
        params = call_args.args[1] if len(call_args.args) > 1 else call_args.kwargs.get("parameters")
        assert params["raw_package_lf"] == "SOT23-5L"
        assert params["merged_group"] == "SOT23-5L/6L"
        assert params["updated_by"] == "tester"

    @patch("mes_dashboard.services.production_achievement_package_lf_service.MYSQL_OPS_ENABLED", False)
    def test_write_raises_mysqlunavailableerror_when_ops_disabled(self):
        with pytest.raises(MySQLUnavailableError):
            upsert_package_lf(
                raw_package_lf="SOT23-5L", merged_group="SOT23-5L/6L", updated_by="tester"
            )


class TestDeletePackageLf:
    @patch("mes_dashboard.services.production_achievement_package_lf_service.MYSQL_OPS_ENABLED", True)
    @patch("mes_dashboard.services.production_achievement_package_lf_service.get_mysql_connection")
    def test_delete_returns_true_when_row_existed(self, mock_conn_ctx):
        conn = MagicMock()
        result = MagicMock()
        result.rowcount = 1
        conn.execute.return_value = result
        mock_conn_ctx.return_value.__enter__.return_value = conn

        assert delete_package_lf(raw_package_lf="SOT23-5L") is True
        call_args = conn.execute.call_args
        sql_text = str(call_args.args[0])
        assert "DELETE" in sql_text.upper()
        assert "production_achievement_package_lf_map" in sql_text

    @patch("mes_dashboard.services.production_achievement_package_lf_service.MYSQL_OPS_ENABLED", True)
    @patch("mes_dashboard.services.production_achievement_package_lf_service.get_mysql_connection")
    def test_delete_returns_false_when_row_absent(self, mock_conn_ctx):
        conn = MagicMock()
        result = MagicMock()
        result.rowcount = 0
        conn.execute.return_value = result
        mock_conn_ctx.return_value.__enter__.return_value = conn

        assert delete_package_lf(raw_package_lf="NOT-THERE") is False

    @patch("mes_dashboard.services.production_achievement_package_lf_service.MYSQL_OPS_ENABLED", False)
    def test_delete_raises_mysqlunavailableerror_when_ops_disabled(self):
        with pytest.raises(MySQLUnavailableError):
            delete_package_lf(raw_package_lf="SOT23-5L")
