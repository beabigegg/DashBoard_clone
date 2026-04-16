# -*- coding: utf-8 -*-
"""Unit tests for mes_dashboard.core.spool_dir_check."""

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

import mes_dashboard.core.spool_dir_check as spool_check


# ---------------------------------------------------------------------------
# write_pid_probe
# ---------------------------------------------------------------------------


def test_write_pid_probe_creates_file(tmp_path, monkeypatch):
    """write_pid_probe() should create probe_<pid>.json in QUERY_SPOOL_DIR."""
    monkeypatch.setenv("QUERY_SPOOL_DIR", str(tmp_path))

    spool_check.write_pid_probe()

    pid = os.getpid()
    probe_path = tmp_path / f"probe_{pid}.json"
    assert probe_path.exists(), f"Expected {probe_path} to exist"

    data = json.loads(probe_path.read_text())
    assert data["pid"] == pid
    assert "boot_at" in data
    assert "hostname" in data


def test_write_pid_probe_missing_dir(tmp_path, monkeypatch, caplog):
    """write_pid_probe() should warn but not raise when the dir is missing."""
    missing = str(tmp_path / "nonexistent")
    monkeypatch.setenv("QUERY_SPOOL_DIR", missing)

    import logging
    with caplog.at_level(logging.WARNING, logger="mes_dashboard.spool_dir_check"):
        spool_check.write_pid_probe()  # must not raise

    assert any("does not exist" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# check_shared_volume
# ---------------------------------------------------------------------------


def test_check_shared_volume_skips_single_worker(monkeypatch, caplog):
    """Single-worker deployment should skip the check silently."""
    monkeypatch.setenv("GUNICORN_WORKERS", "1")

    import logging
    with caplog.at_level(logging.DEBUG, logger="mes_dashboard.spool_dir_check"):
        spool_check.check_shared_volume(timeout=1)

    assert not any(
        "mismatch" in r.message.lower() for r in caplog.records
    ), "Should not log mismatch for single-worker"


def test_check_shared_volume_mismatch_increments_counter(tmp_path, monkeypatch, caplog):
    """When only own probe is visible after timeout, log ERROR and increment counter."""
    monkeypatch.setenv("GUNICORN_WORKERS", "2")
    monkeypatch.setenv("QUERY_SPOOL_DIR", str(tmp_path))

    own_pid = os.getpid()
    # Write only own probe — no peer will be visible
    own_probe = tmp_path / f"probe_{own_pid}.json"
    own_probe.write_text(json.dumps({"pid": own_pid}))

    # Reset counter before test
    with spool_check._COUNT_LOCK:
        spool_check._SHARED_VOLUME_MISMATCH_COUNT = 0

    import logging
    with caplog.at_level(logging.ERROR, logger="mes_dashboard.spool_dir_check"):
        spool_check.check_shared_volume(timeout=1)  # short timeout for unit test

    # Counter must be incremented
    assert spool_check.get_mismatch_count() >= 1

    # ERROR log must mention mismatch
    assert any(
        "mismatch" in r.message.lower() for r in caplog.records
    ), f"Expected mismatch ERROR in logs; got: {[r.message for r in caplog.records]}"


def test_check_shared_volume_ok_when_peer_visible(tmp_path, monkeypatch, caplog):
    """No mismatch should be recorded when a peer probe file is present."""
    monkeypatch.setenv("GUNICORN_WORKERS", "2")
    monkeypatch.setenv("QUERY_SPOOL_DIR", str(tmp_path))

    own_pid = os.getpid()
    peer_pid = own_pid + 1

    (tmp_path / f"probe_{own_pid}.json").write_text(json.dumps({"pid": own_pid}))
    (tmp_path / f"probe_{peer_pid}.json").write_text(json.dumps({"pid": peer_pid}))

    with spool_check._COUNT_LOCK:
        spool_check._SHARED_VOLUME_MISMATCH_COUNT = 0

    import logging
    with caplog.at_level(logging.ERROR, logger="mes_dashboard.spool_dir_check"):
        spool_check.check_shared_volume(timeout=5)

    assert spool_check.get_mismatch_count() == 0
    assert not any("mismatch" in r.message.lower() for r in caplog.records)
