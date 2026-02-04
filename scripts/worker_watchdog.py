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

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
    ]
)
logger = logging.getLogger('mes_dashboard.watchdog')

# ============================================================
# Configuration
# ============================================================

CHECK_INTERVAL = int(os.getenv('WATCHDOG_CHECK_INTERVAL', '5'))
RESTART_FLAG_PATH = os.getenv(
    'WATCHDOG_RESTART_FLAG',
    '/tmp/mes_dashboard_restart.flag'
)
GUNICORN_PID_FILE = os.getenv(
    'WATCHDOG_PID_FILE',
    '/tmp/mes_dashboard_gunicorn.pid'
)
RESTART_STATE_FILE = os.getenv(
    'WATCHDOG_STATE_FILE',
    '/tmp/mes_dashboard_restart_state.json'
)


# ============================================================
# Watchdog Implementation
# ============================================================

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


def save_restart_state(
    requested_by: str | None = None,
    requested_at: str | None = None,
    requested_ip: str | None = None,
    completed_at: str | None = None,
    success: bool = True
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

    state = {
        "last_restart": {
            "requested_by": requested_by,
            "requested_at": requested_at,
            "requested_ip": requested_ip,
            "completed_at": completed_at,
            "success": success
        }
    }

    try:
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
            success=False
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
        success=success
    )

    if success:
        logger.info(
            f"Worker restart completed - "
            f"Requested by: {flag_data.get('user', 'unknown')}, "
            f"IP: {flag_data.get('ip', 'unknown')}"
        )

    return True


def run_watchdog() -> None:
    """Main watchdog loop."""
    logger.info(
        f"Worker watchdog started - "
        f"Check interval: {CHECK_INTERVAL}s, "
        f"Flag path: {RESTART_FLAG_PATH}, "
        f"PID file: {GUNICORN_PID_FILE}"
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
