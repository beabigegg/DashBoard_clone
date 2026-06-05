import logging
import os

_gunicorn_logger = logging.getLogger("gunicorn.startup")

bind = os.getenv("GUNICORN_BIND", "0.0.0.0:8080")
workers = int(os.getenv("GUNICORN_WORKERS", "2"))  # DEV: 2, PRD: 4
threads = int(os.getenv("GUNICORN_THREADS", "4"))
worker_class = "gthread"

# Timeout settings - critical for dashboard stability.
# Keep this above slow-query timeout paths (e.g. read_sql_df_slow 300s) and DB pool timeout.
timeout = int(os.getenv("GUNICORN_TIMEOUT", "360"))
graceful_timeout = int(os.getenv("GUNICORN_GRACEFUL_TIMEOUT", "120"))
keepalive = 5         # Keep-alive connections timeout

# Worker lifecycle management - prevent state accumulation.
# Make these configurable so high-load test environments can raise the ceiling.
max_requests = int(os.getenv("GUNICORN_MAX_REQUESTS", "5000"))
max_requests_jitter = int(os.getenv("GUNICORN_MAX_REQUESTS_JITTER", "1000"))

# preload_app=True: gunicorn runs create_app() once in the master process before
# forking workers.  Single-run prewarm tasks (DuckDB, downtime_analysis,
# material_consumption, resource_cache init) execute once in the master and their
# results (Redis cache, DuckDB parquet files) are shared across all workers.
# The post_fork hook below reinitialises every fork-unsafe resource (Oracle pools,
# Redis pools, SQLite handles) and restarts per-worker background threads.
# Design reference: design.md D2; implementation-plan.md IP-3.
preload_app = True


# ============================================================
# Worker Lifecycle Hooks
# ============================================================


def post_fork(server, worker):
    """Reinitialise fork-unsafe resources in each worker after preload_app fork.

    preload_app=True causes create_app() to run in the master process before
    fork().  Every file descriptor and connection pool opened in the master is
    inherited (shared, raw-copied) by all workers.  Using them concurrently
    across processes corrupts the protocol state.

    This hook is called by gunicorn inside each worker process immediately
    after the fork, before the worker accepts its first request.  It must:
      1. Dispose inherited Oracle SQLAlchemy connection pools.
      2. Drop inherited Redis connection pools.
      3. Close inherited SQLite file handles (per-store).
      4. Start all per-worker background threads (_start_per_worker_services).

    Each step is wrapped in its own try/except so a single failure never
    cascades to crash the worker (an uncaught exception in post_fork is fatal
    to the worker — gunicorn respawns it, which re-crashes under a broken
    environment; wrapping prevents the cascade).

    Design reference: design.md D2; implementation-plan.md IP-3.
    """
    # 1. Oracle connection pools — dispose() drops inherited FDs; workers
    #    rebuild their own pool lazily on first request.
    try:
        from mes_dashboard.core.database import dispose_engine
        dispose_engine()
    except Exception as e:
        server.log.warning("post_fork: dispose_engine failed: %s", e)

    # 2. Redis connection pools — close() drops inherited _REDIS_CLIENT /
    #    _REDIS_CONTROL_CLIENT; workers rebuild lazily on first cache access.
    try:
        from mes_dashboard.core.redis_client import close_redis
        close_redis()
    except Exception as e:
        server.log.warning("post_fork: close_redis failed: %s", e)

    # 3. SQLite handles — reopen per-worker so each worker has its own fd.
    #    Inherited sqlite3 connections are not fork-safe.
    try:
        from mes_dashboard.app import _reinit_sqlite_handles
        _reinit_sqlite_handles()
    except Exception as e:
        server.log.warning("post_fork: _reinit_sqlite_handles failed: %s", e)

    # 4. Background threads — threads do not survive fork(); each worker must
    #    start its own set of daemon threads.
    try:
        from mes_dashboard.app import _start_per_worker_services
        _start_per_worker_services(worker)
    except Exception as e:
        server.log.warning("post_fork: _start_per_worker_services failed: %s", e)


def on_starting(server):
    """Check system memory sufficiency before starting workers."""
    try:
        import psutil
        vm = psutil.virtual_memory()
        available_mb = vm.available / (1024 * 1024)
        rq_workers = int(os.getenv("RQ_WORKER_COUNT_ESTIMATE", "3"))  # trace + reject + msd
        required_mb = workers * 400 + rq_workers * 200
        if available_mb >= required_mb:
            server.log.info(
                "Startup memory check: %.0f MB available, %.0f MB required — OK",
                available_mb,
                required_mb,
            )
        else:
            shortfall = required_mb - available_mb
            server.log.warning(
                "Startup memory check: %.0f MB available, %.0f MB required — "
                "shortfall %.0f MB. Consider reducing GUNICORN_WORKERS from %d.",
                available_mb,
                required_mb,
                shortfall,
                workers,
            )
    except Exception as exc:
        server.log.warning("Startup memory check failed (skipping): %s", exc)


def worker_exit(server, worker):
    """Clean up background threads and database connections when worker exits."""
    # Stop RSS memory guard first
    try:
        from mes_dashboard.core.worker_memory_guard import stop_worker_memory_guard
        stop_worker_memory_guard()
    except Exception as e:
        server.log.warning(f"Error stopping worker memory guard: {e}")

    # Stop background sync threads
    try:
        from mes_dashboard.services.realtime_equipment_cache import (
            stop_equipment_status_sync_worker
        )
        stop_equipment_status_sync_worker()
    except Exception as e:
        server.log.warning(f"Error stopping equipment sync worker: {e}")

    try:
        from mes_dashboard.core.cache_updater import stop_cache_updater
        stop_cache_updater()
    except Exception as e:
        server.log.warning(f"Error stopping cache updater: {e}")

    try:
        from mes_dashboard.core.redis_client import close_redis
        close_redis()
    except Exception as e:
        server.log.warning(f"Error closing redis client: {e}")

    # Then dispose database connections
    try:
        from mes_dashboard.core.database import dispose_engine
        dispose_engine()
    except Exception as e:
        server.log.warning(f"Error disposing database engine: {e}")
