-- Resource Status Summary Query
-- Returns aggregate statistics for resources
--
-- This query wraps the latest_status subquery

SELECT
    COUNT(*) as TOTAL_COUNT,
    COUNT(DISTINCT WORKCENTERNAME) as WORKCENTER_COUNT,
    COUNT(DISTINCT RESOURCEFAMILYNAME) as FAMILY_COUNT,
    COUNT(DISTINCT PJ_DEPARTMENT) as DEPT_COUNT
FROM ({{ LATEST_STATUS_SUBQUERY }}) rs
