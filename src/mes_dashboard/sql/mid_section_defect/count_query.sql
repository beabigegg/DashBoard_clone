-- Mid-Section Defect Row Count for row-count chunking (USE_ROW_COUNT_CHUNKING=true)
-- Counts the ACTUAL combined-CTE row count: detection_deduped LEFT JOIN detection_rejects.
-- This matches dataset_paged.sql's combined CTE which expands to one row per
-- (container, loss_reason) pair.  Counting only DISTINCT CONTAINERID underestimates
-- when containers have multiple loss reasons, causing dataset_paged.sql to truncate
-- late-in-range records when end_row < actual combined rows.
-- Placeholders:
--   STATION_FILTER        - WIP station filter condition
--   STATION_FILTER_REJECTS - Reject station filter condition
-- Parameters:
--   :start_date - Start date (YYYY-MM-DD)
--   :end_date   - End date (YYYY-MM-DD)

WITH detection_deduped AS (
    SELECT DISTINCT h.CONTAINERID
    FROM DWH.DW_MES_LOTWIPHISTORY h
    WHERE h.TRACKINTIMESTAMP >= TO_DATE(:start_date, 'YYYY-MM-DD')
      AND h.TRACKINTIMESTAMP < TO_DATE(:end_date, 'YYYY-MM-DD') + 1
      AND ({{ STATION_FILTER }})
      AND h.EQUIPMENTID IS NOT NULL
      AND h.TRACKINTIMESTAMP IS NOT NULL
),
detection_rejects AS (
    SELECT DISTINCT r.CONTAINERID, r.LOSSREASONNAME
    FROM DWH.DW_MES_LOTREJECTHISTORY r
    WHERE r.TXNDATE >= TO_DATE(:start_date, 'YYYY-MM-DD')
      AND r.TXNDATE < TO_DATE(:end_date, 'YYYY-MM-DD') + 1
      AND ({{ STATION_FILTER_REJECTS }})
)
SELECT COUNT(*) AS row_count
FROM detection_deduped d
LEFT JOIN detection_rejects r ON d.CONTAINERID = r.CONTAINERID
