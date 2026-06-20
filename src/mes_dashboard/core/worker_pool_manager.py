# -*- coding: utf-8 -*-
"""Dynamic RQ worker pool manager.

Replaces the static ``numprocs`` approach in supervisord with demand-driven
worker spawning.  Workers use ``--max-idle-time`` so they self-terminate after
an idle window; the manager re-spawns them when queue depth rises above zero.

Environment variables (all optional):
  POOL_MIN_PER_QUEUE    Minimum always-alive workers per queue  (default 0)
  POOL_MAX_PER_QUEUE    Default max workers per queue           (default 2)
  POOL_GLOBAL_MAX       Total worker cap across all queues      (default 8)
  POOL_IDLE_TIME        Seconds a worker stays alive while idle (default 90)
  POOL_POLL_INTERVAL    Manager check frequency in seconds      (default 5)
  REDIS_URL             Redis connection URL

Per-queue overrides use the queue's env key, e.g.:
  POOL_MAX_TRACE_WORKER_QUEUE=3
  POOL_MIN_WARMUP_QUEUE_NAME=1
  POOL_MAX_WARMUP_QUEUE_NAME=1
"""

from __future__ import annotations

import logging
import os
import shutil
import signal
import subprocess
import sys
import time
from typing import Dict, List

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] pool-manager: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stderr,
)
logger = logging.getLogger("mes_dashboard.worker_pool_manager")


# ---------------------------------------------------------------------------
# Queue definitions — ordered high→low priority so that when the global cap
# is nearly full, slots go to the more time-sensitive queues first.
# ---------------------------------------------------------------------------
_QUEUE_DEFS: List[tuple] = [
    # (env_key,                              default_queue_name)
    ("TRACE_WORKER_QUEUE",                "trace-events"),
    ("REJECT_WORKER_QUEUE",               "reject-query"),
    ("HOLD_WORKER_QUEUE",                 "hold-history-query"),
    ("RESOURCE_WORKER_QUEUE",             "resource-history-query"),
    ("PRODUCTION_HISTORY_WORKER_QUEUE",   "production-history-query"),
    ("MSD_WORKER_QUEUE",                  "msd-analysis"),
    ("YIELD_ALERT_WORKER_QUEUE",          "yield-alert-query"),
    ("WIP_WORKER_QUEUE",                  "wip-detail-query"),
    ("MATERIAL_CONSUMPTION_WORKER_QUEUE", "material-consumption"),
    ("DOWNTIME_WORKER_QUEUE",             "downtime-query"),
    ("EAP_ALARM_WORKER_QUEUE",            "eap-alarm-query"),
    ("QUERY_TOOL_WORKER_QUEUE",           "query-tool"),
    ("WARMUP_QUEUE_NAME",                 "warmup"),   # lowest priority
]

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
_DEFAULT_MIN   = int(os.getenv("POOL_MIN_PER_QUEUE",  "0"))
_DEFAULT_MAX   = int(os.getenv("POOL_MAX_PER_QUEUE",  "2"))
_GLOBAL_MAX    = int(os.getenv("POOL_GLOBAL_MAX",     "8"))
_IDLE_TIME     = int(os.getenv("POOL_IDLE_TIME",      "90"))
_POLL_INTERVAL = int(os.getenv("POOL_POLL_INTERVAL",  "5"))
_REDIS_URL     = os.getenv("REDIS_URL", "redis://localhost:6379/0")


def _per_queue_int(prefix: str, env_key: str, default: int) -> int:
    raw = os.getenv(f"{prefix}_{env_key.upper()}")
    if raw is not None:
        try:
            return max(0, int(raw))
        except ValueError:
            pass
    return default


def _build_queue_configs() -> List[dict]:
    return [
        {
            "env_key": env_key,
            "name": os.getenv(env_key, default),
            "min": _per_queue_int("POOL_MIN", env_key, _DEFAULT_MIN),
            "max": _per_queue_int("POOL_MAX", env_key, _DEFAULT_MAX),
        }
        for env_key, default in _QUEUE_DEFS
    ]


# ---------------------------------------------------------------------------
# Redis — thin wrapper; avoids pulling full RQ at module-level import
# ---------------------------------------------------------------------------

def _make_redis():
    import redis as _redis
    return _redis.from_url(
        _REDIS_URL,
        socket_connect_timeout=3,
        socket_timeout=3,
        decode_responses=True,
    )


def _queue_depth(conn, queue_name: str) -> int:
    """Pending job count for one queue (RQ stores pending jobs in a Redis list)."""
    try:
        return int(conn.llen(f"rq:queue:{queue_name}") or 0)
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# Process tracking
# ---------------------------------------------------------------------------

_spawned: Dict[str, List[subprocess.Popen]] = {}   # queue_name → live procs


def _reap(queue_name: str) -> None:
    """Remove terminated processes from the tracking list."""
    alive = []
    for p in _spawned.get(queue_name, []):
        rc = p.poll()
        if rc is None:
            alive.append(p)
        else:
            logger.debug(
                "Worker exited  pid=%d  queue=%s  rc=%d",
                p.pid, queue_name, rc,
            )
    _spawned[queue_name] = alive


def _local_count(queue_name: str) -> int:
    _reap(queue_name)
    return len(_spawned.get(queue_name, []))


def _total_count() -> int:
    return sum(len(ps) for ps in _spawned.values())


# ---------------------------------------------------------------------------
# Worker spawn
# ---------------------------------------------------------------------------

_RQ_CMD: List[str] = []   # resolved once at startup


def _resolve_rq_cmd() -> List[str]:
    rq_path = shutil.which("rq")
    if rq_path:
        return [rq_path]
    return [sys.executable, "-m", "rq"]


def _spawn(queue_name: str) -> None:
    cmd = _RQ_CMD + [
        "worker", queue_name,
        "--url", _REDIS_URL,
        "--max-idle-time", str(_IDLE_TIME),
    ]
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=sys.stdout,
            stderr=sys.stderr,
        )
        _spawned.setdefault(queue_name, []).append(proc)
        logger.info("Spawned  pid=%-6d  queue=%s", proc.pid, queue_name)
    except Exception as exc:
        logger.error("Failed to spawn worker for %s: %s", queue_name, exc)


# ---------------------------------------------------------------------------
# Graceful shutdown
# ---------------------------------------------------------------------------

_shutdown = False


def _on_signal(signum, _frame) -> None:
    global _shutdown
    logger.info("Signal %d received — stopping pool manager", signum)
    _shutdown = True
    for procs in _spawned.values():
        for p in procs:
            if p.poll() is None:
                try:
                    p.terminate()
                except OSError:
                    pass


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def run() -> None:
    global _RQ_CMD

    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)

    _RQ_CMD = _resolve_rq_cmd()
    queues = _build_queue_configs()

    logger.info(
        "Started  global_max=%d  idle=%ds  poll=%ds  rq=%s",
        _GLOBAL_MAX, _IDLE_TIME, _POLL_INTERVAL, " ".join(_RQ_CMD),
    )
    logger.info(
        "Queues: %s",
        " | ".join(
            f"{q['name']}(min={q['min']} max={q['max']})"
            for q in queues
        ),
    )

    conn = None
    last_redis_attempt: float = 0.0

    while not _shutdown:
        now = time.monotonic()

        # Reconnect with 10-second back-off on failure
        if conn is None:
            if now - last_redis_attempt < 10.0:
                time.sleep(_POLL_INTERVAL)
                continue
            last_redis_attempt = now
            try:
                conn = _make_redis()
                conn.ping()
                logger.info("Redis connected: %s", _REDIS_URL)
            except Exception as exc:
                logger.warning("Redis unavailable: %s — retrying in 10s", exc)
                conn = None
                time.sleep(_POLL_INTERVAL)
                continue

        try:
            for q in queues:
                if _shutdown:
                    break

                qname = q["name"]
                local = _local_count(qname)
                global_free = _GLOBAL_MAX - _total_count()

                # --- maintain minimum (keep-warm queues) ---
                if local < q["min"] and global_free > 0:
                    _spawn(qname)
                    continue

                # --- demand-driven spawning ---
                depth = _queue_depth(conn, qname)
                if depth == 0:
                    # idle workers will self-terminate via --max-idle-time
                    continue

                want = min(depth, q["max"]) - local   # workers still needed
                # spawn ≤2 per queue per cycle to avoid thundering-herd
                can = min(max(0, want), global_free, 2)
                for _ in range(can):
                    _spawn(qname)

        except Exception as exc:
            logger.warning("Poll error: %s — will reconnect", exc)
            conn = None

        time.sleep(_POLL_INTERVAL)

    # -----------------------------------------------------------------------
    # Drain: wait for in-flight jobs to complete (up to worker job timeout)
    # -----------------------------------------------------------------------
    logger.info("Draining workers (up to 60 s)...")
    for qname, procs in _spawned.items():
        for p in procs:
            try:
                p.wait(timeout=60)
            except subprocess.TimeoutExpired:
                logger.warning("Force-killing stuck worker pid=%d queue=%s", p.pid, qname)
                p.kill()
    logger.info("pool-manager stopped")


if __name__ == "__main__":
    run()
