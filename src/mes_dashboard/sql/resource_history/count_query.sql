-- Resource History Row Count for row-count chunking (USE_ROW_COUNT_CHUNKING=true)
-- Counts the daily aggregated rows matching the same WHERE clause as base_facts.sql.
-- Placeholders:
--   HISTORYID_FILTER - Resource ID filter condition
-- Parameters:
--   :start_date - Start date (YYYY-MM-DD)
--   :end_date   - End date (YYYY-MM-DD)

SELECT COUNT(*) AS row_count
FROM (
    SELECT HISTORYID, TRUNC(TXNDATE) AS DATA_DATE
    FROM DWH.DW_MES_RESOURCESTATUS_SHIFT
    WHERE TXNDATE >= TO_DATE(:start_date, 'YYYY-MM-DD')
      AND TXNDATE < TO_DATE(:end_date, 'YYYY-MM-DD') + 1
      AND {{ HISTORYID_FILTER }}
    GROUP BY HISTORYID, TRUNC(TXNDATE)
)
