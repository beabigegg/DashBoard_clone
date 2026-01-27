import os

bind = os.getenv("GUNICORN_BIND", "0.0.0.0:8080")
workers = int(os.getenv("GUNICORN_WORKERS", "2"))  # 2 workers for redundancy
threads = int(os.getenv("GUNICORN_THREADS", "4"))
worker_class = "gthread"

# Timeout settings - critical for dashboard stability
timeout = 60          # Worker timeout: 60 seconds max per request
graceful_timeout = 30 # Graceful shutdown timeout
keepalive = 5         # Keep-alive connections timeout
