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

-- ============================================================================
-- production-achievement-overhaul (2026-07-14) -- 3 additional idempotent
-- CREATE TABLE IF NOT EXISTS blocks (data-shape-contract.md §3.30/§3.31/§3.32).
-- Same manual-apply precondition as the two tables above -- applied BEFORE
-- the backend deploy that reads/writes them (design.md §Migration/Rollback).
-- Do NOT wire these into core/sync_worker.py -- read/written directly via
-- core/mysql_client.get_mysql_connection(), same as the two tables above.
-- ============================================================================

-- §3.30 -- PACKAGE_LF merge-mapping table (D1 -- sparse exceptions-only,
-- fallback-to-self on absence, business-rules.md PA-09). raw_package_lf is
-- VARCHAR(60) to match the Oracle DW_MES_LOTWIPHISTORY.PACKAGE_LF column
-- (VARCHAR2(60)).
CREATE TABLE IF NOT EXISTS production_achievement_package_lf_map (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    raw_package_lf VARCHAR(60) NOT NULL,
    merged_group VARCHAR(100) NOT NULL,
    updated_at DATETIME(3) NOT NULL,
    updated_by VARCHAR(100) NOT NULL,
    UNIQUE KEY uq_raw_package_lf (raw_package_lf)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- §3.31 -- Workcenter merge-mapping table (D2 -- explicit-inclusion,
-- exclude-by-absence -- the OPPOSITE default from the table above,
-- business-rules.md PA-10). Do NOT copy-paste this table's semantics onto
-- production_achievement_package_lf_map above, or vice versa.
--
-- parent_group (business-rules.md PA-19, production-achievement-moveout): the
-- "大項" a子站 rolls up under for the station dropdown + Excel-style expanded
-- detail. Most stations are single-layer (parent_group = merged_workcenter_group
-- = itself). The two exceptions are 電鍍 (parent of 掛鍍/條鍍/滾鍍/委外) and
-- 切割 (parent of 切割/PKG_SAW). The dropdown lists DISTINCT parent_group;
-- selecting a parent with >1 child expands its sub-stations in the detail table.
CREATE TABLE IF NOT EXISTS production_achievement_workcenter_merge_map (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    raw_workcenter_group VARCHAR(100) NOT NULL,
    merged_workcenter_group VARCHAR(100) NOT NULL,
    parent_group VARCHAR(100) NOT NULL,
    updated_at DATETIME(3) NOT NULL,
    updated_by VARCHAR(100) NOT NULL,
    UNIQUE KEY uq_raw_workcenter_group (raw_workcenter_group)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Idempotent column-add + backfill for installs created BEFORE parent_group
-- existed (CREATE TABLE IF NOT EXISTS above is a no-op on an existing table).
-- Backfill parent_group = merged_workcenter_group (single-layer default). NOTE:
-- an existing deployment still needs a MANUAL reseed to adopt the 電鍍/切割
-- sub-station taxonomy below -- INSERT IGNORE never overwrites the old
-- (電鍍→電鍍) row, and this backfill only fills the NEW column, it does not
-- restructure existing rows.
SET @col_exists := (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'production_achievement_workcenter_merge_map'
      AND COLUMN_NAME = 'parent_group'
);
SET @ddl := IF(@col_exists = 0,
    'ALTER TABLE production_achievement_workcenter_merge_map ADD COLUMN parent_group VARCHAR(100) NOT NULL DEFAULT '''' AFTER merged_workcenter_group',
    'SELECT 1');
PREPARE _pa_alter FROM @ddl; EXECUTE _pa_alter; DEALLOCATE PREPARE _pa_alter;
UPDATE production_achievement_workcenter_merge_map
    SET parent_group = merged_workcenter_group
    WHERE parent_group IS NULL OR parent_group = '';

-- §3.32 -- Daily-plan table, keyed on (workcenter_group, package_lf_group)
-- (both already-MERGED/resolved values) with NO shift dimension -- unlike
-- production_achievement_targets above. Fully independent/additive; writing
-- this table never mutates production_achievement_targets (business-rules.md
-- PA-11). No seed data (admin-filled via the settings UI).
CREATE TABLE IF NOT EXISTS production_achievement_daily_plans (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    workcenter_group VARCHAR(100) NOT NULL,
    package_lf_group VARCHAR(100) NOT NULL,
    daily_plan_qty BIGINT NOT NULL,
    updated_at DATETIME(3) NOT NULL,
    updated_by VARCHAR(100) NOT NULL,
    UNIQUE KEY uq_workcenter_package_lf_group (workcenter_group, package_lf_group)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ----------------------------------------------------------------------------
-- Seed data (business-rules.md PA-09 / PA-10). INSERT IGNORE so re-running
-- this script is idempotent AND never clobbers an admin's later edit to a
-- seeded row (a plain re-run silently skips rows whose unique key already
-- exists, rather than overwriting them via ON DUPLICATE KEY UPDATE).
-- ----------------------------------------------------------------------------

-- PA-09: ~9 rows behind the 4 confirmed PACKAGE_LF merges. Every other raw
-- PACKAGE_LF value observed in Oracle (~37 distinct year-to-date) is
-- INTENTIONALLY absent -- D1's fallback-to-self default means it groups
-- under itself with zero code/table changes required.
INSERT IGNORE INTO production_achievement_package_lf_map
    (raw_package_lf, merged_group, updated_at, updated_by)
VALUES
    ('SOD-123FL OP1', 'SOD-123FL',        NOW(3), 'system-seed'),
    ('SOD-123FL',     'SOD-123FL',        NOW(3), 'system-seed'),
    ('SOT23-5L',      'SOT23-5L/6L',      NOW(3), 'system-seed'),
    ('SOT23-6L',      'SOT23-5L/6L',      NOW(3), 'system-seed'),
    ('SOT-543',       'SOT-543/553/563',  NOW(3), 'system-seed'),
    ('SOT-553',       'SOT-543/553/563',  NOW(3), 'system-seed'),
    ('SOT-563',       'SOT-543/553/563',  NOW(3), 'system-seed'),
    ('TO-277',        'TO-277(B)',        NOW(3), 'system-seed'),
    ('TO-277B',       'TO-277(B)',        NOW(3), 'system-seed');

-- PA-10 / PA-19: raw FROMWORKCENTER -> (merged 子站, parent 大項). Every raw
-- workcenter NOT listed here is INTENTIONALLY excluded (D2 exclude-by-absence;
-- notably TCT / MA / IST / 補鍍 -- the change request confirmed these are not
-- shown in either 產出 or 轉出). Two-layer stations:
--   電鍍(parent) = 掛鍍 / 條鍍 / 滾鍍 / 委外(=BANDL+TOTAI, Excel presentation-
--                  layer merge -- 025.txt keeps BANDL/TOTAI raw & separate)
--   切割(parent) = 切割 / PKG_SAW
-- All other stations are single-layer (parent_group = merged = itself). 焊接_DW
-- still merges into 焊接_WB (unchanged), parent 焊接_WB.
INSERT IGNORE INTO production_achievement_workcenter_merge_map
    (raw_workcenter_group, merged_workcenter_group, parent_group, updated_at, updated_by)
VALUES
    ('焊接_WB',  '焊接_WB',  '焊接_WB',  NOW(3), 'system-seed'),
    ('焊接_DW',  '焊接_WB',  '焊接_WB',  NOW(3), 'system-seed'),
    ('焊接_DB',  '焊接_DB',  '焊接_DB',  NOW(3), 'system-seed'),
    ('成型',     '成型',     '成型',     NOW(3), 'system-seed'),
    ('去膠',     '去膠',     '去膠',     NOW(3), 'system-seed'),
    ('移印',     '移印',     '移印',     NOW(3), 'system-seed'),
    ('水吹砂',   '水吹砂',   '水吹砂',   NOW(3), 'system-seed'),
    ('切彎腳',   '切彎腳',   '切彎腳',   NOW(3), 'system-seed'),
    ('TMTT',     'TMTT',     'TMTT',     NOW(3), 'system-seed'),
    ('品檢',     '品檢',     '品檢',     NOW(3), 'system-seed'),
    ('FQC',      'FQC',      'FQC',      NOW(3), 'system-seed'),
    ('成品入庫', '成品入庫', '成品入庫', NOW(3), 'system-seed'),
    ('切割',     '切割',     '切割',     NOW(3), 'system-seed'),
    ('PKG_SAW',  'PKG_SAW',  '切割',     NOW(3), 'system-seed'),
    ('掛鍍',     '掛鍍',     '電鍍',     NOW(3), 'system-seed'),
    ('條鍍',     '條鍍',     '電鍍',     NOW(3), 'system-seed'),
    ('滾鍍',     '滾鍍',     '電鍍',     NOW(3), 'system-seed'),
    ('BANDL',    '委外',     '電鍍',     NOW(3), 'system-seed'),
    ('TOTAI',    '委外',     '電鍍',     NOW(3), 'system-seed');
