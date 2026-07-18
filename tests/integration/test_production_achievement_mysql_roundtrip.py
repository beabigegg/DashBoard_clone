# -*- coding: utf-8 -*-
"""Mock-based integration tests: direct-MySQL round-trip for the two new
production-achievement tables (data-shape §3.26/§3.27), and MYSQL_OPS_ENABLED
fallback behavior (read -> null/empty, write -> 503), per design.md's
per-endpoint MySQL-failure matrix.

Fully mock-based (in-memory fake MySQL connection) -- no real MySQL required,
so marker is integration (PR-gate) not integration_real.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

pytestmark = pytest.mark.integration


class _FakeMySQLTable:
    """Minimal in-memory upsert store keyed by a tuple key, simulating
    INSERT ... ON DUPLICATE KEY UPDATE semantics for round-trip tests."""

    def __init__(self):
        self.rows: dict = {}

    def upsert(self, key, row):
        self.rows[key] = row

    def all(self):
        return list(self.rows.values())


class _FakeConn:
    def __init__(self, table: _FakeMySQLTable, key_fields):
        self._table = table
        self._key_fields = key_fields
        self.executed = []

    def execute(self, sql, params=None):
        sql_text = str(sql)
        self.executed.append((sql_text, params))
        if "INSERT" in sql_text.upper() and "SELECT" not in sql_text.upper()[:20]:
            key = tuple(params[f] for f in self._key_fields)
            row = dict(params)
            # Simulate server-side NOW() for any *_at timestamp column not
            # provided as a bound param (real SQL uses NOW(), not a param).
            row.setdefault("updated_at", "2026-07-02T00:00:00")
            row.setdefault("granted_at", "2026-07-02T00:00:00")
            self._table.upsert(key, row)
            return None
        if "SELECT" in sql_text.upper():
            class _Result:
                def __init__(self, rows):
                    self._rows = rows

                def fetchall(self):
                    return self._rows

            class _Row:
                def __init__(self, mapping):
                    self._mapping = mapping

            return _Result([_Row(r) for r in self._table.all()])
        return None


class _FakeConnCtx:
    def __init__(self, conn):
        self._conn = conn

    def __enter__(self):
        return self._conn

    def __exit__(self, *args):
        return False


class TestTargetTableRoundtrip:
    @patch("mes_dashboard.services.production_achievement_target_service.MYSQL_OPS_ENABLED", True)
    def test_target_table_write_then_read_roundtrip(self, monkeypatch):
        from mes_dashboard.services import production_achievement_target_service as svc

        table = _FakeMySQLTable()
        conn = _FakeConn(table, key_fields=("shift_code", "workcenter_group"))
        monkeypatch.setattr(svc, "get_mysql_connection", lambda: _FakeConnCtx(conn))

        svc.upsert_target(
            shift_code="D", workcenter_group="切割", target_qty=1000, updated_by="tester"
        )
        rows = svc.get_targets()
        assert len(rows) == 1
        assert rows[0]["shift_code"] == "D"
        assert rows[0]["workcenter_group"] == "切割"
        assert rows[0]["target_qty"] == 1000

    @patch("mes_dashboard.services.production_achievement_target_service.MYSQL_OPS_ENABLED", False)
    def test_mysql_ops_disabled_read_degrades_to_null(self):
        from mes_dashboard.services import production_achievement_target_service as svc

        # No target rows configured -> report-level achievement_rate computation
        # (in production_achievement_service) treats missing target as null (PA-07).
        assert svc.get_targets() == []

    @patch("mes_dashboard.services.production_achievement_target_service.MYSQL_OPS_ENABLED", False)
    def test_mysql_ops_disabled_write_returns_503(self):
        from mes_dashboard.services import production_achievement_target_service as svc

        with pytest.raises(svc.MySQLUnavailableError):
            svc.upsert_target(
                shift_code="D", workcenter_group="切割", target_qty=1000, updated_by="tester"
            )


class TestPermissionTableRoundtrip:
    @patch("mes_dashboard.services.production_achievement_permission_service.MYSQL_OPS_ENABLED", True)
    def test_permission_table_write_then_read_roundtrip(self, monkeypatch):
        from mes_dashboard.services import production_achievement_permission_service as svc

        table = _FakeMySQLTable()
        conn = _FakeConn(table, key_fields=("user_identifier",))
        monkeypatch.setattr(svc, "get_mysql_connection", lambda: _FakeConnCtx(conn))

        svc.upsert_permission(
            user_identifier="alice", can_edit_targets=True, granted_by="admin"
        )
        rows = svc.get_permissions()
        assert len(rows) == 1
        assert rows[0]["user_identifier"] == "alice"
        assert rows[0]["can_edit_targets"] is True

    @patch("mes_dashboard.services.production_achievement_permission_service.MYSQL_OPS_ENABLED", False)
    def test_ops_disabled_write_returns_503(self):
        from mes_dashboard.services import production_achievement_permission_service as svc

        with pytest.raises(svc.MySQLUnavailableError):
            svc.upsert_permission(
                user_identifier="alice", can_edit_targets=True, granted_by="admin"
            )

    @patch("mes_dashboard.services.production_achievement_permission_service.MYSQL_OPS_ENABLED", False)
    def test_ops_disabled_is_user_whitelisted_fails_closed(self):
        from mes_dashboard.services import production_achievement_permission_service as svc

        assert svc.is_user_whitelisted("alice") is False


class TestPackageLfTableRoundtrip:
    """production-achievement-overhaul, D1 (sparse, fallback-to-self on
    absence). Mirrors TestTargetTableRoundtrip."""

    @patch("mes_dashboard.services.production_achievement_package_lf_service.MYSQL_OPS_ENABLED", True)
    def test_package_lf_table_write_then_read_roundtrip(self, monkeypatch):
        from mes_dashboard.services import production_achievement_package_lf_service as svc

        table = _FakeMySQLTable()
        conn = _FakeConn(table, key_fields=("raw_package_lf",))
        monkeypatch.setattr(svc, "get_mysql_connection", lambda: _FakeConnCtx(conn))

        svc.upsert_package_lf(
            raw_package_lf="SOT23-5L", merged_group="SOT23-5L/6L", updated_by="tester"
        )
        rows = svc.get_package_lf_entries()
        assert len(rows) == 1
        assert rows[0]["raw_package_lf"] == "SOT23-5L"
        assert rows[0]["merged_group"] == "SOT23-5L/6L"

        assert svc.get_package_lf_map() == {"SOT23-5L": "SOT23-5L/6L"}

    @patch("mes_dashboard.services.production_achievement_package_lf_service.MYSQL_OPS_ENABLED", False)
    def test_mysql_ops_disabled_read_degrades_to_empty(self):
        """D1: an empty/degraded table means every raw value falls back to
        itself -- a valid report, not an error state."""
        from mes_dashboard.services import production_achievement_package_lf_service as svc

        assert svc.get_package_lf_entries() == []
        assert svc.get_package_lf_map() == {}

    @patch("mes_dashboard.services.production_achievement_package_lf_service.MYSQL_OPS_ENABLED", False)
    def test_mysql_ops_disabled_write_returns_503(self):
        from mes_dashboard.services import production_achievement_package_lf_service as svc

        with pytest.raises(svc.MySQLUnavailableError):
            svc.upsert_package_lf(
                raw_package_lf="SOT23-5L", merged_group="SOT23-5L/6L", updated_by="tester"
            )

    @patch("mes_dashboard.services.production_achievement_package_lf_service.MYSQL_OPS_ENABLED", False)
    def test_mysql_ops_disabled_delete_returns_503(self):
        from mes_dashboard.services import production_achievement_package_lf_service as svc

        with pytest.raises(svc.MySQLUnavailableError):
            svc.delete_package_lf(raw_package_lf="SOT23-5L")


class TestWorkcenterMergeTableRoundtrip:
    """production-achievement-overhaul, D2 (explicit-inclusion,
    exclude-by-absence -- the OPPOSITE default from
    TestPackageLfTableRoundtrip above). Mirrors TestTargetTableRoundtrip."""

    @patch("mes_dashboard.services.production_achievement_workcenter_merge_service.MYSQL_OPS_ENABLED", True)
    def test_workcenter_merge_table_write_then_read_roundtrip(self, monkeypatch):
        from mes_dashboard.services import production_achievement_workcenter_merge_service as svc

        table = _FakeMySQLTable()
        conn = _FakeConn(table, key_fields=("raw_workcenter_group",))
        monkeypatch.setattr(svc, "get_mysql_connection", lambda: _FakeConnCtx(conn))

        svc.upsert_workcenter_merge(
            raw_workcenter_group="焊接_DW", merged_workcenter_group="焊接_WB",
            plan_source_side="output", updated_by="tester",
        )
        rows = svc.get_workcenter_merge_entries()
        assert len(rows) == 1
        assert rows[0]["raw_workcenter_group"] == "焊接_DW"
        assert rows[0]["merged_workcenter_group"] == "焊接_WB"
        assert rows[0]["plan_source_side"] == "output"

        assert svc.get_workcenter_merge_map() == {"焊接_DW": "焊接_WB"}

    @patch("mes_dashboard.services.production_achievement_workcenter_merge_service.MYSQL_OPS_ENABLED", False)
    def test_mysql_ops_disabled_read_degrades_to_empty(self):
        """D2: an empty/degraded table means the report renders empty for
        every workcenter_group (INNER JOIN matches nothing) -- the OPPOSITE
        downstream effect from D1's degrade above."""
        from mes_dashboard.services import production_achievement_workcenter_merge_service as svc

        assert svc.get_workcenter_merge_entries() == []
        assert svc.get_workcenter_merge_map() == {}

    @patch("mes_dashboard.services.production_achievement_workcenter_merge_service.MYSQL_OPS_ENABLED", False)
    def test_mysql_ops_disabled_write_returns_503(self):
        from mes_dashboard.services import production_achievement_workcenter_merge_service as svc

        with pytest.raises(svc.MySQLUnavailableError):
            svc.upsert_workcenter_merge(
                raw_workcenter_group="焊接_DW", merged_workcenter_group="焊接_WB", updated_by="tester"
            )

    @patch("mes_dashboard.services.production_achievement_workcenter_merge_service.MYSQL_OPS_ENABLED", False)
    def test_mysql_ops_disabled_delete_returns_503(self):
        from mes_dashboard.services import production_achievement_workcenter_merge_service as svc

        with pytest.raises(svc.MySQLUnavailableError):
            svc.delete_workcenter_merge(raw_workcenter_group="焊接_DW")

