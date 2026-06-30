-- Mid-Section Defect - Step A: Detection Container ID Resolution (date-range mode)
-- Returns the DISTINCT set of CONTAINERIDs that had any detection-station
-- track-in within [start_date, end_date].  This is the CONTAINERID-first entry
-- point for date-range mode; the resolved IDs are then enriched by
-- station_detection_by_ids.sql (Step B) using the full time window.
--
-- Parameters:
--   {{ STATION_FILTER }} - Dynamic LIKE clause for the detection workcenter group
--   :start_date - Start date (YYYY-MM-DD)
--   :end_date   - End date (YYYY-MM-DD)
--
-- Tables used:
--   DWH.DW_MES_LOTWIPHISTORY (detection station records; CONTAINERID indexed)
--
-- Notes:
--   Single-column, indexed scan - intentionally lightweight so it can be
--   time-chunked cheaply for long date ranges without Oracle timeout.
--   Dedup (latest track-in per container) is NOT done here; Step B recomputes
--   it over the full window so chunked/unioned CID sets stay correct.

SELECT DISTINCT h.CONTAINERID
FROM DWH.DW_MES_LOTWIPHISTORY h
WHERE h.TRACKINTIMESTAMP >= TO_DATE(:start_date, 'YYYY-MM-DD')
  AND h.TRACKINTIMESTAMP < TO_DATE(:end_date, 'YYYY-MM-DD') + 1
  AND ({{ STATION_FILTER }})
  AND h.EQUIPMENTID IS NOT NULL
  AND h.TRACKINTIMESTAMP IS NOT NULL
