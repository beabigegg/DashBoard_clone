# -*- coding: utf-8 -*-
"""Runtime contract helpers shared by app, scripts, and watchdog."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any, Mapping

CONTRACT_VERSION = "2026.02-p2"
DEFAULT_PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _to_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _resolve_path(value: str | None, fallback: Path, project_root: Path) -> Path:
    if value is None or not str(value).strip():
        return fallback.resolve()
    raw = Path(str(value).strip())
    if raw.is_absolute():
        return raw.resolve()
    return (project_root / raw).resolve()


def load_runtime_contract(
    environ: Mapping[str, str] | None = None,
    *,
    project_root: Path | str | None = None,
) -> dict[str, Any]:
    """Load effective runtime contract from environment with normalized paths."""
    env = environ or os.environ
    root = Path(project_root or env.get("MES_DASHBOARD_ROOT", DEFAULT_PROJECT_ROOT)).resolve()
    runtime_dir = _resolve_path(
        env.get("WATCHDOG_RUNTIME_DIR"),
        root / "tmp",
        root,
    )

    restart_flag = _resolve_path(
        env.get("WATCHDOG_RESTART_FLAG"),
        runtime_dir / "mes_dashboard_restart.flag",
        root,
    )
    pid_file = _resolve_path(
        env.get("WATCHDOG_PID_FILE"),
        runtime_dir / "gunicorn.pid",
        root,
    )
    state_file = _resolve_path(
        env.get("WATCHDOG_STATE_FILE"),
        runtime_dir / "mes_dashboard_restart_state.json",
        root,
    )

    contract = {
        "version": env.get("RUNTIME_CONTRACT_VERSION", CONTRACT_VERSION),
        "project_root": str(root),
        "gunicorn_bind": env.get("GUNICORN_BIND", "0.0.0.0:8080"),
        "conda_bin": (env.get("CONDA_BIN", "") or "").strip(),
        "conda_env_name": (env.get("CONDA_ENV_NAME", "mes-dashboard") or "").strip(),
        "watchdog_runtime_dir": str(runtime_dir),
        "watchdog_restart_flag": str(restart_flag),
        "watchdog_pid_file": str(pid_file),
        "watchdog_state_file": str(state_file),
        "watchdog_check_interval": int(env.get("WATCHDOG_CHECK_INTERVAL", "5")),
        "validation_enforced": _to_bool(env.get("RUNTIME_CONTRACT_ENFORCE"), False),
    }
    return contract


def validate_runtime_contract(
    contract: Mapping[str, Any] | None = None,
    *,
    strict: bool = False,
) -> list[str]:
    """Validate runtime contract and return actionable errors."""
    cfg = dict(contract or load_runtime_contract())
    errors: list[str] = []

    runtime_dir = Path(str(cfg["watchdog_runtime_dir"])).resolve()
    restart_flag = Path(str(cfg["watchdog_restart_flag"])).resolve()
    pid_file = Path(str(cfg["watchdog_pid_file"])).resolve()
    state_file = Path(str(cfg["watchdog_state_file"])).resolve()

    if restart_flag.parent != runtime_dir:
        errors.append(
            "WATCHDOG_RESTART_FLAG must be under WATCHDOG_RUNTIME_DIR "
            f"({restart_flag} not under {runtime_dir})."
        )
    if pid_file.parent != runtime_dir:
        errors.append(
            "WATCHDOG_PID_FILE must be under WATCHDOG_RUNTIME_DIR "
            f"({pid_file} not under {runtime_dir})."
        )

    if not state_file.is_absolute():
        errors.append("WATCHDOG_STATE_FILE must resolve to an absolute path.")

    bind = str(cfg.get("gunicorn_bind", "")).strip()
    if ":" not in bind:
        errors.append(f"GUNICORN_BIND must include host:port (current: {bind!r}).")

    conda_bin = str(cfg.get("conda_bin", "")).strip()
    if strict and not conda_bin:
        conda_on_path = shutil.which("conda")
        if not conda_on_path:
            errors.append(
                "CONDA_BIN is required when strict runtime validation is enabled "
                "and conda is not discoverable on PATH."
            )
    if conda_bin:
        conda_path = Path(conda_bin)
        if not conda_path.exists():
            errors.append(f"CONDA_BIN does not exist: {conda_bin}")
        elif not os.access(conda_bin, os.X_OK):
            errors.append(f"CONDA_BIN is not executable: {conda_bin}")

    conda_env_name = str(cfg.get("conda_env_name", "")).strip()
    active_env = (os.getenv("CONDA_DEFAULT_ENV") or "").strip()
    if strict and conda_env_name and active_env and active_env != conda_env_name:
        errors.append(
            "CONDA_DEFAULT_ENV mismatch: "
            f"expected {conda_env_name!r}, got {active_env!r}."
        )

    return errors


def build_runtime_contract_diagnostics(*, strict: bool = False) -> dict[str, Any]:
    """Build diagnostics payload for runtime contract introspection."""
    contract = load_runtime_contract()
    errors = validate_runtime_contract(contract, strict=strict)
    return {
        "valid": not errors,
        "strict": strict,
        "errors": errors,
        "contract": contract,
    }
