-- Optimized: query_tool/lot_jobs
-- Change: Simplified 3-way OR date overlap condition to standard interval overlap
--         Original: (CREATE BETWEEN start/end) OR (COMPLETE BETWEEN start/end)
--                   OR (CREATE <= start AND COMPLETE >= end)
--         Optimized: CREATE <= end AND (COMPLETE IS NULL OR COMPLETE >= start)
--         Logically equivalent and allows single index range scan on CREATEDATE
--
-- Parameters:
--   :equipment_id - Equipment ID
--   :time_start - Start time of LOT processing
--   :time_end - End time of LOT processing

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
  AND j.CREATEDATE <= :time_end
  AND (
    (j.COMPLETEDATE IS NOT NULL AND j.COMPLETEDATE >= :time_start)
    OR
    (j.COMPLETEDATE IS NULL AND j.CREATEDATE >= :time_start)
  )
ORDER BY j.CREATEDATE
