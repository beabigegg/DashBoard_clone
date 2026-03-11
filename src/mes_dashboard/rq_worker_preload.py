# -*- coding: utf-8 -*-
"""RQ worker logging bootstrap.

RQ workers run as standalone processes outside the Flask app factory,
so ``mes_dashboard.*`` loggers have no handlers by default.  Import this
module (or call ``ensure_rq_logging()``) to attach a stderr handler and
the SQLite log handler with the same format used by the main application.

Integration points:
  1. start_server.sh — ``rq worker … -c mes_dashboard.rq_worker_preload``
  2. Job entry modules — ``from mes_dashboard.rq_worker_preload import ensure_rq_logging``
     called at the top of execute_*_job functions as a safety net.
"""

import logging
import sys

_configured = False


def ensure_rq_logging() -> None:
    """Idempotently attach stderr + SQLite handlers to the ``mes_dashboard`` logger."""
    global _configured
    if _configured:
        return
    logger = logging.getLogger("mes_dashboard")
    if not logger.handlers:
        logger.setLevel(logging.INFO)

        # stderr handler (captured by >> rq_worker.log 2>&1)
        handler = logging.StreamHandler(sys.stderr)
        handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

        # SQLite log handler (shared with main app for admin dashboard queries)
        try:
            from mes_dashboard.core.log_store import get_sqlite_log_handler, LOG_STORE_ENABLED
            if LOG_STORE_ENABLED:
                sqlite_handler = get_sqlite_log_handler()
                sqlite_handler.setLevel(logging.INFO)
                logger.addHandler(sqlite_handler)
        except Exception:
            pass  # SQLite log is best-effort; stderr is the primary channel

        logger.propagate = False
    _configured = True


# Auto-configure on import (covers ``rq worker -c`` preload path).
ensure_rq_logging()
