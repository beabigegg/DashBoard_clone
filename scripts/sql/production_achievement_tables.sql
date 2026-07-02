-- Production Achievement Rate — MySQL OPS DDL (production-achievement-kanban)
--
-- Idempotent CREATE TABLE IF NOT EXISTS for the two new tables backing the
-- 生產達成率 report page (data-shape-contract.md §3.26/§3.27). Applied
-- MANUALLY by an operator against the MySQL OPS database before first
-- deploy (design.md §Migration/Rollback) -- this project has no automated
-- MySQL migration runner. Precondition: MYSQL_OPS_ENABLED=true in
-- production (env-contract.md §MySQL OPS).
--
-- Do NOT wire this script into core/sync_worker.py._ensure_mysql_tables()
-- or app startup -- these tables are read/written directly via
-- core/mysql_client.get_mysql_connection(), never via the SQLite dual-layer
-- sync_worker path (design.md Key Decisions).
--
-- Rollback: do NOT DROP these tables (design.md §Migration/Rollback) --
-- they are left in place (orphaned but harmless) if the feature's
-- nav/manifest entries are reverted.
--
-- Usage:
--   mysql -h <MYSQL_OPS_HOST> -P <MYSQL_OPS_PORT> -u <MYSQL_OPS_USER> -p \
--       <MYSQL_OPS_DATABASE> < scripts/sql/production_achievement_tables.sql

CREATE TABLE IF NOT EXISTS production_achievement_targets (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    shift_code VARCHAR(10) NOT NULL,
    workcenter_group VARCHAR(100) NOT NULL,
    target_qty BIGINT NOT NULL,
    updated_at DATETIME(3) NOT NULL,
    updated_by VARCHAR(100) NOT NULL,
    UNIQUE KEY uq_shift_workcenter_group (shift_code, workcenter_group)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS production_achievement_edit_permissions (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_identifier VARCHAR(100) NOT NULL,
    can_edit_targets TINYINT(1) NOT NULL DEFAULT 0,
    granted_at DATETIME(3) NOT NULL,
    granted_by VARCHAR(100) NOT NULL,
    UNIQUE KEY uq_user_identifier (user_identifier)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
