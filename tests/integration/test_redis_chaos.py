# -*- coding: utf-8 -*-
"""
Redis chaos integration tests.

These tests spawn dedicated Redis instances (cache-plane + control-plane),
induce real outages mid-flight, and verify fail-mode behaviour and reconnect
semantics of the distributed lock layer.

Run with:
    conda run -n mes-dashboard pytest tests/integration/test_redis_chaos.py \\
        --run-integration-real -v
"""

from __future__ import annotations

import os
import signal
import time
from pathlib import Path

import pytest
import redis as redis_lib

pytestmark = pytest.mark.integration_real


# ---------------------------------------------------------------------------
# conftest-local helpers
# ---------------------------------------------------------------------------


def _redis_port(url: str) -> int:
    """Extract the port number from a redis://... URL."""
    return int(url.split(":")[-1].split("/")[0])


def _make_redis(url: str, socket_timeout: float = 1.0) -> redis_lib.Redis:
    return redis_lib.Redis.from_url(
        url,
        decode_responses=True,
        socket_timeout=socket_timeout,
        socket_connect_timeout=socket_timeout,
        retry_on_timeout=False,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def cache_and_control_redis(local_redis, tmp_path):
    """Spawn a second Redis instance as the control-plane Redis.

    Returns ``(cache_url, control_url)`` where:
    - ``cache_url``   == local_redis (shared from the base fixture)
    - ``control_url`` == a second Redis with noeviction policy
    """
    from tests.integration.conftest import _find_free_port
    import subprocess

    port = _find_free_port()
    log_file = tmp_path / "redis-control.log"

    proc = subprocess.Popen(
        [
            "redis-server",
            "--port", str(port),
            "--maxmemory", "16mb",
            "--maxmemory-policy", "noeviction",
            "--save", "",
            "--loglevel", "warning",
        ],
        stdout=log_file.open("w"),
        stderr=subprocess.STDOUT,
    )

    control_url = f"redis://127.0.0.1:{port}/0"
    client = redis_lib.Redis(host="127.0.0.1", port=port, db=0, socket_connect_timeout=1)
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            client.ping()
            break
        except Exception:
            time.sleep(0.1)
    else:
        proc.kill()
        raise RuntimeError(f"Control Redis did not start on port {port}")

    yield (local_redis, control_url, proc)

    # Teardown
    try:
        client.shutdown(nosave=True)
    except Exception:
        pass
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_fail_closed_during_outage(cache_and_control_redis, monkeypatch):
    """When control-plane Redis is killed, fail_mode='closed' returns False."""
    cache_url, control_url, control_proc = cache_and_control_redis

    # Point the redis_client module at our ephemeral control Redis
    monkeypatch.setenv("REDIS_URL", cache_url)
    monkeypatch.setenv("REDIS_CONTROL_URL", control_url)
    monkeypatch.setenv("REDIS_ENABLED", "true")

    # Force module to re-read env and rebuild clients
    import mes_dashboard.core.redis_client as rc
    import importlib
    # Patch module-level globals to use our URLs
    rc.REDIS_URL = cache_url
    rc.REDIS_CONTROL_URL = control_url
    rc.REDIS_ENABLED = True
    rc._REDIS_CLIENT = None
    rc._REDIS_CONTROL_CLIENT = None

    import mes_dashboard.core.heavy_query_telemetry as telemetry
    from threading import Lock
    with telemetry._LOCK:
        initial_count = telemetry._LOCK_FAIL_MODE_TOTAL

    # Verify lock acquisition works before chaos
    acquired = rc.try_acquire_lock(f"chaos-test-{os.getpid()}", ttl_seconds=5, fail_mode="closed")
    assert acquired is True, "Lock should be acquirable before Redis outage"

    # Kill control Redis
    os.kill(control_proc.pid, signal.SIGKILL)
    control_proc.wait(timeout=3)

    # Force client reconnect attempt on next call
    rc._REDIS_CONTROL_CLIENT = None

    # With Redis dead, fail_mode='closed' should return False
    result = rc.try_acquire_lock(f"chaos-fail-{os.getpid()}", ttl_seconds=5, fail_mode="closed")
    assert result is False, (
        f"Expected False (fail-closed) when Redis is down, got {result!r}"
    )

    # Counter must have incremented
    with telemetry._LOCK:
        new_count = telemetry._LOCK_FAIL_MODE_TOTAL
    assert new_count > initial_count, "mes.lock.fail_mode_triggered counter should have incremented"


def test_fail_raise_during_outage(cache_and_control_redis, monkeypatch):
    """When control-plane Redis is killed, fail_mode='raise' raises LockUnavailableError."""
    cache_url, control_url, control_proc = cache_and_control_redis

    import mes_dashboard.core.redis_client as rc
    rc.REDIS_URL = cache_url
    rc.REDIS_CONTROL_URL = control_url
    rc.REDIS_ENABLED = True
    rc._REDIS_CLIENT = None
    rc._REDIS_CONTROL_CLIENT = None

    # Kill control Redis
    os.kill(control_proc.pid, signal.SIGKILL)
    control_proc.wait(timeout=3)
    rc._REDIS_CONTROL_CLIENT = None

    from mes_dashboard.core.exceptions import LockUnavailableError
    with pytest.raises(LockUnavailableError):
        rc.try_acquire_lock(f"chaos-raise-{os.getpid()}", ttl_seconds=5, fail_mode="raise")


def test_reconnect_after_redis_restart(cache_and_control_redis, tmp_path, monkeypatch):
    """After Redis restart on the same port, next lock acquisition should succeed."""
    cache_url, control_url, control_proc = cache_and_control_redis
    control_port = _redis_port(control_url)

    import mes_dashboard.core.redis_client as rc
    rc.REDIS_URL = cache_url
    rc.REDIS_CONTROL_URL = control_url
    rc.REDIS_ENABLED = True
    rc._REDIS_CLIENT = None
    rc._REDIS_CONTROL_CLIENT = None

    # Kill control Redis
    os.kill(control_proc.pid, signal.SIGKILL)
    control_proc.wait(timeout=3)
    time.sleep(0.5)

    # Restart Redis on the same port
    import subprocess
    log_file = tmp_path / "redis-control-restart.log"
    new_proc = subprocess.Popen(
        [
            "redis-server",
            "--port", str(control_port),
            "--maxmemory", "16mb",
            "--maxmemory-policy", "noeviction",
            "--save", "",
            "--loglevel", "warning",
        ],
        stdout=log_file.open("w"),
        stderr=subprocess.STDOUT,
    )

    # Wait for the new Redis to accept connections
    client = redis_lib.Redis(host="127.0.0.1", port=control_port, db=0, socket_connect_timeout=1)
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            client.ping()
            break
        except Exception:
            time.sleep(0.1)
    else:
        new_proc.kill()
        pytest.fail("Restarted Redis did not come up within 10s")

    # Force reconnect
    rc._REDIS_CONTROL_CLIENT = None

    # Should succeed without restarting any gunicorn process
    result = rc.try_acquire_lock(f"chaos-reconnect-{os.getpid()}", ttl_seconds=5, fail_mode="closed")
    assert result is True, f"Expected True after Redis reconnect, got {result!r}"

    # Cleanup
    try:
        client.shutdown(nosave=True)
    except Exception:
        pass
    try:
        new_proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        new_proc.kill()


def test_cache_eviction_does_not_affect_control(cache_and_control_redis, monkeypatch):
    """Cache-plane allkeys-lru eviction must not evict control-plane lock keys.

    The cache Redis has a 16mb cap with noeviction by default in our fixture,
    but we reconfigure it to allkeys-lru for this test to force eviction.
    The control-plane Redis keeps noeviction, so the lock key should survive.
    """
    cache_url, control_url, _control_proc = cache_and_control_redis
    cache_port = _redis_port(cache_url)
    control_port = _redis_port(control_url)

    # Reconfigure cache Redis to allkeys-lru with 1mb to force eviction
    cache_client = _make_redis(cache_url, socket_timeout=2.0)
    cache_client.config_set("maxmemory-policy", "allkeys-lru")
    cache_client.config_set("maxmemory", "1mb")

    control_client = _make_redis(control_url, socket_timeout=2.0)

    # Write a lock key on the control plane
    lock_key = f"mes_wip:lock:eviction-test-{os.getpid()}"
    control_client.set(lock_key, "held", ex=60)
    assert control_client.exists(lock_key) == 1, "Lock key should exist on control Redis"

    # Fill the cache Redis past maxmemory with many random keys
    pipe = cache_client.pipeline(transaction=False)
    for i in range(5000):
        pipe.set(f"cache:fill:{i}", "x" * 200)
    try:
        pipe.execute()
    except Exception:
        pass  # Eviction may interrupt some writes — that's expected

    # Lock key on control plane must still be present
    assert control_client.exists(lock_key) == 1, (
        "Control-plane lock key was evicted! "
        "The noeviction policy on the control Redis should prevent this."
    )
