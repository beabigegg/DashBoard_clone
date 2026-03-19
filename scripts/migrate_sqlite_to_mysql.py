#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""One-off migration: flush all existing SQLite records to MySQL, then clean SQLite.

Usage:
    conda run -n mes-dashboard python scripts/migrate_sqlite_to_mysql.py
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    datefmt='%H:%M:%S',
)
logger = logging.getLogger('migrate')


def main():
    from mes_dashboard.core.mysql_client import MYSQL_OPS_ENABLED
    if not MYSQL_OPS_ENABLED:
        logger.error("MYSQL_OPS_ENABLED is false — set it to true before migrating.")
        sys.exit(1)

    from mes_dashboard.core.log_store import get_log_store
    from mes_dashboard.core.metrics_history import get_metrics_history_store
    from mes_dashboard.core.sync_worker import SyncWorker

    log_store = get_log_store()
    metrics_store = get_metrics_history_store()
    worker = SyncWorker(log_store=log_store, metrics_store=metrics_store)

    # --- migrate logs ---
    log_total = 0
    while True:
        batch = log_store.get_unsynced(batch_size=500)
        if not batch:
            break
        worker._sync_logs()
        log_total += len(batch)
        logger.info("logs: synced %d rows so far...", log_total)

    # --- migrate metrics ---
    metrics_total = 0
    while True:
        batch = metrics_store.get_unsynced(batch_size=500)
        if not batch:
            break
        worker._sync_metrics()
        metrics_total += len(batch)
        logger.info("metrics: synced %d rows so far...", metrics_total)

    logger.info("Migration done — logs=%d, metrics=%d", log_total, metrics_total)

    # --- cleanup: remove all synced records from SQLite immediately ---
    logger.info("Cleaning up synced records from SQLite...")
    log_store.cleanup_synced(older_than_hours=0)
    metrics_store.cleanup_synced(older_than_hours=0)
    logger.info("SQLite cleanup complete.")

    # --- final counts ---
    from mes_dashboard.core.mysql_client import get_mysql_connection
    from sqlalchemy import text
    with get_mysql_connection() as conn:
        logs_mysql = conn.execute(text("SELECT COUNT(*) FROM dashboard_logs")).scalar()
        metrics_mysql = conn.execute(text("SELECT COUNT(*) FROM dashboard_metrics_snapshots")).scalar()

    logger.info("MySQL final — dashboard_logs=%d, dashboard_metrics_snapshots=%d", logs_mysql, metrics_mysql)


if __name__ == '__main__':
    main()
