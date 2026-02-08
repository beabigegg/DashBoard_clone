-- Trend Query for Resource History
-- Aggregates status hours by date for trend visualization
-- Placeholders:
--   HISTORYID_FILTER - Resource ID filter condition (e.g., HISTORYID IN (...))
--   DATE_TRUNC       - Date truncation expression (e.g., TRUNC(TXNDATE, 'MM'))
-- Parameters:
--   :start_date - Start date (YYYY-MM-DD)
--   :end_date   - End date (YYYY-MM-DD)

WITH shift_data AS (
    SELECT /*+ MATERIALIZE */ HISTORYID, TXNDATE, OLDSTATUSNAME, HOURS
    FROM DWH.DW_MES_RESOURCESTATUS_SHIFT
    WHERE TXNDATE >= TO_DATE(:start_date, 'YYYY-MM-DD')
      AND TXNDATE < TO_DATE(:end_date, 'YYYY-MM-DD') + 1
      AND {{ HISTORYID_FILTER }}
)
SELECT
    {{ DATE_TRUNC }} as DATA_DATE,
    SUM(CASE WHEN OLDSTATUSNAME = 'PRD' THEN HOURS ELSE 0 END) as PRD_HOURS,
    SUM(CASE WHEN OLDSTATUSNAME = 'SBY' THEN HOURS ELSE 0 END) as SBY_HOURS,
    SUM(CASE WHEN OLDSTATUSNAME = 'UDT' THEN HOURS ELSE 0 END) as UDT_HOURS,
    SUM(CASE WHEN OLDSTATUSNAME = 'SDT' THEN HOURS ELSE 0 END) as SDT_HOURS,
    SUM(CASE WHEN OLDSTATUSNAME = 'EGT' THEN HOURS ELSE 0 END) as EGT_HOURS,
    SUM(CASE WHEN OLDSTATUSNAME = 'NST' THEN HOURS ELSE 0 END) as NST_HOURS,
    COUNT(DISTINCT HISTORYID) as MACHINE_COUNT
FROM shift_data
GROUP BY {{ DATE_TRUNC }}
ORDER BY DATA_DATE
