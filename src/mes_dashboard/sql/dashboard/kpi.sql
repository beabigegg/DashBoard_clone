-- Dashboard KPI Query
-- Returns overall KPI statistics for dashboard header
--
-- Status categories:
--   RUN: PRD (Production)
--   DOWN: UDT + SDT (Down Time)
--   IDLE: SBY + NST (Idle)
--   ENG: EGT (Engineering Time)
--
-- OU% = PRD / (PRD + SBY + EGT + SDT + UDT) * 100
--
-- Placeholders:
--   LATEST_STATUS_SUBQUERY - Base subquery for latest resource status
--   WHERE_CLAUSE - Additional filter conditions

SELECT
    COUNT(*) as TOTAL,
    SUM(CASE WHEN NEWSTATUSNAME = 'PRD' THEN 1 ELSE 0 END) as PRD_COUNT,
    SUM(CASE WHEN NEWSTATUSNAME = 'SBY' THEN 1 ELSE 0 END) as SBY_COUNT,
    SUM(CASE WHEN NEWSTATUSNAME = 'UDT' THEN 1 ELSE 0 END) as UDT_COUNT,
    SUM(CASE WHEN NEWSTATUSNAME = 'SDT' THEN 1 ELSE 0 END) as SDT_COUNT,
    SUM(CASE WHEN NEWSTATUSNAME = 'EGT' THEN 1 ELSE 0 END) as EGT_COUNT,
    SUM(CASE WHEN NEWSTATUSNAME = 'NST' THEN 1 ELSE 0 END) as NST_COUNT,
    SUM(CASE WHEN NEWSTATUSNAME NOT IN ('PRD','SBY','UDT','SDT','EGT','NST') THEN 1 ELSE 0 END) as OTHER_COUNT
FROM ({{ LATEST_STATUS_SUBQUERY }}) rs
{{ WHERE_CLAUSE }}
