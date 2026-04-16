# -*- coding: utf-8 -*-
"""Smoke test: verify that the integration fixtures boot correctly."""

import urllib.request

import pytest

pytestmark = pytest.mark.integration_real


@pytest.mark.parametrize("gunicorn_workers", [1], indirect=True)
def test_workers_boot(gunicorn_workers):
    """1 gunicorn worker should boot and return 200 on /health."""
    assert len(gunicorn_workers) == 1
    pid, port = gunicorn_workers[0]
    assert pid > 0

    url = f"http://127.0.0.1:{port}/health"
    with urllib.request.urlopen(url, timeout=5) as resp:
        assert resp.status == 200


def test_local_redis_fixture(local_redis):
    """local_redis fixture should return a working Redis URL."""
    import redis as redis_lib

    assert local_redis.startswith("redis://")
    parts = local_redis.split(":")
    port = int(parts[-1].split("/")[0])
    client = redis_lib.Redis(host="127.0.0.1", port=port, db=0)
    assert client.ping() is True


def test_temp_spool_dir_fixture(temp_spool_dir):
    """temp_spool_dir fixture should create a writable directory and set env var."""
    import os

    assert temp_spool_dir.exists()
    assert os.environ.get("QUERY_SPOOL_DIR") == str(temp_spool_dir)

    # Should be writable
    probe = temp_spool_dir / "probe_smoke.txt"
    probe.write_text("ok")
    assert probe.read_text() == "ok"
