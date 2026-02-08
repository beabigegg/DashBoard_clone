-- Resource workcenter × status matrix
-- Placeholders:
--   LATEST_STATUS_SUBQUERY - Base subquery for latest resource status

SELECT
    WORKCENTERNAME,
    CASE NEWSTATUSNAME
        WHEN 'PRD' THEN 'PRD'
        WHEN 'SBY' THEN 'SBY'
        WHEN 'UDT' THEN 'UDT'
        WHEN 'SDT' THEN 'SDT'
        WHEN 'EGT' THEN 'EGT'
        WHEN 'NST' THEN 'NST'
        WHEN 'SCRAP' THEN 'SCRAP'
        ELSE 'OTHER'
    END as STATUS_CATEGORY,
    NEWSTATUSNAME,
    COUNT(*) as COUNT
FROM ({{ LATEST_STATUS_SUBQUERY }}) rs
WHERE WORKCENTERNAME IS NOT NULL
GROUP BY WORKCENTERNAME,
    CASE NEWSTATUSNAME
        WHEN 'PRD' THEN 'PRD'
        WHEN 'SBY' THEN 'SBY'
        WHEN 'UDT' THEN 'UDT'
        WHEN 'SDT' THEN 'SDT'
        WHEN 'EGT' THEN 'EGT'
        WHEN 'NST' THEN 'NST'
        WHEN 'SCRAP' THEN 'SCRAP'
        ELSE 'OTHER'
    END,
    NEWSTATUSNAME
ORDER BY WORKCENTERNAME, STATUS_CATEGORY
