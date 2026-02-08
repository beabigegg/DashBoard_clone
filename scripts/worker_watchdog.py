#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Worker watchdog for MES Dashboard.

Monitors a restart flag file and signals Gunicorn master to gracefully
reload workers when the flag is detected.

Usage:
    python scripts/worker_watchdog.py

The watchdog:
- Checks for /tmp/mes_dashboard_restart.flag every 5 seconds
- Sends SIGHUP to Gunicorn master process when flag is detected
- Removes the flag file after signaling
- Logs all restart events

Configuration via environment variables:
- WATCHDOG_CHECK_INTERVAL: Check interval in seconds (default: 5)
- WATCHDOG_RESTART_FLAG: Path to restart flag file
- WATCHDOG_PID_FILE: Path to Gunicorn PID file
"""

from __future__ import annotations

import json
import logging
import os
import signal
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from mes_dashboard.core.runtime_contract import (  # noqa: E402
    build_runtime_contract_diagnostics,
    load_runtime_contract,
)
from mes_dashboard.core.watchdog_logging import attach_sqlite_log_handler  # noqa: E402
from mes_dashboard.core.worker_recovery_policy import (  # noqa: E402
    decide_restart_request,
    evaluate_worker_recovery_state,
    extract_last_requested_at,
    extract_restart_history,
    get_worker_recovery_policy_config,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
    ]
)
logger = logging.getLogger('mes_dashboard.watchdog')
attach_sqlite_log_handler(logger)

# ============================================================
# Configuration
# ============================================================

_RUNTIME_CONTRACT = load_runtime_contract(project_root=PROJECT_ROOT)
CHECK_INTERVAL = int(
    os.getenv('WATCHDOG_CHECK_INTERVAL', str(_RUNTIME_CONTRACT['watchdog_check_interval']))
)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


DEFAULT_RUNTIME_DIR = Path(_RUNTIME_CONTRACT['watchdog_runtime_dir'])
RESTART_FLAG_PATH = _RUNTIME_CONTRACT['watchdog_restart_flag']
GUNICORN_PID_FILE = _RUNTIME_CONTRACT['watchdog_pid_file']
RESTART_STATE_FILE = _RUNTIME_CONTRACT['watchdog_state_file']
RUNTIME_CONTRACT_VERSION = _RUNTIME_CONTRACT['version']
RESTART_HISTORY_MAX = _env_int('WATCHDOG_RESTART_HISTORY_MAX', 50)


# ============================================================
# Watchdog Implementation
# ============================================================


def validate_runtime_contract_or_raise() -> None:
    """Fail fast if runtime contract is inconsistent."""
    strict = os.getenv("RUNTIME_CONTRACT_ENFORCE", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    diagnostics = build_runtime_contract_diagnostics(strict=strict)
    if diagnostics["valid"]:
        return

    details = "; ".join(diagnostics["errors"])
    raise RuntimeError(f"Runtime contract validation failed: {details}")


def log_restart_audit(event: str, payload: dict) -> None:
    entry = {
        "event": event,
        "timestamp": datetime.utcnow().isoformat(),
        "runtime_contract_version": RUNTIME_CONTRACT_VERSION,
        **payload,
    }
    logger.info("worker_watchdog_audit %s", json.dumps(entry, ensure_ascii=False))

def get_gunicorn_pid() -> int | None:
    """Get Gunicorn master PID from PID file.

    Returns:
        PID of Gunicorn master process, or None if not found.
    """
    pid_path = Path(GUNICORN_PID_FILE)

    if not pid_path.exists():
        logger.warning(f"PID file not found: {GUNICORN_PID_FILE}")
        return None

    try:
        pid = int(pid_path.read_text().strip())
        # Verify process exists
        os.kill(pid, 0)
        return pid
    except (ValueError, ProcessLookupError, PermissionError) as e:
        logger.warning(f"Invalid or stale PID file: {e}")
        return None


def read_restart_flag() -> dict | None:
    """Read and parse the restart flag file.

    Returns:
        Dictionary with restart metadata, or None if no flag exists.
    """
    flag_path = Path(RESTART_FLAG_PATH)

    if not flag_path.exists():
        return None

    try:
        content = flag_path.read_text().strip()
        if content:
            return json.loads(content)
        return {"timestamp": datetime.now().isoformat()}
    except (json.JSONDecodeError, IOError) as e:
        logger.warning(f"Error reading restart flag: {e}")
        return {"timestamp": datetime.now().isoformat(), "error": str(e)}


def remove_restart_flag() -> bool:
    """Remove the restart flag file.

    Returns:
        True if file was removed, False otherwise.
    """
    flag_path = Path(RESTART_FLAG_PATH)

    try:
        if flag_path.exists():
            flag_path.unlink()
            return True
        return False
    except IOError as e:
        logger.error(f"Failed to remove restart flag: {e}")
        return False


def load_restart_state() -> dict:
    """Load persisted restart state from disk."""
    state_path = Path(RESTART_STATE_FILE)
    if not state_path.exists():
        return {}
    try:
        return json.loads(state_path.read_text())
    except (json.JSONDecodeError, IOError):
        return {}


def save_restart_state(
    requested_by: str | None = None,
    requested_at: str | None = None,
    requested_ip: str | None = None,
    completed_at: str | None = None,
    success: bool = True,
    source: str = "manual",
    decision: str = "allowed",
    decision_reason: str | None = None,
    manual_override: bool = False,
    policy_state: dict | None = None,
) -> None:
    """Save restart state for status queries.

    Args:
        requested_by: Username who requested the restart.
        requested_at: ISO timestamp when restart was requested.
        requested_ip: IP address of requester.
        completed_at: ISO timestamp when restart was completed.
        success: Whether the restart was successful.
    """
    state_path = Path(RESTART_STATE_FILE)

    entry = {
        "requested_by": requested_by,
        "requested_at": requested_at,
        "requested_ip": requested_ip,
        "completed_at": completed_at,
        "success": success,
        "source": source,
        "decision": decision,
        "decision_reason": decision_reason,
        "manual_override": manual_override,
        "policy_state": policy_state or {},
    }
    current_state = load_restart_state()
    history = current_state.get("history", [])
    if not isinstance(history, list):
        history = []
    history.append(entry)
    if len(history) > RESTART_HISTORY_MAX:
        history = history[-RESTART_HISTORY_MAX:]

    state = {
        "last_restart": entry,
        "history": history,
        "history_limit": RESTART_HISTORY_MAX,
    }

    try:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(state, indent=2))
    except IOError as e:
        logger.error(f"Failed to save restart state: {e}")


def send_reload_signal(pid: int) -> bool:
    """Send SIGHUP to Gunicorn master to reload workers.

    Args:
        pid: PID of Gunicorn master process.

    Returns:
        True if signal was sent successfully, False otherwise.
    """
    try:
        os.kill(pid, signal.SIGHUP)
        logger.info(f"Sent SIGHUP to Gunicorn master (PID: {pid})")
        return True
    except ProcessLookupError:
        logger.error(f"Process {pid} not found")
        return False
    except PermissionError:
        logger.error(f"Permission denied sending signal to PID {pid}")
        return False


def process_restart_request() -> bool:
    """Process a restart request if flag file exists.

    Returns:
        True if restart was processed, False if no restart needed.
    """
    flag_data = read_restart_flag()

    if flag_data is None:
        return False

    logger.info(f"Restart flag detected: {flag_data}")
    source = str(flag_data.get("source") or "manual").strip().lower()
    manual_override = bool(flag_data.get("manual_override"))
    override_ack = bool(flag_data.get("override_acknowledged"))
    restart_state = load_restart_state()
    restart_history = extract_restart_history(restart_state)
    policy_state = evaluate_worker_recovery_state(
        restart_history,
        last_requested_at=extract_last_requested_at(restart_state),
    )
    decision = decide_restart_request(
        policy_state,
        source=source,
        manual_override=manual_override,
        override_acknowledged=override_ack,
    )

    if not decision["allowed"]:
        remove_restart_flag()
        save_restart_state(
            requested_by=flag_data.get("user"),
            requested_at=flag_data.get("timestamp"),
            requested_ip=flag_data.get("ip"),
            completed_at=datetime.now().isoformat(),
            success=False,
            source=source,
            decision=decision["decision"],
            decision_reason=decision["reason"],
            manual_override=manual_override,
            policy_state=policy_state,
        )
        log_restart_audit(
            "restart_blocked",
            {
                "source": source,
                "actor": flag_data.get("user"),
                "ip": flag_data.get("ip"),
                "decision": decision,
                "policy_state": policy_state,
            },
        )
        return True

    # Get Gunicorn master PID
    pid = get_gunicorn_pid()

    if pid is None:
        logger.error("Cannot restart: Gunicorn master PID not found")
        # Still remove flag to prevent infinite loop
        remove_restart_flag()
        save_restart_state(
            requested_by=flag_data.get("user"),
            requested_at=flag_data.get("timestamp"),
            requested_ip=flag_data.get("ip"),
            completed_at=datetime.now().isoformat(),
            success=False,
            source=source,
            decision="failed",
            decision_reason="gunicorn_pid_unavailable",
            manual_override=manual_override,
            policy_state=policy_state,
        )
        log_restart_audit(
            "restart_failed",
            {
                "source": source,
                "actor": flag_data.get("user"),
                "ip": flag_data.get("ip"),
                "decision_reason": "gunicorn_pid_unavailable",
                "policy_state": policy_state,
            },
        )
        return True

    # Send reload signal
    success = send_reload_signal(pid)

    # Remove flag file
    remove_restart_flag()

    # Save state
    save_restart_state(
        requested_by=flag_data.get("user"),
        requested_at=flag_data.get("timestamp"),
        requested_ip=flag_data.get("ip"),
        completed_at=datetime.now().isoformat(),
        success=success,
        source=source,
        decision="executed" if success else "failed",
        decision_reason="signal_sighup" if success else "signal_failed",
        manual_override=manual_override,
        policy_state=policy_state,
    )

    if success:
        logger.info(
            f"Worker restart completed - "
            f"Requested by: {flag_data.get('user', 'unknown')}, "
            f"IP: {flag_data.get('ip', 'unknown')}"
        )
        log_restart_audit(
            "restart_executed",
            {
                "source": source,
                "actor": flag_data.get("user"),
                "ip": flag_data.get("ip"),
                "manual_override": manual_override,
                "policy_state": policy_state,
            },
        )
    else:
        log_restart_audit(
            "restart_failed",
            {
                "source": source,
                "actor": flag_data.get("user"),
                "ip": flag_data.get("ip"),
                "decision_reason": "signal_failed",
                "policy_state": policy_state,
            },
        )

    return True


def run_watchdog() -> None:
    """Main watchdog loop."""
    validate_runtime_contract_or_raise()
    policy = get_worker_recovery_policy_config()
    logger.info(
        f"Worker watchdog started - "
        f"Check interval: {CHECK_INTERVAL}s, "
        f"Flag path: {RESTART_FLAG_PATH}, "
        f"PID file: {GUNICORN_PID_FILE}, "
        f"Policy(cooldown={policy['cooldown_seconds']}s, "
        f"retry_budget={policy['retry_budget']}, "
        f"window={policy['window_seconds']}s, "
        f"guarded={policy['guarded_mode_enabled']})"
    )

    while True:
        try:
            process_restart_request()
        except Exception as e:
            logger.exception(f"Error in watchdog loop: {e}")

        time.sleep(CHECK_INTERVAL)


def main() -> None:
    """Entry point for watchdog script."""
    try:
        run_watchdog()
    except KeyboardInterrupt:
        logger.info("Watchdog stopped by user")
        sys.exit(0)


if __name__ == "__main__":
    main()
