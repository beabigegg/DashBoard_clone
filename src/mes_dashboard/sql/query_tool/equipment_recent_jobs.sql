-- Recent JOB records for a specific equipment (last 30 days)
--
-- Parameters:
--   :equipment_id - Equipment ID (RESOURCEID)

SELECT
    j.JOBID,
    j.JOBSTATUS,
    j.JOBMODELNAME,
    j.CREATEDATE,
    j.COMPLETEDATE,
    j.CAUSECODENAME,
    j.REPAIRCODENAME,
    j.RESOURCENAME
FROM DWH.DW_MES_JOB j
WHERE j.RESOURCEID = :equipment_id
  AND j.CREATEDATE >= SYSDATE - 30
ORDER BY j.CREATEDATE DESC
FETCH FIRST 5 ROWS ONLY
