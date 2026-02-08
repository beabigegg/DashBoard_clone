import os

bind = os.getenv("GUNICORN_BIND", "0.0.0.0:8080")
workers = int(os.getenv("GUNICORN_WORKERS", "2"))  # 2 workers for redundancy
threads = int(os.getenv("GUNICORN_THREADS", "4"))
worker_class = "gthread"

# Timeout settings - critical for dashboard stability
timeout = 65          # Worker timeout: must be > call_timeout (55s)
graceful_timeout = 30 # Graceful shutdown timeout (enough for thread cleanup)
keepalive = 5         # Keep-alive connections timeout

# Worker lifecycle management - prevent state accumulation
max_requests = 1000       # Restart worker after N requests
max_requests_jitter = 100 # Random jitter to prevent simultaneous restarts


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

    # Then dispose database connections
    try:
        from mes_dashboard.core.database import dispose_engine
        dispose_engine()
    except Exception as e:
        server.log.warning(f"Error disposing database engine: {e}")
