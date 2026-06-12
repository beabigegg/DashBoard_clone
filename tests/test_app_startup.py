# -*- coding: utf-8 -*-
"""AC-1 absence tests: daemon-thread prewarm calls must not exist in app.py.

Uses AST inspection — NOT mock — so a removed symbol is detected even if
a test-time mock would otherwise hide the gap.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_APP_PY = Path(__file__).resolve().parent.parent / "src" / "mes_dashboard" / "app.py"


class TestDaemonPrewarmRemovedFromApp:
    """AC-1: start_duckdb_prewarm and start_downtime_prewarm must not be called in app.py."""

    def _parse_app(self) -> ast.Module:
        source = _APP_PY.read_text(encoding="utf-8")
        return ast.parse(source, filename=str(_APP_PY))

    def _all_call_names(self, tree: ast.Module) -> list[str]:
        """Return function/method names from all Call nodes in the AST."""
        names = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name):
                    names.append(func.id)
                elif isinstance(func, ast.Attribute):
                    names.append(func.attr)
        return names

    def _all_imported_names(self, tree: ast.Module) -> list[str]:
        """Return all names imported at module/function level."""
        names = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    asname = alias.asname or alias.name
                    names.append(asname)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    asname = alias.asname or alias.name
                    names.append(asname)
        return names

    def test_start_duckdb_prewarm_not_called_in_app(self):
        """app.py must have no Call node for start_duckdb_prewarm (AC-1)."""
        tree = self._parse_app()
        calls = self._all_call_names(tree)
        assert "start_duckdb_prewarm" not in calls, (
            "app.py still calls start_duckdb_prewarm(). "
            "Remove this daemon-thread call (IP-4); the RQ warmup queue handles it now."
        )

    def test_start_downtime_prewarm_not_called_in_app(self):
        """app.py must have no Call node for start_downtime_prewarm (AC-1)."""
        tree = self._parse_app()
        calls = self._all_call_names(tree)
        assert "start_downtime_prewarm" not in calls, (
            "app.py still calls start_downtime_prewarm(). "
            "Remove this daemon-thread call (IP-4); the RQ warmup queue handles it now."
        )

    def test_start_duckdb_prewarm_not_imported_in_app(self):
        """app.py must not import start_duckdb_prewarm (AC-1)."""
        tree = self._parse_app()
        imported = self._all_imported_names(tree)
        assert "start_duckdb_prewarm" not in imported, (
            "app.py still imports start_duckdb_prewarm. "
            "Remove the import alongside the call (IP-4)."
        )

    def test_start_downtime_prewarm_not_imported_in_app(self):
        """app.py must not import start_downtime_prewarm (AC-1)."""
        tree = self._parse_app()
        imported = self._all_imported_names(tree)
        assert "start_downtime_prewarm" not in imported, (
            "app.py still imports start_downtime_prewarm. "
            "Remove the import alongside the call (IP-4)."
        )
