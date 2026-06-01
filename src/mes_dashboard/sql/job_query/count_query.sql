-- Job Query Row Count for row-count chunking (USE_ROW_COUNT_CHUNKING=true)
-- Counts job rows matching the same WHERE clause as job_list.sql.
-- Placeholders:
--   RESOURCE_FILTER - Resource ID filter condition
-- Parameters:
--   :start_date - Start date (YYYY-MM-DD)
--   :end_date   - End date (YYYY-MM-DD)

SELECT COUNT(*) AS row_count
FROM DWH.DW_MES_JOB j
WHERE {{ RESOURCE_FILTER }}
  AND j.CREATEDATE >= TO_DATE(:start_date, 'YYYY-MM-DD')
  AND j.CREATEDATE < TO_DATE(:end_date, 'YYYY-MM-DD') + 1
