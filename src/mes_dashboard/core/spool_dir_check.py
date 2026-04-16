# -*- coding: utf-8 -*-
"""Shared-volume probe and mismatch detection for QUERY_SPOOL_DIR.

At app startup each gunicorn worker writes a per-PID probe file into
``QUERY_SPOOL_DIR``.  A background check then verifies that, for a
multi-worker deployment, at least one *other* worker's probe is visible
within 30 seconds.  If not, the QUERY_SPOOL_DIR paths are not shared
across workers (volume misconfiguration) and the situation is logged at
ERROR level with a ``mes.spool.shared_volume_mismatch`` counter
increment.
"""

from __future__ import annotations

import json
import logging
import os
import socket
import time
from pathlib import Path

logger = logging.getLogger("mes_dashboard.spool_dir_check")


# ---------------------------------------------------------------------------
# Counter (process-local; mirrors the heavy_query_telemetry pattern)
# ---------------------------------------------------------------------------

_SHARED_VOLUME_MISMATCH_COUNT: int = 0

from threading import Lock as _Lock

_COUNT_LOCK = _Lock()


def _increment_mismatch_counter() -> None:
    global _SHARED_VOLUME_MISMATCH_COUNT
    with _COUNT_LOCK:
        _SHARED_VOLUME_MISMATCH_COUNT += 1


def get_mismatch_count() -> int:
    """Return the current value of the mes.spool.shared_volume_mismatch counter."""
    with _COUNT_LOCK:
        return _SHARED_VOLUME_MISMATCH_COUNT


# ---------------------------------------------------------------------------
# Probe write
# ---------------------------------------------------------------------------


def write_pid_probe() -> None:
    """Write a per-PID probe file into QUERY_SPOOL_DIR.

    The file name is ``probe_<pid>.json`` and contains::

        {"pid": <int>, "boot_at": <iso-timestamp>, "hostname": <str>}

    Errors are logged as WARNING but do not abort startup.
    """
    raw_dir = os.getenv("QUERY_SPOOL_DIR", "tmp/query_spool")
    spool_path = Path(raw_dir)

    if not spool_path.exists():
        logger.warning(
            "spool_dir_check: QUERY_SPOOL_DIR does not exist (%s); skipping probe write",
            spool_path,
        )
        return

    pid = os.getpid()
    probe_path = spool_path / f"probe_{pid}.json"
    payload = {
        "pid": pid,
        "boot_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "hostname": socket.gethostname(),
    }
    try:
        probe_path.write_text(json.dumps(payload))
        logger.debug("spool_dir_check: wrote probe %s", probe_path)
    except OSError as exc:
        logger.warning("spool_dir_check: failed to write probe %s: %s", probe_path, exc)


# ---------------------------------------------------------------------------
# Background check
# ---------------------------------------------------------------------------


def check_shared_volume(timeout: int = 30) -> None:
    """Verify that other gunicorn workers' probes are visible in QUERY_SPOOL_DIR.

    This runs in a background thread after startup (so it does not block boot).
    It only performs the check when ``GUNICORN_WORKERS > 1``; single-worker
    dev setups are silently skipped.

    If the check expires without seeing any peer probe, it logs an ERROR and
    increments ``mes.spool.shared_volume_mismatch``.
    """
    gunicorn_workers = int(os.getenv("GUNICORN_WORKERS", "1"))
    if gunicorn_workers <= 1:
        logger.debug(
            "spool_dir_check: GUNICORN_WORKERS=%d — shared-volume check skipped (single-worker)",
            gunicorn_workers,
        )
        return

    raw_dir = os.getenv("QUERY_SPOOL_DIR", "tmp/query_spool")
    spool_path = Path(raw_dir)
    own_pid = os.getpid()
    own_probe = f"probe_{own_pid}.json"

    deadline = time.monotonic() + timeout
    interval = 5

    while time.monotonic() < deadline:
        time.sleep(min(interval, max(0.1, deadline - time.monotonic())))
        if not spool_path.exists():
            continue
        try:
            probes = [f for f in os.listdir(spool_path) if f.startswith("probe_") and f.endswith(".json")]
        except OSError:
            continue

        peer_probes = [p for p in probes if p != own_probe]
        if peer_probes:
            logger.debug(
                "spool_dir_check: shared volume OK — found peer probes: %s",
                peer_probes,
            )
            return

    # Timed out with only own probe visible
    logger.error(
        "mes.spool.shared_volume_mismatch: worker pid=%d cannot see other gunicorn workers' "
        "probe files in QUERY_SPOOL_DIR=%r after %ds. "
        "This indicates workers are not sharing the same filesystem volume.",
        own_pid,
        raw_dir,
        timeout,
    )
    _increment_mismatch_counter()
