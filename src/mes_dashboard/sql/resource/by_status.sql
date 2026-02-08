-- Resource count by status
-- Placeholders:
--   LATEST_STATUS_SUBQUERY - Base subquery for latest resource status

SELECT
    NEWSTATUSNAME,
    COUNT(*) as COUNT
FROM ({{ LATEST_STATUS_SUBQUERY }}) rs
WHERE NEWSTATUSNAME IS NOT NULL
GROUP BY NEWSTATUSNAME
ORDER BY COUNT DESC
