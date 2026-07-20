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
--
-- production-achievement-oracle-plan-source (PA-09 amendment): this table is
-- now a MANUAL OVERRIDE layer on top of DWH.MES_WIP_OUTPUTPLAN_DETAIL, which
-- is consulted first as the default raw->merged mapping
-- (production_achievement_package_lf_service.get_oracle_package_lf_map());
-- rows here only need to exist for a raw code that must diverge from
-- Oracle's own PACKAGE->PACKAGEGROUP value, or for a code Oracle doesn't
-- know at all (confirmed gap: PACKAGEGROUP='DFN1006-2L/3L' has no
-- MES_WIP_OUTPUTPLAN_DETAIL.PACKAGE row -- see production_achievement_plan.sql).
-- Seeding every Oracle-known code here is no longer necessary.
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
-- = itself). The one exception is 電鍍 (parent of 掛鍍/條鍍/滾鍍/委外). The
-- dropdown lists DISTINCT parent_group; selecting a parent with >1 child
-- expands its sub-stations in the detail table.
--
-- 切割 was a second two-layer exception (parent of 切割/PKG_SAW) until the
-- production-achievement-moveout PKG_SAW fix (2026-07): real-DB reconciliation
-- against 025.txt found PKG_SAW is Live's OWN separate report column
-- (WorkCenter85, raw QTY), never summed into 切割 (WorkCenter10, which Live
-- also divides by consumefactor). Rolling PKG_SAW into 切割's parent_group
-- here both double-counted PKG_SAW's volume onto 切割 AND masked that 切割
-- alone needed the consumefactor division (see production_achievement_
-- moveout.sql's header comment for the full derivation and the exact-match
-- validation). The PKG_SAW row is REMOVED below (not reassigned) -- PKG_SAW
-- is now D2 excluded, same as TCT/MA/IST/補鍍.
--
-- plan_source_side (business-rules.md PA-20, production-achievement-oracle-
-- plan-source): which Oracle MES_WIP_OUTPUTPLAN column a parent_group's target
-- is sourced from -- 'input' (Planqty_Input, 前中段/投入目標) or 'output'
-- (PLANQTY_OUTPUT, TMTT後/產出目標). Confirmed with the user against 025.txt's
-- column order (切割/焊接_DB/焊接_WB/成型/去膠/移印/水吹砂/電鍍/切彎腳 -> TMTT ->
-- 品檢/FQC/成品入庫): TMTT/品檢/FQC/成品入庫 are 'output', every other
-- parent_group is 'input'.
CREATE TABLE IF NOT EXISTS production_achievement_workcenter_merge_map (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    raw_workcenter_group VARCHAR(100) NOT NULL,
    merged_workcenter_group VARCHAR(100) NOT NULL,
    parent_group VARCHAR(100) NOT NULL,
    plan_source_side VARCHAR(10) NOT NULL DEFAULT 'input',
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

-- Idempotent column-add + backfill for installs created BEFORE plan_source_side
-- existed (production-achievement-oracle-plan-source). Every row defaults to
-- 'input' (both the DDL's own DEFAULT and this backfill), then TMTT/品檢/FQC/
-- 成品入庫 are flipped to 'output' -- see the plan_source_side comment above
-- for the derivation. Re-running this block is always safe: it recomputes the
-- full column from parent_group every time, reflecting whatever parent_group
-- currently holds (including any later admin reassignment), never a stale
-- snapshot from an earlier run.
SET @col_exists2 := (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'production_achievement_workcenter_merge_map'
      AND COLUMN_NAME = 'plan_source_side'
);
SET @ddl2 := IF(@col_exists2 = 0,
    'ALTER TABLE production_achievement_workcenter_merge_map ADD COLUMN plan_source_side VARCHAR(10) NOT NULL DEFAULT ''input'' AFTER parent_group',
    'SELECT 1');
PREPARE _pa_alter2 FROM @ddl2; EXECUTE _pa_alter2; DEALLOCATE PREPARE _pa_alter2;
UPDATE production_achievement_workcenter_merge_map
    SET plan_source_side = IF(parent_group IN ('TMTT', '品檢', 'FQC', '成品入庫'), 'output', 'input');

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

-- PA-09: ~7 rows behind the 3 confirmed PACKAGE_LF merges. Every other raw
-- PACKAGE_LF value observed in Oracle (~37 distinct year-to-date) is
-- INTENTIONALLY absent -- D1's fallback-to-self default means it groups
-- under itself with zero code/table changes required.
--
-- SOT23-5L/SOT23-6L (production-achievement-oracle-plan-source, caught by
-- user review) intentionally REMOVED from this seed -- it originally seeded
-- both to 'SOT23-5L/6L' (no hyphen), which never matched Oracle's real
-- MES_WIP_OUTPUTPLAN_DETAIL.PACKAGE_REPORT value 'SOT-23-5L/6L' (WITH a
-- hyphen after SOT). A later manual edit (via the settings UI) corrected the
-- live SOT23-6L row to the right hyphenated value but left SOT23-5L on the
-- original wrong seed value -- the two rows silently disagreed with each
-- other. Now that D1 has an Oracle default layer
-- (get_oracle_package_lf_map(), PA-09 amendment), both raw codes are
-- correctly and automatically covered by Oracle's own 'SOT-23-5L/6L' without
-- any manual row -- re-adding one here would only risk re-introducing the
-- same divergence by silently overriding the correct Oracle default.
INSERT IGNORE INTO production_achievement_package_lf_map
    (raw_package_lf, merged_group, updated_at, updated_by)
VALUES
    ('SOD-123FL OP1', 'SOD-123FL',        NOW(3), 'system-seed'),
    ('SOD-123FL',     'SOD-123FL',        NOW(3), 'system-seed'),
    ('SOT-543',       'SOT-543/553/563',  NOW(3), 'system-seed'),
    ('SOT-553',       'SOT-543/553/563',  NOW(3), 'system-seed'),
    ('SOT-563',       'SOT-543/553/563',  NOW(3), 'system-seed'),
    ('TO-277',        'TO-277(B)',        NOW(3), 'system-seed'),
    ('TO-277B',       'TO-277(B)',        NOW(3), 'system-seed');

-- PA-10 / PA-19: raw FROMWORKCENTER -> (merged 子站, parent 大項). Every raw
-- workcenter NOT listed here is INTENTIONALLY excluded (D2 exclude-by-absence;
-- notably TCT / MA / IST / 補鍍 -- the change request confirmed these are not
-- shown in either 產出 or 轉出). Two 大項 are two-layer:
--   電鍍(parent) = 掛鍍 / 條鍍 / 滾鍍 / 委外(=BANDL+TOTAI, Excel presentation-
--                  layer merge -- 025.txt keeps BANDL/TOTAI raw & separate)
--   切割(parent) = 切割 / PKG_SAW -- DISPLAY-ONLY presentation merge
--                  (2026-07-20, re-requested after the production-achievement-
--                  moveout PKG_SAW fix had un-merged it): 切割's dashboard
--                  大項小計 total is now knowingly ROUND(QTY/CONSUMEFACTOR,0)
--                  (its own rows) + raw QTY (PKG_SAW rows) summed together,
--                  purely for the 子站/大項小計 rollup UI -- the same kind of
--                  presentation-layer merge as 電鍍's 委外. Live's 025.txt
--                  itself NEVER sums these two (WorkCenter10 and WorkCenter85
--                  stay separate report columns) -- this dashboard's 切割
--                  total will diverge from Live's own report by PKG_SAW's
--                  volume as a deliberate, confirmed choice. Do NOT "fix"
--                  this back to single-layer without re-confirming with the
--                  requester -- see production_achievement_moveout.sql's
--                  header comment for the full back-and-forth history on
--                  this exact station.
-- 焊接_DW still merges into 焊接_WB (unchanged), parent 焊接_WB.
--
-- plan_source_side given explicitly per-row here (not left to the ALTER
-- block's backfill UPDATE above): that backfill runs BEFORE this INSERT in
-- script order, so on a fresh install it would never touch these rows --
-- they'd silently keep the column's 'input' DEFAULT even for TMTT/品檢/FQC/
-- 成品入庫. The ALTER block's backfill still matters for pre-existing
-- deployments upgrading in place (rows already seeded before this column
-- existed); this explicit list is what makes a from-scratch run correct too.
INSERT IGNORE INTO production_achievement_workcenter_merge_map
    (raw_workcenter_group, merged_workcenter_group, parent_group, plan_source_side, updated_at, updated_by)
VALUES
    ('焊接_WB',  '焊接_WB',  '焊接_WB',  'input',  NOW(3), 'system-seed'),
    ('焊接_DW',  '焊接_WB',  '焊接_WB',  'input',  NOW(3), 'system-seed'),
    ('焊接_DB',  '焊接_DB',  '焊接_DB',  'input',  NOW(3), 'system-seed'),
    ('成型',     '成型',     '成型',     'input',  NOW(3), 'system-seed'),
    ('去膠',     '去膠',     '去膠',     'input',  NOW(3), 'system-seed'),
    ('移印',     '移印',     '移印',     'input',  NOW(3), 'system-seed'),
    ('水吹砂',   '水吹砂',   '水吹砂',   'input',  NOW(3), 'system-seed'),
    ('切彎腳',   '切彎腳',   '切彎腳',   'input',  NOW(3), 'system-seed'),
    ('TMTT',     'TMTT',     'TMTT',     'output', NOW(3), 'system-seed'),
    ('品檢',     '品檢',     '品檢',     'output', NOW(3), 'system-seed'),
    ('FQC',      'FQC',      'FQC',      'output', NOW(3), 'system-seed'),
    ('成品入庫', '成品入庫', '成品入庫', 'output', NOW(3), 'system-seed'),
    ('切割',     '切割',     '切割',     'input',  NOW(3), 'system-seed'),
    ('PKG_SAW',  'PKG_SAW',  '切割',     'input',  NOW(3), 'system-seed'),
    ('掛鍍',     '掛鍍',     '電鍍',     'input',  NOW(3), 'system-seed'),
    ('條鍍',     '條鍍',     '電鍍',     'input',  NOW(3), 'system-seed'),
    ('滾鍍',     '滾鍍',     '電鍍',     'input',  NOW(3), 'system-seed'),
    ('BANDL',    '委外',     '電鍍',     'input',  NOW(3), 'system-seed'),
    ('TOTAI',    '委外',     '電鍍',     'input',  NOW(3), 'system-seed');
