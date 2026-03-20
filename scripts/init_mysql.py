#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""MySQL schema initialisation for the MES Dashboard dual-layer sync.

Creates the `dashboard_logs` and `dashboard_metrics_snapshots` tables
in the configured MySQL OPS database.  Safe to run multiple times
(all statements use IF NOT EXISTS / CREATE INDEX IF NOT EXISTS).

Usage:
    python scripts/init_mysql.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Allow running from project root
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dotenv import load_dotenv
load_dotenv()

import logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ============================================================
# DDL
# ============================================================

_CREATE_LOGS = """
CREATE TABLE IF NOT EXISTS dashboard_logs (
    id           BIGINT AUTO_INCREMENT PRIMARY KEY,
    sync_id      VARCHAR(255) NOT NULL,
    timestamp    DATETIME(3)  NOT NULL,
    level        VARCHAR(20)  NOT NULL,
    logger_name  VARCHAR(255) NOT NULL,
    message      TEXT         NOT NULL,
    request_id   VARCHAR(100),
    user         VARCHAR(255),
    ip           VARCHAR(45),
    extra        TEXT,
    synced_at    DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    UNIQUE INDEX idx_sync_id  (sync_id),
    INDEX        idx_timestamp (timestamp),
    INDEX        idx_level     (level)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

_CREATE_METRICS = """
CREATE TABLE IF NOT EXISTS dashboard_metrics_snapshots (
    id                        BIGINT AUTO_INCREMENT PRIMARY KEY,
    sync_id                   VARCHAR(255) NOT NULL,
    ts                        DATETIME(3)  NOT NULL,
    worker_pid                INT          NOT NULL,
    pool_saturation           DOUBLE,
    pool_checked_out          INT,
    pool_checked_in           INT,
    pool_overflow             INT,
    pool_max_capacity         INT,
    redis_used_memory         BIGINT,
    redis_hit_rate            DOUBLE,
    rc_l1_hit_rate            DOUBLE,
    rc_l2_hit_rate            DOUBLE,
    rc_miss_rate              DOUBLE,
    latency_p50_ms            DOUBLE,
    latency_p95_ms            DOUBLE,
    latency_p99_ms            DOUBLE,
    latency_count             INT,
    slow_query_active         INT,
    slow_query_waiting        INT,
    worker_rss_bytes          BIGINT,
    system_mem_available_mb   DOUBLE,
    system_mem_used_pct       DOUBLE,
    rq_workers_total          INT,
    rq_workers_busy           INT,
    rq_queue_depth            INT,
    heavy_query_slots_active  INT,
    synced_at                 DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    UNIQUE INDEX idx_sync_id (sync_id),
    INDEX        idx_ts      (ts)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""


_CREATE_LOGIN_SESSIONS = """
CREATE TABLE IF NOT EXISTS dashboard_login_sessions (
    id           BIGINT AUTO_INCREMENT PRIMARY KEY,
    sync_id      VARCHAR(255) NOT NULL,
    session_id   VARCHAR(100) NOT NULL,
    emp_id       VARCHAR(20)  NOT NULL,
    username     VARCHAR(50)  NOT NULL,
    display_name VARCHAR(100) NOT NULL,
    real_name    VARCHAR(50),
    department   VARCHAR(200),
    email        VARCHAR(200),
    phone        VARCHAR(20),
    domain       VARCHAR(50),
    ip           VARCHAR(45),
    login_time   DATETIME(3)  NOT NULL,
    last_active  DATETIME(3),
    logout_time  DATETIME(3),
    duration_sec INT,
    is_admin     TINYINT      DEFAULT 0,
    synced_at    DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    UNIQUE INDEX idx_sync_id  (sync_id),
    INDEX        idx_login_time (login_time),
    INDEX        idx_emp_id     (emp_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""


def main() -> None:
    enabled = os.getenv("MYSQL_OPS_ENABLED", "false").lower() == "true"
    if not enabled:
        logger.error(
            "MYSQL_OPS_ENABLED is not 'true'. "
            "Set it in your .env file before running this script."
        )
        sys.exit(1)

    from mes_dashboard.core.mysql_client import get_mysql_connection
    from sqlalchemy import text

    logger.info("Connecting to MySQL…")
    try:
        with get_mysql_connection() as conn:
            logger.info("Creating dashboard_logs table…")
            conn.execute(text(_CREATE_LOGS))

            logger.info("Creating dashboard_metrics_snapshots table…")
            conn.execute(text(_CREATE_METRICS))

            logger.info("Creating dashboard_login_sessions table…")
            conn.execute(text(_CREATE_LOGIN_SESSIONS))

        logger.info("MySQL schema initialised successfully.")
    except Exception as exc:
        logger.error("Failed to initialise MySQL schema: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
