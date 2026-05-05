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

import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

import redis as redis_lib

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
