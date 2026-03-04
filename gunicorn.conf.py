import os

bind = os.getenv("GUNICORN_BIND", "0.0.0.0:8080")
workers = int(os.getenv("GUNICORN_WORKERS", "2"))  # 2 workers for redundancy
threads = int(os.getenv("GUNICORN_THREADS", "4"))
worker_class = "gthread"

# Timeout settings - critical for dashboard stability.
# Keep this above slow-query timeout paths (e.g. read_sql_df_slow 300s) and DB pool timeout.
timeout = int(os.getenv("GUNICORN_TIMEOUT", "360"))
graceful_timeout = int(os.getenv("GUNICORN_GRACEFUL_TIMEOUT", "120"))
keepalive = 5         # Keep-alive connections timeout

# Worker lifecycle management - prevent state accumulation.
# Make these configurable so high-load test environments can raise the ceiling.
max_requests = int(os.getenv("GUNICORN_MAX_REQUESTS", "1200"))
max_requests_jitter = int(os.getenv("GUNICORN_MAX_REQUESTS_JITTER", "300"))


# ============================================================
# Worker Lifecycle Hooks
# ============================================================

def worker_exit(server, worker):
    """Clean up background threads and database connections when worker exits."""
    # Stop background sync threads first
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
