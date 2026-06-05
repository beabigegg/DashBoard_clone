# -*- coding: utf-8 -*-
"""
Multi-worker test harness: subprocess lifecycle, barrier synchronisation, log capture.

Usage
-----
    with MultiWorkerHarness(redis_url, worker_count=2, queue_name="test") as h:
        q = Queue("test", connection=h.redis)
        q.enqueue(some_job, ...)
        # h.worker_logs: dict[int, str] — captured stdout+stderr per worker index

WorkerBarrier
-------------
    Used inside RQ job functions (running inside worker subprocesses) to synchronise
    N workers at a named checkpoint, eliminating time.sleep-based race windows.

    barrier = WorkerBarrier(redis_url)
    barrier.wait("phase_1", n=2)   # blocks until 2 workers have called this
"""

from __future__ import annotations

import atexit
import os
import re
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

import redis as redis_lib
import requests

try:
    from rq import Worker as _RQWorker
    _RQ_AVAILABLE = True
except ImportError:
    _RQ_AVAILABLE = False

# ---------------------------------------------------------------------------
# Worker startup script — injected into each subprocess via python -c
# ---------------------------------------------------------------------------

_WORKER_SCRIPT = """
import sys, os, signal

project_root = os.environ.get("MWT_PROJECT_ROOT", "")
src_path = os.path.join(project_root, "src")
for p in [project_root, src_path]:
    if p and p not in sys.path:
        sys.path.insert(0, p)

from rq import SimpleWorker, Queue
from redis import Redis

def _shutdown(signum, frame):
    raise SystemExit(0)

signal.signal(signal.SIGTERM, _shutdown)

url   = os.environ["MWT_REDIS_URL"]
name  = os.environ.get("MWT_WORKER_NAME", "mwt-worker")
queue = os.environ.get("MWT_QUEUE_NAME", "test")

r = Redis.from_url(url)
q = Queue(queue, connection=r)
w = SimpleWorker([q], connection=r, name=name)
w.work(burst=False)
"""


# ---------------------------------------------------------------------------
# WorkerBarrier
# ---------------------------------------------------------------------------


class WorkerBarrier:
    """Redis-based N-way barrier — safe to call from inside RQ worker subprocesses.

    All N callers of ``wait(phase, n)`` block until every one has arrived,
    then all proceed together.  No ``time.sleep`` required.
    """

    def __init__(self, redis_url: str, ns: str = "mwb") -> None:
        self._url = redis_url
        self.ns = ns

    def _r(self) -> redis_lib.Redis:
        return redis_lib.Redis.from_url(self._url, decode_responses=True,
                                        socket_connect_timeout=5)

    def wait(self, phase: str, n: int, timeout: float = 30.0) -> None:
        """Block until *n* concurrent callers have all reached this barrier."""
        r = self._r()
        counter_key = f"{self.ns}:{phase}:count"
        release_key = f"{self.ns}:{phase}:release"

        count = r.incr(counter_key)
        r.expire(counter_key, 120)

        if count == n:
            # Last arrival — release all waiters atomically
            pipe = r.pipeline()
            for _ in range(n):
                pipe.rpush(release_key, "1")
            pipe.expire(release_key, 120)
            pipe.execute()
        elif count > n:
            # Extra arrival (retry path) — push one extra token
            r.rpush(release_key, "1")
            r.expire(release_key, 120)

        result = r.blpop(release_key, timeout=int(timeout) + 1)
        if result is None:
            raise TimeoutError(
                f"WorkerBarrier '{phase}' timed out after {timeout}s "
                f"(this worker's count={count}, waiting for n={n})"
            )


# ---------------------------------------------------------------------------
# Log capture
# ---------------------------------------------------------------------------


def _capture_lines(stream, lines: List[str]) -> None:
    """Read *stream* line by line into *lines* until EOF."""
    try:
        for line in stream:
            lines.append(line.rstrip())
    except Exception:
        pass


# ---------------------------------------------------------------------------
# MultiWorkerHarness
# ---------------------------------------------------------------------------


class MultiWorkerHarness:
    """Manage N RQ SimpleWorker subprocesses against an isolated Redis URL.

    Provides:
    - ``redis``: connected Redis client (same URL as workers)
    - ``barrier``: WorkerBarrier instance for test-side use
    - ``worker_logs``: dict[worker_index, str] — combined stdout+stderr per worker
    - ``_processes``: list of Popen objects (use .pid for SIGKILL targeting)

    Lifecycle:
    - ``start()``: FLUSHDB → spawn workers → wait for registration
    - ``stop()``: SIGTERM → wait 5 s → SIGKILL → FLUSHDB
    - Context manager: calls start/stop automatically
    """

    def __init__(
        self,
        redis_url: str,
        worker_count: int = 3,
        queue_name: str = "test",
        flush_on_start: bool = True,
        flush_on_stop: bool = True,
    ) -> None:
        self.redis_url = redis_url
        self.worker_count = worker_count
        self.queue_name = queue_name
        self.flush_on_start = flush_on_start
        self.flush_on_stop = flush_on_stop

        self._processes: List[subprocess.Popen] = []
        self._raw_logs: Dict[int, Dict[str, List[str]]] = {}
        self._log_threads: List[threading.Thread] = []
        self.redis: Optional[redis_lib.Redis] = None
        self.barrier: Optional[WorkerBarrier] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> "MultiWorkerHarness":

        self.redis = self._connect()
        if self.flush_on_start:
            self.redis.flushdb()
        self.barrier = WorkerBarrier(self.redis_url)

        project_root = str(Path(__file__).resolve().parent.parent.parent)
        src_path = str(Path(project_root) / "src")

        base_env = os.environ.copy()
        base_env.update({
            "MWT_REDIS_URL": self.redis_url,
            "MWT_QUEUE_NAME": self.queue_name,
            "MWT_PROJECT_ROOT": project_root,
        })

        import uuid as _uuid
        harness_id = _uuid.uuid4().hex[:6]
        for i in range(self.worker_count):
            env = {
                **base_env,
                # Unique name prevents RQ register_birth() ValueError when a previous
                # worker with the same name was killed without recording its death.
                "MWT_WORKER_NAME": f"mwt-{harness_id}-{i}",
                "MWT_WORKER_ID": str(i),
            }
            proc = subprocess.Popen(
                [sys.executable, "-c", _WORKER_SCRIPT],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                text=True,
            )
            logs: Dict[str, List[str]] = {"stdout": [], "stderr": []}
            self._raw_logs[i] = logs
            self._processes.append(proc)

            t_out = threading.Thread(
                target=_capture_lines, args=(proc.stdout, logs["stdout"]), daemon=True
            )
            t_err = threading.Thread(
                target=_capture_lines, args=(proc.stderr, logs["stderr"]), daemon=True
            )
            t_out.start()
            t_err.start()
            self._log_threads.extend([t_out, t_err])

        self._wait_for_workers()
        return self

    def stop(self) -> None:
        for proc in self._processes:
            try:
                if proc.poll() is None:
                    proc.send_signal(signal.SIGTERM)
            except Exception:
                pass

        deadline = time.monotonic() + 5.0
        for proc in self._processes:
            remaining = max(0.05, deadline - time.monotonic())
            try:
                proc.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                try:
                    proc.kill()
                except Exception:
                    pass

        if self.redis and self.flush_on_stop:
            try:
                self.redis.flushdb()
            except Exception:
                pass

    @property
    def worker_logs(self) -> Dict[int, str]:
        return {
            i: (
                f"=== worker-{i} STDOUT ===\n"
                + ("\n".join(logs["stdout"]) or "(no stdout)")
                + f"\n=== worker-{i} STDERR ===\n"
                + ("\n".join(logs["stderr"]) or "(no stderr)")
            )
            for i, logs in self._raw_logs.items()
        }

    def __enter__(self) -> "MultiWorkerHarness":
        self.start()
        return self

    def __exit__(self, *args: object) -> None:
        self.stop()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _connect(self) -> redis_lib.Redis:
        import pytest

        try:
            r = redis_lib.Redis.from_url(
                self.redis_url, decode_responses=True, socket_connect_timeout=3
            )
            r.ping()
            return r
        except Exception as exc:
            pytest.skip(f"Redis unavailable at {self.redis_url!r}: {exc}")

    def _wait_for_workers(self, timeout: float = 30.0) -> None:
        if not _RQ_AVAILABLE:
            time.sleep(2)
            return

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            # Check for premature death
            for i, proc in enumerate(self._processes):
                if proc.poll() is not None:
                    logs_text = "\n".join(
                        self._raw_logs[i]["stdout"] + self._raw_logs[i]["stderr"]
                    )
                    raise RuntimeError(
                        f"Worker {i} (pid={proc.pid}) exited prematurely "
                        f"(code={proc.returncode}).\n{logs_text}"
                    )
            try:
                workers = _RQWorker.all(connection=self.redis)
                if len(workers) >= self.worker_count:
                    return
            except Exception:
                pass
            time.sleep(0.1)

        raise RuntimeError(
            f"Workers failed to register within {timeout}s. "
            f"Logs: {self.worker_logs}"
        )


# ---------------------------------------------------------------------------
# GunicornHarness — single master + N forked workers (preload_app=True)
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]
GUNICORN_STARTUP_TIMEOUT = 120  # prewarm can take 30-60s

# Module-level registry for atexit cleanup — separate from conftest _SPAWNED_PROCS
# because conftest.py is not importable as a regular module.
_GHN_SPAWNED_PROCS: List[subprocess.Popen] = []


def _ghn_atexit_cleanup() -> None:
    """Kill any surviving GunicornHarness processes on interpreter exit."""
    for proc in list(_GHN_SPAWNED_PROCS):
        try:
            if proc.poll() is None:
                proc.kill()
        except Exception:
            pass


atexit.register(_ghn_atexit_cleanup)


def _find_free_port_ghn() -> int:
    """Find an unused TCP port on loopback by binding to port 0."""
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _pid_alive_ghn(pid: int) -> bool:
    """Return True if a process with *pid* is alive (signal 0 test)."""
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        # Process exists but we lack permission to signal it.
        return True


class GunicornHarness:
    """Spawn a single gunicorn master with N forked workers (preload_app=True).

    Unlike ``MultiWorkerHarness`` (which manages RQ workers), this harness
    tests the gunicorn fork lifecycle: preload_app prewarm runs once in the
    master; post_fork reinit runs in each worker.  The harness captures all
    stdout+stderr (gunicorn merges them via ``--access-logfile -``) into an
    in-memory log and exposes helpers for log inspection and per-worker
    metrics collection via ``/internal/metrics``.

    Environment variables injected into the subprocess:
    - ``REGISTER_INTERNAL_METRICS=true``  — enables Layer 1 blueprint gate
    - ``INTERNAL_METRICS_ENABLED=1``      — enables Layer 2 env gate
    - ``GUNICORN_BIND``                   — determined at start() time
    - ``GUNICORN_WORKERS``                — set to ``self.workers``
    - ``FLASK_TESTING`` / ``PYTEST_CURRENT_TEST`` stripped to avoid
      TestingConfig being selected (which sets DB_POOL_SIZE=1, etc.)

    Usage::

        with GunicornHarness() as h:
            h.wait_for_log("resource_history DuckDB prewarm complete")
            assert h.log_count("prewarm complete") == 1
            metrics = h.collect_per_worker_metrics()
    """

    def __init__(self, port: int = 0, workers: int = 2) -> None:
        self.workers = workers
        self._port = port       # 0 = auto-find a free port
        self._proc: Optional[subprocess.Popen] = None
        self._log_lines: List[str] = []
        self._log_lock = threading.Lock()
        self._ready_event = threading.Event()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def port(self) -> int:
        return self._port

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self._port}"

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> "GunicornHarness":
        if self._port == 0:
            self._port = _find_free_port_ghn()

        env = os.environ.copy()
        # Strip pytest/testing markers so gunicorn uses production config
        # (real Oracle pools, real Redis).
        # Strip all pytest/testing markers so gunicorn uses production config
        # (real Oracle pools, real Redis, real prewarm — not testing short-circuit).
        env.pop("FLASK_TESTING", None)
        env.pop("PYTEST_CURRENT_TEST", None)
        env.pop("FLASK_ENV", None)          # removes testing→TestingConfig guard
        env["REDIS_ENABLED"] = "true"       # pytest conftest sets false by default
        env.setdefault("REDIS_URL", "redis://localhost:6379/0")
        env.setdefault("REDIS_CONTROL_URL", env["REDIS_URL"])
        # Enable the internal-metrics blueprint via env (Layer 1 + 2 gates).
        env["REGISTER_INTERNAL_METRICS"] = "true"
        env["INTERNAL_METRICS_ENABLED"] = "1"
        # Gunicorn process model overrides.
        env["GUNICORN_BIND"] = f"0.0.0.0:{self._port}"
        env["GUNICORN_WORKERS"] = str(self.workers)
        env["GUNICORN_THREADS"] = "2"
        env["GUNICORN_TIMEOUT"] = "360"
        # Add src/ to PYTHONPATH so gunicorn can import mes_dashboard directly.
        _src_path = str(PROJECT_ROOT / "src")
        existing_pp = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = f"{_src_path}:{existing_pp}" if existing_pp else _src_path

        import shutil
        gunicorn_bin = shutil.which("gunicorn") or str(
            Path(sys.executable).parent / "gunicorn"
        )
        self._proc = subprocess.Popen(
            [
                gunicorn_bin,
                "-c", "gunicorn.conf.py",
                "mes_dashboard:create_app()",
            ],
            cwd=str(PROJECT_ROOT),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  # merge stderr into stdout for unified log
            text=True,
        )
        _GHN_SPAWNED_PROCS.append(self._proc)

        # Start background thread to drain the combined stdout stream.
        reader = threading.Thread(target=self._read_logs, daemon=True)
        reader.start()

        # Block until gunicorn emits "Listening at:" (all workers booted).
        if not self._ready_event.wait(timeout=GUNICORN_STARTUP_TIMEOUT):
            self.stop()
            with self._log_lock:
                last_lines = "".join(self._log_lines[-20:])
            raise TimeoutError(
                f"Gunicorn did not start within {GUNICORN_STARTUP_TIMEOUT}s.\n"
                f"Last 20 log lines:\n{last_lines}"
            )
        return self

    def _read_logs(self) -> None:
        """Drain gunicorn's combined stdout/stderr into self._log_lines."""
        assert self._proc is not None
        try:
            for line in self._proc.stdout:  # type: ignore[union-attr]
                with self._log_lock:
                    self._log_lines.append(line)
                # Gunicorn emits "Listening at: http://0.0.0.0:<port> (<pid>)"
                # once the arbiter is ready and all workers have booted.
                if "Listening at:" in line and not self._ready_event.is_set():
                    self._ready_event.set()
        except Exception:
            pass
        finally:
            # EOF — unblock any pending wait_for_log calls.
            self._ready_event.set()

    def stop(self) -> None:
        if self._proc is not None and self._proc.poll() is None:
            self._proc.send_signal(signal.SIGTERM)
            try:
                self._proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        try:
            _GHN_SPAWNED_PROCS.remove(self._proc)
        except (ValueError, AttributeError):
            pass

    def __enter__(self) -> "GunicornHarness":
        self.start()
        return self

    def __exit__(self, *_: object) -> None:
        self.stop()

    # ------------------------------------------------------------------
    # Log helpers
    # ------------------------------------------------------------------

    def log_count(self, pattern: str) -> int:
        """Return the number of log lines that contain *pattern*."""
        with self._log_lock:
            return sum(1 for line in self._log_lines if pattern in line)

    def log_contains(self, pattern: str) -> bool:
        """Return True if any log line contains *pattern*."""
        with self._log_lock:
            return any(pattern in line for line in self._log_lines)

    @property
    def full_log(self) -> str:
        """Combined log as a single string (thread-safe snapshot)."""
        with self._log_lock:
            return "".join(self._log_lines)

    def wait_for_log(self, pattern: str, timeout: float = 120.0) -> bool:
        """Block until *pattern* appears in captured logs or *timeout* elapses.

        Returns True if found, False on timeout.
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.log_contains(pattern):
                return True
            time.sleep(0.5)
        return False

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    def get(self, path: str, **kwargs: object) -> requests.Response:
        """Issue a GET request to the running gunicorn instance."""
        return requests.get(f"{self.base_url}{path}", timeout=30, **kwargs)

    def collect_per_worker_metrics(
        self,
        target_workers: Optional[int] = None,
        timeout: float = 30.0,
    ) -> List[Dict]:
        """Hit ``/internal/metrics`` repeatedly until data from all workers is seen.

        Gunicorn round-robins requests across workers, so multiple calls are
        needed to sample each worker.  Returns a list of ``data`` dicts, one
        per distinct PID.

        The response envelope shape is ``{"status": "success", "data": {...}}``
        (from ``success_response()``); this method indexes into ``data``.
        """
        n = target_workers if target_workers is not None else self.workers
        seen: Dict[int, Dict] = {}
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline and len(seen) < n:
            try:
                resp = self.get("/internal/metrics")
                if resp.status_code == 200:
                    data = resp.json().get("data", {})
                    pid = data.get("worker_rss", {}).get("pid")
                    if pid is not None and pid not in seen:
                        seen[pid] = data
            except Exception:
                pass
            time.sleep(0.15)
        return list(seen.values())

    # ------------------------------------------------------------------
    # Worker PID control (for AC-9 crash + respawn tests)
    # ------------------------------------------------------------------

    def worker_pids(self) -> List[int]:
        """Parse all worker PIDs seen in gunicorn's boot log (may include dead ones)."""
        pids: List[int] = []
        with self._log_lock:
            for line in self._log_lines:
                m = re.search(r"Booting worker with pid: (\d+)", line)
                if m:
                    pids.append(int(m.group(1)))
        # Preserve insertion order, deduplicate.
        return list(dict.fromkeys(pids))

    def worker_pids_alive(self) -> List[int]:
        """Return the subset of known worker PIDs that are still alive."""
        return [p for p in self.worker_pids() if _pid_alive_ghn(p)]

    def kill_worker(self, pid: int) -> None:
        """Send SIGKILL to the gunicorn worker with *pid*."""
        os.kill(pid, signal.SIGKILL)

    def wait_for_respawn(
        self,
        old_pids: List[int],
        timeout: float = 30.0,
    ) -> List[int]:
        """Block until at least one PID not in *old_pids* appears in the boot log
        and is alive.

        Returns the list of newly-seen PIDs.  Raises ``TimeoutError`` if none
        appear within *timeout* seconds.
        """
        old_set = set(old_pids)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            new = set(self.worker_pids_alive()) - old_set
            if new:
                return list(new)
            time.sleep(0.5)
        raise TimeoutError(
            f"No new worker appeared within {timeout}s "
            f"(old pids={old_pids}, current alive={self.worker_pids_alive()})"
        )
