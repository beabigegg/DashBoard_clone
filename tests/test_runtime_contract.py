# -*- coding: utf-8 -*-
"""Tests for runtime contract loading and drift validation."""

from __future__ import annotations

from pathlib import Path

from mes_dashboard.core.runtime_contract import (
    load_runtime_contract,
    validate_runtime_contract,
)


def test_runtime_contract_resolves_relative_watchdog_paths(tmp_path, monkeypatch):
    monkeypatch.setenv("MES_DASHBOARD_ROOT", str(tmp_path))
    monkeypatch.setenv("WATCHDOG_RUNTIME_DIR", "./tmp")
    monkeypatch.setenv("WATCHDOG_RESTART_FLAG", "./tmp/restart.flag")
    monkeypatch.setenv("WATCHDOG_PID_FILE", "./tmp/gunicorn.pid")
    monkeypatch.setenv("WATCHDOG_STATE_FILE", "./tmp/restart_state.json")

    contract = load_runtime_contract()
    assert Path(contract["watchdog_runtime_dir"]) == (tmp_path / "tmp").resolve()
    assert Path(contract["watchdog_restart_flag"]) == (tmp_path / "tmp" / "restart.flag").resolve()
    assert Path(contract["watchdog_pid_file"]) == (tmp_path / "tmp" / "gunicorn.pid").resolve()


def test_runtime_contract_detects_flag_pid_drift():
    contract = {
        "watchdog_runtime_dir": "/opt/runtime",
        "watchdog_restart_flag": "/tmp/restart.flag",
        "watchdog_pid_file": "/tmp/gunicorn.pid",
        "watchdog_state_file": "/tmp/restart_state.json",
        "gunicorn_bind": "0.0.0.0:8080",
        "conda_bin": "",
        "conda_env_name": "mes-dashboard",
    }
    errors = validate_runtime_contract(contract, strict=False)
    assert any("WATCHDOG_RESTART_FLAG" in err for err in errors)
    assert any("WATCHDOG_PID_FILE" in err for err in errors)
