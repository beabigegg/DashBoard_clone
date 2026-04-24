# -*- coding: utf-8 -*-
"""
Real multi-worker gunicorn integration tests.

These tests spawn actual gunicorn worker processes and exercise cross-process
spool sharing, distributed lock exclusion, and shared-volume probe visibility.

Run with:
    conda run -n mes-dashboard pytest tests/integration/test_real_multi_worker.py \\
        --run-integration-real -v
"""

from __future__ import annotations

import json
import os
import signal
import time
import urllib.request
import urllib.parse
import urllib.error

import pytest

pytestmark = pytest.mark.integration_real


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _http_post(url: str, payload: dict, timeout: int = 5) -> dict:
    """POST JSON to *url* and return the parsed response body."""
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def _http_get(url: str, timeout: int = 5) -> tuple[int, dict]:
    """GET *url*, return (status_code, parsed_body)."""
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        try:
            body = json.loads(exc.read())
        except Exception:
            body = {}
        return exc.code, body


# ---------------------------------------------------------------------------
# Test: shared-volume probe visibility (task 4.5)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("gunicorn_workers", [2], indirect=True)
def test_shared_volume_probe_visibility(gunicorn_workers, temp_spool_dir):
    """Both workers should write their probe files to the shared spool dir.

    Each gunicorn instance spawns one worker (GUNICORN_WORKERS=1).  The
    worker process has a *different* PID from the master process tracked by
    the test fixture.  We therefore check that at least 2 distinct PIDs wrote
    probe files — one per gunicorn instance — rather than matching against the
    master PIDs returned by the fixture.
    """
    n_instances = len(gunicorn_workers)
    assert n_instances == 2, "Expected 2 gunicorn instances"

    # Probe files are written at boot; give workers up to 30 s to appear
    deadline = time.monotonic() + 30
    found_pids: set[int] = set()

    while time.monotonic() < deadline:
        try:
            entries = list(temp_spool_dir.iterdir())
        except OSError:
            time.sleep(0.5)
            continue

        found_pids = set()
        for entry in entries:
            if entry.name.startswith("probe_") and entry.name.endswith(".json"):
                try:
                    data = json.loads(entry.read_text())
                    found_pids.add(data["pid"])
                except Exception:
                    pass

        if len(found_pids) >= n_instances:
            break
        time.sleep(0.5)

    assert len(found_pids) >= n_instances, (
        f"Expected at least {n_instances} probe files (one per gunicorn instance); "
        f"found probes for {len(found_pids)} distinct PIDs in {temp_spool_dir}: {found_pids!r}"
    )


# ---------------------------------------------------------------------------
# Test: cross-process lock exclusion (task 4.3)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("gunicorn_workers", [2], indirect=True)
def test_cross_process_lock_exclusion(gunicorn_workers):
    """A lock held by worker A should not be acquirable by worker B.

    We use the /health endpoint to confirm both workers are live, then
    call the debug-lock endpoints to verify cross-process exclusion.

    Note: This test uses the /api/debug/lock/* endpoints that must be
    available in testing mode (they are registered only when FLASK_ENV=testing).
    If those endpoints are not present, this test is skipped gracefully.
    """
    assert len(gunicorn_workers) >= 2

    pid_a, port_a = gunicorn_workers[0]
    pid_b, port_b = gunicorn_workers[1]

    # Confirm both workers are healthy
    for port in (port_a, port_b):
        status, _ = _http_get(f"http://127.0.0.1:{port}/health")
        assert status == 200, f"Worker on port {port} is not healthy"

    # Acquire lock on worker A
    lock_name = f"integ-test-lock-{os.getpid()}"
    ttl = 10

    acquire_url_a = f"http://127.0.0.1:{port_a}/api/debug/lock/acquire"
    acquire_url_b = f"http://127.0.0.1:{port_b}/api/debug/lock/acquire"
    release_url_a = f"http://127.0.0.1:{port_a}/api/debug/lock/release"

    # Check if debug lock endpoints exist
    status_check, _ = _http_get(f"http://127.0.0.1:{port_a}/api/debug/lock/acquire")
    if status_check == 404:
        pytest.skip("Debug lock endpoints not available in this build")

    try:
        # Acquire on A
        resp_a = _http_post(acquire_url_a, {"lock_name": lock_name, "ttl_seconds": ttl, "fail_mode": "closed"})
        assert resp_a.get("data", {}).get("acquired") is True, f"Worker A failed to acquire lock: {resp_a}"

        # Worker B must see it as taken
        resp_b = _http_post(acquire_url_b, {"lock_name": lock_name, "ttl_seconds": ttl, "fail_mode": "closed"})
        b_acquired = resp_b.get("data", {}).get("acquired")
        assert b_acquired is False, (
            f"Worker B should NOT have acquired the lock held by Worker A, "
            f"but got: {resp_b}"
        )
    finally:
        # Release lock on A
        try:
            _http_post(release_url_a, {"lock_name": lock_name})
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Test: lock TTL expiry after SIGKILL (task 4.4)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("gunicorn_workers", [2], indirect=True)
def test_lock_ttl_expiry_after_sigkill(gunicorn_workers):
    """After worker A is SIGKILLed, the lock TTL should expire and worker B can re-acquire."""
    assert len(gunicorn_workers) >= 2

    pid_a, port_a = gunicorn_workers[0]
    pid_b, port_b = gunicorn_workers[1]

    lock_name = f"integ-ttl-lock-{os.getpid()}"
    ttl = 3  # Short TTL for the test

    acquire_url_a = f"http://127.0.0.1:{port_a}/api/debug/lock/acquire"
    acquire_url_b = f"http://127.0.0.1:{port_b}/api/debug/lock/acquire"

    # Check if debug lock endpoints exist
    status_check, _ = _http_get(f"http://127.0.0.1:{port_a}/api/debug/lock/acquire")
    if status_check == 404:
        pytest.skip("Debug lock endpoints not available in this build")

    # Acquire lock on A with short TTL
    resp_a = _http_post(acquire_url_a, {"lock_name": lock_name, "ttl_seconds": ttl, "fail_mode": "closed"})
    assert resp_a.get("data", {}).get("acquired") is True, f"Worker A failed to acquire lock: {resp_a}"

    # SIGKILL worker A (does not release the lock gracefully)
    os.kill(pid_a, signal.SIGKILL)

    # Wait for TTL + buffer
    time.sleep(ttl + 1)

    # Worker B should now be able to acquire
    resp_b = _http_post(acquire_url_b, {"lock_name": lock_name, "ttl_seconds": ttl, "fail_mode": "closed"})
    b_acquired = resp_b.get("data", {}).get("acquired")
    assert b_acquired is True, (
        f"Worker B should have acquired the lock after TTL expiry, "
        f"but got: {resp_b}"
    )


# ---------------------------------------------------------------------------
# Test: cross-worker spool round-trip (task 4.2)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("gunicorn_workers", [2], indirect=True)
def test_cross_worker_spool_round_trip(gunicorn_workers, temp_spool_dir):
    """A query written by worker A should be readable via worker B.

    Uses the /api/debug/spool/* endpoints which are only available in
    testing mode.  Skips gracefully if those endpoints are absent.
    """
    assert len(gunicorn_workers) >= 2
    pid_a, port_a = gunicorn_workers[0]
    pid_b, port_b = gunicorn_workers[1]

    write_url = f"http://127.0.0.1:{port_a}/api/debug/spool/write"
    read_url_b = f"http://127.0.0.1:{port_b}/api/debug/spool/read"

    # Check endpoint availability
    status_check, _ = _http_get(f"http://127.0.0.1:{port_a}/api/debug/spool/write")
    if status_check == 404:
        pytest.skip("Debug spool endpoints not available in this build")

    # Write a tiny spool entry via worker A
    query_id = f"integ-spool-{os.getpid()}"
    payload = {"query_id": query_id, "data": {"rows": [{"x": 1, "y": 2}]}}
    resp_write = _http_post(write_url, payload)
    assert resp_write.get("data", {}).get("ok") is True, f"Spool write failed: {resp_write}"

    # Read it back via worker B
    read_url = f"{read_url_b}?query_id={urllib.parse.quote(query_id)}"
    status, resp_read = _http_get(read_url)
    assert status == 200, f"Worker B could not read spool file: {resp_read}"
    assert resp_read.get("data", {}).get("rows") == [{"x": 1, "y": 2}], (
        f"Round-trip data mismatch: {resp_read}"
    )


# ---------------------------------------------------------------------------
# Stage 4a dispatched smoke: today-snapshot endpoint (hold-history-today-mode)
# ---------------------------------------------------------------------------

_TODAY_SUMMARY_REQUIRED_KEYS = {
    "onHoldTotalCount",
    "onHoldTotalQty",
    "todayNewQty",
    "todayReleaseQty",
    "todayFutureHoldQty",
    "onHoldAvgHours",
    "onHoldMaxHours",
}


@pytest.mark.parametrize("gunicorn_workers", [1], indirect=True)
def test_today_snapshot_stage4a_smoke(gunicorn_workers):
    """Stage 4a: POST /api/hold-history/today-snapshot returns 200 with envelope + summary keys.

    Accepts 503 when Oracle is unavailable (CI without a real DB).
    Never accepts 500 — that indicates an unhandled application error.
    """
    assert len(gunicorn_workers) >= 1
    _, port = gunicorn_workers[0]

    url = f"http://127.0.0.1:{port}/api/hold-history/today-snapshot"
    body = json.dumps({"hold_type": "quality", "record_type": "on_hold"}).encode()
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            status = resp.status
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        status = exc.code
        raw = exc.read()

    assert status != 500, (
        f"today-snapshot returned HTTP 500 — unhandled exception in route. "
        f"Body: {raw[:300]!r}"
    )
    assert status in (200, 503), (
        f"today-snapshot returned unexpected status {status}. "
        f"Body: {raw[:300]!r}"
    )

    payload = json.loads(raw)
    assert "success" in payload, f"Response missing 'success' field: {payload}"

    if status == 200:
        assert payload["success"] is True
        data = payload.get("data", {})
        assert isinstance(data, dict), f"'data' should be a dict, got {type(data)}"
        summary = data.get("summary", {})
        missing = _TODAY_SUMMARY_REQUIRED_KEYS - set(summary.keys())
        assert not missing, (
            f"today-snapshot summary missing keys: {missing}. "
            f"Got keys: {list(summary.keys())}"
        )
        assert "trend" not in data, (
            "today-snapshot must NOT include 'trend' (range-mode only)"
        )
