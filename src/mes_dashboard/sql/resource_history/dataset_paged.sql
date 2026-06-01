-- Resource History Paged Dataset (ROW_NUMBER() row-count chunking)
-- Used when USE_ROW_COUNT_CHUNKING=true.
-- Placeholders:
--   HISTORYID_FILTER - Resource ID filter condition
-- Parameters:
--   :start_date - Start date (YYYY-MM-DD)
--   :end_date   - End date (YYYY-MM-DD)
--   :start_row  - 1-based inclusive start (from decompose_by_row_count)
--   :end_row    - 1-based inclusive end
--
-- ORDER BY key (BQE-03): HISTORYID ASC, DATA_DATE ASC

WITH ranked AS (
    SELECT
        HISTORYID,
        TRUNC(TXNDATE) AS DATA_DATE,
        SUM(CASE WHEN OLDSTATUSNAME = 'PRD' THEN HOURS ELSE 0 END) AS PRD_HOURS,
        SUM(CASE WHEN OLDSTATUSNAME = 'SBY' THEN HOURS ELSE 0 END) AS SBY_HOURS,
        SUM(CASE WHEN OLDSTATUSNAME = 'UDT' THEN HOURS ELSE 0 END) AS UDT_HOURS,
        SUM(CASE WHEN OLDSTATUSNAME = 'SDT' THEN HOURS ELSE 0 END) AS SDT_HOURS,
        SUM(CASE WHEN OLDSTATUSNAME = 'EGT' THEN HOURS ELSE 0 END) AS EGT_HOURS,
        SUM(CASE WHEN OLDSTATUSNAME = 'NST' THEN HOURS ELSE 0 END) AS NST_HOURS,
        SUM(HOURS) AS TOTAL_HOURS,
        ROW_NUMBER() OVER (
            ORDER BY HISTORYID ASC, TRUNC(TXNDATE) ASC
        ) AS _rn
    FROM DWH.DW_MES_RESOURCESTATUS_SHIFT
    WHERE TXNDATE >= TO_DATE(:start_date, 'YYYY-MM-DD')
      AND TXNDATE < TO_DATE(:end_date, 'YYYY-MM-DD') + 1
      AND {{ HISTORYID_FILTER }}
    GROUP BY HISTORYID, TRUNC(TXNDATE)
)
SELECT
    HISTORYID,
    DATA_DATE,
    PRD_HOURS,
    SBY_HOURS,
    UDT_HOURS,
    SDT_HOURS,
    EGT_HOURS,
    NST_HOURS,
    TOTAL_HOURS
FROM ranked
WHERE _rn BETWEEN :start_row AND :end_row
