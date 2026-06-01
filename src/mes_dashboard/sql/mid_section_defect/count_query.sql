-- Mid-Section Defect Row Count for row-count chunking (USE_ROW_COUNT_CHUNKING=true)
-- Counts detection rows matching the same WHERE clause as station_detection.sql.
-- Placeholders:
--   STATION_FILTER        - WIP station filter condition
--   STATION_FILTER_REJECTS - Reject station filter condition
-- Parameters:
--   :start_date - Start date (YYYY-MM-DD)
--   :end_date   - End date (YYYY-MM-DD)

SELECT COUNT(*) AS row_count
FROM (
    SELECT DISTINCT h.CONTAINERID
    FROM DWH.DW_MES_LOTWIPHISTORY h
    WHERE h.TRACKINTIMESTAMP >= TO_DATE(:start_date, 'YYYY-MM-DD')
      AND h.TRACKINTIMESTAMP < TO_DATE(:end_date, 'YYYY-MM-DD') + 1
      AND ({{ STATION_FILTER }})
      AND h.EQUIPMENTID IS NOT NULL
      AND h.TRACKINTIMESTAMP IS NOT NULL
)
