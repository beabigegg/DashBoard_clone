# -*- coding: utf-8 -*-
"""
Pytest configuration and fixtures for the real-environment integration test tier.

Tests in this directory are marked with ``@pytest.mark.integration_real`` and
are **skipped by default**.  Pass ``--run-integration-real`` on the command line
to opt in:

    conda run -n mes-dashboard pytest tests/integration/ --run-integration-real -v

Prerequisites:
- ``redis-server`` binary on $PATH
- ``gunicorn`` available in the conda env  (already in environment.yml)
- Playwright browsers in ~/.cache/ms-playwright  (DO NOT run playwright install)
"""

from __future__ import annotations

import atexit
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Generator, List, Tuple

import pytest
import redis as redis_lib

# Registry of subprocesses spawned by this test tier; used by the atexit handler
# to sweep leaked processes if a test crashes between Popen and teardown.
_SPAWNED_PROCS: List[subprocess.Popen] = []


def _atexit_sweep() -> None:
    """Kill any test-spawned subprocess that is still running at process exit."""
    for proc in _SPAWNED_PROCS:
        try:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=3)
        except Exception:
            pass


atexit.register(_atexit_sweep)


# ---------------------------------------------------------------------------
# CLI option and collection hook
# ---------------------------------------------------------------------------


def pytest_collection_modifyitems(
    config: pytest.Config, items: List[pytest.Item]
) -> None:
    if config.getoption("--run-integration-real", default=False):
        return  # flag present — run everything

    skip_marker = pytest.mark.skip(
        reason="real-subprocess integration tests require --run-integration-real"
    )
    for item in items:
        if item.get_closest_marker("integration_real"):
            item.add_marker(skip_marker)


# ---------------------------------------------------------------------------
# Port helper
# ---------------------------------------------------------------------------


def _find_free_port(retries: int = 3) -> int:
    """Return a free TCP port by binding to port 0 then releasing it.

    There is a small race window between release and actual use; we retry
    up to *retries* times if the port disappears before the caller binds.
    """
    for _ in range(retries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            port = s.getsockname()[1]
        # Verify the port looks free (non-zero)
        if port:
            return port
    raise RuntimeError("Could not find a free TCP port after retries")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def temp_spool_dir(tmp_path: Path) -> Generator[Path, None, None]:
    """Create a temporary spool directory and set QUERY_SPOOL_DIR env var.

    On teardown the env var is restored and the directory is left for
    tmp_path cleanup to handle.
    """
    spool = tmp_path / "query_spool"
    spool.mkdir(parents=True, exist_ok=True)

    original = os.environ.get("QUERY_SPOOL_DIR")
    os.environ["QUERY_SPOOL_DIR"] = str(spool)
    try:
        yield spool
    finally:
        if original is None:
            os.environ.pop("QUERY_SPOOL_DIR", None)
        else:
            os.environ["QUERY_SPOOL_DIR"] = original


@pytest.fixture()
def local_redis(tmp_path: Path) -> Generator[str, None, None]:
    """Spawn a dedicated Redis instance for the test.

    Yields the Redis URL string (``redis://127.0.0.1:<port>/0``).
    On teardown, issues SHUTDOWN NOSAVE and waits for the process to exit.
    """
    port = _find_free_port()
    log_file = tmp_path / "redis.log"

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
    _SPAWNED_PROCS.append(proc)

    url = f"redis://127.0.0.1:{port}/0"

    # Wait for Redis to accept connections (up to 10 s)
    deadline = time.monotonic() + 10
    client = redis_lib.Redis(host="127.0.0.1", port=port, db=0, socket_connect_timeout=1)
    while time.monotonic() < deadline:
        try:
            client.ping()
            break
        except Exception:
            time.sleep(0.1)
    else:
        proc.kill()
        raise RuntimeError(f"Redis did not start on port {port} within 10s")

    try:
        yield url
    finally:
        # Graceful shutdown
        try:
            client.shutdown(nosave=True)
        except Exception:
            pass
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        try:
            _SPAWNED_PROCS.remove(proc)
        except ValueError:
            pass


@pytest.fixture()
def gunicorn_workers(
    tmp_path: Path,
    local_redis: str,
    temp_spool_dir: Path,
    request: pytest.FixtureRequest,
) -> Generator[List[Tuple[int, int]], None, None]:
    """Spawn N real gunicorn worker processes and yield [(pid, port), ...].

    The number of workers is controlled via indirect parametrisation or
    defaults to 2.  Each worker gets:
    - its own TCP port
    - the shared ``temp_spool_dir``
    - the ``local_redis`` URL for both REDIS_URL and REDIS_CONTROL_URL

    Teardown: SIGTERM each worker, wait 5 s, SIGKILL stragglers.
    Stdout/stderr are captured to ``tmp_path/gunicorn-{i}.log``.
    """
    n_workers: int = getattr(request, "param", 2)
    _project_root = Path(__file__).resolve().parent.parent.parent
    _src_path = str(_project_root / "src")

    # Find the gunicorn binary in the same Python environment we're running in.
    # Using `sys.executable -m gunicorn` is unreliable; find the binary instead.
    import shutil
    _gunicorn_bin = shutil.which("gunicorn") or str(Path(sys.executable).parent / "gunicorn")

    procs: List[subprocess.Popen] = []
    workers_info: List[Tuple[int, int]] = []

    # Inherit current env, then override per-worker settings.
    # Clear PYTEST_CURRENT_TEST so create_app() treats this as a real boot,
    # but keep FLASK_ENV=testing to suppress Oracle/cache connections.
    base_env = {k: v for k, v in os.environ.items() if k != "PYTEST_CURRENT_TEST"}
    # Ensure src/ is in PYTHONPATH so gunicorn can import mes_dashboard
    existing_pp = base_env.get("PYTHONPATH", "")
    base_env["PYTHONPATH"] = f"{_src_path}:{existing_pp}" if existing_pp else _src_path

    for i in range(n_workers):
        port = _find_free_port()
        log_file = tmp_path / f"gunicorn-{i}.log"
        env = {
            **base_env,
            "GUNICORN_BIND": f"127.0.0.1:{port}",
            "GUNICORN_WORKERS": "1",
            "GUNICORN_THREADS": "2",
            "GUNICORN_TIMEOUT": "60",
            "REDIS_URL": local_redis,
            "REDIS_ENABLED": "true",
            "REDIS_CONTROL_URL": local_redis,
            "QUERY_SPOOL_DIR": str(temp_spool_dir),
            "FLASK_ENV": "testing",
        }
        proc = subprocess.Popen(
            [
                _gunicorn_bin,
                "-c", str(_project_root / "gunicorn.conf.py"),
                "mes_dashboard:create_app()",
            ],
            cwd=str(_project_root),
            env=env,
            stdout=log_file.open("w"),
            stderr=subprocess.STDOUT,
        )
        _SPAWNED_PROCS.append(proc)
        procs.append(proc)
        workers_info.append((proc.pid, port))

    # Wait for each worker's /health to return 200
    for pid, port in workers_info:
        _wait_for_health(f"http://127.0.0.1:{port}/health", timeout=15)

    try:
        yield workers_info
    finally:
        # Graceful SIGTERM
        for proc in procs:
            try:
                if proc.poll() is None:
                    proc.send_signal(signal.SIGTERM)
            except ProcessLookupError:
                pass

        deadline = time.monotonic() + 5
        for proc in procs:
            remaining = max(0.1, deadline - time.monotonic())
            try:
                proc.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                proc.kill()

        for proc in procs:
            try:
                _SPAWNED_PROCS.remove(proc)
            except ValueError:
                pass


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _wait_for_health(url: str, timeout: float = 15) -> None:
    """Poll *url* until it returns HTTP 200 or *timeout* seconds elapse."""
    import urllib.request
    import urllib.error

    deadline = time.monotonic() + timeout
    last_exc: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                if resp.status == 200:
                    return
        except Exception as exc:
            last_exc = exc
        time.sleep(0.3)

    raise RuntimeError(
        f"Health check {url!r} did not return 200 within {timeout}s. "
        f"Last error: {last_exc}"
    )


# ---------------------------------------------------------------------------
# Oracle XE + toxiproxy fixtures (Phase 1 — real Oracle fault injection)
# ---------------------------------------------------------------------------
# Fixtures defined in _oracle_xe_fixture.py (gitignored / in-progress); imported
# here so pytest auto-discovers them when the infra support module is present.
# The import is soft so unit/integration collection keeps working on machines
# that don't have the Oracle-XE fault-injection support files yet.

try:
    from ._oracle_xe_fixture import oracle_xe, oracle_xe_fault  # noqa: F401, E402
except ImportError:
    pass


# ---------------------------------------------------------------------------
# Oracle XE app bridge fixture (Phase 2B — HTTP envelope + circuit breaker)
# ---------------------------------------------------------------------------


@pytest.fixture()
def oracle_xe_app(oracle_xe: str, monkeypatch: pytest.MonkeyPatch):
    """Function-scoped Flask test_client routed to the Oracle XE container.

    Patches CONNECTION_STRING in core/database.py before creating a fresh
    Flask app, so any route that calls get_engine() will use the Oracle XE
    container rather than the production DB.  Engine singletons (_ENGINE,
    _HEALTH_ENGINE, _SLOW_ENGINE) are reset to None on entry; monkeypatch
    teardown restores them automatically.

    Yields a Flask test_client for Phase 2B HTTP envelope assertions.

    Prerequisite: oracle_xe fixture must succeed (container ready and
    toxiproxy proxy entry created).
    """
    from urllib.parse import quote_plus

    import mes_dashboard.core.database as _db
    from mes_dashboard.app import create_app

    from ._infra_topology import ORACLE_TEST_PASSWORD, ORACLE_TEST_USER

    # oracle_xe yields "127.0.0.1:1521/XEPDB1"
    host_port, service_name = oracle_xe.rsplit("/", 1)
    host, port = host_port.rsplit(":", 1)

    xe_url = (
        f"oracle+oracledb://{ORACLE_TEST_USER}:{quote_plus(ORACLE_TEST_PASSWORD)}"
        f"@{host}:{port}/?service_name={service_name}"
    )

    monkeypatch.setattr(_db, "CONNECTION_STRING", xe_url)
    monkeypatch.setattr(_db, "_ENGINE", None)
    monkeypatch.setattr(_db, "_HEALTH_ENGINE", None)
    monkeypatch.setattr(_db, "_SLOW_ENGINE", None)

    app = create_app("testing")
    app.config["TESTING"] = True

    with app.test_client() as client:
        yield client
