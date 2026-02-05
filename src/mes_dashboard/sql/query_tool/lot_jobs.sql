-- LOT Related JOB Records Query
-- Retrieves JOB records for equipment during LOT processing
--
-- Parameters:
--   :equipment_id - Equipment ID (EQUIPMENTID = RESOURCEID in same ID system)
--   :time_start - Start time of LOT processing
--   :time_end - End time of LOT processing
--
-- Note: DW_MES_JOB uses RESOURCEID/RESOURCENAME
--       LOTWIPHISTORY uses EQUIPMENTID/EQUIPMENTNAME
--       EQUIPMENTID = RESOURCEID (same ID system, can JOIN directly)
--       CONTAINERIDS/CONTAINERNAMES are comma-separated strings

SELECT
    j.JOBID,
    j.RESOURCEID,
    j.RESOURCENAME,
    j.JOBSTATUS,
    j.JOBMODELNAME,
    j.JOBORDERNAME,
    j.CREATEDATE,
    j.COMPLETEDATE,
    j.CAUSECODENAME,
    j.REPAIRCODENAME,
    j.SYMPTOMCODENAME,
    j.CONTAINERIDS,
    j.CONTAINERNAMES
FROM DWH.DW_MES_JOB j
WHERE j.RESOURCEID = :equipment_id
  AND (
    (j.CREATEDATE BETWEEN :time_start AND :time_end)
    OR (j.COMPLETEDATE BETWEEN :time_start AND :time_end)
    OR (j.CREATEDATE <= :time_start AND (j.COMPLETEDATE IS NULL OR j.COMPLETEDATE >= :time_end))
  )
ORDER BY j.CREATEDATE
