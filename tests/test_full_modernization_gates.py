# -*- coding: utf-8 -*-
"""Tests for full modernization governance gate runner."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_full_modernization_gates.py"
REPORT = ROOT / "docs" / "migration" / "full-modernization-architecture-blueprint" / "quality_gate_report.json"
SCOPE_MATRIX = ROOT / "docs" / "migration" / "full-modernization-architecture-blueprint" / "route_scope_matrix.json"

_GATES_SPEC = importlib.util.spec_from_file_location("check_full_modernization_gates", SCRIPT)
assert _GATES_SPEC and _GATES_SPEC.loader
gates = importlib.util.module_from_spec(_GATES_SPEC)
sys.modules[_GATES_SPEC.name] = gates
_GATES_SPEC.loader.exec_module(gates)


def _run(mode: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python", str(SCRIPT), "--mode", mode, "--report", str(REPORT)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )


def test_gate_runner_warn_mode_passes_and_generates_report():
    result = _run("warn")
    assert result.returncode == 0, result.stdout + result.stderr

    payload = json.loads(REPORT.read_text(encoding="utf-8"))
    assert payload["mode"] == "warn"
    assert payload["passed"] is True


def test_gate_runner_block_mode_passes_current_baseline():
    result = _run("block")
    assert result.returncode == 0, result.stdout + result.stderr

    payload = json.loads(REPORT.read_text(encoding="utf-8"))
    assert payload["mode"] == "block"
    assert payload["passed"] is True


def test_scope_matrix_keeps_deferred_routes_for_follow_up_only():
    matrix = json.loads(SCOPE_MATRIX.read_text(encoding="utf-8"))
    deferred = {item["route"] for item in matrix["deferred"]}
    assert deferred == {"/tables", "/excel-query", "/query-tool", "/mid-section-defect"}


def test_route_contract_parity_check_detects_route_set_drift():
    report = gates.CheckReport(mode="block")
    backend = {"/wip-overview": {"scope": "in-scope"}}
    frontend = {
        "/wip-overview": "in-scope",
        "/extra": "deferred",
    }

    gates._check_frontend_backend_route_contract_parity(backend, frontend, report)

    assert any("/extra" in error for error in report.errors)


def test_route_contract_parity_check_detects_scope_mismatch():
    report = gates.CheckReport(mode="block")
    backend = {"/wip-overview": {"scope": "in-scope"}}
    frontend = {"/wip-overview": "deferred"}

    gates._check_frontend_backend_route_contract_parity(backend, frontend, report)

    assert any("scope mismatch" in error for error in report.errors)


def test_style_governance_flags_shell_tokens_without_fallback(tmp_path):
    report = gates.CheckReport(mode="block")
    css_file = tmp_path / "route.css"
    css_file.write_text(
        ".demo { background: linear-gradient(var(--portal-brand-start), #fff); }",
        encoding="utf-8",
    )

    original_route_css_targets = gates._route_css_targets
    try:
        gates._route_css_targets = lambda: {"/wip-overview": [css_file]}  # type: ignore[assignment]
        gates._check_style_governance({"/wip-overview"}, {}, report)
    finally:
        gates._route_css_targets = original_route_css_targets  # type: ignore[assignment]

    assert any("without fallback" in error for error in report.errors)
