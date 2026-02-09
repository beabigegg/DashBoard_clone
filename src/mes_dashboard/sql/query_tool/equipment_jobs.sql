-- Equipment JOB Records Query
-- Retrieves JOB records for equipment in a time period
--
-- Parameters:
--   :start_date - Start date (YYYY-MM-DD)
--   :end_date - End date (YYYY-MM-DD)
--
-- Dynamic placeholders:
--   EQUIPMENT_FILTER - Equipment filter condition (on RESOURCEID)
--
-- Note: DW_MES_JOB uses RESOURCEID/RESOURCENAME
--       EQUIPMENTID = RESOURCEID (same ID system)
--       Uses CREATEDATE for date filtering

SELECT
    JOBID,
    RESOURCEID,
    RESOURCENAME,
    JOBSTATUS,
    JOBMODELNAME,
    JOBORDERNAME,
    CREATEDATE,
    COMPLETEDATE,
    CAUSECODENAME,
    REPAIRCODENAME,
    SYMPTOMCODENAME,
    CONTAINERIDS,
    CONTAINERNAMES
FROM DWH.DW_MES_JOB
WHERE CREATEDATE >= TO_DATE(:start_date, 'YYYY-MM-DD')
  AND CREATEDATE < TO_DATE(:end_date, 'YYYY-MM-DD') + 1
  AND {{ EQUIPMENT_FILTER }}
ORDER BY RESOURCENAME, CREATEDATE DESC
